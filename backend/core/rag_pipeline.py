# src/core/rag_pipeline.py
import os
import re
import secrets
from typing import Dict, List, Any, Optional

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
    "你是一名专业的中文文档助理。请根据下方的【文档集合】回答用户的【问题】。\n"
    "规则：\n"
    "1. 严格基于文档内容回答，不要编造。\n"
    "2. 如果用户询问某人、某事出现在哪里，或者询问来源，请务必列出对应的文件名。\n"
    "3. 如果答案仅出现在文件名中（例如文件名包含查询词），请明确指出该文件。\n"
    "4. 如果文档中没有相关信息，请直接说明未找到。\n\n"
    "【文档集合】:\n{context}\n\n"
    "【问题】: {question}\n\n"
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
        default_total = self.max_context_chars * self.max_docs
        self.max_context_chars_total = int(rag_config.get('max_context_chars_total', default_total))
        self.max_history_turns = int(rag_config.get('max_history_turns', 6))
        self.max_history_chars = int(rag_config.get('max_history_chars', 800))
        self.max_output_tokens = int(rag_config.get('max_output_tokens', 512))
        self.temperature = float(rag_config.get('temperature', 0.7))
        self.prompt_template = rag_config.get('prompt_template', DEFAULT_PROMPT)
        self.fallback_response = rag_config.get(
            'fallback_response',
            "你好！我是 FileTools Copilot，当前检索没有找到相关文档，请告诉我需要查询的内容。"
        )
        self.context_exhausted_response = rag_config.get(
            'context_exhausted_response',
            "对话过长，为避免超出上下文，请说‘重置’或简要概括后再继续。"
        )
        self.reset_response = rag_config.get(
            'reset_response',
            "已清空上下文，可以重新开始提问。"
        )
        self.greeting_response = rag_config.get('greeting_response', self.fallback_response)
        phrases = rag_config.get('greeting_keywords', []) or []
        if isinstance(phrases, str):
            phrases = [p.strip() for p in phrases.split(',') if p.strip()]
        self.greeting_keywords = [p.lower() for p in phrases if p]

        reset_cmds = rag_config.get('reset_commands', ['重置', '清空上下文', 'reset', 'restart']) or []
        self.reset_commands = [c.strip().lower() for c in reset_cmds if c]

        self.session_histories: Dict[str, List[Dict[str, str]]] = {}

    @staticmethod
    def _render_template(template: str, query: str) -> str:
        if not template:
            return ''
        query_text = (query or '').strip()
        try:
            return template.replace('{query}', query_text)
        except Exception:
            return template

    @staticmethod
    def _is_noise_query(query: str) -> bool:
        """Detect inputs that are too short or repetitive to search meaningfully."""
        normalized = re.sub(r'\s+', '', query or '')
        if not normalized:
            return True
        alnum_text = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]', '', normalized)
        if not alnum_text:
            return True
        if len(alnum_text) <= 1:
            return True
        unique_chars = set(alnum_text.lower())
        if len(alnum_text) <= 2 and len(unique_chars) == 1:
            return True
        return False

    @staticmethod
    def _strip_tags(text: str) -> str:
        clean = re.sub(r'<[^>]+>', '', text or '')
        return clean.replace('\xa0', ' ').strip()

    def _build_history(self, session_id: str, budget: int) -> (str, int):
        history = self.session_histories.get(session_id, []) or []
        if not history or budget <= 0:
            return '', 0

        turns = history[-self.max_history_turns :]
        used = 0
        parts: List[str] = []
        for idx, turn in enumerate(turns, start=1):
            q = turn.get('q', '') or ''
            a = turn.get('a', '') or ''
            block = f"【上文{idx}】用户: {q}\n助手: {a}"

            if used + len(block) > budget:
                remaining = budget - used
                if remaining <= 0:
                    break
                block = block[:remaining] + '...'

            parts.append(block)
            used += len(block)
            if used >= budget:
                break

        return "\n".join(parts), used

    def _remember_turn(self, session_id: str, query: str, answer: str) -> None:
        history = self.session_histories.setdefault(session_id, [])
        history.append({'q': query, 'a': answer})

        if len(history) > self.max_history_turns:
            overflow = len(history) - self.max_history_turns
            del history[0:overflow]

        def _total_len(items: List[Dict[str, str]]) -> int:
            total = 0
            for item in items:
                total += len(item.get('q', '') or '')
                total += len(item.get('a', '') or '')
            return total

        while _total_len(history) > self.max_history_chars and len(history) > 1:
            history.pop(0)

    def _reset_session(self, session_id: str) -> None:
        self.session_histories.pop(session_id, None)

    @staticmethod
    def _has_query_overlap(cleaned: str, query: str) -> bool:
        """Check if cleaned text (or filename/path) contains meaningful overlap with query keywords/names."""
        if not cleaned or not query:
            return False

        def _normalize(txt: str) -> str:
            # remove spaces, underscores, hyphens and common punctuation to improve filename matching
            return re.sub(r'[\s_\-，。；、,.!?:；:]+', '', txt.lower())

        text_norm = _normalize(cleaned)
        q_norm = _normalize(query)

        if len(q_norm) >= 2 and q_norm in text_norm:
            return True

        # Split by common separators to get tokens; keep tokens length>=2
        tokens = re.split(r'[\s,;，。；、_\-]+', query)
        for t in tokens:
            t_norm = _normalize(t)
            if len(t_norm) >= 2 and t_norm in text_norm:
                return True
        return False

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

            # 优先使用路径获取真实文件名，避免索引返回的 filename 字段可能存在的截断或分词问题
            if path:
                filename = os.path.basename(path)
            else:
                filename = res.get('filename') or res.get('file_name') or '未知文件'

            composite = cleaned or ''
            for extra in (filename, res.get('file_name'), os.path.basename(path), path):
                if extra:
                    composite += f" {extra}"

            if not self._has_query_overlap(composite, query):
                # Skip results that neither content nor filename/path contain the query keywords
                continue

            # 如果文件名包含查询词，显式添加到内容开头，确保LLM能看到
            if filename and self._has_query_overlap(filename, query):
                prefix = f"【重要证据：文件名包含查询词】文件名: {filename}\n"
                if not cleaned.startswith("【重要证据"):
                    cleaned = prefix + cleaned

            if not cleaned:
                cleaned = f"文件名匹配：{filename}" if filename else "文件名匹配"

            if len(cleaned) > self.max_context_chars:
                cleaned = cleaned[: self.max_context_chars] + '...'

            documents.append({
                'path': path,
                'filename': filename,
                'score': float(res.get('score', 0.0)),
                'content': cleaned
            })

            if len(documents) >= self.max_docs:
                break

        return documents

    def _build_prompt(self, query: str, documents: List[Dict[str, Any]], history_text: str, doc_budget: Optional[int]) -> str:
        if not documents and not history_text:
            return ''

        context_sections = []

        if history_text:
            context_sections.append(f"对话历史（最近）:\n{history_text}")

        if doc_budget is None:
            context_budget = max(self.max_context_chars_total, 0)
        else:
            context_budget = max(doc_budget, 0)

        enforce_budget = context_budget > 0
        used_chars = 0

        for idx, doc in enumerate(documents, start=1):
            if enforce_budget and used_chars >= context_budget:
                break

            content = doc.get('content', '') or ''
            if enforce_budget:
                remaining = context_budget - used_chars
                if remaining <= 0:
                    break
                if len(content) > remaining:
                    content = content[:remaining] + '...'
                used_chars += len(content)

            if not content:
                continue

            section = (
                f"[文档{idx}] {doc.get('filename', '未知文件')}\n"
                f"路径: {doc.get('path', '未知路径')}\n"
                f"相关性: {doc.get('score', 0.0):.2f}\n"
                f"内容:\n{content}"
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

    def _is_small_talk(self, query: str) -> bool:
        normalized = (query or '').strip().lower()
        if not normalized:
            return True
        for phrase in self.greeting_keywords:
            if not phrase:
                continue
            if normalized == phrase:
                return True
            if normalized.startswith(phrase) and len(normalized) <= len(phrase) + 2:
                return True
        return False

    def query(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """执行检索增强生成流程，支持简单会话记忆与重置"""
        session_key = (session_id or '').strip()
        if not session_key:
            # 没有提供 session_id 时，为避免不同用户共享“default”历史，生成一次性会话键
            session_key = secrets.token_hex(8)

        normalized_reset = (query or '').strip().lower()
        if normalized_reset in self.reset_commands:
            self._reset_session(session_key)
            return {"answer": self.reset_response, "sources": []}

        try:
            if self._is_small_talk(query):
                return {"answer": self.greeting_response, "sources": []}

            if self._is_noise_query(query):
                return {"answer": self._render_template(self.fallback_response, query), "sources": []}

            if self.max_context_chars_total > 0:
                history_budget = min(self.max_history_chars, self.max_context_chars_total)
            else:
                history_budget = self.max_history_chars

            history_text, used_history = self._build_history(session_key, history_budget)

            doc_budget: Optional[int] = None
            if self.max_context_chars_total > 0:
                doc_budget = max(self.max_context_chars_total - used_history, 0)
                if doc_budget <= 0:
                    return {"answer": self.context_exhausted_response, "sources": []}

            documents = self._collect_documents(query)
            if not documents and not history_text:
                answer = self._render_template(self.fallback_response, query)
                return {"answer": answer, "sources": []}

            prompt = self._build_prompt(query, documents, history_text, doc_budget)
            if not prompt:
                return {"answer": self._render_template(self.fallback_response, query), "sources": []}

            chunks: List[str] = []
            for piece in self.model_manager.generate(prompt, max_tokens=self.max_output_tokens, temperature=self.temperature):
                if piece:
                    chunks.append(str(piece))

            answer = ''.join(chunks).strip()
            if not answer:
                answer = self._render_template(self.fallback_response, query)

            sources = [doc.get('path') or doc.get('filename') for doc in documents]
            self._remember_turn(session_key, query, answer)
            return {"answer": answer, "sources": sources}
        except Exception as exc:
            logger.error(f"RAG查询失败: {exc}")
            return {"answer": f"错误：处理查询时发生异常 ({str(exc)})。", "sources": []}
