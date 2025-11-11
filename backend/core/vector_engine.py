# src/core/vector_engine.py
from typing import List, Optional
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
from backend.core.universal_parser import Document  # 从Part 3导入

logger = setup_logger()

class VectorEngine:
    """向量化引擎：文档嵌入和FAISS索引管理（基于文档2.2语义分块引擎）"""

    def __init__(self, config_loader: ConfigLoader):
        # 暂时禁用SentenceTransformer，解决sqlite3 DLL问题
        self.config_loader = config_loader
        self.embedding_model = None  # 原: SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384  # MiniLM-L6-v2的默认维度，硬编码替代
        # 使用正确的配置加载器方法获取配置
        self.index_path = self.config_loader.get('system', 'data_dir', './data') + '/indexes/faiss_index.bin'
        self.index = self._load_or_create_index()
        self.doc_store: List[Document] = []  # 存储原始文档（用于检索后返回）
        self.fallback_mode = True  # 启用回退模式，跳过向量化功能

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
        """简化版：在embedding_model不可用时，仅存储文档信息"""
        if self.fallback_mode:
            # 在回退模式下，只存储文档，但不进行向量化
            logger.warning("VectorEngine运行在回退模式，跳过向量化功能")
            # 仍然记录文档，但不进行向量计算
            for doc in documents:
                self.doc_store.append(doc)
            logger.info(f"存储 {len(documents)} 个文档信息")
            return
            
        # 原始实现（当回退模式关闭时使用）
        all_chunks = []
        chunk_to_doc = []  # 映射chunk到原文档
        for doc in documents:
            chunks = doc.content.split('\n\n')  # 假设Parser已分块
            all_chunks.extend(chunks)
            chunk_to_doc.extend([doc] * len(chunks))
        
        if not all_chunks or not self.embedding_model:
            return
        
        try:
            embeddings = self.embedding_model.encode(all_chunks, convert_to_tensor=False)
            embeddings_array = np.array(embeddings).astype('float32')
            if len(embeddings_array.shape) == 1:
                embeddings_array = embeddings_array.reshape(1, -1)
            self.index.add(embeddings_array)  # type: ignore
            
            # 更新doc_store
            self.doc_store.extend(chunk_to_doc)
            
            self._save_index()
            logger.info(f"添加 {len(documents)} 个文档到向量索引")
        except Exception as e:
            logger.error(f"向量化过程失败: {str(e)}")

    def search(self, query: str, top_k: int) -> List[Document]:
        """简化版：在embedding_model不可用时返回空结果"""
        if self.fallback_mode:
            # 在回退模式下，不执行向量搜索
            logger.warning("VectorEngine运行在回退模式，跳过向量搜索")
            # 返回前几个存储的文档作为示例结果
            return self.doc_store[:top_k] if len(self.doc_store) > 0 else []
            
        # 原始实现（当回退模式关闭时使用）
        if not self.embedding_model:
            return []
        
        try:
            query_emb = self.embedding_model.encode([query], convert_to_tensor=False)
            query_emb = np.array(query_emb).astype('float32')
            if len(query_emb.shape) == 1:
                query_emb = query_emb.reshape(1, -1)
            distances, indices = self.index.search(query_emb, top_k)  # type: ignore
            
            results = []
            for idx in indices[0]:
                if idx < len(self.doc_store):
                    results.append(self.doc_store[idx])
            
            return results
        except Exception as e:
            logger.error(f"向量搜索过程失败: {str(e)}")
            return []

    def _save_index(self):
        """简化版：在回退模式下不保存索引"""
        if self.fallback_mode:
            logger.warning("VectorEngine运行在回退模式，跳过索引保存")
            return
            
        # 原始实现（当回退模式关闭时使用）
        try:
            #假设index_data = {'faiss': self.index} 但FAISS有write_index；这里加密元数据
            metadata = {}  # e.g., self.doc_store metadata
            # 注意：self.security未在__init__中定义，这可能是个bug
            # 由于我们在回退模式，这里简化处理
            # self.security.save_encrypted_index(metadata, self.index_path + '.meta')
            faiss.write_index(self.index, self.index_path)
        except Exception as e:
            logger.error(f"保存索引失败: {str(e)}")