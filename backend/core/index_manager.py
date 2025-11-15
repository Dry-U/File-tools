#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""索引管理器模块"""
import os
import shutil
import time
import logging
import tantivy
import jieba
import hnswlib
import numpy as np
from datetime import datetime
import json

 


class IndexManager:
    """索引管理器类，负责创建、更新和查询索引"""
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)
        
        # 获取索引路径配置 - 使用ConfigLoader
        try:
            data_dir = config_loader.get('system', 'data_dir', './data')
            self.tantivy_index_path = config_loader.get('index', 'tantivy_path', f'{data_dir}/tantivy_index')
            self.hnsw_index_path = config_loader.get('index', 'hnsw_path', f'{data_dir}/hnsw_index')
            self.metadata_path = config_loader.get('index', 'metadata_path', f'{data_dir}/metadata')
        except Exception as e:
            self.logger.error(f"获取索引路径配置失败: {str(e)}")
            self.tantivy_index_path = './data/tantivy_index'
            self.hnsw_index_path = './data/hnsw_index'
            self.metadata_path = './data/metadata'
        
        # 创建索引目录
        os.makedirs(self.tantivy_index_path, exist_ok=True)
        os.makedirs(self.hnsw_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)
        try:
            custom_dict_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'custom_dict.txt')
            if os.path.exists(custom_dict_path):
                jieba.load_userdict(custom_dict_path)
        except Exception:
            pass
        self.text_docs = {}
        
        # 初始化嵌入模型
        self.embedding_provider = config_loader.get('embedding', 'provider', 'fastembed')
        model_enabled = config_loader.get('embedding', 'enabled', False)
        if model_enabled:
            if str(self.embedding_provider).lower() in ['sentence_transformers', 'sentence-transformers']:
                try:
                    from sentence_transformers import SentenceTransformer
                    model_path = config_loader.get('embedding', 'model_path', None)
                    model_name = config_loader.get('embedding', 'model_name', None)
                    if model_path:
                        try:
                            if os.path.isfile(model_path):
                                model_path = os.path.dirname(model_path)
                            self.embedding_model = SentenceTransformer(model_path, local_files_only=True)
                        except Exception:
                            self.embedding_model = SentenceTransformer(model_path)
                    elif model_name:
                        try:
                            self.embedding_model = SentenceTransformer(model_name, local_files_only=True)
                        except Exception:
                            self.embedding_model = SentenceTransformer(model_name)
                    else:
                        self.embedding_model = SentenceTransformer('BAAI/bge-small-zh')
                    try:
                        self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
                    except Exception:
                        sample_vec = self.embedding_model.encode(['测试'])[0]
                        self.vector_dim = len(sample_vec)
                except Exception:
                    self.embedding_model = None
                    self.vector_dim = 384
            else:
                try:
                    from fastembed import TextEmbedding
                    model_name = config_loader.get('embedding', 'model_name', 'bge-small-zh')
                    cache_dir = config_loader.get('embedding', 'cache_dir', None)
                    if cache_dir:
                        self.embedding_model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
                    else:
                        self.embedding_model = TextEmbedding(model_name=model_name)
                    try:
                        sample = "测试"
                        vec = next(self.embedding_model.embed([sample]))
                        self.vector_dim = len(vec)
                    except Exception:
                        self.vector_dim = 384
                except Exception:
                    self.embedding_model = None
                    self.vector_dim = 384
        else:
            self.embedding_model = None
            self.vector_dim = 384
        
        self._init_tantivy_index()
        self._init_hnsw_index()
        
        # 索引状态
        self.index_ready = self.is_index_ready()
        
    def _init_tantivy_index(self):
        schema_builder = tantivy.SchemaBuilder()
        self.t_path = schema_builder.add_text_field("path", stored=True, tokenizer_name='raw')
        self.t_filename = schema_builder.add_text_field("filename", stored=True)
        self.t_content = schema_builder.add_text_field("content", stored=True)
        self.t_keywords = schema_builder.add_text_field("keywords", stored=True)
        self.t_file_type = schema_builder.add_text_field("file_type", stored=True)
        self.t_size = schema_builder.add_integer_field("size", stored=True)
        self.t_created = schema_builder.add_integer_field("created", stored=True)
        self.t_modified = schema_builder.add_integer_field("modified", stored=True)
        self.schema = schema_builder.build()
        try:
            self.tantivy_index = tantivy.Index(self.schema, path=self.tantivy_index_path)
        except Exception:
            self.tantivy_index = tantivy.Index(self.schema)
    
    def _init_hnsw_index(self):
        index_file = os.path.join(self.hnsw_index_path, 'vector_index.bin')
        metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
        if os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata_dict = json.load(f)
                    self.vector_metadata = metadata_dict.get('metadata', {})
                    self.next_id = metadata_dict.get('next_id', len(self.vector_metadata))
                self.hnsw = hnswlib.Index(space='cosine', dim=self.vector_dim)
                max_elements = max(self.next_id + 1024, 1024)
                self.hnsw.load_index(index_file, max_elements=max_elements)
            except Exception:
                self._create_new_hnsw_index()
        else:
            self._create_new_hnsw_index()
    
    def _create_new_hnsw_index(self):
        try:
            self.hnsw = hnswlib.Index(space='cosine', dim=self.vector_dim)
            self.hnsw.init_index(max_elements=1024, ef_construction=200, M=16)
            self.hnsw.set_ef(200)
            self.vector_metadata = {}
            self.next_id = 0
        except Exception:
            self.hnsw = None
            self.vector_metadata = {}
            self.next_id = 0
    
    def _segment(self, text):
        try:
            tokens = jieba.lcut_for_search(text or "")
            return " ".join([t for t in tokens if t.strip()])
        except Exception:
            return text or ""

    def add_document(self, document):
        if not self.tantivy_index:
            return False
        try:
            seg_filename = self._segment(document['filename'])
            seg_content = self._segment(document['content'])
            seg_keywords = self._segment(document.get('keywords', ''))
            with self.tantivy_index.writer() as writer:
                tdoc = tantivy.Document(
                    path=document['path'],
                    filename=[seg_filename],
                    content=[seg_content],
                    file_type=[document['file_type']],
                    size=int(document['size']),
                    created=int(time.mktime(document['created'].timetuple())) if isinstance(document['created'], datetime) else int(document['created']),
                    modified=int(time.mktime(document['modified'].timetuple())) if isinstance(document['modified'], datetime) else int(document['modified']),
                    keywords=[seg_keywords]
                )
                writer.add_document(tdoc)
                writer.commit()
            self.text_docs[document['path']] = {
                'filename': seg_filename,
                'content': seg_content,
                'file_type': document['file_type']
            }
            if self.embedding_model and self.hnsw is not None:
                v = np.array([self._encode_text(document['content'][:5000])], dtype=np.float32)
                doc_id = self.next_id
                ids = np.array([doc_id])
                try:
                    self.hnsw.add_items(v, ids)
                except Exception:
                    self.hnsw.resize_index(self.hnsw.get_max_elements() + 1024)
                    self.hnsw.add_items(v, ids)
                self.vector_metadata[str(doc_id)] = {
                    'path': document['path'],
                    'filename': document['filename'],
                    'file_type': document['file_type'],
                    'modified': document['modified'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(document['modified'], datetime) else str(document['modified'])
                }
                self.next_id += 1
            return True
        except Exception as e:
            self.logger.error(f"添加文档到索引失败 {document.get('path', '')}: {str(e)}")
            return False
    
    def update_document(self, document):
        """更新文档在索引中的信息"""
        # 类型检查：确保 document 是字典
        if not isinstance(document, dict):
            self.logger.error(f"无效的文档格式，期望字典但得到 {type(document)}")
            return False
        
        old_doc_id = None
        old_doc_id = None
        for doc_id, metadata in self.vector_metadata.items():
            if metadata.get('path') == document.get('path'):
                old_doc_id = int(doc_id)
                break
        if old_doc_id is not None and self.embedding_model and self.hnsw is not None:
            try:
                pass
            except Exception as e:
                self.logger.error(f"删除旧向量失败: {str(e)}")
        
        # 添加更新后的文档
        return self.add_document(document)
    
    def delete_document(self, file_path):
        if not self.tantivy_index:
            return False
        try:
            with self.tantivy_index.writer() as writer:
                term = tantivy.Term(self.t_path, file_path)
                writer.delete_term(term)
                writer.commit()
            old_doc_id = None
            for doc_id, metadata in self.vector_metadata.items():
                if metadata['path'] == file_path:
                    old_doc_id = int(doc_id)
                    break
            if old_doc_id is not None and self.hnsw is not None:
                if str(old_doc_id) in self.vector_metadata:
                    del self.vector_metadata[str(old_doc_id)]
            return True
        except Exception as e:
            self.logger.error(f"从索引中删除文档失败 {file_path}: {str(e)}")
            return False
    
    def search_text(self, query_str, limit=10):
        if not self.tantivy_index:
            return []
        try:
            results = []
            seg_query = self._segment(query_str)
            q_terms = [t for t in seg_query.lower().split() if t]
            for path, info in self.text_docs.items():
                content = info['content'].lower()
                coverage = 0
                for t in q_terms:
                    if t in content:
                        c = content.count(t)
                        coverage += c / max(1, len(content.split()))
                if coverage == 0:
                    continue
                adjusted = coverage * 10.0
                if any('\u4e00' <= c <= '\u9fff' for c in query_str):
                    content_chars = set(content)
                    query_chars = set(query_str.lower())
                    jaccard = len(content_chars & query_chars) / max(1, len(content_chars | query_chars))
                    adjusted += jaccard * 3.0
                results.append({
                    'path': path,
                    'filename': info['filename'],
                    'content': content[:200] + ('...' if len(content) > 200 else ''),
                    'file_type': info['file_type'],
                    'score': adjusted
                })
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:limit]
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []
    
    def search_vector(self, query_str, limit=10):
        if self.hnsw is None:
            return []
        if not self.embedding_model:
            return []
        try:
            v = np.array([self._encode_text(query_str)], dtype=np.float32)
            k = min(limit*2, max(self.next_id, 1))
            labels, distances = self.hnsw.knn_query(v, k=k)
            results = []
            for i, idx in enumerate(labels[0]):
                if str(idx) in self.vector_metadata:
                    metadata = self.vector_metadata[str(idx)]
                    d = distances[0][i]
                    sim = 1.0 - float(d)
                    adjusted = sim
                    if any('\u4e00' <= c <= '\u9fff' for c in query_str):
                        content = self.get_document_content(metadata['path']).lower()
                        query_chars = set(query_str.lower())
                        content_chars = set(content)
                        jaccard = len(content_chars & query_chars) / max(1, len(content_chars | query_chars))
                        adjusted = sim + (jaccard * sim * 0.3)
                    results.append({
                        'path': metadata['path'],
                        'filename': metadata['filename'],
                        'file_type': metadata['file_type'],
                        'score': adjusted
                    })
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:limit]
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []

    def _encode_text(self, text: str):
        try:
            if str(self.embedding_provider).lower() in ['sentence_transformers', 'sentence-transformers']:
                vec = self.embedding_model.encode([text])[0]
                return np.array(vec, dtype=np.float32)
            else:
                vec = next(self.embedding_model.embed([text]))
                return np.array(vec, dtype=np.float32)
        except Exception:
            return np.zeros(self.vector_dim, dtype=np.float32)
    
    def save_indexes(self):
        try:
            if self.hnsw is not None:
                index_file = os.path.join(self.hnsw_index_path, 'vector_index.bin')
                self.hnsw.save_index(index_file)
            metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
            metadata_dict = {
                'metadata': self.vector_metadata,
                'next_id': self.next_id
            }
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"保存索引失败: {str(e)}")
            return False
    
    def rebuild_index(self):
        try:
            if os.path.exists(self.tantivy_index_path):
                shutil.rmtree(self.tantivy_index_path)
            if os.path.exists(self.hnsw_index_path):
                shutil.rmtree(self.hnsw_index_path)
            if os.path.exists(self.metadata_path):
                shutil.rmtree(self.metadata_path)
            os.makedirs(self.tantivy_index_path, exist_ok=True)
            os.makedirs(self.hnsw_index_path, exist_ok=True)
            os.makedirs(self.metadata_path, exist_ok=True)
            self._init_tantivy_index()
            self._init_hnsw_index()
            return True
        except Exception as e:
            self.logger.error(f"重建索引失败: {str(e)}")
            return False
    
    def get_index_stats(self):
        """获取索引统计信息"""
        stats = {
            'tantivy_initialized': self.tantivy_index is not None,
            'hnsw_initialized': self.hnsw is not None,
            'embedding_model_loaded': self.embedding_model is not None,
            'document_count': 0,
            'vector_count': 0
        }
        try:
            if self.tantivy_index:
                self.tantivy_index.reload()
                searcher = self.tantivy_index.searcher()
                stats['document_count'] = getattr(searcher, 'num_docs', lambda: 0)()
        except Exception:
            pass
        if self.hnsw is not None:
            stats['vector_count'] = self.next_id
        return stats
    
    def is_index_ready(self):
        """检查索引是否就绪(文本索引必须就绪,向量索引可选)"""
        return self.tantivy_index is not None and self.hnsw is not None
    
    def close(self):
        """关闭索引管理器，释放资源"""
        try:
            if self.embedding_model:
                self.embedding_model = None
            self.tantivy_index = None
            self.hnsw = None
            self.logger.info("索引管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭索引管理器时出错: {str(e)}")

    def get_document_content(self, file_path):
        try:
            self.tantivy_index.reload()
            searcher = self.tantivy_index.searcher()
            term = tantivy.Term(self.t_path, file_path)
            query = tantivy.Query.term_query(term)
            hits = searcher.search(query, 1).hits
            if not hits:
                return ""
            _, addr = hits[0]
            doc = searcher.doc(addr)
            content_val = doc.get("content", [""])
            return content_val[0] if isinstance(content_val, list) else content_val
        except Exception:
            return ""