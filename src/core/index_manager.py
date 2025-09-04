#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""索引管理器模块 - 管理Whoosh文本索引和FAISS向量索引"""
import os
import shutil
import time
import logging
from whoosh import index
from whoosh.fields import Schema, TEXT, ID, STORED, KEYWORD, DATETIME
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.analysis import StemmingAnalyzer
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from datetime import datetime
import json

class IndexManager:
    """索引管理器类，负责创建、更新和查询索引"""
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 获取索引路径配置
        self.whoosh_index_path = config.get('index', 'whoosh_path', fallback='./data/whoosh_index')
        self.faiss_index_path = config.get('index', 'faiss_path', fallback='./data/faiss_index')
        self.metadata_path = config.get('index', 'metadata_path', fallback='./data/metadata')
        
        # 创建索引目录
        os.makedirs(self.whoosh_index_path, exist_ok=True)
        os.makedirs(self.faiss_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)
        
        # 初始化嵌入模型
        model_name = config.get('embedding', 'model_name', fallback='all-MiniLM-L6-v2')
        try:
            self.embedding_model = SentenceTransformer(model_name)
            self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
            self.logger.info(f"成功加载嵌入模型: {model_name}, 向量维度: {self.vector_dim}")
        except Exception as e:
            self.logger.error(f"加载嵌入模型失败: {str(e)}")
            self.embedding_model = None
            self.vector_dim = 384  # 默认维度
        
        # 初始化Whoosh索引
        self._init_whoosh_index()
        
        # 初始化FAISS索引
        self._init_faiss_index()
        
        # 索引状态
        self.index_ready = False
        
    def _init_whoosh_index(self):
        """初始化Whoosh索引"""
        # 定义索引模式
        self.schema = Schema(
            path=ID(stored=True, unique=True),  # 文件路径作为唯一标识符
            filename=TEXT(stored=True, analyzer=StemmingAnalyzer()),  # 文件名
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),  # 文件内容
            file_type=KEYWORD(stored=True),  # 文件类型
            size=STORED(),  # 文件大小
            created=DATETIME(stored=True),  # 创建时间
            modified=DATETIME(stored=True),  # 修改时间
            keywords=KEYWORD(stored=True)  # 关键词
        )
        
        # 检查索引是否存在，不存在则创建
        if index.exists_in(self.whoosh_index_path):
            try:
                self.whoosh_index = index.open_dir(self.whoosh_index_path)
                self.logger.info(f"成功打开Whoosh索引: {self.whoosh_index_path}")
            except Exception as e:
                self.logger.error(f"打开Whoosh索引失败: {str(e)}")
                self.whoosh_index = None
        else:
            try:
                self.whoosh_index = index.create_in(self.whoosh_index_path, self.schema)
                self.logger.info(f"成功创建Whoosh索引: {self.whoosh_index_path}")
            except Exception as e:
                self.logger.error(f"创建Whoosh索引失败: {str(e)}")
                self.whoosh_index = None
    
    def _init_faiss_index(self):
        """初始化FAISS索引"""
        index_file = os.path.join(self.faiss_index_path, 'vector_index.faiss')
        metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
        
        # 检查FAISS索引是否存在
        if os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                self.faiss_index = faiss.read_index(index_file)
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    self.vector_metadata = json.load(f)
                self.logger.info(f"成功加载FAISS索引: {index_file}, 向量数量: {self.faiss_index.ntotal}")
            except Exception as e:
                self.logger.error(f"加载FAISS索引失败: {str(e)}")
                self._create_new_faiss_index()
        else:
            self._create_new_faiss_index()
    
    def _create_new_faiss_index(self):
        """创建新的FAISS索引"""
        try:
            # 创建一个空的FAISS索引
            self.faiss_index = faiss.IndexFlatL2(self.vector_dim)  # 使用L2距离
            self.vector_metadata = {}
            self.logger.info(f"成功创建新的FAISS索引，向量维度: {self.vector_dim}")
        except Exception as e:
            self.logger.error(f"创建FAISS索引失败: {str(e)}")
            self.faiss_index = None
            self.vector_metadata = {}
    
    def add_document(self, document):
        """添加文档到索引"""
        if not self.whoosh_index or not self.faiss_index or not self.embedding_model:
            self.logger.error("索引组件未初始化完成，无法添加文档")
            return False
        
        try:
            # 添加到Whoosh索引
            with self.whoosh_index.writer() as writer:
                writer.update_document(
                    path=document['path'],
                    filename=document['filename'],
                    content=document['content'],
                    file_type=document['file_type'],
                    size=document['size'],
                    created=document['created'],
                    modified=document['modified'],
                    keywords=document['keywords']
                )
            
            # 生成向量嵌入
            vector = self.embedding_model.encode(document['content'][:5000])  # 限制内容长度以提高效率
            vector = np.array([vector], dtype=np.float32)
            
            # 获取当前索引的ID
            doc_id = len(self.vector_metadata)
            
            # 添加到FAISS索引
            self.faiss_index.add(vector)
            
            # 保存元数据
            self.vector_metadata[str(doc_id)] = {
                'path': document['path'],
                'filename': document['filename'],
                'file_type': document['file_type'],
                'modified': document['modified'].strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return True
        except Exception as e:
            self.logger.error(f"添加文档到索引失败 {document.get('path', '')}: {str(e)}")
            return False
    
    def update_document(self, document):
        """更新文档在索引中的信息"""
        # 对于Whoosh，update_document方法已经支持更新
        # 对于FAISS，我们需要先删除旧向量，再添加新向量
        
        # 首先尝试查找并删除旧向量
        old_doc_id = None
        for doc_id, metadata in self.vector_metadata.items():
            if metadata['path'] == document['path']:
                old_doc_id = int(doc_id)
                break
        
        if old_doc_id is not None:
            # 创建一个新的索引，排除要删除的向量
            new_index = faiss.IndexFlatL2(self.vector_dim)
            new_metadata = {}
            
            # 添加所有不包含要删除向量的向量
            for i in range(self.faiss_index.ntotal):
                if i != old_doc_id:
                    vector = self.faiss_index.reconstruct(i).reshape(1, -1)
                    new_index.add(vector)
                    
                    # 更新元数据ID
                    old_key = str(i)
                    if old_key in self.vector_metadata:
                        new_metadata[str(len(new_metadata))] = self.vector_metadata[old_key]
            
            # 更新FAISS索引和元数据
            self.faiss_index = new_index
            self.vector_metadata = new_metadata
        
        # 添加更新后的文档
        return self.add_document(document)
    
    def delete_document(self, file_path):
        """从索引中删除文档"""
        if not self.whoosh_index or not self.faiss_index:
            self.logger.error("索引组件未初始化完成，无法删除文档")
            return False
        
        try:
            # 从Whoosh索引中删除
            with self.whoosh_index.writer() as writer:
                writer.delete_by_term('path', file_path)
            
            # 从FAISS索引中删除
            old_doc_id = None
            for doc_id, metadata in self.vector_metadata.items():
                if metadata['path'] == file_path:
                    old_doc_id = int(doc_id)
                    break
            
            if old_doc_id is not None:
                # 创建一个新的索引，排除要删除的向量
                new_index = faiss.IndexFlatL2(self.vector_dim)
                new_metadata = {}
                
                # 添加所有不包含要删除向量的向量
                for i in range(self.faiss_index.ntotal):
                    if i != old_doc_id:
                        vector = self.faiss_index.reconstruct(i).reshape(1, -1)
                        new_index.add(vector)
                        
                        # 更新元数据ID
                        old_key = str(i)
                        if old_key in self.vector_metadata:
                            new_metadata[str(len(new_metadata))] = self.vector_metadata[old_key]
                
                # 更新FAISS索引和元数据
                self.faiss_index = new_index
                self.vector_metadata = new_metadata
            
            return True
        except Exception as e:
            self.logger.error(f"从索引中删除文档失败 {file_path}: {str(e)}")
            return False
    
    def search_text(self, query_str, limit=10):
        """在文本索引中搜索"""
        if not self.whoosh_index:
            self.logger.error("Whoosh索引未初始化完成，无法搜索")
            return []
        
        try:
            results = []
            
            with self.whoosh_index.searcher() as searcher:
                # 使用多字段查询解析器
                parser = MultifieldParser(['filename', 'content', 'keywords'], schema=self.schema)
                query = parser.parse(query_str)
                
                # 执行搜索
                hits = searcher.search(query, limit=limit)
                
                # 处理搜索结果
                for hit in hits:
                    results.append({
                        'path': hit['path'],
                        'filename': hit['filename'],
                        'content': hit['content'][:200] + ('...' if len(hit['content']) > 200 else ''),
                        'file_type': hit['file_type'],
                        'score': hit.score
                    })
            
            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []
    
    def search_vector(self, query_str, limit=10):
        """在向量索引中搜索"""
        if not self.faiss_index or not self.embedding_model:
            self.logger.error("FAISS索引或嵌入模型未初始化完成，无法进行向量搜索")
            return []
        
        try:
            # 生成查询向量
            query_vector = self.embedding_model.encode([query_str])
            query_vector = np.array(query_vector, dtype=np.float32)
            
            # 执行向量搜索
            distances, indices = self.faiss_index.search(query_vector, limit)
            
            # 处理搜索结果
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and str(idx) in self.vector_metadata:
                    metadata = self.vector_metadata[str(idx)]
                    results.append({
                        'path': metadata['path'],
                        'filename': metadata['filename'],
                        'file_type': metadata['file_type'],
                        'score': 1.0 / (1.0 + distances[0][i])  # 将距离转换为相似度分数
                    })
            
            return results
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []
    
    def save_indexes(self):
        """保存索引到磁盘"""
        if not self.whoosh_index or not self.faiss_index:
            self.logger.error("索引组件未初始化完成，无法保存")
            return False
        
        try:
            # Whoosh索引会自动保存，但我们可以显式提交任何未完成的写入
            if self.whoosh_index.is_modified():
                self.whoosh_index.commit()
            
            # 保存FAISS索引
            index_file = os.path.join(self.faiss_index_path, 'vector_index.faiss')
            faiss.write_index(self.faiss_index, index_file)
            
            # 保存向量元数据
            metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.vector_metadata, f, ensure_ascii=False, indent=2)
            
            self.logger.info("索引已成功保存到磁盘")
            return True
        except Exception as e:
            self.logger.error(f"保存索引失败: {str(e)}")
            return False
    
    def rebuild_index(self):
        """重建索引"""
        try:
            # 删除旧索引
            if os.path.exists(self.whoosh_index_path):
                shutil.rmtree(self.whoosh_index_path)
            if os.path.exists(self.faiss_index_path):
                shutil.rmtree(self.faiss_index_path)
            if os.path.exists(self.metadata_path):
                shutil.rmtree(self.metadata_path)
            
            # 重新创建目录
            os.makedirs(self.whoosh_index_path, exist_ok=True)
            os.makedirs(self.faiss_index_path, exist_ok=True)
            os.makedirs(self.metadata_path, exist_ok=True)
            
            # 重新初始化索引
            self._init_whoosh_index()
            self._init_faiss_index()
            
            self.logger.info("索引已成功重建")
            return True
        except Exception as e:
            self.logger.error(f"重建索引失败: {str(e)}")
            return False
    
    def get_index_stats(self):
        """获取索引统计信息"""
        stats = {
            'whoosh_initialized': self.whoosh_index is not None,
            'faiss_initialized': self.faiss_index is not None,
            'embedding_model_loaded': self.embedding_model is not None,
            'document_count': 0,
            'vector_count': 0
        }
        
        # 获取Whoosh文档数量
        if self.whoosh_index:
            try:
                with self.whoosh_index.searcher() as searcher:
                    stats['document_count'] = searcher.doc_count()
            except:
                pass
        
        # 获取FAISS向量数量
        if self.faiss_index:
            stats['vector_count'] = self.faiss_index.ntotal
        
        return stats
    
    def is_index_ready(self):
        """检查索引是否就绪"""
        return self.whoosh_index is not None and self.faiss_index is not None and self.embedding_model is not None