#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试缓存模块 - 使用 cachetools 实现"""

import threading
import time

from backend.core.sharded_cache import LRUCache, ShardedCache


class TestShardedCache:
    """测试缓存（基于 cachetools TTLCache）"""

    def test_sharded_cache_basic(self):
        """测试缓存基本功能"""
        cache = ShardedCache(max_size=100)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None

    def test_sharded_cache_stats(self):
        """测试缓存统计"""
        cache = ShardedCache(max_size=100)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # 命中一次
        cache.get("key1")
        # 未命中一次
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats["total_size"] == 2
        assert stats["max_size"] == 100
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_sharded_cache_clear(self):
        """测试清空缓存"""
        cache = ShardedCache(max_size=100)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

        stats = cache.get_stats()
        assert stats["total_size"] == 0

    def test_sharded_cache_concurrent_access(self):
        """测试并发访问"""
        cache = ShardedCache(max_size=1000)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.put(f"key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=writer))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发访问出错: {errors}"

    def test_sharded_cache_ttl_expiration(self):
        """测试 TTL 过期"""
        cache = ShardedCache(max_size=100, ttl=1)

        cache.put("key1", "value1")
        # 立即获取应该存在
        assert cache.get("key1") == "value1"

        # 等待过期
        time.sleep(1.5)
        assert cache.get("key1") is None

    def test_sharded_cache_max_size(self):
        """测试缓存大小限制"""
        cache = ShardedCache(max_size=3)

        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")

        # 添加新 key 会淘汰最旧的
        cache.put("key4", "value4")

        stats = cache.get_stats()
        assert stats["total_size"] == 3


class TestLRUCache:
    """测试 LRU 缓存"""

    def test_lru_cache_basic(self):
        """测试 LRU 缓存基本功能"""
        cache = LRUCache(max_size=10, ttl=3600)

        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.get("nonexistent") is None

    def test_lru_cache_stats(self):
        """测试 LRU 缓存统计"""
        cache = LRUCache(max_size=10, ttl=3600)

        cache.put("key1", "value1")
        cache.get("key1")  # 命中
        cache.get("key2")  # 未命中

        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
