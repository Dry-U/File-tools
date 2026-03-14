#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""搜索引擎模块 - 集成文本搜索和向量搜索功能"""
import os
import re
import time
import json
import hashlib
import fnmatch
import logging
import traceback
from datetime import datetime
from collections import OrderedDict
from typing import List, Dict, Any, Optional
import numpy as np
from threading import RLock

from backend.core.constants import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_TEXT_WEIGHT,
    DEFAULT_VECTOR_WEIGHT,
    DEFAULT_CACHE_TTL,
    DEFAULT_CACHE_SIZE,
    DEFAULT_RERANK_BASE_WEIGHT,
    DEFAULT_RERANK_FILENAME_WEIGHT,
    DEFAULT_RERANK_KEYWORD_WEIGHT,
    DEFAULT_RERANK_RECENCY_WEIGHT,
    DEFAULT_RERANK_LENGTH_WEIGHT,
    FILENAME_VARIANT_KEYWORDS,
    KEYWORD_SCORE_MAX,
    LENGTH_PENALTY_THRESHOLD_HIGH,
    LENGTH_PENALTY_THRESHOLD_LOW,
)
from backend.core.sharded_cache import ShardedCache
from backend.core.query_processor import QueryProcessor

class SearchEngine:
    """搜索引擎类，负责执行文件搜索和结果排序"""
    def __init__(
        self,
        index_manager: Any,
        config_loader: Any
    ) -> None:
        self.index_manager: Any = index_manager
        self.config_loader: Any = config_loader
        self.logger: logging.Logger = logging.getLogger(__name__)

        # 搜索配置 - 使用ConfigLoader获取配置（只读取一次）
        search_config: Dict[str, Any] = config_loader.get('search') or {}

        # 辅助函数：从配置中安全获取数值
        def get_config_float(key: str, default: float) -> float:
            return float(search_config.get(key, default))

        def get_config_int(key: str, default: int) -> int:
            return int(search_config.get(key, default))

        def get_config_bool(key: str, default: bool) -> bool:
            val = search_config.get(key, default)
            if isinstance(val, bool):
                return val
            return str(val).lower() in ('true', '1', 'yes', 'on')

        self.text_weight: float = get_config_float('text_weight', 0.6)
        self.vector_weight: float = get_config_float('vector_weight', 0.4)
        self.max_results: int = get_config_int('max_results', 50)

        # 新增的高级搜索配置参数
        self.bm25_k1 = get_config_float('bm25_k1', 1.5)
        self.bm25_b = get_config_float('bm25_b', 0.75)
        self.result_boost = get_config_bool('result_boost', True)
        self.filename_boost = get_config_float('filename_boost', 1.5)
        self.keyword_boost = get_config_float('keyword_boost', 1.2)
        self.hybrid_boost = get_config_float('hybrid_boost', 1.1)
        # 语义搜索结果阈值（从配置读取）
        self.semantic_score_high_threshold = get_config_float('semantic_score_high_threshold', 60.0)
        self.semantic_score_low_threshold = get_config_float('semantic_score_low_threshold', 30.0)

        # 重排权重配置（从配置读取，使用常量作为默认值）
        self.rerank_weights = {
            'base': get_config_float('rerank_base_weight', DEFAULT_RERANK_BASE_WEIGHT),
            'filename': get_config_float('rerank_filename_weight', DEFAULT_RERANK_FILENAME_WEIGHT),
            'keyword': get_config_float('rerank_keyword_weight', DEFAULT_RERANK_KEYWORD_WEIGHT),
            'recency': get_config_float('rerank_recency_weight', DEFAULT_RERANK_RECENCY_WEIGHT),
            'length': get_config_float('rerank_length_weight', DEFAULT_RERANK_LENGTH_WEIGHT),
        }

        # 缓存配置
        self.enable_cache = bool(search_config.get('enable_cache', True))
        self.cache_ttl = int(search_config.get('cache_ttl', DEFAULT_CACHE_TTL))
        self.cache_size = int(search_config.get('cache_size', DEFAULT_CACHE_SIZE))

        # 确保权重之和为1，但如果其中一个为0，则另一个为1
        if self.text_weight == 0 and self.vector_weight == 0:
            # 默认情况下，两个都为0.5
            self.text_weight = 0.5
            self.vector_weight = 0.5
        elif self.text_weight == 0:
            # 只使用向量搜索
            self.vector_weight = 1.0
        elif self.vector_weight == 0:
            # 只使用文本搜索
            self.text_weight = 1.0
        else:
            # 确保权重之和为1
            total_weight = self.text_weight + self.vector_weight
            self.text_weight /= total_weight
            self.vector_weight /= total_weight

        # 初始化缓存（使用分片缓存提高并发性能）
        if self.enable_cache:
            self.cache = ShardedCache(max_size=self.cache_size)
            self.cache.set_ttl(self.cache_ttl)
            self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}, 分片缓存已启用")
        else:
            self.cache = None
            self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}, 缓存已禁用")

    def _get_cache_key(self, query, filters=None) -> str:
        """生成缓存键"""
        if filters is None:
            filters = {}
        try:
            normalized_filters = {}
            for k, v in sorted(filters.items()):
                if isinstance(v, (list, tuple)):
                    normalized_filters[k] = tuple(sorted(str(x) for x in v))
                elif isinstance(v, dict):
                    normalized_filters[k] = json.dumps(v, sort_keys=True, ensure_ascii=True)
                else:
                    normalized_filters[k] = str(v)
            cache_str = f"{query}:{json.dumps(normalized_filters, sort_keys=True, ensure_ascii=True)}"
        except (TypeError, ValueError):
            cache_str = f"{query}:{str(sorted(filters.items()))}"
        return hashlib.md5(cache_str.encode(), usedforsecurity=False).hexdigest()


    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取结果"""
        if not self.enable_cache or self.cache is None:
            return None
        return self.cache.get(key)

    def _put_in_cache(self, key: str, result: Any) -> None:
        """将结果放入缓存"""
        if not self.enable_cache or self.cache is None:
            return
        self.cache.put(key, result)
    
    def search(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行搜索，整合文本搜索和向量搜索结果"""
        start_time = time.time()
        self.logger.info(f"执行搜索: {query}, 过滤器: {filters}")

        # 使用QueryProcessor扩展查询
        try:
            expanded_queries = QueryProcessor(self.config_loader).process(query)
            self.logger.info(f"查询扩展: {expanded_queries}")
        except Exception as e:
            self.logger.warning(f"查询扩展失败: {e}")
            expanded_queries = [query]

        # 检查缓存
        cache_key = self._get_cache_key(query, filters)
        if self.enable_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                cache_hit_time = time.time() - start_time
                self.logger.info(f"缓存命中，返回缓存结果，耗时: {cache_hit_time:.3f}秒")
                return cached_result

        # 保存当前查询以供后续使用
        self.current_query = query

        # 如果没有提供过滤器，使用默认空字典
        if filters is None:
            filters = {}
        else:
            filters = filters.copy()

        file_type_filter = self._detect_file_type_filter(query)
        if file_type_filter:
            filters['file_types'] = file_type_filter

        # 保持查询与类型筛选相互独立：不再基于查询自动推断文件类型过滤

        # 执行多路召回：原始查询 + 扩展查询
        all_text_results = []
        all_vector_results = []
        seen_paths = set()

        # 对每个扩展查询执行搜索
        for search_query in expanded_queries[:3]:  # 限制最多3个查询以避免性能问题
            # 执行文本搜索
            text_results = self._search_text(search_query, filters)
            for result in text_results:
                path = result.get('path', '')
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    result['search_query'] = search_query  # 记录匹配的查询
                    all_text_results.append(result)

            # 执行向量搜索
            vector_results = self._search_vector(search_query, filters)
            for result in vector_results:
                path = result.get('path', '')
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    result['search_query'] = search_query
                    all_vector_results.append(result)

        self.logger.info(f"多路召回: 文本搜索 {len(all_text_results)} 条, 向量搜索 {len(all_vector_results)} 条")

        # 合并和排序结果
        combined_results = self._combine_results(all_text_results, all_vector_results)
        self.logger.info(f"合并后 {len(combined_results)} 条结果")

        # 重排序优化
        combined_results = self._rerank_results(query, combined_results)
        self.logger.info(f"重排序后 {len(combined_results)} 条结果")

        # 应用过滤器
        filtered_results = self._apply_filters(combined_results, filters)
        self.logger.info(f"过滤后 {len(filtered_results)} 条结果")

        # 优先返回真正包含查询词的结果，剩余语义匹配结果追加在后
        limited_results = filtered_results
        if query and filtered_results:
            primary_hits = []
            semantic_hits = []
            for item in filtered_results:
                snippet = item.get('snippet') or ''
                has_highlight = 'text-danger' in snippet
                if has_highlight or item.get('has_query'):
                    primary_hits.append(item)
                else:
                    # 标记语义结果，避免用户误以为缺少高亮是 bug
                    if snippet:
                        item['snippet'] = f'（未直接匹配搜索词，展示语义相关内容）<br>{snippet}'
                    else:
                        item['snippet'] = '（未直接匹配搜索词，展示语义相关内容）'
                    semantic_hits.append(item)

            if primary_hits:
                # 如果找到了精确匹配的结果，则对语义匹配结果进行严格过滤
                # 仅保留分数较高的语义结果（使用配置的高质量阈值），过滤掉低相关性的噪音
                # 这样既保留了高质量的语义补充，又避免了不相关的文档干扰用户
                high_quality_semantic = [item for item in semantic_hits if item['score'] > self.semantic_score_high_threshold]
                limited_results = primary_hits + high_quality_semantic
            else:
                # 如果没有精确匹配，则展示语义匹配结果，但也可以设置一个最低门槛（使用配置的低阈值）
                limited_results = [item for item in semantic_hits if item['score'] > self.semantic_score_low_threshold]

        # 限制结果数量
        limited_results = limited_results[:self.max_results]

        search_time = time.time() - start_time
        self.logger.info(f"搜索完成，找到 {len(limited_results)} 条结果，耗时: {search_time:.3f}秒")

        # 将结果存入缓存
        if self.enable_cache:
            self._put_in_cache(cache_key, limited_results)

        return limited_results

    def _detect_file_type_filter(self, query: str):
        q = (query or '').strip().lower()
        if not q:
            return None
        mapping = {
            '.pdf': {'pdf', 'pdf文件', '找pdf', '搜索pdf', 'pdf资料', '全部pdf'},
            '.doc': {'doc', 'doc文件', 'word文档'},
            '.docx': {'docx', 'docx文件'},
            '.ppt': {'ppt', 'ppt文件'},
            '.pptx': {'pptx', 'pptx文件'},
            '.xls': {'xls', 'excel', 'excel表', '表格'},
            '.xlsx': {'xlsx'},
        }
        for ext, keywords in mapping.items():
            if q in keywords:
                return [ext]
        return None
    
    def _search_text(self, query, filters=None):
        """执行文本搜索"""
        try:
            # 调用索引管理器的文本搜索功能，获取更多结果以确保过滤后有足够数量
            # 将过滤器传递给search_text，包括 case_sensitive 参数
            results = self.index_manager.search_text(query, limit=self.max_results * 3, filters=filters)
            self.logger.info(f"文本搜索返回 {len(results)} 条结果")

            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'text'

            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _search_vector(self, query, filters=None):
        """执行向量搜索"""
        try:
            # 调用索引管理器的向量搜索功能，获取更多结果以确保过滤后有足够数量
            results = self.index_manager.search_vector(query, limit=self.max_results * 3)
            self.logger.info(f"向量搜索返回 {len(results)} 条结果")

            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'vector'

            return results
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _merge_text_results(self, text_results: List[Dict]) -> tuple[Dict, float]:
        """
        合并文本搜索结果，去重并记录最大分数

        Returns:
            tuple: (合并后的结果字典, 最大文本分数)
        """
        combined = {}
        max_text_score = 0.0

        for result in text_results:
            path = result['path']
            if path not in combined:
                combined[path] = result.copy()
                if 'search_type' not in combined[path]:
                    combined[path]['search_type'] = 'text'
                combined[path]['text_score'] = result['score']
                combined[path]['vector_score'] = 0.0
                if result['score'] > max_text_score:
                    max_text_score = result['score']
            else:
                # 保留更高分的结果
                if result['score'] > combined[path]['score']:
                    prev_vector_score = combined[path]['vector_score']
                    combined[path] = result.copy()
                    combined[path]['search_type'] = result['search_type']
                    combined[path]['text_score'] = result['score']
                    combined[path]['vector_score'] = prev_vector_score
                else:
                    combined[path]['text_score'] = max(combined[path]['text_score'], result['score'])

                if result['score'] > max_text_score:
                    max_text_score = result['score']

        return combined, max_text_score

    def _merge_vector_results(self, vector_results: List[Dict], combined: Dict, max_text_score: float) -> Dict:
        """
        合并向量搜索结果，计算混合分数

        Args:
            vector_results: 向量搜索结果列表
            combined: 已合并的文本结果字典
            max_text_score: 最大文本分数，用于归一化

        Returns:
            更新后的合并结果字典
        """
        for result in vector_results:
            path = result['path']
            if path in combined:
                # 已存在，计算混合分数
                prev_text_score = combined[path]['text_score']
                combined[path]['vector_score'] = result['score']

                # 归一化并计算加权分数
                text_norm = min(prev_text_score / max_text_score, 1.0) if max_text_score > 0 else 0.0
                vector_norm = min(result['score'], 100.0) / 100.0

                combined_score = (text_norm * self.text_weight + vector_norm * self.vector_weight) * 100.0
                combined[path]['score'] = min(combined_score, 100.0)
                combined[path]['search_type'] = 'hybrid'
            else:
                # 新路径，直接添加
                combined[path] = result.copy()
                combined[path]['text_score'] = 0.0
                combined[path]['vector_score'] = result['score']
                if 'search_type' not in combined[path]:
                    combined[path]['search_type'] = 'vector'

        return combined

    def _calculate_normalized_scores(self, combined: Dict, max_text_score: float) -> None:
        """
        为纯文本和纯向量结果计算归一化分数

        Args:
            combined: 合并结果字典（就地修改）
            max_text_score: 最大文本分数
        """
        if max_text_score <= 0:
            max_text_score = 1.0

        for result in combined.values():
            if result.get('search_type') == 'hybrid':
                continue

            if result.get('search_type') == 'text':
                ts = float(result.get('text_score', 0.0))
                norm_score = ts / max_text_score
                result['score'] = (norm_score * self.text_weight) * 100.0
            elif result.get('search_type') == 'vector':
                vs = float(result.get('vector_score', 0.0))
                vector_norm = vs / 100.0
                result['score'] = (vector_norm * self.vector_weight) * 100.0

    def _apply_snippet_boost(self, result: Dict) -> None:
        """
        应用关键词命中增强（摘要高亮加分）
        """
        snippet = result.get('snippet', '')
        if 'text-danger' not in snippet:
            return

        # 高亮关键词加分
        result['score'] = min(result['score'] + 20.0, 100.0)

        # 纯文本匹配保底分数
        if result.get('search_type') == 'text':
            result['score'] = max(result['score'], 60.0)

    def _apply_hybrid_boost(self, result: Dict) -> None:
        """
        应用混合结果增强
        """
        if self.result_boost and result.get('search_type') == 'hybrid':
            result['score'] *= self.hybrid_boost

    def _apply_filename_boost(self, result: Dict) -> None:
        """
        应用文件名匹配增强
        """
        query_words = self._get_query_words()
        if not query_words:
            return

        filename = os.path.basename(result.get('path', '')).lower()
        query_match_count = 0

        # 完整查询匹配（最高优先级）
        if self.current_query and self.current_query.lower() in filename:
            result['score'] = max(result['score'], 95.0)
            return

        # 单词匹配
        for word in query_words:
            if word.lower() in filename:
                query_match_count += 1

        if query_match_count > 0:
            filename_bonus = query_match_count * 15.0
            result['score'] = min(result['score'] + filename_bonus, 100.0)

    def _apply_boosts(self, combined: Dict) -> None:
        """
        应用所有boost因子
        """
        for result in combined.values():
            self._apply_snippet_boost(result)
            self._apply_hybrid_boost(result)
            self._apply_filename_boost(result)

            # 确保分数在合理范围内
            result['score'] = min(max(result['score'], 0.0), 100.0)

    def _combine_results(self, text_results: List[Dict], vector_results: List[Dict]) -> List[Dict]:
        """
        合并文本搜索和向量搜索结果

        处理流程：
        1. 合并文本结果去重
        2. 合并向量结果，计算混合分数
        3. 计算归一化分数
        4. 应用各种boost因子
        5. 排序返回
        """
        # 步骤1: 合并文本结果
        combined, max_text_score = self._merge_text_results(text_results)

        # 步骤2: 合并向量结果
        combined = self._merge_vector_results(vector_results, combined, max_text_score)

        # 步骤3: 计算归一化分数
        self._calculate_normalized_scores(combined, max_text_score)

        # 步骤4: 应用boost因子
        self._apply_boosts(combined)

        # 步骤5: 排序并返回
        return sorted(combined.values(), key=lambda x: x['score'], reverse=True)
    
    def _apply_filters(self, results, filters):
        """应用过滤器"""
        if not filters:
            return results
        filtered = []
        
        for result in results:
            if self._match_filters(result, filters):
                filtered.append(result)
        
        return filtered
    
    def _match_filters(self, result, filters):
        """检查结果是否匹配所有过滤器条件"""
        # 文件类型过滤
        if 'file_types' in filters and filters['file_types']:
            file_ext = os.path.splitext(result['path'])[1].lower()  # 获取文件扩展名（包含点）
            normalized_types = [ft if ft.startswith('.') else f'.{ft}' for ft in filters['file_types']]
            if file_ext not in normalized_types:
                return False
        
        # 日期范围过滤
        if 'date_from' in filters or 'date_to' in filters:
            # 尝试获取文件的修改时间
            try:
                # 从结果中获取修改时间
                if 'modified' in result:
                    # 如果是字符串类型的时间，尝试解析
                    if isinstance(result['modified'], str):
                        file_modified = datetime.strptime(result['modified'], '%Y-%m-%d %H:%M:%S')
                    else:
                        file_modified = result['modified']
                else:
                    # 如果结果中没有，直接从文件系统获取
                    file_modified = datetime.fromtimestamp(os.path.getmtime(result['path']))
                
                # 应用日期范围过滤
                if 'date_from' in filters and filters['date_from']:
                    date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d')
                    if file_modified.date() < date_from.date():
                        return False
                
                if 'date_to' in filters and filters['date_to']:
                    date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d')
                    if file_modified.date() > date_to.date():
                        return False
            except Exception as e:
                self.logger.warning(f"日期过滤失败 {result['path']}: {str(e)}")
                # 如果无法获取或解析日期，默认不过滤
        
        # 文件大小过滤
        if 'size_min' in filters or 'size_max' in filters:
            try:
                # 获取文件大小
                file_size = os.path.getsize(result['path'])
                
                if 'size_min' in filters and filters['size_min'] is not None:
                    if file_size < filters['size_min']:
                        return False
                
                if 'size_max' in filters and filters['size_max'] is not None:
                    if file_size > filters['size_max']:
                        return False
            except Exception as e:
                self.logger.warning(f"大小过滤失败 {result['path']}: {str(e)}")
                # 如果无法获取文件大小，默认不过滤
        
        # 所有过滤条件都通过
        return True
    
    def search_by_path(self, path_pattern):
        """按路径搜索文件"""
        try:
            # 这是一个简化实现，实际可能需要更复杂的路径匹配逻辑
            # 在实际应用中，可能需要使用专门的路径索引或数据库
            results = []
            
            # 这里我们可以利用Whoosh的路径字段进行搜索
            # 但Whoosh的路径字段是ID类型，不支持通配符搜索
            # 所以我们可以先获取所有文档，然后在内存中进行过滤
            # 注意：这种方法对于大量文档可能效率不高
            
            # 为了简化，我们可以使用一个简单的文本搜索，并在结果中过滤
            query = path_pattern.replace('*', '').replace('?', '')  # 去除通配符，用于初始搜索
            initial_results = self.index_manager.search_text(query, limit=1000)
            
            # 在初始结果中过滤路径匹配的文件
            for result in initial_results:
                if self._match_path_pattern(result['path'], path_pattern):
                    results.append(result)
            
            # 按相关性排序
            results.sort(key=lambda x: x['score'], reverse=True)
            
            return results[:self.max_results]
        except Exception as e:
            self.logger.error(f"按路径搜索失败: {str(e)}")
            return []
    
    def _match_path_pattern(self, path, pattern):
        """简单的路径模式匹配"""
        # 使用 fnmatch 模块进行模式匹配
        return fnmatch.fnmatch(path.lower(), pattern.lower())
    
    def get_suggestions(self, query, limit=5):
        """获取搜索建议"""
        try:
            # 这是一个简化实现，实际可能需要更复杂的建议生成逻辑
            # 例如，可以基于搜索历史、热门搜索词或文档中的关键词
            
            # 为了简化，我们可以基于当前查询执行一个快速搜索，并返回匹配的文件名作为建议
            results = self.index_manager.search_text(query, limit=20)  # 获取更多结果以提取建议
            
            # 提取唯一的文件名作为建议
            suggestions = []
            seen = set()
            
            for result in results:
                if result['filename'] not in seen:
                    seen.add(result['filename'])
                    suggestions.append({
                        'text': result['filename'],
                        'type': 'filename',
                        'path': result['path']
                    })
                
                # 如果已经收集了足够的建议，就停止
                if len(suggestions) >= limit:
                    break
            
            return suggestions
        except Exception as e:
            self.logger.error(f"获取搜索建议失败: {str(e)}")
            return []
    
    def get_search_stats(self):
        """获取搜索统计信息"""
        # 这是一个简化实现，可以根据实际需求扩展
        stats = {
            'text_weight': self.text_weight,
            'vector_weight': self.vector_weight,
            'max_results': self.max_results
        }
        
        # 可以添加更多统计信息，例如：
        # - 平均搜索时间
        # - 平均返回结果数量
        # - 搜索类型分布等
        
        return stats
    
    def _get_query_words(self):
        """从当前的搜索查询中提取查询词"""
        if hasattr(self, 'current_query') and self.current_query:
            # 简单的分词处理，按空格和常见分隔符分割
            words = re.findall(r'\w+', self.current_query)
            return words
        return []

    def _rerank_results(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对搜索结果进行重排序

        评分因素（可配置）：
        1. 基础搜索得分 (rerank_weights['base'])
        2. 文件名匹配度 (rerank_weights['filename'])
        3. 关键词密度 (rerank_weights['keyword'])
        4. 时效性 - 文档新旧 (rerank_weights['recency'])
        5. 文档长度惩罚（避免过长文档）(rerank_weights['length'])
        """
        if not results:
            return results

        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))

        # 获取权重配置
        w = self.rerank_weights

        for result in results:
            original_score = result.get('score', 0)
            new_score = 0.0

            # 1. 基础搜索得分
            new_score += original_score * w['base']

            # 2. 文件名匹配度
            filename = os.path.basename(result.get('path', '')).lower()
            filename_score = 0.0

            # 完整查询匹配文件名
            if query_lower in filename:
                filename_score = 100.0
            else:
                # 部分匹配
                matched_words = sum(1 for word in query_words if word in filename)
                if matched_words > 0:
                    filename_score = (matched_words / max(len(query_words), 1)) * 80.0

                # 文件名变体匹配（使用常量）
                for variant in FILENAME_VARIANT_KEYWORDS:
                    if query_lower + variant in filename or variant + query_lower in filename:
                        filename_score = max(filename_score, 90.0)
                        break

            new_score += filename_score * w['filename']

            # 3. 关键词密度
            content = (result.get('content', '') or result.get('snippet', '')).lower()
            keyword_count = content.count(query_lower)
            for word in query_words:
                keyword_count += content.count(word)

            keyword_score = min(keyword_count * 2, KEYWORD_SCORE_MAX)
            new_score += keyword_score * w['keyword']

            # 4. 时效性 - 越新越好
            time_score = 0.0
            try:
                modified_time = result.get('modified')
                if modified_time:
                    if isinstance(modified_time, str):
                        modified_time = datetime.strptime(modified_time, '%Y-%m-%d %H:%M:%S')
                    days_old = (datetime.now() - modified_time).days
                    time_score = max(0, 20 - days_old * 0.1)
            except Exception:
                pass

            new_score += time_score * w['recency']

            # 5. 文档长度惩罚 - 避免过长文档
            length_penalty = 0.0
            content_length = len(content)
            if content_length > LENGTH_PENALTY_THRESHOLD_HIGH:
                length_penalty = -5.0
            elif content_length > LENGTH_PENALTY_THRESHOLD_LOW:
                length_penalty = -2.0

            new_score += length_penalty * w['length']

            # 确保分数在合理范围内
            result['score'] = min(max(new_score, 0.0), 100.0)
            result['original_score'] = original_score

        # 按新分数排序
        return sorted(results, key=lambda x: x['score'], reverse=True)

    def clear_cache(self):
        """清空搜索缓存"""
        if self.enable_cache and self.cache is not None:
            self.cache.clear()
            self.logger.info("搜索缓存已清空")

    def get_cache_stats(self):
        """获取缓存统计信息"""
        if not self.enable_cache or self.cache is None:
            return {'enabled': False}

        stats = self.cache.get_stats()
        return {
            'enabled': True,
            'size': stats.get('total_size', 0),
            'max_size': stats.get('max_size', 0),
            'ttl_seconds': self.cache_ttl,
            'num_shards': stats.get('num_shards', 1),
            'hits': stats.get('hits', 0),
            'misses': stats.get('misses', 0),
            'hit_rate': stats.get('hit_rate', 0.0),
        }

    def search_with_detailed_stats(self, query, filters=None):
        """执行搜索并返回详细统计信息"""
        start_time = time.time()
        
        # 执行搜索
        results = self.search(query, filters)
        
        # 计算统计信息
        search_time = time.time() - start_time
        stats = {
            'results_count': len(results),
            'search_time': search_time,
            'query': query,
            'filters_applied': filters is not None and len(filters) > 0,
            'cache_enabled': self.enable_cache,
            'text_weight': self.text_weight,
            'vector_weight': self.vector_weight
        }
        
        # 添加缓存统计（如果启用）
        if self.enable_cache:
            stats['cache_stats'] = self.get_cache_stats()
        
        return results, stats