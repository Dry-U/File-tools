# src/core/rag_pipeline.py
import os
import sys
from typing import Dict, List, Any

# 修复 torch DLL 加载问题：添加 torch lib 目录到 DLL 搜索路径
try:
    import torch
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')
    if os.path.exists(torch_lib_path) and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(torch_lib_path)
except Exception:
    pass

try:
    from langchain.chains import RetrievalQA
except ImportError:
    # 新版本 langchain 没有这个类，先设置为 None
    RetrievalQA = None
try:
    from langchain.prompts import PromptTemplate
except ImportError:
    from langchain_core.prompts import PromptTemplate
try:
    from langchain.llms.base import LLM
except ImportError:
    from langchain_core.language_models.llms import LLM
try:
    from langchain.schema import Document as LangDocument  # LangChain的Document
except ImportError:
    from langchain_core.documents import Document as LangDocument
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.core.model_manager import ModelManager

# 临时定义缺失的类，实际项目中应创建对应的文件
class HybridRetriever:
    def __init__(self, config_loader, vector_engine):
        self.config_loader = config_loader
        self.vector_engine = vector_engine
    def search(self, query):
        return []

class Document:
    def __init__(self, content="", metadata={}):
        self.content = content
        self.metadata = metadata

class PrivacyFilter:
    def __init__(self, config):
        self.config = config
    def sanitize(self, text):
        return text

class SecurityManager:
    def __init__(self, config):
        self.config = config
        self.current_user_role = "user"
    def check_permission(self, permission):
        return True
    def log_audit(self, action, details):
        pass

logger = setup_logger()

class CustomLLM(LLM):
    """自定义LangChain LLM：包装ModelManager的generate"""
    model_manager: ModelManager

    def __init__(self, model_manager: ModelManager):
        super().__init__()
        self.model_manager = model_manager
        # 使用model_manager的config_loader
        self.privacy_filter = PrivacyFilter(model_manager.config_loader)
        self.security = SecurityManager(model_manager.config_loader)

    def _call(self, prompt: str, stop: List[str] = None) -> str:
        """同步调用（LangChain默认）"""
        response = ''.join(self.model_manager.generate(prompt))
        return response

    @property
    def _llm_type(self) -> str:
        return "custom_llm"

class RAGPipeline:
    """RAG问答管道：使用LangChain实现数据感知和主动性（基于文档3.3）"""

    def __init__(self, model_manager: ModelManager, config_loader: ConfigLoader, retriever: HybridRetriever):
        self.model_manager = model_manager
        self.config_loader = config_loader
        self.retriever = retriever
        self.llm = CustomLLM(model_manager)
        self.qa_chain = self._build_qa_chain()

    def _build_qa_chain(self) -> RetrievalQA:
        """构建LangChain RetrievalQA链"""
        prompt_template = """
        使用以下上下文回答问题。如果不知道答案，就说不知道。

        上下文:
        {context}

        问题: {question}

        回答:
        """
        prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

        def lang_retriever(query: str) -> List[LangDocument]:
            """适配LangChain检索器：从HybridRetriever获取"""
            docs = self.retriever.search(query)
            return [LangDocument(page_content=doc.content, metadata=doc.metadata) for doc in docs]

        qa = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=lang_retriever.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt}
        )
        return qa

    def query(self, query: str) -> Dict[str, Any]:
        """执行RAG查询：检索+生成，返回answer和sources"""
        if not self.security.check_permission('query'):
             return {"answer": "权限不足。", "sources": []}
        try:
            result = self.qa_chain({"query": query})
            answer = result["result"]
            sources = [doc.metadata.get('file_path', '未知') for doc in result["source_documents"]]
            
            # 主动性：如果检索结果为空，触发文件重新扫描（环境交互示例）
            if not sources:
                logger.info("无相关文档，触发主动扫描")
                # 调用FileScanner（假设注入或全局访问；实际可通过事件）
                from src.core.file_scanner import FileScanner  # 延迟导入避免循环
                scanner = FileScanner(self.config)
                scanner.scan_and_index()  # 主动更新索引
                # 重新查询
                result = self.qa_chain({"query": query})
                answer = self.privacy_filter.sanitize(result["result"])
                self.security.log_audit("query_executed", {"query": query, "user_role": self.security.current_user_role})
    
                return {"answer": answer, "sources": sources}
        except Exception as e:
            logger.error(f"RAG查询失败: {e}")
            return {"answer": "错误：无法处理查询。", "sources": []}