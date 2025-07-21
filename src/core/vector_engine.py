# src/core/vector_engine.py
from typing import List, Optional
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.core.universal_parser import Document  # 从Part 3导入

logger = setup_logger()

class VectorEngine:
    """向量化引擎：文档嵌入和FAISS索引管理（基于文档2.2语义分块引擎）"""

    def __init__(self, config: ConfigLoader):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')  # Sentence-BERT
        self.dimension = self.embedding_model.get_sentence_embedding_dimension()
        self.index_path = config.get('system', 'data_dir') + '/indexes/faiss_index.bin'
        self.index = self._load_or_create_index()
        self.doc_store: List[Document] = []  # 存储原始文档（用于检索后返回）

    def _load_or_create_index(self) -> faiss.IndexFlatL2:
        """加载或创建FAISS索引"""
        try:
            index = faiss.read_index(self.index_path)
            logger.info("加载现有FAISS索引")
        except Exception:
            index = faiss.IndexFlatL2(self.dimension)
            logger.info("创建新FAISS索引")
        return index

    def add_documents(self, documents: List[Document]) -> None:
        """向量化并添加到FAISS索引"""
        all_chunks = []
        chunk_to_doc = []  # 映射chunk到原文档
        for doc in documents:
            chunks = doc.content.split('\n\n')  # 假设Parser已分块
            all_chunks.extend(chunks)
            chunk_to_doc.extend([doc] * len(chunks))
        
        if not all_chunks:
            return
        
        embeddings = self.embedding_model.encode(all_chunks, convert_to_tensor=False)
        self.index.add(np.array(embeddings).astype('float32'))
        
        # 更新doc_store（简化：存储所有，但实际可使用更高效的DB如SQLite）
        self.doc_store.extend(chunk_to_doc)
        
        self._save_index()
        logger.info(f"添加 {len(documents)} 个文档到向量索引")

    def search(self, query: str, top_k: int) -> List[Document]:
        """FAISS向量搜索"""
        query_emb = self.embedding_model.encode([query], convert_to_tensor=False).astype('float32')
        distances, indices = self.index.search(query_emb, top_k)
        
        results = []
        for idx in indices[0]:
            if idx < len(self.doc_store):
                results.append(self.doc_store[idx])
        
        return results

    def _save_index(self):
    #假设index_data = {'faiss': self.index} 但FAISS有write_index；这里加密元数据
      metadata = {}  # e.g., self.doc_store metadata
      self.security.save_encrypted_index(metadata, self.index_path + '.meta')
      faiss.write_index(self.index, self.index_path)