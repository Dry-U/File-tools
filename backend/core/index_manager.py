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
from whoosh.analysis import StemmingAnalyzer, Tokenizer, Token
import jieba
import faiss
import numpy as np
# 延迟导入SentenceTransformer，避免在禁用时卡住
# from sentence_transformers import SentenceTransformer
from datetime import datetime
import json

class ChineseTokenizer(Tokenizer):
    """中文分词器 - 优化版本"""
    def __init__(self):
        # 初始化jieba分词器，添加自定义词典以提高分词准确性
        try:
            # 加载自定义词典（如果存在）
            custom_dict_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'custom_dict.txt')
            if os.path.exists(custom_dict_path):
                jieba.load_userdict(custom_dict_path)
                logging.getLogger(__name__).info(f"加载自定义词典: {custom_dict_path}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"加载自定义词典失败: {str(e)}")
    
    def __call__(self, value, positions=False, chars=False, keeporiginal=False, 
                 removestops=True, start_pos=0, start_char=0, mode='', **kwargs):
        # 使用jieba进行中文分词，启用搜索引擎模式以提高分词准确性
        tokens = jieba.lcut_for_search(value)  # 搜索引擎模式，更细粒度分词
        
        # 过滤空白字符和单字符（除非是重要词汇）
        filtered_tokens = []
        for t in tokens:
            if t.strip() and (len(t.strip()) > 1 or self._is_important_char(t.strip())):
                filtered_tokens.append(t.strip())
        
        # 生成token对象
        pos = start_pos
        for t in filtered_tokens:
            token = Token()
            token.__dict__.update({'text': t, 'pos': pos})
            yield token
            pos += 1
    
    def _is_important_char(self, char):
        """判断单个字符是否重要（不应被过滤）"""
        # 常见重要的单个字符
        important_chars = {'一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
                          '个', '种', '类', '型', '式', '法', '术', '学', '工', '程'}
        return char in important_chars


class ChineseAnalyzer:
    """中文分析器 - 优化版本"""
    def __init__(self):
        self.tokenizer = ChineseTokenizer()
    
    def __call__(self, *args, **kwargs):
        return self.tokenizer


class IndexManager:
    """索引管理器类，负责创建、更新和查询索引"""
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)
        
        # 获取索引路径配置 - 使用ConfigLoader
        try:
            # 优先从system配置读取，如果没有则使用index配置
            data_dir = config_loader.get('system', 'data_dir', './data')
            self.whoosh_index_path = config_loader.get('index', 'whoosh_path', f'{data_dir}/whoosh_index')
            self.faiss_index_path = config_loader.get('index', 'faiss_path', f'{data_dir}/faiss_index')
            self.metadata_path = config_loader.get('index', 'metadata_path', f'{data_dir}/metadata')
        except Exception as e:
            self.logger.error(f"获取索引路径配置失败: {str(e)}")
            # 使用默认值
            self.whoosh_index_path = './data/whoosh_index'
            self.faiss_index_path = './data/faiss_index'
            self.metadata_path = './data/metadata'
        
        # 创建索引目录
        os.makedirs(self.whoosh_index_path, exist_ok=True)
        os.makedirs(self.faiss_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)
        
        # 初始化嵌入模型
        model_enabled = config_loader.get('embedding', 'enabled', False)
        if model_enabled:
            try:
                # 延迟导入SentenceTransformer
                from sentence_transformers import SentenceTransformer
                # 从配置获取嵌入模型名称
                embedding_model_name = config_loader.get('embedding', 'model_name', 'all-MiniLM-L6-v2')
                
                # 尝试加载嵌入模型 with local files only to avoid download
                try:
                    self.embedding_model = SentenceTransformer(embedding_model_name, local_files_only=True)
                    self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
                    self.logger.info(f"成功加载本地嵌入模型: {embedding_model_name}, 向量维度: {self.vector_dim}")
                except Exception as local_error:
                    # 如果本地加载失败，尝试在线下载
                    self.logger.warning(f"本地加载嵌入模型失败: {str(local_error)}, 尝试在线加载...")
                    try:
                        self.embedding_model = SentenceTransformer(embedding_model_name)
                        self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
                        self.logger.info(f"成功加载嵌入模型: {embedding_model_name}, 向量维度: {self.vector_dim}")
                    except Exception as online_error:
                        self.logger.warning(f"在线加载嵌入模型也失败: {str(online_error)}")
                        self.embedding_model = None
                        self.vector_dim = 384  # MiniLM-L6-v2的默认维度
                        self.logger.info("嵌入模型已禁用，仅支持文本索引和搜索")
            except Exception as e:
                self.logger.warning(f"加载嵌入模型失败: {str(e)}")
                self.embedding_model = None
                self.vector_dim = 384  # MiniLM-L6-v2的默认维度
                self.logger.info("嵌入模型已禁用，仅支持文本索引和搜索")
        else:
            self.embedding_model = None
            self.vector_dim = 384
            self.logger.info("嵌入模型未启用（配置中禁用），仅支持文本索引和搜索")
        
        # 初始化Whoosh索引
        self._init_whoosh_index()
        
        # 初始化FAISS索引
        self._init_faiss_index()
        
        # 索引状态
        self.index_ready = self.is_index_ready()
        
    def _init_whoosh_index(self):
        """初始化Whoosh索引"""
        # 定义索引模式
        # 对于中文文本，使用自定义的中文分析器
        chinese_analyzer = ChineseAnalyzer()
        self.schema = Schema(
            path=ID(stored=True, unique=True),  # 文件路径作为唯一标识符
            filename=TEXT(stored=True, analyzer=chinese_analyzer),  # 文件名
            content=TEXT(stored=True, analyzer=chinese_analyzer),  # 文件内容
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
                    metadata_dict = json.load(f)
                    self.vector_metadata = metadata_dict.get('metadata', {})
                    self.next_id = metadata_dict.get('next_id', len(self.vector_metadata))
                self.logger.info(f"成功加载FAISS索引: {index_file}, 向量数量: {self.faiss_index.ntotal}")
            except Exception as e:
                self.logger.error(f"加载FAISS索引失败: {str(e)}")
                self._create_new_faiss_index()
        else:
            self._create_new_faiss_index()
    
    def _create_new_faiss_index(self):
        """创建新的FAISS索引"""
        try:
            # 创建一个带ID映射的FAISS索引，支持reconstruct操作
            base_index = faiss.IndexFlatL2(self.vector_dim)  # 使用L2距离
            self.faiss_index = faiss.IndexIDMap(base_index)  # 包装为IDMap支持ID管理
            self.vector_metadata = {}
            self.next_id = 0  # 用于追踪下一个可用的ID
            self.logger.info(f"成功创建新的FAISS索引，向量维度: {self.vector_dim}")
        except Exception as e:
            self.logger.error(f"创建FAISS索引失败: {str(e)}")
            self.faiss_index = None
            self.vector_metadata = {}
            self.next_id = 0
    
    def add_document(self, document):
        """添加文档到索引"""
        if not self.whoosh_index:
            self.logger.error("Whoosh索引未初始化完成，无法添加文档")
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
            
            # 如果嵌入模型可用，生成向量嵌入
            if self.embedding_model:
                vector = self.embedding_model.encode(document['content'][:5000])  # 限制内容长度以提高效率
                vector = np.array([vector], dtype=np.float32)
                
                # 使用递增的ID
                doc_id = self.next_id
                
                # 添加到FAISS索引，使用ID映射
                # add_with_ids(xb, xids) - xb是向量矩阵，xids是ID数组
                ids = np.array([doc_id], dtype=np.int64)
                self.faiss_index.add_with_ids(vector, ids)  # type: ignore
                
                # 保存元数据
                self.vector_metadata[str(doc_id)] = {
                    'path': document['path'],
                    'filename': document['filename'],
                    'file_type': document['file_type'],
                    'modified': document['modified'].strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # 递增ID计数器
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
        
        # 对于Whoosh，update_document方法已经支持更新
        # 对于FAISS，我们需要先删除旧向量，再添加新向量
        
        # 首先尝试查找并删除旧向量
        old_doc_id = None
        for doc_id, metadata in self.vector_metadata.items():
            if metadata.get('path') == document.get('path'):
                old_doc_id = int(doc_id)
                break
        
        if old_doc_id is not None and self.embedding_model and self.faiss_index:
            # 使用IDMap的remove_ids方法删除指定ID的向量
            try:
                ids_to_remove = np.array([old_doc_id], dtype=np.int64)
                self.faiss_index.remove_ids(ids_to_remove)  # type: ignore
                # 删除元数据
                if str(old_doc_id) in self.vector_metadata:
                    del self.vector_metadata[str(old_doc_id)]
            except Exception as e:
                self.logger.error(f"删除旧向量失败: {str(e)}")
        
        # 添加更新后的文档
        return self.add_document(document)
    
    def delete_document(self, file_path):
        """从索引中删除文档"""
        if not self.whoosh_index:
            self.logger.error("Whoosh索引未初始化完成，无法删除文档")
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
            
            if old_doc_id is not None and self.faiss_index:
                # 使用IDMap的remove_ids方法删除指定ID的向量
                try:
                    ids_to_remove = np.array([old_doc_id], dtype=np.int64)
                    self.faiss_index.remove_ids(ids_to_remove)  # type: ignore
                    # 删除元数据
                    if str(old_doc_id) in self.vector_metadata:
                        del self.vector_metadata[str(old_doc_id)]
                except Exception as e:
                    self.logger.error(f"删除向量失败 (ID: {old_doc_id}): {str(e)}")
            
            return True
        except Exception as e:
            self.logger.error(f"从索引中删除文档失败 {file_path}: {str(e)}")
            return False
    
    def search_text(self, query_str, limit=10):
        """在文本索引中搜索 - 优化版本"""
        if not self.whoosh_index:
            self.logger.error("Whoosh索引未初始化完成，无法搜索")
            return []
        
        try:
            results = []
            
            # 获取搜索配置
            search_config = self.config_loader.get('search') or {}
            filename_boost = float(search_config.get('filename_boost', 1.5))
            keyword_boost = float(search_config.get('keyword_boost', 1.2))
            bm25_k1 = float(search_config.get('bm25_k1', 1.5))
            bm25_b = float(search_config.get('bm25_b', 0.75))
            
            with self.whoosh_index.searcher() as searcher:
                # 使用多字段查询解析器，为不同字段设置不同的权重
                parser = MultifieldParser(
                    ['filename', 'content', 'keywords'], 
                    schema=self.schema,
                    fieldboosts={'filename': filename_boost, 'keywords': keyword_boost, 'content': 1.0}
                )
                
                # 优化查询：使用Or查询而非默认的And查询，增加匹配概率
                query = parser.parse(query_str)
                
                # 使用TermBoost提高搜索精度
                # 设置相似度计算模型，使用配置中的参数
                from whoosh import scoring
                searcher.weighting = scoring.BM25F(B=bm25_b, K1=bm25_k1, content_B=bm25_b)
                
                # 执行搜索，增加limit获取更多候选结果
                hits = searcher.search(query, limit=limit*2)
                
                # 计算内容匹配度（关键词出现频率）
                query_terms = query_str.lower().split()
                
                # 处理搜索结果
                for hit in hits:
                    # 获取文档内容
                    content = hit['content'].lower()
                    
                    # 计算关键词覆盖率
                    coverage = 0
                    for term in query_terms:
                        if term in content:
                            # 计算词频
                            term_count = content.count(term)
                            # 考虑文档长度
                            coverage += term_count / max(1, len(content.split()))
                    
                    # 调整分数：结合BM25分数和关键词覆盖率
                    adjusted_score = hit.score + (coverage * 0.2)
                    
                    # 对中文进行额外的相似度计算
                    if any('\u4e00' <= char <= '\u9fff' for char in query_str):
                        # 对中文查询使用Jaccard相似度补充
                        content_chars = set(content)
                        query_chars = set(query_str.lower())
                        jaccard_sim = len(content_chars & query_chars) / max(1, len(content_chars | query_chars))
                        adjusted_score += jaccard_sim * 0.3
                    
                    results.append({
                        'path': hit['path'],
                        'filename': hit['filename'],
                        'content': hit['content'][:200] + ('...' if len(hit['content']) > 200 else ''),
                        'file_type': hit['file_type'],
                        'score': adjusted_score  # 使用调整后的分数
                    })
                
                # 按分数重新排序
                results.sort(key=lambda x: x['score'], reverse=True)
            
            return results[:limit]
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []
    
    def search_vector(self, query_str, limit=10):
        """在向量索引中搜索 - 优化版本"""
        if not self.faiss_index:
            self.logger.error("FAISS索引未初始化完成，无法进行向量搜索")
            return []
        
        if not self.embedding_model:
            # 嵌入模型被禁用，返回空结果而不是示例结果
            # 这样可以避免混淆用户
            self.logger.warning("嵌入模型已禁用，跳过向量搜索")
            return []
        
        try:
            # 生成查询向量
            query_vector = self.embedding_model.encode([query_str])
            query_vector = np.array(query_vector, dtype=np.float32)
            
            # 执行向量搜索 - search(x, k) 返回 (distances, labels)
            # 获取更多候选结果以提高质量
            k = min(limit*2, self.faiss_index.ntotal) if self.faiss_index.ntotal > 0 else limit*2
            distances, indices = self.faiss_index.search(query_vector, k)  # type: ignore
            
            # 处理搜索结果
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and str(idx) in self.vector_metadata:
                    metadata = self.vector_metadata[str(idx)]
                    
                    # 计算相似度分数 - 使用更平滑的转换函数
                    # 使用指数衰减函数而非简单倒数，提高区分度
                    similarity = np.exp(-distances[0][i] / 2.0)
                    
                    # 对中文查询进行额外的字符匹配加分
                    adjusted_similarity = similarity
                    if any('\u4e00' <= char <= '\u9fff' for char in query_str):
                        # 获取文档内容进行字符匹配
                        try:
                            # 尝试从Whoosh索引获取文档内容
                            with self.whoosh_index.searcher() as searcher:
                                doc = searcher.document(path=metadata['path'])
                                if doc and 'content' in doc:
                                    content = doc['content'].lower()
                                    query_chars = set(query_str.lower())
                                    content_chars = set(content)
                                    
                                    # 计算Jaccard相似度
                                    jaccard_sim = len(content_chars & query_chars) / max(1, len(content_chars | query_chars))
                                    # 为字符匹配添加额外分数，但权重不超过总分数的30%
                                    adjusted_similarity = similarity + (jaccard_sim * similarity * 0.3)
                        except Exception as e:
                            # 如果获取内容失败，使用原始相似度
                            self.logger.debug(f"获取文档内容失败: {str(e)}")
                    
                    results.append({
                        'path': metadata['path'],
                        'filename': metadata['filename'],
                        'file_type': metadata['file_type'],
                        'score': adjusted_similarity  # 使用调整后的相似度分数
                    })
            
            # 按分数排序
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:limit]
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []
    
    def save_indexes(self):
        """保存索引到磁盘"""
        if not self.whoosh_index:
            self.logger.error("Whoosh索引未初始化，无法保存")
            return False
        
        try:
            # Whoosh索引会自动保存
            # 注意：FileIndex没有is_modified()方法，索引在writer退出时自动提交
            
            # 保存FAISS索引
            if self.faiss_index:
                index_file = os.path.join(self.faiss_index_path, 'vector_index.faiss')
                faiss.write_index(self.faiss_index, index_file)
            
            # 保存向量元数据（包含next_id）
            metadata_file = os.path.join(self.metadata_path, 'vector_metadata.json')
            metadata_dict = {
                'metadata': self.vector_metadata,
                'next_id': self.next_id
            }
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)
            
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
        """检查索引是否就绪(文本索引必须就绪,向量索引可选)"""
        return self.whoosh_index is not None and self.faiss_index is not None
    
    def close(self):
        """关闭索引管理器，释放资源"""
        try:
            # Whoosh索引在writer退出时自动提交，无需显式调用commit
            if self.whoosh_index:
                self.logger.info("Whoosh索引将在关闭时自动保存")
            
            # FAISS索引不需要显式关闭
            # 释放嵌入模型资源
            if self.embedding_model:
                self.embedding_model = None
                self.logger.info("嵌入模型资源已释放")
            
            # 清空索引引用
            self.whoosh_index = None
            self.faiss_index = None
            self.logger.info("索引管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭索引管理器时出错: {str(e)}")