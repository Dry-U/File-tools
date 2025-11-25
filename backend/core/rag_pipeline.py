# src/core/rag_pipeline.py
import os
import re
from typing import Dict, List, Any

# 修复 torch DLL 加载问题
try:
    import torch
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')
    if os.path.exists(torch_lib_path) and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(torch_lib_path)
except Exception:
    pass

from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
from backend.core.model_manager import ModelManager
from backend.core.search_engine import SearchEngine

logger = setup_logger()

DEFAULT_PROMPT = (
    "你是一名专业的中文文档助理，请严格依据提供的文档内容回答用户的问题。"
    "如果文档中没有相关信息，请明确说明无法找到答案，不要自行编造。\n\n"
    "文档集合:\n{context}\n\n"
    "问题: {question}\n\n"
    "请用清晰、简洁的语言作答。"
)


class RAGPipeline:
    """本地RAG问答管道，依赖检索结果与模型推理"""

    def __init__(self, model_manager: ModelManager, config_loader: ConfigLoader, search_engine: SearchEngine):
        self.model_manager = model_manager
        self.config_loader = config_loader
        self.search_engine = search_engine

        try:
            rag_config = config_loader.get('rag') or {}
        except Exception:
            rag_config = {}

        self.max_docs = int(rag_config.get('max_docs', 3))
        self.max_context_chars = int(rag_config.get('max_context_chars', 1200))
        self.max_output_tokens = int(rag_config.get('max_output_tokens', 512))
        self.temperature = float(rag_config.get('temperature', 0.7))
        self.prompt_template = rag_config.get('prompt_template', DEFAULT_PROMPT)

    @staticmethod
    def _strip_tags(text: str) -> str:
        clean = re.sub(r'<[^>]+>', '', text or '')
        return clean.replace('\xa0', ' ').strip()

    def _collect_documents(self, query: str) -> List[Dict[str, Any]]:
        results = self.search_engine.search(query) or []
        documents: List[Dict[str, Any]] = []

        seen_paths = set()
        for res in results:
            path = res.get('path', '')
            if path and path.lower() in seen_paths:
                continue
            if path:
                seen_paths.add(path.lower())

            raw_content = res.get('content') or ''
            snippet = res.get('snippet') or ''
            cleaned = self._strip_tags(raw_content) if raw_content else self._strip_tags(snippet)
            if not cleaned:
                continue

            if len(cleaned) > self.max_context_chars:
                cleaned = cleaned[: self.max_context_chars] + '...'

            documents.append({
                'path': path,
                'filename': res.get('filename') or res.get('file_name') or os.path.basename(path),
                'score': float(res.get('score', 0.0)),
                'content': cleaned
            })

            if len(documents) >= self.max_docs:
                break

        return documents

    def _build_prompt(self, query: str, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return ''

        context_sections = []
        for idx, doc in enumerate(documents, start=1):
            section = (
                f"[文档{idx}] {doc.get('filename', '未知文件')}\n"
                f"路径: {doc.get('path', '未知路径')}\n"
                f"相关性: {doc.get('score', 0.0):.2f}\n"
                f"内容:\n{doc.get('content', '')}"
            )
            context_sections.append(section)

        context_text = "\n\n".join(context_sections)
        template = self.prompt_template or DEFAULT_PROMPT
        try:
            return template.format(context=context_text, question=query).strip()
        except KeyError:
            # 当模板缺少占位符时退回默认模板，避免崩溃
            logger.warning("RAG提示模板缺少必要占位符，已使用默认模板")
            return DEFAULT_PROMPT.format(context=context_text, question=query).strip()

    def query(self, query: str) -> Dict[str, Any]:
        """执行检索增强生成流程"""
        try:
            documents = self._collect_documents(query)
            if not documents:
                return {"answer": "未找到相关文档，暂时无法回答该问题。", "sources": []}

            prompt = self._build_prompt(query, documents)
            if not prompt:
                return {"answer": "构建回答提示失败。", "sources": []}

            chunks: List[str] = []
            for piece in self.model_manager.generate(prompt, max_tokens=self.max_output_tokens, temperature=self.temperature):
                if piece:
                    chunks.append(str(piece))

            answer = ''.join(chunks).strip()
            if not answer:
                answer = "未能生成回答。"

            sources = [doc.get('path') or doc.get('filename') for doc in documents]
            return {"answer": answer, "sources": sources}
        except Exception as exc:
            logger.error(f"RAG查询失败: {exc}")
            return {"answer": f"错误：处理查询时发生异常 ({str(exc)})。", "sources": []}
