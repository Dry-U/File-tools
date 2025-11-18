#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)
        try:
            data_dir = config_loader.get('system', 'data_dir', './data')
            self.tantivy_index_path = config_loader.get('index', 'tantivy_path', f'{data_dir}/tantivy_index')
            self.hnsw_index_path = config_loader.get('index', 'hnsw_path', f'{data_dir}/hnsw_index')
            self.metadata_path = config_loader.get('index', 'metadata_path', f'{data_dir}/metadata')
        except Exception as e:
            self.logger.error(f"配置读取失败: {str(e)}")
            self.tantivy_index_path = './data/tantivy_index'
            self.hnsw_index_path = './data/hnsw_index'
            self.metadata_path = './data/metadata'
        os.makedirs(self.tantivy_index_path, exist_ok=True)
        os.makedirs(self.hnsw_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)
        try:
            custom_dict_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'custom_dict.txt')
            if os.path.exists(custom_dict_path):
                jieba.load_userdict(custom_dict_path)
        except Exception:
            pass
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
                        sample_vec = self.embedding_model.encode(['test'])[0]
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
                        vec = next(self.embedding_model.embed(['test']))
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
        self.index_ready = self.is_index_ready()
        self.schema_updated = False
        try:
            self._ensure_schema_version()
        except Exception:
            pass

    def _init_tantivy_index(self):
        schema_builder = tantivy.SchemaBuilder()
        self.t_path = schema_builder.add_text_field('path', stored=True, tokenizer_name='raw')
        self.t_filename = schema_builder.add_text_field('filename', stored=True)
        self.t_filename_chars = schema_builder.add_text_field('filename_chars', stored=True)
        self.t_content = schema_builder.add_text_field('content', stored=True)
        self.t_content_chars = schema_builder.add_text_field('content_chars', stored=True)
        self.t_keywords = schema_builder.add_text_field('keywords', stored=True)
        self.t_file_type = schema_builder.add_text_field('file_type', stored=True)
        self.t_size = schema_builder.add_integer_field('size', stored=True)
        self.t_created = schema_builder.add_integer_field('created', stored=True)
        self.t_modified = schema_builder.add_integer_field('modified', stored=True)
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

    def _ensure_schema_version(self):
        expected_fields = ['path','filename','filename_chars','content','content_chars','keywords','file_type','size','created','modified']
        version_file = os.path.join(self.metadata_path, 'schema_version.json')
        current = {}
        try:
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    current = json.load(f)
        except Exception:
            current = {}
        current_fields = current.get('fields', [])
        if current_fields != expected_fields:
            try:
                self.logger.info('检测到索引模式变化，重建索引以支持单字符检索')
                self.rebuild_index()
                self.schema_updated = True
                with open(version_file, 'w', encoding='utf-8') as f:
                    json.dump({'fields': expected_fields}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.error(f'更新索引模式失败: {str(e)}')

    def _segment(self, text):
        try:
            tokens = jieba.lcut_for_search(text or '')
            return ' '.join([t for t in tokens if t.strip()])
        except Exception:
            return text or ''

    def add_document(self, document):
        if not getattr(self, 'tantivy_index', None):
            return False
        try:
            seg_filename = self._segment(document['filename'])
            seg_content = self._segment(document['content'])
            seg_keywords = self._segment(document.get('keywords', ''))
            fname_chars = ' '.join([c for c in document['filename']])
            try:
                raw_content = document['content'] or ''
            except Exception:
                raw_content = ''
            content_chars = ' '.join([c for c in str(raw_content)[:5000]])
            with self.tantivy_index.writer() as writer:
                tdoc = tantivy.Document(
                    path=document['path'],
                    filename=[seg_filename],
                    filename_chars=[fname_chars],
                    content=[seg_content],
                    content_chars=[content_chars],
                    file_type=[document['file_type']],
                    size=int(document['size']),
                    created=int(time.mktime(document['created'].timetuple())) if isinstance(document['created'], datetime) else int(document['created']),
                    modified=int(time.mktime(document['modified'].timetuple())) if isinstance(document['modified'], datetime) else int(document['modified']),
                    keywords=[seg_keywords]
                )
                writer.add_document(tdoc)
                writer.commit()
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
        if not isinstance(document, dict):
            self.logger.error(f"无效的文档格式，期望字典但得到 {type(document)}")
            return False
        try:
            self.delete_document(document.get('path'))
        except Exception:
            pass
        return self.add_document(document)

    def delete_document(self, file_path):
        if not getattr(self, 'tantivy_index', None):
            return False
        try:
            try:
                with self.tantivy_index.writer() as writer:
                    try:
                        query = self.tantivy_index.parse_query(f'"{file_path}"', ['path'])
                        # 尝试通过查询删除，某些版本的python-tantivy不支持Term
                        if hasattr(writer, 'delete_query'):
                            writer.delete_query(query)
                        elif hasattr(writer, 'delete_documents'):
                            writer.delete_documents(query)
                        # 若均不支持，则跳过删除，依赖结果去重与重建索引
                    except Exception:
                        pass
                    writer.commit()
            except Exception:
                pass
            old_doc_id = None
            for doc_id, metadata in list(self.vector_metadata.items()):
                if metadata.get('path') == file_path:
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
        if not getattr(self, 'tantivy_index', None):
            return []
        try:
            results = []
            seg_query = self._segment(query_str)
            self.tantivy_index.reload()
            searcher = self.tantivy_index.searcher()
            queries_to_try = []
            try:
                query1 = self.tantivy_index.parse_query(seg_query, ['filename', 'content', 'keywords', 'filename_chars', 'content_chars'])
                queries_to_try.append(query1)
            except Exception:
                pass
            try:
                query2 = self.tantivy_index.parse_query(query_str, ['filename', 'content', 'keywords', 'filename_chars', 'content_chars'])
                queries_to_try.append(query2)
            except Exception:
                pass
            try:
                for word in seg_query.split():
                    if word.strip():
                        word_query = self.tantivy_index.parse_query(word, ['filename', 'content', 'keywords', 'filename_chars', 'content_chars'])
                        queries_to_try.append(word_query)
            except Exception:
                pass
            try:
                import re
                for ch in re.findall(r'\w', query_str or ''):
                    ch_query = self.tantivy_index.parse_query(ch, ['filename_chars', 'content_chars'])
                    queries_to_try.append(ch_query)
            except Exception:
                pass
            all_hits = []
            for query in queries_to_try:
                try:
                    hits = searcher.search(query, limit * 2).hits
                    all_hits.extend(hits)
                except Exception:
                    continue
            unique_docs = {}
            for score, doc_address in all_hits:
                addr_key = str(doc_address)
                if addr_key not in unique_docs or unique_docs[addr_key][0] < score:
                    unique_docs[addr_key] = (score, doc_address)
            sorted_hits = sorted(unique_docs.values(), key=lambda x: x[0], reverse=True)
            final_hits = sorted_hits[:limit]
            for score, doc_address in final_hits:
                doc = searcher.doc(doc_address)
                try:
                    path_val = doc.get_first('path') or ''
                    filename_val = doc.get_first('filename') or ''
                    content_val = doc.get_first('content') or ''
                    file_type_val = doc.get_first('file_type') or ''
                    size_val = doc.get_first('size') or 0
                except Exception:
                    continue
                normalized_score = min(float(score), 100.0)
                results.append({
                    'path': path_val,
                    'filename': filename_val,
                    'file_name': filename_val,
                    'content': content_val[:200] + ('...' if len(content_val) > 200 else ''),
                    'file_type': file_type_val,
                    'size': size_val,
                    'score': normalized_score
                })
            results.sort(key=lambda x: x['score'], reverse=True)
            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []

    def search_vector(self, query_str, limit=10):
        if getattr(self, 'hnsw', None) is None:
            return []
        if not self.embedding_model:
            return []
        try:
            v = np.array([self._encode_text(query_str)], dtype=np.float32)
            k = min(limit * 2, max(self.next_id, 1))
            labels, distances = self.hnsw.knn_query(v, k=k)
            results = []
            for i, idx in enumerate(labels[0]):
                if str(idx) in self.vector_metadata:
                    metadata = self.vector_metadata[str(idx)]
                    d = distances[0][i]
                    sim = 1.0 - float(d)
                    adjusted = sim * 100.0
                    adjusted = min(adjusted, 100.0)
                    results.append({
                        'path': metadata['path'],
                        'filename': metadata['filename'],
                        'file_name': metadata['filename'],
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
            if str(getattr(self, 'embedding_provider', 'fastembed')).lower() in ['sentence_transformers', 'sentence-transformers']:
                vec = self.embedding_model.encode([text])[0]
                return np.array(vec, dtype=np.float32)
            else:
                vec = next(self.embedding_model.embed([text]))
                return np.array(vec, dtype=np.float32)
        except Exception:
            return np.zeros(getattr(self, 'vector_dim', 384), dtype=np.float32)

    def save_indexes(self):
        try:
            if getattr(self, 'hnsw', None) is not None:
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

    def is_index_ready(self):
        try:
            return os.path.exists(self.tantivy_index_path)
        except Exception:
            return False

    def get_document_content(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(5000)
        except Exception:
            return ''