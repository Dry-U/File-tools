#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""搜索引擎模块 - 集成文本搜索和向量搜索功能"""
import os
import time
import logging
from datetime import datetime
import numpy as np

class SearchEngine:
    """搜索引擎类，负责执行文件搜索和结果排序"""
    def __init__(self, index_manager, config_loader):
        # 添加调试信息，查看参数类型
        print(f"SearchEngine初始化 - index_manager类型: {type(index_manager)}, config_loader类型: {type(config_loader)}")
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
        
        self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}")
    
    def search(self, query, filters=None):
        """执行搜索，整合文本搜索和向量搜索结果"""
        start_time = time.time()
        self.logger.info(f"执行搜索: {query}, 过滤器: {filters}")
        
        # 保存当前查询以供后续使用
        self.current_query = query
        
        # 如果没有提供过滤器，使用默认空字典
        if filters is None:
            filters = {}
        
        # 执行文本搜索
        text_results = self._search_text(query, filters)
        self.logger.info(f"文本搜索返回 {len(text_results)} 条结果")
        
        # 执行向量搜索
        vector_results = self._search_vector(query, filters)
        self.logger.info(f"向量搜索返回 {len(vector_results)} 条结果")
        
        # 合并和排序结果
        combined_results = self._combine_results(text_results, vector_results)
        self.logger.info(f"合并后 {len(combined_results)} 条结果")
        
        # 应用过滤器
        filtered_results = self._apply_filters(combined_results, filters)
        self.logger.info(f"过滤后 {len(filtered_results)} 条结果")
        
        # 限制结果数量
        limited_results = filtered_results[:self.max_results]
        
        search_time = time.time() - start_time
        self.logger.info(f"搜索完成，找到 {len(limited_results)} 条结果，耗时: {search_time:.3f}秒")
        
        return limited_results
    
    def _search_text(self, query, filters=None):
        """执行文本搜索"""
        try:
            # 调用索引管理器的文本搜索功能，不传递filters参数
            results = self.index_manager.search_text(query, limit=self.max_results * 2)  # 获取更多结果以确保过滤后有足够数量
            
            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'text'
            
            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []
    
    def _search_vector(self, query, filters=None):
        """执行向量搜索"""
        try:
            # 调用索引管理器的向量搜索功能，不传递filters参数
            results = self.index_manager.search_vector(query, limit=self.max_results * 2)  # 获取更多结果以确保过滤后有足够数量
            
            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'vector'
            
            return results
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []
    
    def _combine_results(self, text_results, vector_results):
        """合并文本搜索和向量搜索结果 - 优化版本"""
        # 使用字典来跟踪每个文件路径的最高分数
        combined = {}
        
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
            else:
                # 如果已经存在，取较高的分数
                if result['score'] > combined[path]['score']:
                    combined[path]['score'] = result['score']
                    combined[path]['search_type'] = result['search_type']
                combined[path]['text_score'] = result['score']
        
        # 添加向量搜索结果，并根据权重调整分数
        for result in vector_results:
            path = result['path']
            if path in combined:
                # 如果文件路径已经存在，记录向量分数
                combined[path]['vector_score'] = result['score']
                
                # 计算综合分数 - 使用加权几何平均而非算术平均，以提高结果质量
                # 如果任一分数为0，则综合分数会显著降低
                text_norm = combined[path]['text_score']
                vector_norm = result['score']
                
                # 归一化分数到0-1范围
                # 简单归一化方法 - 除以最大可能分数
                text_norm = min(text_norm, 10.0) / 10.0  # 假设10是较高的文本分数
                vector_norm = min(vector_norm, 1.0)  # 向量分数通常在0-1范围内
                
                # 使用加权几何平均
                if text_norm > 0 and vector_norm > 0:
                    combined_score = (text_norm ** self.text_weight) * (vector_norm ** self.vector_weight)
                    combined_score *= 10.0  # 恢复到原始分数范围
                elif text_norm > 0:
                    combined_score = text_norm * 10.0 * self.text_weight
                else:
                    combined_score = vector_norm * 10.0 * self.vector_weight
                
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
        
        # 应用额外的质量评估标准
        for path, result in combined.items():
            # 如果启用了结果增强
            if self.result_boost:
                # 如果是混合搜索结果，给予额外加分
                if result['search_type'] == 'hybrid':
                    # 混合结果通常更可靠，给予额外加分
                    result['score'] *= self.hybrid_boost
            
            # 对文件名匹配给予额外加分
            query_words = self._get_query_words()
            filename = os.path.basename(path).lower()
            filename_bonus = 0
            for word in query_words:
                if word.lower() in filename:
                    filename_bonus += 0.2  # 每个匹配的词加0.2分
            
            result['score'] += filename_bonus
        
        # 转换为列表并按分数排序
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