#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能指标收集模块

提供搜索延迟、缓存命中率等性能指标的收集和导出。
支持 Prometheus 格式导出。
"""

import time
from typing import Dict, Any, Optional, Callable
from functools import wraps
from dataclasses import dataclass, field
from collections import deque
from threading import Lock

from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MetricValue:
    """指标值"""
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """计数器"""

    def __init__(self, name: str, description: str = "", labels: Optional[list] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = Lock()

    def inc(self, value: float = 1.0, **labels):
        """增加计数"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)
        with self._lock:
            self._values[label_tuple] = self._values.get(label_tuple, 0) + value

    def get(self, **labels) -> float:
        """获取当前值"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)
        with self._lock:
            return self._values.get(label_tuple, 0)

    def get_all(self) -> Dict[tuple, float]:
        """获取所有值"""
        with self._lock:
            return self._values.copy()


class Histogram:
    """直方图 - 用于记录分布"""

    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: Optional[list] = None,
        labels: Optional[list] = None
    ):
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self.label_names = labels or []
        self._counts: Dict[tuple, list] = {}
        self._sums: Dict[tuple, float] = {}
        self._lock = Lock()

    def observe(self, value: float, **labels):
        """记录观测值"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)

        with self._lock:
            if label_tuple not in self._counts:
                self._counts[label_tuple] = [0] * (len(self.buckets) + 1)
                self._sums[label_tuple] = 0.0

            self._sums[label_tuple] += value

            # 找到对应的桶
            bucket_idx = len(self.buckets)
            for i, bucket in enumerate(self.buckets):
                if value <= bucket:
                    bucket_idx = i
                    break

            self._counts[label_tuple][bucket_idx] += 1

    def get_stats(self, **labels) -> Dict[str, Any]:
        """获取统计信息"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)

        with self._lock:
            counts = self._counts.get(label_tuple, [0] * (len(self.buckets) + 1))
            total = sum(counts)
            return {
                "count": total,
                "sum": self._sums.get(label_tuple, 0.0),
                "buckets": {b: c for b, c in zip(self.buckets, counts[:-1])},
                "+Inf": counts[-1]
            }


class Gauge:
    """仪表盘 - 用于记录瞬时值"""

    def __init__(self, name: str, description: str = "", labels: Optional[list] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = Lock()

    def set(self, value: float, **labels):
        """设置值"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)
        with self._lock:
            self._values[label_tuple] = value

    def inc(self, value: float = 1.0, **labels):
        """增加值"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)
        with self._lock:
            self._values[label_tuple] = self._values.get(label_tuple, 0) + value

    def dec(self, value: float = 1.0, **labels):
        """减少值"""
        self.inc(-value, **labels)

    def get(self, **labels) -> float:
        """获取当前值"""
        label_tuple = tuple(str(labels.get(k, "")) for k in self.label_names)
        with self._lock:
            return self._values.get(label_tuple, 0)


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._lock = Lock()

        # 初始化默认指标
        self._init_default_metrics()

    def _init_default_metrics(self):
        """初始化默认指标"""
        # 搜索相关指标
        self.search_duration = Histogram(
            "search_duration_seconds",
            "Search request duration in seconds",
            labels=["status"]
        )
        self.search_results = Counter(
            "search_results_total",
            "Total number of search results returned",
            labels=["status"]
        )
        self.search_cache_hits = Counter(
            "search_cache_hits_total",
            "Total number of search cache hits"
        )
        self.search_cache_misses = Counter(
            "search_cache_misses_total",
            "Total number of search cache misses"
        )

        # 文件扫描指标
        self.files_indexed = Counter(
            "files_indexed_total",
            "Total number of files indexed"
        )
        self.files_scanned = Counter(
            "files_scanned_total",
            "Total number of files scanned"
        )
        self.files_skipped = Counter(
            "files_skipped_total",
            "Total number of files skipped"
        )

        # RAG相关指标
        self.chat_requests = Counter(
            "chat_requests_total",
            "Total number of chat requests",
            labels=["status"]
        )
        self.chat_duration = Histogram(
            "chat_duration_seconds",
            "Chat request duration in seconds",
            labels=["status"]
        )
        self.tokens_generated = Counter(
            "tokens_generated_total",
            "Total number of tokens generated"
        )
        self.rag_queries = Counter(
            "rag_queries_total",
            "Total number of RAG queries",
            labels=["status"]
        )

        # 系统指标
        self.active_sessions = Gauge(
            "active_chat_sessions",
            "Number of active chat sessions"
        )
        self.indexed_documents = Gauge(
            "indexed_documents",
            "Total number of indexed documents"
        )
        self.cache_size = Gauge(
            "cache_entries",
            "Current number of cache entries",
            labels=["cache_type"]
        )

        # 错误指标
        self.errors_total = Counter(
            "errors_total",
            "Total number of errors",
            labels=["type"]
        )

    def time_operation(self, metric: Histogram, **labels):
        """上下文管理器用于计时操作"""
        class TimerContext:
            def __init__(self, metric, labels):
                self.metric = metric
                self.labels = labels
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.start_time is not None:
                    duration = time.time() - self.start_time
                    self.metric.observe(duration, **self.labels)
                return False

        return TimerContext(metric, labels)

    def record_cache_hit(self):
        """记录缓存命中"""
        self.search_cache_hits.inc()

    def record_cache_miss(self):
        """记录缓存未命中"""
        self.search_cache_misses.inc()

    def get_cache_hit_rate(self) -> float:
        """获取缓存命中率"""
        hits = self.search_cache_hits.get()
        misses = self.search_cache_misses.get()
        total = hits + misses
        return hits / total if total > 0 else 0.0

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return {
            "search_results": self.search_results.get(),
            "files_indexed": self.files_indexed.get(),
            "cache_hit_rate": self.get_cache_hit_rate(),
            "cache_hits": self.search_cache_hits.get(),
            "cache_misses": self.search_cache_misses.get(),
            "rag_queries": self.rag_queries.get(),
            "chat_requests": self.chat_requests.get(),
            "timestamps": {
                "collected_at": time.time()
            }
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            "search": {
                "cache_hit_rate": self.get_cache_hit_rate(),
                "cache_hits": self.search_cache_hits.get(),
                "cache_misses": self.search_cache_misses.get(),
            },
            "timestamps": {
                "collected_at": time.time()
            }
        }

    def to_prometheus_format(self) -> str:
        """导出为 Prometheus 格式"""
        lines = []

        # 搜索持续时间
        lines.append("# HELP search_duration_seconds Search request duration")
        lines.append("# TYPE search_duration_seconds histogram")
        for (status,), stats in self.search_duration._counts.items():
            label = f'status="{status}"' if status else ""
            for i, bucket in enumerate(self.search_duration.buckets):
                count = sum(stats[:i+1])
                lines.append(f'search_duration_seconds_bucket{{{label},le="{bucket}"}} {count}')
            lines.append(f'search_duration_seconds_bucket{{{label},le="+Inf"}} {sum(stats)}')
            lines.append(f'search_duration_seconds_sum{{{label}}} {self.search_duration._sums.get((status,), 0)}')
            lines.append(f'search_duration_seconds_count{{{label}}} {sum(stats)}')

        # 缓存命中率
        lines.append("# HELP search_cache_hit_rate Cache hit rate")
        lines.append("# TYPE search_cache_hit_rate gauge")
        lines.append(f"search_cache_hit_rate {self.get_cache_hit_rate()}")

        # 错误计数
        lines.append("# HELP errors_total Total errors")
        lines.append("# TYPE errors_total counter")
        for labels, value in self.errors_total.get_all().items():
            error_type = labels[0] if labels else "unknown"
            lines.append(f'errors_total{{type="{error_type}"}} {value}')

        return "\n".join(lines)


# 全局指标收集器实例
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def timed(metric_or_name, **default_labels):
    """装饰器：计时函数执行

    Args:
        metric_or_name: Histogram 对象或指标名称字符串
        **default_labels: 默认标签（可通过 status_label 覆盖状态键名）
    """
    # 检查是否指定了状态标签键名
    status_key = default_labels.pop('status_key', 'status')

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics = get_metrics()
            start = time.time()
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                labels = {**default_labels, status_key: status}
                # 如果传入的是 Histogram 对象，直接使用
                if isinstance(metric_or_name, Histogram):
                    metric_or_name.observe(duration, **labels)
                # 否则按名称从 metrics 获取
                elif hasattr(metrics, metric_or_name):
                    getattr(metrics, metric_or_name).observe(duration, **labels)
        return wrapper
    return decorator


def record_error(error_type: str):
    """记录错误"""
    get_metrics().errors_total.inc(type=error_type)
