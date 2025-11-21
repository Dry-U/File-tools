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

    def _highlight_text(self, content, query, window_size=60, max_snippets=3):
        """生成带有高亮关键词的多段文本摘要"""
        if not content or not query:
            return content[:200] + '...' if content and len(content) > 200 else (content or '')
        
        try:
            import re
            # 提取查询中的关键词
            keywords = [k for k in re.split(r'[\s,;，；]+', query) if k.strip()]
            if not keywords:
                return content[:200] + '...' if len(content) > 200 else content
            
            lower_content = content.lower()
            matches = []
            
            # 找到所有关键词的所有出现位置
            for kw in keywords:
                kw_lower = kw.lower()
                start = 0
                while True:
                    idx = lower_content.find(kw_lower, start)
                    if idx == -1:
                        break
                    matches.append((idx, idx + len(kw)))
                    start = idx + len(kw)
            
            # 如果没有匹配，返回开头
            if not matches:
                return content[:200] + '...' if len(content) > 200 else content
            
            # 按位置排序
            matches.sort(key=lambda x: x[0])
            
            # 合并邻近的匹配窗口
            windows = []
            for start, end in matches:
                # 定义当前匹配的窗口范围
                win_start = max(0, start - window_size // 2)
                win_end = min(len(content), end + window_size // 2)
                
                # 尝试合并到上一个窗口
                if windows and win_start < windows[-1][1]:
                    windows[-1] = (windows[-1][0], max(windows[-1][1], win_end))
                else:
                    windows.append((win_start, win_end))
            
            # 限制摘要数量
            selected_windows = windows[:max_snippets]
            
            snippets = []
            for start, end in selected_windows:
                # 调整边界以避免截断单词（简单优化）
                # 向前寻找空格
                while start > 0 and content[start] not in ' \t\n\r.,;，。；':
                    start -= 1
                if start > 0: start += 1 # 跳过分隔符
                
                # 向后寻找空格
                while end < len(content) and content[end] not in ' \t\n\r.,;，。；':
                    end += 1
                
                text_chunk = content[start:end].strip()
                if text_chunk:
                    snippets.append(text_chunk)
            
            final_snippet = ' ... '.join(snippets)
            
            # 高亮关键词
            for kw in keywords:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                final_snippet = pattern.sub(lambda m: f'<span class="text-danger fw-bold">{m.group(0)}</span>', final_snippet)
                
            return final_snippet
        except Exception as e:
            self.logger.error(f"生成摘要失败: {str(e)}")
            return content[:200] + '...'

    def get_document_content(self, path):
        # 尝试从Tantivy索引中获取内容
        if getattr(self, 'tantivy_index', None):
            try:
                self.tantivy_index.reload()
                searcher = self.tantivy_index.searcher()
                
                # 1. 尝试精确路径查询 (注意转义反斜杠)
                escaped_path = path.replace('\\', '\\\\').replace('"', '\\"')
                query_str = f'path:"{escaped_path}"'
                try:
                    query = self.tantivy_index.parse_query(query_str)
                    hits = searcher.search(query, 1).hits
                    if hits:
                        _, doc_addr = hits[0]
                        doc = searcher.doc(doc_addr)
                        content = doc.get_first('content')
                        if content: return content
                except Exception:
                    pass

                # 2. 如果精确路径失败，尝试通过文件名查询 (作为后备)
                filename = os.path.basename(path)
                escaped_filename = filename.replace('"', '\\"')
                query_str = f'filename:"{escaped_filename}"'
                try:
                    query = self.tantivy_index.parse_query(query_str)
                    hits = searcher.search(query, 5).hits # 获取前5个同名文件
                    for _, doc_addr in hits:
                        doc = searcher.doc(doc_addr)
                        idx_path = doc.get_first('path')
                        # 在Python层面验证路径是否匹配 (忽略大小写和分隔符差异)
                        if os.path.normpath(idx_path).lower() == os.path.normpath(path).lower():
                            content = doc.get_first('content')
                            if content: return content
                except Exception:
                    pass
                    
            except Exception as e:
                self.logger.error(f"从索引获取内容失败: {str(e)}")
        
        # 降级方案：使用DocumentParser解析文件
        try:
            # 动态导入以避免循环依赖
            from backend.core.document_parser import DocumentParser
            parser = DocumentParser(self.config_loader)
            content = parser.extract_text(path)
            if content and not content.startswith("错误"):
                return content
        except Exception as e:
            self.logger.error(f"使用DocumentParser解析失败: {str(e)}")
            
        # 最后的降级方案：直接读取文件
        try:
            # 扩展支持的文本格式列表
            ext = os.path.splitext(path)[1].lower()
            text_exts = ['.txt', '.md', '.py', '.json', '.xml', '.csv', '.log', '.js', '.html', '.css', '.bat', '.sh', '.yaml', '.yml', '.ini', '.conf', '.sql', '.properties', '.gradle', '.java', '.c', '.cpp', '.h', '.hpp']
            if ext in text_exts:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read(10000) # 增加读取长度
        except Exception:
            pass
        return ''

    def _format_result(self, path, filename, content, file_type, size, modified, score, query_str):
        """格式化搜索结果"""
        # 生成高亮摘要
        snippet = self._highlight_text(content, query_str)
        
        # 转换时间戳
        modified_time = None
        if modified:
            try:
                import datetime
                if isinstance(modified, (int, float)):
                    modified_time = datetime.datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    modified_time = str(modified)
            except:
                pass

        return {
            'path': path,
            'filename': filename,
            'file_name': filename,
            'content': content, # 保留原始内容以便后续处理
            'snippet': snippet,     # 添加高亮摘要
            'file_type': file_type,
            'size': size,
            'modified': modified_time, # 添加修改时间
            'score': score
        }

    def search_text(self, query_str, limit=10):
        if not getattr(self, 'tantivy_index', None):
            return []
        try:
            results = []
            seg_query = self._segment(query_str)
            self.tantivy_index.reload()
            searcher = self.tantivy_index.searcher()
            queries_to_try = []
            
            # 简化查询构建逻辑
            fields = ['filename', 'content', 'keywords', 'filename_chars', 'content_chars']
            try:
                queries_to_try.append(self.tantivy_index.parse_query(seg_query, fields))
            except Exception: pass
            
            if query_str != seg_query:
                try:
                    queries_to_try.append(self.tantivy_index.parse_query(query_str, fields))
                except Exception: pass
                
            # 尝试单词查询
            try:
                for word in seg_query.split():
                    if word.strip():
                        queries_to_try.append(self.tantivy_index.parse_query(word, fields))
            except Exception: pass
            
            # 尝试字符查询
            try:
                import re
                for ch in re.findall(r'\w', query_str or ''):
                    queries_to_try.append(self.tantivy_index.parse_query(ch, ['filename_chars', 'content_chars']))
            except Exception: pass
            
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
                    modified_val = doc.get_first('modified') or 0
                except Exception:
                    continue
                
                normalized_score = min(float(score), 100.0)
                results.append(self._format_result(
                    path_val, filename_val, content_val, file_type_val, 
                    size_val, modified_val, normalized_score, query_str
                ))
                
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
                    adjusted = min(sim * 100.0, 100.0)
                    
                    path = metadata['path']
                    content = self.get_document_content(path)
                    
                    results.append(self._format_result(
                        path, metadata['filename'], content, metadata['file_type'],
                        0, metadata.get('modified'), adjusted, query_str
                    ))
                    
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:limit]
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []

    def _encode_text(self, text: str):
        try:
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
        # 尝试从Tantivy索引中获取内容（支持所有已索引的文件类型）
        if getattr(self, 'tantivy_index', None):
            try:
                self.tantivy_index.reload()
                searcher = self.tantivy_index.searcher()
                # 使用路径精确查询
                query = self.tantivy_index.parse_query(f'"{path}"', ['path'])
                hits = searcher.search(query, 1).hits
                if hits:
                    _, doc_addr = hits[0]
                    doc = searcher.doc(doc_addr)
                    content = doc.get_first('content')
                    if content:
                        return content
            except Exception:
                pass
        
        # 降级方案：直接读取文件（仅限文本文件）
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.txt', '.md', '.py', '.json', '.xml', '.csv', '.log', '.js', '.html', '.css', '.bat', '.sh', '.yaml', '.yml', '.ini', '.conf']:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(5000)
        except Exception:
            pass
        return ''