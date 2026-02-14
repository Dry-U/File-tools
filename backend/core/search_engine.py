#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""搜索引擎模块 - 集成文本搜索和向量搜索功能"""
import os
import re
import time
import logging
from datetime import datetime
from typing import List, Dict, Any
import numpy as np

class SearchEngine:
    """搜索引擎类，负责执行文件搜索和结果排序"""
    def __init__(self, index_manager, config_loader):
        self.index_manager = index_manager
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)

        # 搜索配置 - 使用ConfigLoader获取配置
        search_config = config_loader.get('search')
        if search_config is None:
            search_config = {}
        self.text_weight = float(search_config.get('text_weight', 0.6))
        self.vector_weight = float(search_config.get('vector_weight', 0.4))
        self.max_results = int(search_config.get('max_results', 50))

        # 新增的高级搜索配置参数
        self.bm25_k1 = float(search_config.get('bm25_k1', 1.5))
        self.bm25_b = float(search_config.get('bm25_b', 0.75))
        self.result_boost = bool(search_config.get('result_boost', True))
        self.filename_boost = float(search_config.get('filename_boost', 1.5))
        self.keyword_boost = float(search_config.get('keyword_boost', 1.2))
        self.hybrid_boost = float(search_config.get('hybrid_boost', 1.1))
        # 语义搜索结果阈值（从配置读取）
        self.semantic_score_high_threshold = float(search_config.get('semantic_score_high_threshold', 60.0))
        self.semantic_score_low_threshold = float(search_config.get('semantic_score_low_threshold', 30.0))

        # 缓存配置
        self.enable_cache = bool(search_config.get('enable_cache', True))
        self.cache_ttl = int(search_config.get('cache_ttl', 3600))  # 默认1小时
        self.cache_size = int(search_config.get('cache_size', 1000))  # 默认缓存1000个查询

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

        # 初始化缓存
        if self.enable_cache:
            from collections import OrderedDict
            import time
            self.cache = OrderedDict()
            self.cache_timestamps = {}
            self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}, 缓存已启用")
        else:
            self.cache = None
            self.cache_timestamps = None
            self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}, 缓存已禁用")

    def _get_cache_key(self, query, filters=None):
        """生成缓存键"""
        if filters is None:
            filters = {}
        # 使用 json.dumps 确保缓存键稳定（处理嵌套字典等复杂对象）
        import json
        import hashlib
        try:
            # 对 filters 进行标准化处理，确保相同的过滤器产生相同的键
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
            # 如果标准化失败，使用简单的字符串表示
            cache_str = f"{query}:{str(sorted(filters.items()))}"
        return hashlib.md5(cache_str.encode()).hexdigest()

    def _is_cache_valid(self, key):
        """检查缓存是否有效"""
        if not self.enable_cache or key not in self.cache_timestamps:
            return False
        # 检查是否过期
        if time.time() - self.cache_timestamps[key] > self.cache_ttl:
            # 删除过期缓存
            if key in self.cache:
                del self.cache[key]
            if key in self.cache_timestamps:
                del self.cache_timestamps[key]
            return False
        return True

    def _get_from_cache(self, key):
        """从缓存获取结果"""
        if not self.enable_cache:
            return None
        if self._is_cache_valid(key):
            # 将访问的项移到末尾（LRU）
            result = self.cache.pop(key)
            self.cache[key] = result
            return result
        return None

    def _put_in_cache(self, key, result):
        """将结果放入缓存"""
        if not self.enable_cache:
            return
        # 检查缓存大小，如果超过限制则删除最久未使用的项
        if len(self.cache) >= self.cache_size:
            # 删除第一个项（最久未使用的）
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            if oldest_key in self.cache_timestamps:
                del self.cache_timestamps[oldest_key]
        
        # 添加新项
        self.cache[key] = result
        self.cache_timestamps[key] = time.time()
    
    def search(self, query, filters=None):
        """执行搜索，整合文本搜索和向量搜索结果"""
        start_time = time.time()
        self.logger.info(f"执行搜索: {query}, 过滤器: {filters}")

        # 使用QueryProcessor扩展查询
        try:
            from backend.core.query_processor import QueryProcessor
            query_processor = QueryProcessor(self.config_loader)
            expanded_queries = query_processor.process(query)
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
            import traceback
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
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _combine_results(self, text_results, vector_results):
        """合并文本搜索和向量搜索结果 - 优化版本，改进相似度计算和去重算法"""
        # 使用字典来跟踪每个文件路径的最佳结果
        combined = {}
        max_text_score = 0.0

        # 添加文本搜索结果
        for result in text_results:
            path = result['path']
            if path not in combined:
                combined[path] = result.copy()
                # 确保文本搜索结果有search_type字段
                if 'search_type' not in combined[path]:
                    combined[path]['search_type'] = 'text'
                # 记录原始分数
                combined[path]['text_score'] = result['score']
                combined[path]['vector_score'] = 0.0
                if result['score'] > max_text_score:
                    max_text_score = result['score']
            else:
                # 如果路径已存在，检查是否需要更新
                # 用分数更高的结果替换
                if result['score'] > combined[path]['score']:
                    # 保留之前的向量分数（如果有的话）
                    prev_vector_score = combined[path]['vector_score']
                    combined[path] = result.copy()
                    combined[path]['search_type'] = result['search_type']
                    combined[path]['text_score'] = result['score']
                    combined[path]['vector_score'] = prev_vector_score  # 保持之前的向量分数
                else:
                    # 仅更新文本分数
                    combined[path]['text_score'] = max(combined[path]['text_score'], result['score'])
                if result['score'] > max_text_score:
                    max_text_score = result['score']

        # 添加向量搜索结果，并根据权重调整分数
        for result in vector_results:
            path = result['path']
            if path in combined:
                # 如果文件路径已经存在，记录向量分数
                prev_text_score = combined[path]['text_score']
                combined[path]['vector_score'] = result['score']

                # 更精确的混合分数计算 - 使用归一化分数的加权平均
                # 文本分数归一化：相对于最大文本分数
                text_norm = 0.0
                if max_text_score > 0:
                    text_norm = min(prev_text_score / max_text_score, 1.0)
                
                # 向量分数通常已经是0-100或0-1，这里假设是0-100
                vector_norm = min(result['score'], 100.0) / 100.0

                # 使用加权平均
                combined_score = (text_norm * self.text_weight + vector_norm * self.vector_weight) * 100.0

                # 确保分数不超过100
                combined_score = min(combined_score, 100.0)
                combined[path]['score'] = combined_score
                combined[path]['search_type'] = 'hybrid'
            else:
                # 如果是新文件路径，直接添加
                combined[path] = result.copy()
                combined[path]['text_score'] = 0.0
                combined[path]['vector_score'] = result['score']
                # 确保向量搜索结果有search_type字段
                if 'search_type' not in combined[path]:
                    combined[path]['search_type'] = 'vector'

        # 重新计算所有结果的最终分数，确保文本搜索结果也能得到正确归一化
        # 特别是那些只在文本搜索中出现的结果
        if max_text_score <= 0:
            max_text_score = 1.0

        for path, result in combined.items():
            # 如果已经计算过混合分数，跳过
            if result.get('search_type') == 'hybrid':
                continue
            
            # 处理纯文本结果
            if result.get('search_type') == 'text':
                ts = float(result.get('text_score', 0.0))
                # 归一化文本分数 (0.0 - 1.0)
                norm_score = (ts / max_text_score)
                # 应用文本权重，确保与混合搜索的分数尺度一致
                # 这样混合搜索结果（通常有文本+向量贡献）会自然高于纯文本结果
                result['score'] = (norm_score * self.text_weight) * 100.0
            
            # 处理纯向量结果
            elif result.get('search_type') == 'vector':
                # 向量结果分数通常是 0-100
                vs = float(result.get('vector_score', 0.0))
                vector_norm = vs / 100.0
                # 应用向量权重
                result['score'] = (vector_norm * self.vector_weight) * 100.0

        # 应用额外的质量评估标准
        for path, result in combined.items():
            original_score = result['score']

            # 关键词命中增强 (Snippet Boost)
            # 如果摘要中包含高亮关键词，给予显著加分
            snippet = result.get('snippet', '')
            if 'text-danger' in snippet:
                # 这是一个强信号，说明内容中确实包含关键词
                # 给予 20 分的基础加分
                result['score'] = min(result['score'] + 20.0, 100.0)
                
                # 如果是纯文本匹配且有高亮，确保分数至少及格
                # 考虑到权重可能导致分数较低（如 0.6 * 100 = 60），这里给予一个合理的保底
                if result.get('search_type') == 'text':
                    result['score'] = max(result['score'], 60.0)

            # 混合结果增强（如果启用）
            if self.result_boost and result['search_type'] == 'hybrid':
                result['score'] *= self.hybrid_boost

            # 文件名匹配增强
            query_words = self._get_query_words()
            if query_words:
                filename = os.path.basename(path).lower()
                query_match_count = 0
                
                # 检查完整查询是否在文件名中 (最高优先级)
                if self.current_query and self.current_query.lower() in filename:
                    # 如果完整查询字符串直接出现在文件名中，给予巨大加分
                    # 这确保了精确文件名匹配几乎总是排在最前面
                    result['score'] = max(result['score'], 95.0)
                else:
                    # 单词匹配
                    for word in query_words:
                        word_lower = word.lower()
                        if word_lower in filename:
                            query_match_count += 1

                    if query_match_count > 0:
                        # 基于匹配词数给予加分
                        # 增加加分权重，从5.0增加到15.0
                        filename_bonus = query_match_count * 15.0
                        result['score'] = min(result['score'] + filename_bonus, 100.0)

            # 确保分数在合理范围内
            result['score'] = min(max(result['score'], 0.0), 100.0)

        # 转换为列表并按分数降序排序
        sorted_results = sorted(combined.values(), key=lambda x: x['score'], reverse=True)

        return sorted_results
    
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
        # 这是一个简化的实现，实际应用中可能需要使用更复杂的模式匹配库
        # 例如，可以使用fnmatch模块或正则表达式
        import fnmatch
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
            # 简单的分词处理
            import re
            # 按空格和常见分隔符分割
            words = re.findall(r'\w+', self.current_query)
            return words
        return []

    def _rerank_results(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对搜索结果进行重排序

        评分因素：
        1. 基础搜索得分 (30%)
        2. 文件名匹配度 (40%) - 大幅提高文件名权重
        3. 关键词密度 (15%)
        4. 时效性 - 文档新旧 (10%)
        5. 文档长度惩罚（避免过长文档）(5%)
        """
        if not results:
            return results

        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))

        for result in results:
            original_score = result.get('score', 0)
            new_score = 0.0

            # 1. 基础搜索得分 (30%)
            new_score += original_score * 0.3

            # 2. 文件名匹配度 (40%) - 大幅提高权重
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

                # 文件名变体匹配（如"rcp说明"匹配"rcp"）
                for variant in ['说明', '文档', '指南', '手册', '介绍', '简介']:
                    if query_lower + variant in filename or variant + query_lower in filename:
                        filename_score = max(filename_score, 90.0)
                        break

            new_score += filename_score * 0.4

            # 3. 关键词密度 (15%)
            content = (result.get('content', '') or result.get('snippet', '')).lower()
            keyword_count = content.count(query_lower)
            for word in query_words:
                keyword_count += content.count(word)

            keyword_score = min(keyword_count * 2, 30)  # 上限30分
            new_score += keyword_score * 0.15

            # 4. 时效性 (10%) - 越新越好
            time_score = 0.0
            try:
                modified_time = result.get('modified')
                if modified_time:
                    if isinstance(modified_time, str):
                        modified_time = datetime.strptime(modified_time, '%Y-%m-%d %H:%M:%S')
                    days_old = (datetime.now() - modified_time).days
                    time_score = max(0, 20 - days_old * 0.1)  # 新文档加分，每天减0.1分
            except Exception:
                pass

            new_score += time_score * 0.1

            # 5. 文档长度惩罚 (5%) - 避免过长文档
            length_penalty = 0.0
            content_length = len(content)
            if content_length > 10000:
                length_penalty = -5.0
            elif content_length > 5000:
                length_penalty = -2.0

            new_score += length_penalty * 0.05

            # 确保分数在合理范围内
            result['score'] = min(max(new_score, 0.0), 100.0)
            result['original_score'] = original_score  # 保留原始分数用于调试

        # 按新分数排序
        return sorted(results, key=lambda x: x['score'], reverse=True)

    def clear_cache(self):
        """清空搜索缓存"""
        if self.enable_cache and self.cache is not None:
            self.cache.clear()
            self.cache_timestamps.clear()
            self.logger.info("搜索缓存已清空")

    def get_cache_stats(self):
        """获取缓存统计信息"""
        if not self.enable_cache:
            return {'enabled': False}
        
        current_time = time.time()
        valid_items = 0
        expired_items = 0
        
        for key, timestamp in self.cache_timestamps.items():
            if current_time - timestamp <= self.cache_ttl:
                valid_items += 1
            else:
                expired_items += 1
        
        return {
            'enabled': True,
            'size': len(self.cache),
            'max_size': self.cache_size,
            'ttl_seconds': self.cache_ttl,
            'valid_items': valid_items,
            'expired_items': expired_items
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