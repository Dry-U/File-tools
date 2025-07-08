# 集成LangChain的核心文档处理服务
import os
from typing import List, Dict, Any, Optional
from langchain.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.schema import Document as LangDocument
from pydantic import BaseModel
from config import settings

# 数据模型
class ProcessedDocument(BaseModel):
    id: str
    content: str
    metadata: Dict[str, Any]

# 支持的文件类型映射
FILE_LOADERS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".docx": UnstructuredWordDocumentLoader
}

class DocumentProcessor:
    def __init__(self):
        """初始化文档处理器"""
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.nlp.model_name,
            model_kwargs={'device': 'cpu'}
        )
        self.faiss_index_path = settings.retrieval.faiss_index_path
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.nlp.chunk_size,
            chunk_overlap=settings.nlp.overlap
        )
        self.db = self._init_vectorstore()

    def _init_vectorstore(self) -> Optional[FAISS]:
        """初始化FAISS向量存储"""
        if os.path.exists(self.faiss_index_path):
            return FAISS.load_local(
                folder_path=self.faiss_index_path,
                embeddings=self.embeddings
            )
        return None

    def process_files(self, file_paths: List[str]) -> List[ProcessedDocument]:
        """处理多个文件并更新向量索引"""
        documents = []
        for file_path in file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in FILE_LOADERS:
                loader = FILE_LOADERS[ext](file_path)
                documents.extend(loader.load())
        
        if not documents:
            return []

        # 文档分块
        splits = self.text_splitter.split_documents(documents)
        
        # 更新向量存储
        if self.db:
            self.db.add_documents(splits)
        else:
            self.db = FAISS.from_documents(
                documents=splits,
                embedding=self.embeddings
            )
        
        # 保存索引
        os.makedirs(os.path.dirname(self.faiss_index_path), exist_ok=True)
        self.db.save_local(self.faiss_index_path)
        
        return [
            ProcessedDocument(
                id=str(i),
                content=doc.page_content,
                metadata=doc.metadata
            )
            for i, doc in enumerate(splits)
        ]

    def search(self, query: str, top_k: int = 5) -> List[LangDocument]:
        """语义搜索文档"""
        if not self.db:
            return []
        return self.db.similarity_search(query, k=top_k)

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        if not self.db:
            return {"index_size": 0}
        return {
            "index_size": self.db.index.ntotal,
            "dimensions": self.db.index.d
        }