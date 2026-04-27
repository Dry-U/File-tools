#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""搜索引擎模块 - 集成文本搜索和向量搜索功能

类型注解完善版本，提升代码可维护性和 IDE 支持。
"""

import fnmatch
import hashlib
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.constants import (
    DEFAULT_CACHE_SIZE,
    DEFAULT_CACHE_TTL,
    DEFAULT_RERANK_BASE_WEIGHT,
    DEFAULT_RERANK_FILENAME_WEIGHT,
    DEFAULT_RERANK_KEYWORD_WEIGHT,
    DEFAULT_RERANK_LENGTH_WEIGHT,
    DEFAULT_RERANK_RECENCY_WEIGHT,
    FILENAME_VARIANT_KEYWORDS,
    KEYWORD_SCORE_MAX,
    LENGTH_PENALTY_THRESHOLD_HIGH,
    LENGTH_PENALTY_THRESHOLD_LOW,
)
from backend.core.query_processor import QueryProcessor
from backend.core.sharded_cache import ShardedCache

# 类型别名定义
FilterDict = Dict[str, Any]
SearchResult = Dict[str, Any]
ScoredResult = Tuple[str, float]


class SearchEngine:
    """搜索引擎类，负责执行文件搜索和结果排序"""

    def __init__(self, index_manager: Any, config_loader: Any) -> None:
        self.index_manager: Any = index_manager
        self.config_loader: Any = config_loader
        self.logger: logging.Logger = logging.getLogger(__name__)

        # 初始化查询处理器（复用实例）
        self.query_processor = QueryProcessor(config_loader)

        # 搜索配置 - 使用ConfigLoader获取配置（只读取一次）
        search_config: Dict[str, Any] = config_loader.get("search") or {}

        # 辅助函数：从配置中安全获取数值
        def get_config_float(key: str, default: float) -> float:
            return float(search_config.get(key, default))

        def get_config_int(key: str, default: int) -> int:
            return int(search_config.get(key, default))

        def get_config_bool(key: str, default: bool) -> bool:
            val = search_config.get(key, default)
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes", "on")

        self.text_weight: float = get_config_float("text_weight", 0.6)
        self.vector_weight: float = get_config_float("vector_weight", 0.4)
        self.max_results: int = min(max(get_config_int("max_results", 50), 1), 500)

        # 高级搜索配置参数
        self.result_boost = get_config_bool("result_boost", True)
        self.filename_boost = get_config_float("filename_boost", 1.5)
        self.keyword_boost = get_config_float("keyword_boost", 1.2)
        self.hybrid_boost = get_config_float("hybrid_boost", 1.1)
        # 语义搜索结果阈值（从配置读取）
        self.semantic_score_high_threshold = get_config_float(
            "semantic_score_high_threshold", 60.0
        )
        self.semantic_score_low_threshold = get_config_float(
            "semantic_score_low_threshold", 30.0
        )

        # RRF (Reciprocal Rank Fusion) 配置
        # RRF 是一种鲁棒的排名融合方法，比加权求和更抗噪声
        # 公式: RRF(doc) = Σ weight/(k + rank(doc, source))
        self.rrf_k = get_config_int("rrf_k", 60)  # RRF 常数，通常 60

        # 重排权重配置（从配置读取，使用常量作为默认值）
        self.rerank_weights = {
            "base": get_config_float("rerank_base_weight", DEFAULT_RERANK_BASE_WEIGHT),
            "filename": get_config_float(
                "rerank_filename_weight", DEFAULT_RERANK_FILENAME_WEIGHT
            ),
            "keyword": get_config_float(
                "rerank_keyword_weight", DEFAULT_RERANK_KEYWORD_WEIGHT
            ),
            "recency": get_config_float(
                "rerank_recency_weight", DEFAULT_RERANK_RECENCY_WEIGHT
            ),
            "length": get_config_float(
                "rerank_length_weight", DEFAULT_RERANK_LENGTH_WEIGHT
            ),
        }

        # 缓存配置
        self.enable_cache = bool(search_config.get("enable_cache", True))
        self.cache_ttl = int(search_config.get("cache_ttl", DEFAULT_CACHE_TTL))
        self.cache_size = int(search_config.get("cache_size", DEFAULT_CACHE_SIZE))

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
            self.logger.info(
                f"搜索引擎初始化完成，文本权重: {self.text_weight}, "
                f"向量权重: {self.vector_weight}, 分片缓存已启用"
            )
        else:
            self.cache = None
            self.logger.info(
                f"搜索引擎初始化完成，文本权重: {self.text_weight}, "
                f"向量权重: {self.vector_weight}, 缓存已禁用"
            )

        # 初始化 EmbeddingModelManager（用于 ColBERT reranker）
        self._init_reranker()

    def _init_reranker(self) -> None:
        """初始化 ColBERT Reranker"""
        try:
            from backend.core.embedding_manager import EmbeddingModelManager

            self.reranker_manager = EmbeddingModelManager(self.config_loader)
            reranker_enabled = self.config_loader.getboolean(
                "reranker", "enabled", True
            )
            if reranker_enabled:
                self.logger.info(
                    "[SearchEngine] Reranker 已启用: "
                    f"{self.reranker_manager.reranker_model_name}"
                )
            else:
                self.logger.info("[SearchEngine] Reranker 未启用")
        except Exception as e:
            self.logger.warning(f"[SearchEngine] Reranker 初始化失败: {e}")
            self.reranker_manager = None

    def _get_cache_key(self, query, filters=None) -> str:
        """生成缓存键

        使用 JSON 序列化确保过滤器字典顺序一致性，避免缓存键冲突。
        """
        if filters is None:
            filters = {}
        try:
            # 使用 json.dumps 统一序列化，确保一致性
            normalized_filters = json.dumps(filters, sort_keys=True, ensure_ascii=True)
            cache_str = f"{query}:{normalized_filters}"
        except (TypeError, ValueError):
            # 降级处理：直接转换为字符串
            cache_str = f"{query}:{str(filters)}"
        return hashlib.sha256(cache_str.encode(), usedforsecurity=False).hexdigest()

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

    def search(
        self, query: str, filters: Optional[FilterDict] = None
    ) -> List[SearchResult]:
        """执行搜索，整合文本搜索和向量搜索结果

        Args:
            query: 搜索查询字符串
            filters: 可选的过滤器字典，包含 file_types, date_from, date_to 等

        Returns:
            搜索结果列表，每个结果包含 path, filename, score, snippet 等字段
        """
        start_time = time.time()
        self.logger.debug(f"执行搜索: {query}, 过滤器: {filters}")

        # 准备搜索：检查缓存、处理查询
        cache_key, expanded_queries, filters = self._prepare_search(query, filters)

        # 检查缓存命中
        if self.enable_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                cache_hit_time = time.time() - start_time
                self.logger.info(
                    f"缓存命中，返回缓存结果，耗时: {cache_hit_time:.3f}秒"
                )
                return cached_result

        # 确保 filters 不为 None
        if filters is None:
            filters = {}

        # 执行多路召回搜索
        all_text_results, all_vector_results = self._execute_multi_recall(
            expanded_queries, filters
        )

        # 后处理结果：合并、重排、过滤
        limited_results = self._post_process_results(
            query, filters, all_text_results, all_vector_results
        )

        search_time = time.time() - start_time
        self.logger.info(
            f"搜索完成，找到 {len(limited_results)} 条结果，耗时: {search_time:.3f}秒"
        )

        # 将结果存入缓存
        if self.enable_cache:
            self._put_in_cache(cache_key, limited_results)

        return limited_results

    def _prepare_search(self, query: str, filters: Optional[FilterDict]) -> tuple:
        """准备搜索：检查缓存、处理查询、处理过滤器

        Returns:
            (cache_key, expanded_queries, processed_filters)
        """
        # 使用QueryProcessor扩展查询
        try:
            expanded_queries = self.query_processor.process(query)
            self.logger.info(f"查询扩展: {expanded_queries}")
        except Exception as e:
            self.logger.warning(f"查询扩展失败: {e}")
            expanded_queries = [query]

        # 检查缓存
        cache_key = self._get_cache_key(query, filters)

        # 如果没有提供过滤器，使用默认空字典
        if filters is None:
            filters = {}
        else:
            filters = filters.copy()

        file_type_filter = self._detect_file_type_filter(query)
        if file_type_filter:
            filters["file_types"] = file_type_filter

        return cache_key, expanded_queries, filters

    def _execute_multi_recall(
        self, expanded_queries: List[str], filters: FilterDict
    ) -> tuple:
        """执行多路召回搜索

        Returns:
            (all_text_results, all_vector_results)
            每个结果包含原始排名信息 (text_rank, vector_rank)
        """
        all_text_results = []
        all_vector_results = []
        seen_text_paths = set()
        seen_vector_paths = set()

        # 优化：检测短查询，减少召回路数
        original_query = expanded_queries[0] if expanded_queries else ""
        is_short_query = len(original_query.strip()) <= 2

        # 短查询：只使用原始查询，避免扩展查询带来的性能开销
        if is_short_query:
            queries_to_search = [original_query]
            self.logger.info(f"短查询优化：只使用原始查询 '{original_query}'")
        else:
            # 正常查询：限制最多3个扩展查询
            queries_to_search = expanded_queries[:3]

        # 对每个查询执行搜索
        for search_query in queries_to_search:
            # 执行文本搜索
            text_results = self._search_text(search_query, filters)
            for rank, result in enumerate(text_results):
                path = result.get("path", "")
                if path and path not in seen_text_paths:
                    seen_text_paths.add(path)
                    result["search_query"] = search_query  # 记录匹配的查询
                    result["text_rank"] = rank  # 记录在该查询中的排名
                    result["vector_rank"] = -1  # 初始化向量排名
                    all_text_results.append(result)

            # 短查询跳过向量搜索以提升性能（文本搜索已足够）
            if not is_short_query:
                # 执行向量搜索
                vector_results = self._search_vector(search_query, filters)
                for rank, result in enumerate(vector_results):
                    path = result.get("path", "")
                    if path and path not in seen_vector_paths:
                        seen_vector_paths.add(path)
                        result["search_query"] = search_query
                        result["vector_rank"] = rank  # 记录在该查询中的排名
                        result["text_rank"] = -1  # 初始化文本排名
                        all_vector_results.append(result)

        self.logger.info(
            f"多路召回: 文本搜索 {len(all_text_results)} 条, "
            f"向量搜索 {len(all_vector_results)} 条"
        )

        return all_text_results, all_vector_results

    def _post_process_results(
        self,
        query: str,
        filters: FilterDict,
        all_text_results: List,
        all_vector_results: List,
    ) -> List[SearchResult]:
        """后处理搜索结果：合并、重排、过滤、排序

        Returns:
            处理后的搜索结果列表
        """
        # 合并和排序结果
        combined_results = self._combine_results(
            query, all_text_results, all_vector_results
        )
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
                snippet = item.get("snippet") or ""
                has_highlight = "text-danger" in snippet
                if has_highlight or item.get("has_query"):
                    primary_hits.append(item)
                else:
                    # 标记语义结果，避免用户误以为缺少高亮是 bug
                    if snippet:
                        item["snippet"] = (
                            f"（未直接匹配搜索词，展示语义相关内容）<br>{snippet}"
                        )
                    else:
                        item["snippet"] = "（未直接匹配搜索词，展示语义相关内容）"
                    semantic_hits.append(item)

            if primary_hits:
                # 如果找到了精确匹配的结果，则对语义匹配结果进行宽松过滤
                # 仅保留分数超过低阈值的语义结果作为补充，过滤掉明显无关的噪音
                # 有精确匹配作为基础时可以更宽松地补充语义结果
                supplemental_semantic = [
                    item
                    for item in semantic_hits
                    if item["score"] > self.semantic_score_low_threshold
                ]
                limited_results = primary_hits + supplemental_semantic
            else:
                # 如果没有精确匹配，则只展示语义匹配结果
                # 使用中等阈值(40)作为兜底，避免用户看不到任何结果
                # 注：如果语义结果在30-60分之间仍可能被过滤，但至少40分以上的会显示
                fallback_threshold = 40.0
                fallback_semantic = [
                    item for item in semantic_hits if item["score"] > fallback_threshold
                ]
                limited_results = fallback_semantic

        # 限制结果数量
        limited_results = limited_results[: self.max_results]

        return limited_results

    def _detect_file_type_filter(self, query: str) -> Optional[List[str]]:
        """检测查询中的文件类型过滤器

        Args:
            query: 用户查询字符串

        Returns:
            文件扩展名列表，如果没有检测到则返回 None
        """
        q = (query or "").strip().lower()
        if not q:
            return None
        mapping = {
            ".pdf": {"pdf", "pdf文件", "找pdf", "搜索pdf", "pdf资料", "全部pdf"},
            ".doc": {"doc", "doc文件", "word文档"},
            ".docx": {"docx", "docx文件"},
            ".ppt": {"ppt", "ppt文件"},
            ".pptx": {"pptx", "pptx文件"},
            ".xls": {"xls", "excel", "excel表", "表格"},
            ".xlsx": {"xlsx"},
        }
        for ext, keywords in mapping.items():
            if q in keywords:
                return [ext]
        return None

    def _search_text(
        self, query: str, filters: Optional[FilterDict] = None
    ) -> List[SearchResult]:
        """执行文本搜索

        Args:
            query: 搜索查询字符串
            filters: 可选的过滤器字典

        Returns:
            文本搜索结果列表
        """
        try:
            # 调用索引管理器的文本搜索功能，获取更多结果以确保过滤后有足够数量
            # 将过滤器传递给search_text，包括 case_sensitive 参数
            results = self.index_manager.search_text(
                query, limit=self.max_results * 3, filters=filters
            )
            self.logger.info(f"文本搜索返回 {len(results)} 条结果")

            # 为每个结果添加搜索类型标识
            for result in results:
                result["search_type"] = "text"

            return results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _search_vector(
        self, query: str, filters: Optional[FilterDict] = None
    ) -> List[SearchResult]:
        """执行向量搜索

        Args:
            query: 搜索查询字符串
            filters: 可选的过滤器字典

        Returns:
            向量搜索结果列表
        """
        try:
            # 调用索引管理器的向量搜索功能，获取更多结果以确保过滤后有足够数量
            # 注意：向量搜索暂不支持 filters 参数，
            # 过滤在 _post_process_results 中对合并结果统一处理
            results = self.index_manager.search_vector(
                query, limit=self.max_results * 3
            )
            self.logger.info(f"向量搜索返回 {len(results)} 条结果")

            # 为每个结果添加搜索类型标识
            for result in results:
                result["search_type"] = "vector"

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
            path = result["path"]
            if path not in combined:
                combined[path] = result.copy()
                if "search_type" not in combined[path]:
                    combined[path]["search_type"] = "text"
                combined[path]["text_score"] = result["score"]
                combined[path]["vector_score"] = 0.0
                combined[path]["text_rank"] = result.get("text_rank", 0)
                combined[path]["vector_rank"] = result.get("vector_rank", -1)
                if result["score"] > max_text_score:
                    max_text_score = result["score"]
            else:
                # 保留更高分的结果和更好的排名
                if result["score"] > combined[path]["score"]:
                    prev_vector_score = combined[path]["vector_score"]
                    prev_vector_rank = combined[path]["vector_rank"]
                    combined[path] = result.copy()
                    combined[path]["search_type"] = result["search_type"]
                    combined[path]["text_score"] = result["score"]
                    combined[path]["vector_score"] = prev_vector_score
                    combined[path]["vector_rank"] = prev_vector_rank
                else:
                    combined[path]["text_score"] = max(
                        combined[path]["text_score"], result["score"]
                    )
                    # 保留最佳排名
                    if result.get("text_rank", 0) < combined[path].get(
                        "text_rank", 9999
                    ):
                        combined[path]["text_rank"] = result.get("text_rank", 0)

                if result["score"] > max_text_score:
                    max_text_score = result["score"]

        return combined, max_text_score

    def _merge_vector_results(self, vector_results: List[Dict], combined: Dict) -> Dict:
        """
        合并向量搜索结果（RRF模式）

        保存向量排名信息，由后续的 _calculate_rrf_scores 计算最终分数。

        Args:
            vector_results: 向量搜索结果列表
            combined: 已合并的文本结果字典

        Returns:
            更新后的合并结果字典
        """
        for result in vector_results:
            path = result["path"]
            if path in combined:
                # 已存在，更新向量信息和排名
                combined[path]["vector_score"] = result["score"]
                combined[path]["vector_rank"] = result.get("vector_rank", -1)
                combined[path]["search_type"] = "hybrid"
            else:
                # 新路径，直接添加
                combined[path] = result.copy()
                combined[path]["text_score"] = 0.0
                combined[path]["text_rank"] = -1
                combined[path]["vector_score"] = result["score"]
                if "search_type" not in combined[path]:
                    combined[path]["search_type"] = "vector"

        return combined

    def _calculate_rrf_scores(self, combined: Dict) -> None:
        """
        使用 Reciprocal Rank Fusion (RRF) 计算混合分数

        RRF 是一种鲁棒的排名融合方法，比加权求和更抗噪声。
        公式: RRF(doc) = Σ weight/(k + rank(doc, source))

        分数映射：
        - 排名 0 (最佳): ~90-100分
        - 排名 10: ~60-70分
        - 排名 50+: <30分

        Args:
            combined: 合并结果字典（就地修改）
        """
        k = self.rrf_k  # RRF 常数，默认 60

        for result in combined.values():
            text_rank = result.get("text_rank", -1)
            vector_rank = result.get("vector_rank", -1)

            rrf_score = 0.0
            num_sources = 0  # 实际有多少个来源

            # 标准 RRF：不使用权重因子
            if text_rank >= 0:
                rrf_score += 1.0 / (k + text_rank)
                num_sources += 1

            if vector_rank >= 0:
                rrf_score += 1.0 / (k + vector_rank)
                num_sources += 1

            # 动态计算 max_rrf，基于实际来源数量
            # 单源 (rank=0): max = 1/k; 双源 (rank=0,0): max = 2/k
            max_rrf = num_sources / k if num_sources > 0 else 0.0

            # 归一化到 0-100 范围，使用线性插值使分数更分散
            if max_rrf > 0:
                relative_score = rrf_score / max_rrf
                # 线性映射：rank 0 -> 95, rank 60 -> ~30, 避免分数过于集中
                result["score"] = min(95 * relative_score, 100.0)
            else:
                result["score"] = 50.0

            # 标记搜索类型
            if text_rank >= 0 and vector_rank >= 0:
                result["search_type"] = "hybrid"
            elif text_rank >= 0:
                result["search_type"] = "text"
            else:
                result["search_type"] = "vector"

    def _apply_snippet_boost(self, result: Dict) -> None:
        """
        应用关键词命中增强（摘要高亮加分）
        """
        snippet = result.get("snippet", "")
        if "text-danger" not in snippet:
            return

        # 高亮关键词加分
        result["score"] = min(result["score"] + 20.0, 100.0)

        # 纯文本匹配保底分数
        if result.get("search_type") == "text":
            result["score"] = max(result["score"], 60.0)

    def _apply_hybrid_boost(self, result: Dict) -> None:
        """
        应用混合结果增强
        """
        if self.result_boost and result.get("search_type") == "hybrid":
            result["score"] *= self.hybrid_boost

    def _apply_filename_boost(self, result: Dict, query: str) -> None:
        """
        应用文件名匹配增强
        """
        query_words = self._get_query_words(query)
        if not query_words:
            return

        filename = os.path.basename(result.get("path", "")).lower()
        query_match_count = 0

        # 完整查询匹配（最高优先级）
        if query and query.lower() in filename:
            result["score"] = max(result["score"], 95.0)
            return

        # 单词匹配
        for word in query_words:
            if word.lower() in filename:
                query_match_count += 1

        if query_match_count > 0:
            filename_bonus = query_match_count * 15.0
            result["score"] = min(result["score"] + filename_bonus, 100.0)

    def _apply_boosts(self, combined: Dict, query: str) -> None:
        """
        应用所有boost因子
        """
        for result in combined.values():
            self._apply_snippet_boost(result)
            self._apply_hybrid_boost(result)
            self._apply_filename_boost(result, query)

            # 确保分数在合理范围内
            result["score"] = min(max(result["score"], 0.0), 100.0)

    def _combine_results(
        self, query: str, text_results: List[Dict], vector_results: List[Dict]
    ) -> List[Dict]:
        """
        合并文本搜索和向量搜索结果

        使用 RRF (Reciprocal Rank Fusion) 算法融合排名：
        - 使用排名而非原始分数，更鲁棒
        - RRF(doc) = Σ weight/(k + rank(doc, source))
        - k 是常数，默认 60

        处理流程：
        1. 合并文本结果去重（保留最佳排名）
        2. 合并向量结果
        3. 使用 RRF 计算混合分数
        4. 应用各种boost因子
        5. 排序返回
        """
        # 步骤1: 合并文本结果（追踪排名）
        combined, max_text_score = self._merge_text_results(text_results)

        # 步骤2: 合并向量结果
        combined = self._merge_vector_results(vector_results, combined)

        # 步骤3: 使用 RRF 计算混合分数
        self._calculate_rrf_scores(combined)

        # 步骤4: 应用boost因子
        self._apply_boosts(combined, query)

        # 步骤5: 排序并返回
        return sorted(combined.values(), key=lambda x: x["score"], reverse=True)

    def _apply_filters(self, results: list[dict], filters: dict) -> list[dict]:
        """应用过滤器"""
        if not filters:
            return results
        filtered = []

        for result in results:
            if self._match_filters(result, filters):
                filtered.append(result)

        return filtered

    def _match_filters(self, result: dict, filters: dict) -> bool:
        """检查结果是否匹配所有过滤器条件"""
        # 文件类型过滤
        if "file_types" in filters and filters["file_types"]:
            file_ext = os.path.splitext(result["path"])[
                1
            ].lower()  # 获取文件扩展名（包含点）
            normalized_types = [
                ft if ft.startswith(".") else f".{ft}" for ft in filters["file_types"]
            ]
            if file_ext not in normalized_types:
                return False

        # 日期范围过滤
        if "date_from" in filters or "date_to" in filters:
            # 尝试获取文件的修改时间
            try:
                # 从结果中获取修改时间
                if "modified" in result:
                    # 如果是字符串类型的时间，尝试解析
                    if isinstance(result["modified"], str):
                        file_modified = datetime.strptime(
                            result["modified"], "%Y-%m-%d %H:%M:%S"
                        )
                    else:
                        file_modified = result["modified"]
                else:
                    # 如果结果中没有，直接从文件系统获取
                    file_modified = datetime.fromtimestamp(
                        os.path.getmtime(result["path"])
                    )

                # 应用日期范围过滤
                if "date_from" in filters and filters["date_from"]:
                    date_from = datetime.strptime(filters["date_from"], "%Y-%m-%d")
                    if file_modified.date() < date_from.date():
                        return False

                if "date_to" in filters and filters["date_to"]:
                    date_to = datetime.strptime(filters["date_to"], "%Y-%m-%d")
                    if file_modified.date() > date_to.date():
                        return False
            except Exception as e:
                self.logger.warning(f"日期过滤失败 {result['path']}: {str(e)}")
                # 如果无法获取或解析日期，默认不过滤

        # 文件大小过滤
        if "size_min" in filters or "size_max" in filters:
            try:
                # 获取文件大小
                file_size = os.path.getsize(result["path"])

                if "size_min" in filters and filters["size_min"] is not None:
                    if file_size < filters["size_min"]:
                        return False

                if "size_max" in filters and filters["size_max"] is not None:
                    if file_size > filters["size_max"]:
                        return False
            except Exception as e:
                self.logger.warning(f"大小过滤失败 {result['path']}: {str(e)}")
                # 如果无法获取文件大小，默认不过滤

        # 所有过滤条件都通过
        return True

    def search_by_path(self, path_pattern: str) -> list[dict]:
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
            query = path_pattern.replace("*", "").replace(
                "?", ""
            )  # 去除通配符，用于初始搜索
            initial_results = self.index_manager.search_text(query, limit=1000)

            # 在初始结果中过滤路径匹配的文件
            for result in initial_results:
                if self._match_path_pattern(result["path"], path_pattern):
                    results.append(result)

            # 按相关性排序
            results.sort(key=lambda x: x["score"], reverse=True)

            return results[: self.max_results]
        except Exception as e:
            self.logger.error(f"按路径搜索失败: {str(e)}")
            return []

    def _match_path_pattern(self, path: str, pattern: str) -> bool:
        """简单的路径模式匹配"""
        # 使用 fnmatch 模块进行模式匹配
        return fnmatch.fnmatch(path.lower(), pattern.lower())

    def get_suggestions(self, query: str, limit: int = 5) -> list[dict]:
        """获取搜索建议"""
        try:
            # 这是一个简化实现，实际可能需要更复杂的建议生成逻辑
            # 例如，可以基于搜索历史、热门搜索词或文档中的关键词

            # 为了简化，我们可以基于当前查询执行一个快速搜索，并返回匹配的文件名作为建议
            results = self.index_manager.search_text(
                query, limit=20
            )  # 获取更多结果以提取建议

            # 提取唯一的文件名作为建议
            suggestions = []
            seen = set()

            for result in results:
                if result["filename"] not in seen:
                    seen.add(result["filename"])
                    suggestions.append(
                        {
                            "text": result["filename"],
                            "type": "filename",
                            "path": result["path"],
                        }
                    )

                # 如果已经收集了足够的建议，就停止
                if len(suggestions) >= limit:
                    break

            return suggestions
        except Exception as e:
            self.logger.error(f"获取搜索建议失败: {str(e)}")
            return []

    def get_search_stats(self) -> Dict[str, Any]:
        """获取搜索统计信息"""
        # 这是一个简化实现，可以根据实际需求扩展
        stats = {
            "text_weight": self.text_weight,
            "vector_weight": self.vector_weight,
            "max_results": self.max_results,
        }

        # 可以添加更多统计信息，例如：
        # - 平均搜索时间
        # - 平均返回结果数量
        # - 搜索类型分布等

        return stats

    def _get_query_words(self, query: str) -> list[str]:
        """从搜索查询中提取查询词"""
        if query:
            # 简单的分词处理，按空格和常见分隔符分割
            words = re.findall(r"\w+", query)
            return words
        return []

    def _get_query_alpha_tokens(self, query: str) -> list[str]:
        """提取查询中的英文/数字关键 token（如 rag、bert、faiss）"""
        if not query:
            return []
        tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
        # 过滤 1 字符噪音 token，保留真正有区分度的关键词
        return [t for t in tokens if len(t) >= 2]

    def _normalize_for_match(self, text: str) -> str:
        """统一文本用于短语匹配：仅保留中英文和数字"""
        if not text:
            return ""
        return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower()))

    def _get_query_cjk_tokens(self, query: str) -> list[str]:
        """提取中文 token，并补充双字切片用于提升召回鲁棒性"""
        if not query:
            return []
        tokens = []
        seen = set()
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", query):
            if chunk not in seen:
                seen.add(chunk)
                tokens.append(chunk)
            # 为 3+ 长度中文词增加双字切片（避免分词边界不一致）
            if len(chunk) >= 3:
                for i in range(len(chunk) - 1):
                    bi = chunk[i : i + 2]
                    if bi not in seen:
                        seen.add(bi)
                        tokens.append(bi)
        return tokens

    def _rerank_results(
        self, query: str, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        对搜索结果进行重排序

        评分因素（可配置）：
        1. ColBERT Reranker（如果启用，短查询跳过）
        2. 基础搜索得分 (rerank_weights['base'])
        3. 文件名匹配度 (rerank_weights['filename'])
        4. 关键词密度 (rerank_weights['keyword'])
        5. 时效性 - 文档新旧 (rerank_weights['recency'])
        6. 文档长度惩罚（避免过长文档）(rerank_weights['length'])
        """
        if not results:
            return results

        # 检测短查询
        query_stripped = query.strip()
        is_short_query = len(query_stripped) <= 2

        # 尝试使用 ColBERT Reranker（短查询跳过以提升性能）
        if (
            not is_short_query
            and hasattr(self, "reranker_manager")
            and self.reranker_manager
        ):
            try:
                reranker_enabled = self.config_loader.getboolean(
                    "reranker", "enabled", True
                )
                if reranker_enabled:
                    top_k = self.config_loader.getint("reranker", "top_k", 5)
                    # 调用 reranker（只对 top 50 进行精排）
                    results_to_rerank = results[:50]
                    reranked = self.reranker_manager.rerank(
                        query, results_to_rerank, top_k=top_k
                    )
                    if reranked:
                        # 合并 rerank 分数到原结果
                        rerank_map = {
                            r.get("path"): r.get("rerank_score", 0) for r in reranked
                        }
                        for result in results:
                            path = result.get("path", "")
                            if path in rerank_map:
                                result["colbert_score"] = rerank_map[path]
                        self.logger.info(
                            f"[SearchEngine] ColBERT rerank 完成, top_k={top_k}"
                        )
            except Exception as e:
                self.logger.warning(f"[SearchEngine] ColBERT rerank 失败: {e}")
        elif is_short_query:
            self.logger.info(
                f"[SearchEngine] 短查询 '{query}' 跳过 ColBERT rerank 以提升性能"
            )

        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))
        alpha_tokens = self._get_query_alpha_tokens(query)
        cjk_tokens = self._get_query_cjk_tokens(query)
        normalized_query = self._normalize_for_match(query)

        # 获取权重配置
        w = self.rerank_weights

        for result in results:
            original_score = result.get("score", 0)
            new_score = 0.0

            # 1. 基础搜索得分
            new_score += original_score * w["base"]

            # 2. 文件名匹配度
            filename = os.path.basename(result.get("path", "")).lower()
            filename_norm = self._normalize_for_match(filename)
            snippet_text = (result.get("snippet", "") or "").lower()
            snippet_norm = self._normalize_for_match(snippet_text)
            filename_score = 0.0

            # 完整查询匹配文件名
            if query_lower in filename:
                filename_score = 100.0
            elif normalized_query and normalized_query in filename_norm:
                # 处理中英文混合查询（如“基于rag的实现”）的强短语匹配
                filename_score = 98.0
            else:
                # 部分匹配
                matched_words = sum(1 for word in query_words if word in filename)
                if matched_words > 0:
                    filename_score = (matched_words / max(len(query_words), 1)) * 80.0

                # 文件名变体匹配（使用常量）
                for variant in FILENAME_VARIANT_KEYWORDS:
                    if (
                        query_lower + variant in filename
                        or variant + query_lower in filename
                    ):
                        filename_score = max(filename_score, 90.0)
                        break

            new_score += filename_score * w["filename"]

            # 2.1 英文关键 token 匹配增强（如 rag/bert/faiss）
            # 语义融合在中文论文场景下容易把“相关但不含关键术语”的结果抬高，
            # 这里对文件名中包含 query 关键术语的文档做显式增强。
            if alpha_tokens:
                alpha_hits = sum(1 for token in alpha_tokens if token in filename)
                alpha_ratio = alpha_hits / len(alpha_tokens)
                if alpha_hits > 0:
                    new_score += 18.0 * alpha_ratio
                    # 所有关键 token 全命中时，给一个强保底，保证直觉排序
                    if alpha_hits == len(alpha_tokens):
                        result["score"] = max(result.get("score", 0.0), 88.0)
                else:
                    # 查询包含明确英文术语但文件名完全不含时轻微降权
                    new_score -= 8.0

            # 2.2 中文关键词覆盖增强（文件名 + 摘要）
            if cjk_tokens:
                lexical_text = f"{filename_norm} {snippet_norm}"
                cjk_hits = sum(1 for token in cjk_tokens if token in lexical_text)
                if cjk_hits > 0:
                    new_score += min(16.0, 4.0 * cjk_hits)
                else:
                    # 语义命中但中文关键词零覆盖时，适度降权避免“跑题文档”上浮
                    if result.get("search_type") == "vector":
                        new_score -= 6.0

            # 3. 关键词密度
            content = (result.get("content", "") or result.get("snippet", "")).lower()
            keyword_count = content.count(query_lower)
            for word in query_words:
                keyword_count += content.count(word)

            keyword_score = min(keyword_count * 2, KEYWORD_SCORE_MAX)
            new_score += keyword_score * w["keyword"]

            # 4. 时效性 - 越新越好
            time_score = 0.0
            try:
                modified_time = result.get("modified")
                if modified_time:
                    if isinstance(modified_time, str):
                        modified_time = datetime.strptime(
                            modified_time, "%Y-%m-%d %H:%M:%S"
                        )
                    days_old = (datetime.now() - modified_time).days
                    time_score = max(0, 20 - days_old * 0.1)
            except Exception:
                pass

            new_score += time_score * w["recency"]

            # 5. 文档长度惩罚 - 避免过长文档
            length_penalty = 0.0
            content_length = len(content)
            if content_length > LENGTH_PENALTY_THRESHOLD_HIGH:
                length_penalty = -5.0
            elif content_length > LENGTH_PENALTY_THRESHOLD_LOW:
                length_penalty = -2.0

            new_score += length_penalty * w["length"]

            # 确保分数在合理范围内
            result["score"] = min(max(new_score, 0.0), 100.0)
            result["original_score"] = original_score

        # 按新分数排序
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def clear_cache(self):
        """清空搜索缓存"""
        if self.enable_cache and self.cache is not None:
            self.cache.clear()
            self.logger.info("搜索缓存已清空")

    def get_cache_stats(self):
        """获取缓存统计信息"""
        if not self.enable_cache or self.cache is None:
            return {"enabled": False}

        stats = self.cache.get_stats()
        return {
            "enabled": True,
            "size": stats.get("total_size", 0),
            "max_size": stats.get("max_size", 0),
            "ttl_seconds": self.cache_ttl,
            "num_shards": stats.get("num_shards", 1),
            "hits": stats.get("hits", 0),
            "misses": stats.get("misses", 0),
            "hit_rate": stats.get("hit_rate", 0.0),
        }

    def search_with_detailed_stats(self, query, filters=None):
        """执行搜索并返回详细统计信息"""
        start_time = time.time()

        # 执行搜索
        results = self.search(query, filters)

        # 计算统计信息
        search_time = time.time() - start_time
        stats = {
            "results_count": len(results),
            "search_time": search_time,
            "query": query,
            "filters_applied": filters is not None and len(filters) > 0,
            "cache_enabled": self.enable_cache,
            "text_weight": self.text_weight,
            "vector_weight": self.vector_weight,
        }

        # 添加缓存统计（如果启用）
        if self.enable_cache:
            stats["cache_stats"] = self.get_cache_stats()

        return results, stats
