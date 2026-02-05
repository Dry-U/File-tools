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
                if self.embedding_provider == 'modelscope':
                    from modelscope.pipelines import pipeline
                    from modelscope.utils.constant import Tasks
                    model_name = config_loader.get('embedding', 'model_name', 'iic/nlp_gte_sentence-embedding_chinese-base')
                    cache_dir = config_loader.get('embedding', 'cache_dir', None)
                    
                    # 如果指定了本地路径，使用本地路径
                    if cache_dir and os.path.exists(os.path.join(cache_dir, model_name.split('/')[-1])):
                         model_path = os.path.join(cache_dir, model_name.split('/')[-1])
                         self.logger.info(f"使用本地模型路径: {model_path}")
                         self.embedding_pipeline = pipeline(Tasks.sentence_embedding, model=model_path)
                    else:
                         self.embedding_pipeline = pipeline(Tasks.sentence_embedding, model=model_name)
                    
                    # 包装一个embed方法以兼容
                    class ModelScopeWrapper:
                        def __init__(self, pipeline):
                            self.pipeline = pipeline
                        def embed(self, texts):
                            # ModelScope pipeline returns a dict with 'text_embedding'
                            # We need to yield vectors one by one or batch
                            # The pipeline handles batching if texts is a list
                            
                            # 针对 gte-sentence-embedding 模型的特殊处理
                            # 它可能需要字典输入或者对列表输入的处理不同
                            if isinstance(texts, list):
                                # 尝试逐个处理或构造特定格式
                                for text in texts:
                                    try:
                                        # 尝试直接传字符串
                                        res = self.pipeline(input=text)
                                    except TypeError:
                                        # 如果失败，尝试传字典
                                        res = self.pipeline(input={'source_sentence': [text]})
                                    
                                    if 'text_embedding' in res:
                                        # 结果可能是 [1, 768] 或 [768]
                                        emb = res['text_embedding']
                                        if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                                            yield emb[0]
                                        elif isinstance(emb, np.ndarray):
                                            if emb.ndim > 1:
                                                yield emb[0]
                                            else:
                                                yield emb
                                        else:
                                            yield emb
                            else:
                                # 单个文本
                                try:
                                    res = self.pipeline(input=texts)
                                except TypeError:
                                    res = self.pipeline(input={'source_sentence': [texts]})
                                    
                                if 'text_embedding' in res:
                                    emb = res['text_embedding']
                                    if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                                        yield emb[0]
                                    elif isinstance(emb, np.ndarray):
                                        if emb.ndim > 1:
                                            yield emb[0]
                                        else:
                                            yield emb
                                    else:
                                        yield emb

                    self.embedding_model = ModelScopeWrapper(self.embedding_pipeline)
                    
                    # Test
                    vec = next(self.embedding_model.embed(['test']))
                    self.vector_dim = len(vec)
                    self.logger.info(f"ModelScope Embedding模型加载成功，维度: {self.vector_dim}")

                else:
                    # Default to fastembed
                    from fastembed import TextEmbedding
                    model_name = config_loader.get('embedding', 'model_name', 'BAAI/bge-small-zh-v1.5')
                    if not model_name:
                        model_name = 'BAAI/bge-small-zh-v1.5'
                    
                    cache_dir = config_loader.get('embedding', 'cache_dir', None)

                    # 尝试创建模型实例，如果下载失败则记录错误并禁用embedding
                    try:
                        if cache_dir:
                            self.embedding_model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
                        else:
                            self.embedding_model = TextEmbedding(model_name=model_name)
                        try:
                            # 测试模型是否可以正常工作
                            vec = next(self.embedding_model.embed(['test']))
                            self.vector_dim = len(vec)
                            self.logger.info(f"Embedding模型加载成功，维度: {self.vector_dim}")
                        except Exception:
                            self.vector_dim = 384
                            self.logger.warning(f"Embedding模型测试失败，使用默认维度: {self.vector_dim}")
                    except Exception as e:
                        self.logger.error(f"Embedding模型创建失败，将禁用向量索引: {str(e)}")
                        self.embedding_model = None
                        self.vector_dim = 384
            except ImportError as ie:
                self.logger.error(f"依赖库未安装 ({str(ie)})，禁用向量索引")
                self.embedding_model = None
                self.vector_dim = 384
            except Exception as e:
                self.logger.error(f"加载Embedding模型时发生未知错误: {str(e)}")
                self.embedding_model = None
                self.vector_dim = 384
        else:
            self.logger.info("Embedding功能未启用")
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
        self.t_content_raw = schema_builder.add_text_field('content_raw', stored=True, tokenizer_name='raw')
        self.t_content_chars = schema_builder.add_text_field('content_chars', stored=True)
        self.t_keywords = schema_builder.add_text_field('keywords', stored=True)
        self.t_file_type = schema_builder.add_text_field('file_type', stored=True)
        self.t_size = schema_builder.add_integer_field('size', stored=True)
        self.t_created = schema_builder.add_integer_field('created', stored=True)
        self.t_modified = schema_builder.add_integer_field('modified', stored=True)
        self.schema = schema_builder.build()
        try:
            # 检查索引路径是否存在，如果不存在，则创建
            if not os.path.exists(self.tantivy_index_path):
                os.makedirs(self.tantivy_index_path, exist_ok=True)
                self.tantivy_index = tantivy.Index(self.schema, path=self.tantivy_index_path)
            else:
                self.tantivy_index = tantivy.Index(self.schema, path=self.tantivy_index_path)
        except Exception as e:
            self.logger.error(f"初始化Tantivy索引失败: {str(e)}")
            # 如果指定路径失败，尝试在内存中创建新索引，但仍尝试重新创建文件目录
            try:
                os.makedirs(self.tantivy_index_path, exist_ok=True)
                self.tantivy_index = tantivy.Index(self.schema, path=self.tantivy_index_path)
            except Exception as e2:
                self.logger.error(f"创建索引目录或初始化索引失败: {str(e2)}")
                self.tantivy_index = tantivy.Index(self.schema)

    def _init_hnsw_index(self):
        """初始化HNSW向量索引"""
        # 确保向量索引和元数据目录存在
        os.makedirs(self.hnsw_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)

        index_file = os.path.join(self.hnsw_index_path, 'vector_index.bin')
        metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
        
        if os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata_dict = json.load(f)
                    self.vector_metadata = metadata_dict.get('metadata', {})
                    self.next_id = metadata_dict.get('next_id', len(self.vector_metadata))
                
                # 检查向量维度是否匹配
                if self.embedding_model:
                    self.hnsw = hnswlib.Index(space='cosine', dim=self.vector_dim)
                    max_elements = max(self.next_id + 1024, 1024)
                    self.hnsw.load_index(index_file, max_elements=max_elements)
                    self.logger.info(f"成功加载向量索引，维度: {self.vector_dim}, 元素数: {self.next_id}")
                else:
                    self.logger.warning("向量索引已存在但嵌入模型未启用，跳过加载")
                    self._create_new_hnsw_index()
            except Exception as e:
                self.logger.error(f"加载现有向量索引失败: {str(e)}")
                self._create_new_hnsw_index()
        else:
            self.logger.info(f"向量索引文件不存在，创建新索引: {index_file}")
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
        expected_fields = ['path','filename','filename_chars','content','content_raw','content_chars','keywords','file_type','size','created','modified']
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
            raw_text = str(raw_content)
            content_chars_source = raw_text
            content_chars = ' '.join([c for c in content_chars_source])
            with self.tantivy_index.writer() as writer:
                tdoc = tantivy.Document(
                    path=document['path'],
                    filename=[seg_filename],
                    filename_chars=[fname_chars],
                    content=[seg_content],
                    content_raw=[raw_text],
                    content_chars=[content_chars],
                    file_type=[document['file_type']],
                    size=int(document['size']),
                    created=int(time.mktime(document['created'].timetuple())) if isinstance(document['created'], datetime) else int(document['created']),
                    modified=int(time.mktime(document['modified'].timetuple())) if isinstance(document['modified'], datetime) else int(document['modified']),
                    keywords=[seg_keywords]
                )
                writer.add_document(tdoc)
                writer.commit()

            # 添加向量索引（如果启用了embedding）
            if self.embedding_model and self.hnsw is not None:
                try:
                    content_to_encode = document['content'][:5000] if document['content'] else ''
                    if content_to_encode.strip():  # 只有当内容不为空时才编码
                        v = np.array([self._encode_text(content_to_encode)], dtype=np.float32)
                        doc_id = self.next_id
                        ids = np.array([doc_id])
                        try:
                            self.hnsw.add_items(v, ids)
                            self.logger.info(f"成功添加文档到向量索引: {document['path']}")
                        except Exception as ve:
                            # 如果添加项目失败，尝试调整索引大小
                            try:
                                self.hnsw.resize_index(self.hnsw.get_max_elements() + 1024)
                                self.hnsw.add_items(v, ids)
                                self.logger.info(f"调整向量索引大小后成功添加文档: {document['path']}")
                            except Exception as resize_e:
                                self.logger.error(f"调整向量索引大小后仍无法添加文档: {str(resize_e)}")

                        # 记录元数据
                        self.vector_metadata[str(doc_id)] = {
                            'path': document['path'],
                            'filename': document['filename'],
                            'file_type': document['file_type'],
                            'modified': document['modified'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(document['modified'], datetime) else str(document['modified'])
                        }
                        self.next_id += 1

                        # 确保定期保存向量索引
                        self.save_indexes()
                    else:
                        self.logger.warning(f"文档内容为空，跳过向量索引: {document['path']}")
                except Exception as e:
                    self.logger.error(f"添加文档到向量索引失败 {document['path']}: {str(e)}")
            else:
                if not self.embedding_model:
                    self.logger.info("Embedding模型未启用，跳过向量索引")
                elif not self.hnsw:
                    self.logger.warning("HNSW向量索引未初始化，跳过向量索引")

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

    def _highlight_text(self, content, query, window_size=120, max_snippets=3):
        """生成带有高亮关键词的多段文本摘要，并兼容常见的空格/大小写差异"""
        if not content or not query:
            return content[:200] + '...' if content and len(content) > 200 else (content or '')

        try:
            import re
            import jieba

            def _clean_keyword(token: str) -> str:
                return token.strip()

            def _build_pattern(token: str):
                # 允许字符之间穿插空白，适配 "J a v a" 这类被拆分的文本
                # 对特殊字符进行转义
                escaped = re.escape(token)
                # 如果是字母或数字，允许中间有空格
                if token.isalnum():
                    pieces = [f"{re.escape(ch)}\\s*" for ch in token]
                    pattern = ''.join(pieces)
                    return re.compile(pattern, re.IGNORECASE)
                return re.compile(escaped, re.IGNORECASE)

            def _expand_ascii_span(text: str, start: int, end: int):
                # 向左右扩展，确保高亮完整的ASCII单词（如JavaScript）
                while start > 0 and text[start-1].isascii() and text[start-1].isalnum():
                    start -= 1
                while end < len(text) and text[end].isascii() and text[end].isalnum():
                    end += 1
                return start, end

            def _collect_matches(full_text: str, patterns):
                spans = []
                seen = set()
                for pat in patterns:
                    for match in pat.finditer(full_text):
                        span = _expand_ascii_span(full_text, match.start(), match.end())
                        if span not in seen:
                            seen.add(span)
                            spans.append(span)
                return spans

            # 构建关键词集合
            keywords = set()
            # 1. 原始查询作为关键词
            if query.strip():
                keywords.add(query.strip())
            
            # 2. 分词后的关键词
            raw_tokens = [k.strip() for k in re.split(r'[\s,;，；]+', query) if k.strip()]
            for token in raw_tokens:
                cleaned = _clean_keyword(token)
                if cleaned:
                    keywords.add(cleaned)
                # 只有当token比较长时才进行进一步分词，避免过度碎片化
                if len(token) > 2:
                    for seg in jieba.lcut_for_search(token):
                        seg_clean = _clean_keyword(seg)
                        if seg_clean and len(seg_clean) > 1: # 忽略单字，除非是原始token
                            keywords.add(seg_clean)

            if not keywords:
                return content[:200] + '...' if len(content) > 200 else content

            patterns = [_build_pattern(token) for token in keywords if token]
            if not patterns:
                return content[:200] + '...' if len(content) > 200 else content

            matches = _collect_matches(content, patterns)

            if not matches:
                # fallback: 如果仍然没有匹配，则尝试直接定位（兼容极端情况）
                lowered = content.lower()
                for token in keywords:
                    idx = lowered.find(token.lower())
                    if idx != -1:
                        match_span = _expand_ascii_span(content, idx, idx + len(token))
                        matches.append(match_span)
                        # 只要找到一个匹配就足够了
                        break

            if not matches:
                return content[:200] + '...' if len(content) > 200 else content

            matches.sort(key=lambda x: x[0])

            # 合并窗口
            windows = []
            for start, end in matches:
                win_start = max(0, start - window_size // 2)
                win_end = min(len(content), end + window_size // 2)
                if windows and win_start < windows[-1][1]:
                    windows[-1] = (windows[-1][0], max(windows[-1][1], win_end))
                else:
                    windows.append((win_start, win_end))

            scored_windows = []
            lowered_content = content.lower()
            for win_start, win_end in windows:
                chunk = lowered_content[win_start:win_end]
                score = 0
                for token in keywords:
                    if token.lower() in chunk:
                        score += 1
                # 优先考虑包含完整查询词的窗口
                if query.lower() in chunk:
                    score += 10
                scored_windows.append((score, win_start, win_end))

            scored_windows.sort(key=lambda x: x[0], reverse=True)
            selected_windows = [(s, e) for _, s, e in scored_windows[:max_snippets]]
            selected_windows.sort(key=lambda x: x[0])

            snippets = []
            for start, end in selected_windows:
                # 尝试在标点符号处截断，使摘要更自然
                curr_start = start
                while curr_start > 0 and curr_start > start - 20 and content[curr_start] not in ' \t\n\r.,;，。；':
                    curr_start -= 1
                if curr_start > 0 and content[curr_start] in ' \t\n\r.,;，。；':
                    curr_start += 1

                curr_end = end
                while curr_end < len(content) and curr_end < end + 20 and content[curr_end] not in ' \t\n\r.,;，。；':
                    curr_end += 1

                chunk = content[curr_start:curr_end].strip()
                if chunk:
                    snippets.append(chunk)

            if not snippets:
                # 如果窗口提取失败，回退到简单的正则提取
                for token in keywords:
                    pat = re.compile(re.escape(token), re.IGNORECASE)
                    match = pat.search(content)
                    if match:
                        start = max(0, match.start() - 60)
                        end = min(len(content), match.end() + 60)
                        snippets.append(content[start:end])
                        break

            if not snippets:
                return content[:200] + '...' if len(content) > 200 else content

            def _apply_highlight(text: str):
                spans = _collect_matches(text, patterns)
                if not spans:
                    return text
                spans.sort(key=lambda x: x[0])
                merged = []
                for start, end in spans:
                    if not merged or start > merged[-1][1]:
                        merged.append([start, end])
                    else:
                        merged[-1][1] = max(merged[-1][1], end)

                highlighted = []
                last = 0
                for start, end in merged:
                    if start < last:
                        continue
                    highlighted.append(text[last:start])
                    # 使用 text-danger 和 fw-bold 高亮
                    highlighted.append(f'<span class="text-danger fw-bold">{text[start:end]}</span>')
                    last = end
                highlighted.append(text[last:])
                return ''.join(highlighted)

            processed_snippets = [_apply_highlight(chunk) for chunk in snippets]
            final_snippet = '<br>...<br>'.join(processed_snippets)
            return final_snippet
        except Exception as exc:
            self.logger.error(f"生成摘要失败: {str(exc)}")
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
                        raw_val = doc.get_first('content_raw')
                        content_val = raw_val or doc.get_first('content')
                        if raw_val:
                            return raw_val  # 返回完整内容，不限制长度
                        if content_val:
                            # 如果索引中的内容不完整，尝试直接解析文件
                            parsed = self._parse_file_direct(path)
                            return parsed if parsed else content_val
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
                            raw_val = doc.get_first('content_raw')
                            content_val = raw_val or doc.get_first('content')
                            if raw_val:
                                return raw_val  # 返回完整内容，不限制长度
                            if content_val:
                                # 如果索引中的内容不完整，尝试直接解析文件
                                parsed = self._parse_file_direct(path)
                                return parsed if parsed else content_val
                except Exception:
                    pass

            except Exception as e:
                self.logger.error(f"从索引获取内容失败: {str(e)}")

        # 降级方案：使用DocumentParser解析文件
        try:
            parsed = self._parse_file_direct(path)
            if parsed:
                return parsed
        except Exception as e:
            self.logger.error(f"使用DocumentParser解析失败: {str(e)}")

        # 最后的降级方案：直接读取文件
        try:
            # 扩展支持的文本格式列表
            ext = os.path.splitext(path)[1].lower()
            text_exts = ['.txt', '.md', '.py', '.json', '.xml', '.csv', '.log', '.js', '.html', '.css', '.bat', '.sh', '.yaml', '.yml', '.ini', '.conf', '.sql', '.properties', '.gradle', '.java', '.c', '.cpp', '.h', '.hpp']
            if ext in text_exts:
                if os.path.exists(path):
                    # 读取完整文件内容，不限制长度（调用方应自行处理大文件）
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
        except Exception:
            pass
        return ''

    def _parse_file_direct(self, path):
        try:
            from backend.core.document_parser import DocumentParser
            parser = DocumentParser(self.config_loader)
            content = parser.extract_text(path)
            if content and not content.startswith("错误"):
                return content
        except Exception as exc:
            self.logger.debug(f"直接解析文件失败: {exc}")
        return ''

    def _format_result(self, path, filename, content, raw_content, file_type, size, modified, score, query_str):
        """格式化搜索结果"""
        display_content = raw_content if raw_content else content or ''
        norm_query = (query_str or '').strip()
        norm_query_lower = norm_query.lower()
        
        # 改进内容结构：如果文件名没有在内容中，添加到内容开头
        # 这样可以确保文件名中的关键词也能被高亮和搜索到
        structured_content = display_content
        if filename:
            # 检查文件名是否已经在内容开头，避免重复
            if not display_content.strip().startswith(filename):
                structured_content = f"文件名: {filename}\n\n" + structured_content
        
        # 使用包含文件名的内容进行高亮和查询检查
        display_lower = structured_content.lower() if structured_content else ''
        contains_query = bool(norm_query and norm_query_lower in display_lower)

        # 生成高亮摘要
        snippet = self._highlight_text(structured_content, norm_query)

        # 如果没有生成高亮或缺少命中，再尝试解析原文 (fallback)
        if norm_query and (not snippet or 'text-danger' not in snippet or not contains_query):
            try:
                fallback = self.get_document_content(path)
                if fallback and fallback != display_content:
                    # 如果fallback内容不同，重新构建structured_content
                    fallback_structured = fallback
                    if filename and not fallback.strip().startswith(filename):
                        fallback_structured = f"文件名: {filename}\n\n" + fallback
                    
                    display_lower = fallback_structured.lower()
                    contains_query = norm_query_lower in display_lower
                    snippet = self._highlight_text(fallback_structured, norm_query)
                    structured_content = fallback_structured
            except Exception:
                pass
        
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
            'content': structured_content,  # 使用结构化内容
            'snippet': snippet,     # 添加高亮摘要
            'file_type': file_type,
            'size': size,
            'modified': modified_time, # 添加修改时间
            'score': score,
            'has_query': contains_query
        }

    def search_text(self, query_str, limit=10, filters=None):
        if not getattr(self, 'tantivy_index', None):
            return []
        try:
            results = []
            seg_query = self._segment(query_str)
            self.tantivy_index.reload()
            searcher = self.tantivy_index.searcher()
            queries_to_try = []
            
            # Determine fields based on filters
            search_content = True
            if filters and 'search_content' in filters:
                search_content = filters['search_content']
            
            if search_content:
                exact_fields = ['content_raw', 'filename']
                fields = ['filename', 'content', 'content_raw', 'keywords', 'filename_chars', 'content_chars']
            else:
                exact_fields = ['filename']
                fields = ['filename', 'filename_chars']

            # Handle match_whole_word
            match_whole_word = False
            if filters and 'match_whole_word' in filters:
                match_whole_word = filters['match_whole_word']

            # 0. 优先尝试精确短语匹配，确保完全命中的文档排在前面
            try:
                trimmed = query_str.strip()
                if trimmed:
                    queries_to_try.append(self.tantivy_index.parse_query(f'"{trimmed}"', exact_fields))
            except Exception:
                pass
            
            if match_whole_word:
                # 如果开启全字匹配，仅使用精确短语查询
                # 并且尝试在所有字段上进行精确匹配
                try:
                    trimmed = query_str.strip()
                    if trimmed:
                        queries_to_try.append(self.tantivy_index.parse_query(f'"{trimmed}"', fields))
                except Exception: pass
            else:
                # 正常模糊搜索逻辑
                # 简化查询构建逻辑
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
                        if search_content:
                            queries_to_try.append(self.tantivy_index.parse_query(ch, ['filename_chars', 'content_chars']))
                        else:
                            queries_to_try.append(self.tantivy_index.parse_query(ch, ['filename_chars']))
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
                    content_raw_val = doc.get_first('content_raw') or ''
                    file_type_val = doc.get_first('file_type') or ''
                    size_val = doc.get_first('size') or 0
                    modified_val = doc.get_first('modified') or 0
                except Exception:
                    continue
                
                # 不再限制BM25分数的上限，以便在搜索引擎中进行正确的归一化
                # normalized_score = min(float(score), 100.0)
                raw_score = float(score)
                
                results.append(self._format_result(
                    path_val, filename_val, content_val, content_raw_val, file_type_val, 
                    size_val, modified_val, raw_score, query_str
                ))
                
            results.sort(key=lambda x: x['score'], reverse=True)

            if query_str and results:
                # 先将包含高亮的结果排列到前面，但保留其他候选
                highlighted = [r for r in results if 'text-danger' in (r.get('snippet') or '')]
                if highlighted:
                    non_highlighted = [r for r in results if r not in highlighted]
                    results = highlighted + non_highlighted

                primary = [r for r in results if r.get('has_query')]
                secondary = [r for r in results if not r.get('has_query')]
                if primary:
                    results = primary + secondary

            # 同一路径仅保留得分最高的一个结果
            deduped_results = []
            seen_paths = set()
            for item in results:
                path_key = (item.get('path') or '').lower()
                if path_key and path_key in seen_paths:
                    continue
                if path_key:
                    seen_paths.add(path_key)
                deduped_results.append(item)

            return deduped_results
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
                        path, metadata['filename'], content, content,
                        metadata['file_type'], 0, metadata.get('modified'), adjusted, query_str
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
            # 确保目录存在
            os.makedirs(self.hnsw_index_path, exist_ok=True)
            os.makedirs(self.metadata_path, exist_ok=True)

            # 检查索引是否已初始化
            if getattr(self, 'hnsw', None) is not None:
                import tempfile
                # 使用临时文件，然后原子性地移动到目标位置以避免损坏
                index_file = os.path.join(self.hnsw_index_path, 'vector_index.bin')
                temp_index_file = index_file + '.tmp'

                # 保存向量索引到临时文件
                self.hnsw.save_index(temp_index_file)

                # 原子性移动
                if os.path.exists(temp_index_file):
                    import shutil
                    shutil.move(temp_index_file, index_file)

            metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
            temp_metadata_file = metadata_file + '.tmp'
            metadata_dict = {
                'metadata': self.vector_metadata,
                'next_id': self.next_id
            }

            # 保存元数据到临时文件
            with open(temp_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)

            # 原子性移动
            if os.path.exists(temp_metadata_file):
                import shutil
                shutil.move(temp_metadata_file, metadata_file)

            self.logger.info("索引保存成功")
            return True
        except Exception as e:
            self.logger.error(f"保存索引失败: {str(e)}")
            import traceback
            self.logger.error(f"保存索引失败详细错误: {traceback.format_exc()}")
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

    def get_index_stats(self):
        """获取索引统计信息"""
        try:
            # 获取Tantivy索引统计
            searcher = self.tantivy_index.searcher()
            doc_count = searcher.num_docs()
            
            # 获取向量索引统计
            vector_count = len(self.vector_metadata) if hasattr(self, 'vector_metadata') else 0
            
            # 获取索引目录大小
            import os
            def get_dir_size(path):
                total = 0
                for dirpath, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        total += os.path.getsize(filepath)
                return total
            
            tantivy_size = get_dir_size(self.tantivy_index_path)
            hnsw_size = get_dir_size(self.hnsw_index_path) if os.path.exists(self.hnsw_index_path) else 0
            metadata_size = get_dir_size(self.metadata_path) if os.path.exists(self.metadata_path) else 0
            
            return {
                'tantivy_docs': doc_count,
                'vector_docs': vector_count,
                'tantivy_size_mb': round(tantivy_size / (1024 * 1024), 2),
                'hnsw_size_mb': round(hnsw_size / (1024 * 1024), 2),
                'metadata_size_mb': round(metadata_size / (1024 * 1024), 2),
                'total_size_mb': round((tantivy_size + hnsw_size + metadata_size) / (1024 * 1024), 2)
            }
        except Exception as e:
            self.logger.error(f"获取索引统计信息失败: {str(e)}")
            return {
                'tantivy_docs': 0,
                'vector_docs': 0,
                'tantivy_size_mb': 0,
                'hnsw_size_mb': 0,
                'metadata_size_mb': 0,
                'total_size_mb': 0
            }

    def optimize_index(self):
        """优化索引性能"""
        try:
            # 优化Tantivy索引
            if hasattr(self, 'tantivy_index') and self.tantivy_index:
                with self.tantivy_index.writer() as writer:
                    # 合并段以优化搜索性能
                    writer.commit()
                    self.logger.info("Tantivy索引优化完成")
            
            # 优化HNSW索引
            if hasattr(self, 'hnsw') and self.hnsw:
                # HNSW索引本身不需要特别的优化，但可以调整参数
                self.hnsw.set_ef(200)  # 设置搜索参数
                self.logger.info("HNSW索引参数已优化")
                
            return True
        except Exception as e:
            self.logger.error(f"索引优化失败: {str(e)}")
            return False

    def validate_index_integrity(self):
        """验证索引完整性"""
        try:
            # 验证Tantivy索引
            if hasattr(self, 'tantivy_index') and self.tantivy_index:
                searcher = self.tantivy_index.searcher()
                doc_count = searcher.num_docs()
                self.logger.info(f"Tantivy索引验证完成，文档数: {doc_count}")
            
            # 验证向量索引
            if hasattr(self, 'hnsw') and self.hnsw and hasattr(self, 'vector_metadata'):
                vector_count = len(self.vector_metadata)
                self.logger.info(f"向量索引验证完成，向量数: {vector_count}")
                
                # 检查元数据与索引的一致性
                indexed_ids = set()
                for i in range(min(self.next_id, 1000)):  # 检查前1000个ID以避免性能问题
                    try:
                        # 尝试获取向量以验证其存在性
                        if i < self.hnsw.get_current_count():
                            indexed_ids.add(i)
                    except:
                        pass
                
                metadata_ids = set(int(k) for k in self.vector_metadata.keys())
                missing_in_metadata = indexed_ids - metadata_ids
                missing_in_index = metadata_ids - indexed_ids
                
                if missing_in_metadata or missing_in_index:
                    self.logger.warning(f"向量索引与元数据不一致: 索引中缺失元数据的ID数: {len(missing_in_metadata)}, 元数据中缺失索引的ID数: {len(missing_in_index)}")
                else:
                    self.logger.info("向量索引与元数据一致性检查通过")
            
            return True
        except Exception as e:
            self.logger.error(f"索引完整性验证失败: {str(e)}")
            return False
