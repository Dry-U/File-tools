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
    def __init__(self, index_manager, config):
        self.index_manager = index_manager
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 搜索配置
        self.text_weight = config.getfloat('search', 'text_weight', fallback=0.5)
        self.vector_weight = config.getfloat('search', 'vector_weight', fallback=0.5)
        self.max_results = config.getint('search', 'max_results', fallback=50)
        
        # 确保权重之和为1
        total_weight = self.text_weight + self.vector_weight
        if total_weight > 0:
            self.text_weight /= total_weight
            self.vector_weight /= total_weight
        else:
            self.text_weight = 0.5
            self.vector_weight = 0.5
        
        self.logger.info(f"搜索引擎初始化完成，文本权重: {self.text_weight}, 向量权重: {self.vector_weight}")
    
    def search(self, query, filters=None):
        """执行搜索，整合文本搜索和向量搜索结果"""
        start_time = time.time()
        self.logger.info(f"执行搜索: {query}")
        
        # 如果没有提供过滤器，使用默认空字典
        if filters is None:
            filters = {}
        
        # 执行文本搜索
        text_results = self._search_text(query, filters)
        
        # 执行向量搜索
        vector_results = self._search_vector(query, filters)
        
        # 合并和排序结果
        combined_results = self._combine_results(text_results, vector_results)
        
        # 应用过滤器
        filtered_results = self._apply_filters(combined_results, filters)
        
        # 限制结果数量
        limited_results = filtered_results[:self.max_results]
        
        search_time = time.time() - start_time
        self.logger.info(f"搜索完成，找到 {len(limited_results)} 条结果，耗时: {search_time:.3f}秒")
        
        return limited_results
    
    def _search_text(self, query, filters):
        """执行文本搜索"""
        try:
            # 调用索引管理器的文本搜索功能
            results = self.index_manager.search_text(query, limit=self.max_results * 2)  # 获取更多结果以确保过滤后有足够数量
            
            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'text'
            
            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []
    
    def _search_vector(self, query, filters):
        """执行向量搜索"""
        try:
            # 调用索引管理器的向量搜索功能
            results = self.index_manager.search_vector(query, limit=self.max_results * 2)  # 获取更多结果以确保过滤后有足够数量
            
            # 为每个结果添加搜索类型标识
            for result in results:
                result['search_type'] = 'vector'
            
            return results
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []
    
    def _combine_results(self, text_results, vector_results):
        """合并文本搜索和向量搜索结果"""
        # 使用字典来跟踪每个文件路径的最高分数
        combined = {}
        
        # 添加文本搜索结果
        for result in text_results:
            path = result['path']
            if path not in combined:
                combined[path] = result.copy()
            else:
                # 如果已经存在，取较高的分数
                if result['score'] > combined[path]['score']:
                    combined[path]['score'] = result['score']
                    combined[path]['search_type'] = result['search_type']
        
        # 添加向量搜索结果，并根据权重调整分数
        for result in vector_results:
            path = result['path']
            if path in combined:
                # 如果文件路径已经存在，根据权重计算综合分数
                combined_score = (combined[path]['score'] * self.text_weight + 
                                 result['score'] * self.vector_weight)
                combined[path]['score'] = combined_score
                combined[path]['search_type'] = 'hybrid'
            else:
                # 如果是新文件路径，直接添加
                combined[path] = result.copy()
        
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
            file_ext = os.path.splitext(result['path'])[1].lower()[1:]  # 获取文件扩展名
            if file_ext not in filters['file_types']:
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