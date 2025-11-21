# src/core/rag_pipeline.py
import os
import sys
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

# 尝试导入 LangChain 组件
try:
    from langchain.prompts import PromptTemplate
    from langchain.schema import Document as LangDocument
    from langchain.chains import RetrievalQA
    from langchain_core.language_models.llms import LLM
    from langchain_core.callbacks import CallbackManagerForLLMRun
except ImportError:
    logger.warning("LangChain 未安装或版本不兼容，RAG功能将不可用")
    LLM = object
    RetrievalQA = None
    LangDocument = None

class CustomLLM(LLM):
    """自定义LangChain LLM：包装ModelManager的generate"""
    model_manager: Any = None

    def __init__(self, model_manager):
        super().__init__()
        self.model_manager = model_manager

    @property
    def _llm_type(self) -> str:
        return "custom_llm"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """同步调用"""
        if not self.model_manager:
            return "Model Manager not initialized"
        # ModelManager.generate 返回生成器，我们需要合并结果
        response = ''.join(self.model_manager.generate(prompt))
        return response

class RAGPipeline:
    """RAG问答管道"""

    def __init__(self, model_manager: ModelManager, config_loader: ConfigLoader, search_engine: SearchEngine):
        self.model_manager = model_manager
        self.config_loader = config_loader
        self.search_engine = search_engine
        self.qa_chain = None
        
        if LLM is not object and RetrievalQA is not None:
            self.llm = CustomLLM(model_manager)
            self.qa_chain = self._build_qa_chain()
        else:
            logger.warning("LangChain依赖缺失，RAG管道未完全初始化")

    def _build_qa_chain(self) -> Any:
        """构建LangChain RetrievalQA链"""
        prompt_template = """
        使用以下上下文回答问题。如果不知道答案，就说不知道。

        上下文:
        {context}

        问题: {question}

        回答:
        """
        prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

        # 创建一个简单的检索器适配器
        class SearchEngineRetriever:
            def __init__(self, search_engine):
                self.search_engine = search_engine

            def get_relevant_documents(self, query: str) -> List[LangDocument]:
                # 使用SearchEngine进行搜索
                results = self.search_engine.search(query)
                docs = []
                for res in results[:5]: # 取前5个结果
                    content = res.get('content', '')
                    metadata = {
                        'source': res.get('path', ''),
                        'filename': res.get('filename', ''),
                        'score': res.get('score', 0)
                    }
                    docs.append(LangDocument(page_content=content, metadata=metadata))
                return docs
            
            # LangChain 新版可能需要这个方法
            def invoke(self, input: str, config: Optional[Any] = None) -> List[LangDocument]:
                return self.get_relevant_documents(input)

        retriever = SearchEngineRetriever(self.search_engine)

        qa = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt}
        )
        return qa

    def query(self, query: str) -> Dict[str, Any]:
        """执行RAG查询"""
        if self.qa_chain is None:
            return {"answer": "错误：RAG组件未初始化（可能是缺少依赖）。", "sources": []}
            
        try:
            # LangChain invoke or call
            if hasattr(self.qa_chain, 'invoke'):
                result = self.qa_chain.invoke({"query": query})
            else:
                result = self.qa_chain({"query": query})
                
            answer = result.get("result", "")
            source_docs = result.get("source_documents", [])
            sources = [doc.metadata.get('source', '未知') for doc in source_docs]
            
            return {"answer": answer, "sources": sources}
        except Exception as e:
            logger.error(f"RAG查询失败: {e}")
            return {"answer": f"错误：处理查询时发生异常 ({str(e)})。", "sources": []}
