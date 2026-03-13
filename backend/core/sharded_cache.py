#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分片缓存实现

使用分片锁减少并发竞争，提高多线程环境下的缓存性能。
"""

import time
import hashlib
from collections import OrderedDict
from typing import Dict, Any, Optional, Generic, TypeVar
from threading import RLock

from backend.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class Shard:
    """单个缓存分片"""

    def __init__(self, max_size: int):
        self.max_size = max_size
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.lock = RLock()

    def get(self, key: str, ttl: float) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key not in self.cache:
                return None

            # 检查是否过期
            if time.time() - self.timestamps[key] > ttl:
                del self.cache[key]
                del self.timestamps[key]
                return None

            # LRU: 移到末尾
            value = self.cache.pop(key)
            self.cache[key] = value
            return value

    def put(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self.lock:
            # 如果已存在，更新
            if key in self.cache:
                self.cache.pop(key)
            # 如果满了，移除最旧的
            elif len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]

            self.cache[key] = value
            self.timestamps[key] = time.time()

    def clear(self) -> None:
        """清空分片"""
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()

    def get_stats(self) -> Dict[str, int]:
        """获取分片统计"""
        with self.lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size
            }


class ShardedCache:
    """
    分片缓存

    将缓存分成多个分片，每个分片有自己的锁，减少锁竞争。
    """

    DEFAULT_NUM_SHARDS = 16

    def __init__(self, max_size: int = 1000, num_shards: int = DEFAULT_NUM_SHARDS):
        self.max_size = max_size
        self.num_shards = num_shards
        self.shard_size = max(1, max_size // num_shards)
        self.shards: list[Shard] = [Shard(self.shard_size) for _ in range(num_shards)]
        self.ttl: float = 3600  # 默认1小时
        self._stats = {'hits': 0, 'misses': 0}
        self._stats_lock = RLock()

    def _get_shard_index(self, key: str) -> int:
        """根据key计算分片索引"""
        # 使用MD5哈希保证均匀分布
        hash_val = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return hash_val % self.num_shards

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        shard_idx = self._get_shard_index(key)
        value = self.shards[shard_idx].get(key, self.ttl)

        with self._stats_lock:
            if value is not None:
                self._stats['hits'] += 1
            else:
                self._stats['misses'] += 1

        return value

    def put(self, key: str, value: Any) -> None:
        """设置缓存值"""
        shard_idx = self._get_shard_index(key)
        self.shards[shard_idx].put(key, value)

    def clear(self) -> None:
        """清空所有缓存"""
        for shard in self.shards:
            shard.clear()
        with self._stats_lock:
            self._stats = {'hits': 0, 'misses': 0}

    def set_ttl(self, ttl: float) -> None:
        """设置TTL"""
        self.ttl = ttl

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        shard_stats = [shard.get_stats() for shard in self.shards]
        total_size = sum(s['size'] for s in shard_stats)

        with self._stats_lock:
            hits = self._stats['hits']
            misses = self._stats['misses']

        total_requests = hits + misses
        hit_rate = hits / total_requests if total_requests > 0 else 0.0

        return {
            'total_size': total_size,
            'max_size': self.max_size,
            'num_shards': self.num_shards,
            'hits': hits,
            'misses': misses,
            'hit_rate': hit_rate,
            'shard_stats': shard_stats
        }


class LRUCache:
    """
    简单的线程安全LRU缓存（非分片，用于小缓存）
    """

    def __init__(self, max_size: int = 100, ttl: float = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.lock = RLock()
        self._stats = {'hits': 0, 'misses': 0}

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key not in self.cache:
                self._stats['misses'] += 1
                return None

            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                self._stats['misses'] += 1
                return None

            self._stats['hits'] += 1
            value = self.cache.pop(key)
            self.cache[key] = value
            return value

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.pop(key)
            elif len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]

            self.cache[key] = value
            self.timestamps[key] = time.time()

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()
            self._stats = {'hits': 0, 'misses': 0}

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            total = self._stats['hits'] + self._stats['misses']
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': self._stats['hits'] / total if total > 0 else 0.0
            }
