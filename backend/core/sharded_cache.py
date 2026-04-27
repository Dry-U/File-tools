#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
缓存实现 - 使用 cachetools 库

提供线程安全的 TTL 缓存，替代自实现的分片缓存。
"""

import threading
from typing import Any, Dict, Optional

from cachetools import TTLCache

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class Shard:
    """单个缓存分片（保留接口兼容）"""

    def __init__(self, max_size: int):
        self.max_size = max_size
        self._stats = {"hits": 0, "misses": 0}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float) -> Optional[Any]:
        """获取缓存值"""
        # 注：cachetools.TTLCache 不支持按 key 设置不同 TTL
        # 这里 ttl 参数被忽略，使用外层的 TTL 设置
        raise NotImplementedError("Use ShardedCache directly")

    def put(self, key: str, value: Any) -> None:
        """设置缓存值"""
        raise NotImplementedError("Use ShardedCache directly")

    def clear(self) -> None:
        """清空分片"""
        raise NotImplementedError("Use ShardedCache directly")

    def get_stats(self) -> Dict[str, int]:
        """获取分片统计"""
        with self._lock:
            return {"size": 0, "max_size": self.max_size}


class ThreadSafeTTLCache:
    """
    线程安全的 TTL 缓存包装器

    使用 cachetools.TTLCache 并添加线程安全支持。
    """

    def __init__(self, max_size: int = 1000, ttl: float = 3600):
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=max_size, ttl=ttl)
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                self._stats["hits"] += 1
                return self._cache[key]
            self._stats["misses"] += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self._lock:
            # 先删除旧值（如果存在）
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = value

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0}

    def set_ttl(self, ttl: float) -> None:
        """重新创建带新 TTL 的缓存"""
        with self._lock:
            # TTLCache 不支持动态修改 TTL，需要重建
            max_size = self._cache.maxsize
            self._cache = TTLCache(maxsize=max_size, ttl=ttl)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            hits = self._stats["hits"]
            misses = self._stats["misses"]
            total_requests = hits + misses
            return {
                "total_size": len(self._cache),
                "max_size": self._cache.maxsize,
                "ttl": self._cache.ttl,
                "hits": hits,
                "misses": misses,
                "hit_rate": hits / total_requests if total_requests > 0 else 0.0,
            }


# 别名：保持向后兼容
ShardedCache = ThreadSafeTTLCache


class LRUCache:
    """
    简单的线程安全LRU缓存

    使用 cachetools.LRUCache 并添加线程安全支持。
    """

    def __init__(self, max_size: int = 100, ttl: float = 3600):
        from cachetools import LRUCache as _LRUCache

        self._cache: _LRUCache[str, Any] = _LRUCache(maxsize=max_size)
        self._ttl = ttl
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None
            self._stats["hits"] += 1
            return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0}

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                "size": len(self._cache),
                "max_size": self._cache.maxsize,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": self._stats["hits"] / total if total > 0 else 0.0,
            }
