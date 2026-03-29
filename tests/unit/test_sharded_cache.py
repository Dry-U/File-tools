#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试分片缓存模块"""

import time
import threading
from backend.core.sharded_cache import Shard, ShardedCache, LRUCache


class TestShard:
    """测试单个分片"""

    def test_shard_basic_operations(self):
        """测试分片基本操作"""
        shard = Shard(max_size=10)

        # 测试 put 和 get
        shard.put("key1", "value1")
        assert shard.get("key1", ttl=3600) == "value1"

        # 测试不存在的 key
        assert shard.get("nonexistent", ttl=3600) is None

    def test_shard_ttl_expiration(self):
        """测试分片 TTL 过期"""
        shard = Shard(max_size=10)

        shard.put("key1", "value1")
        # 立即获取应该存在
        assert shard.get("key1", ttl=1) == "value1"

        # 等待过期
        time.sleep(1.1)
        assert shard.get("key1", ttl=1) is None

    def test_shard_lru_eviction(self):
        """测试分片 LRU 淘汰"""
        shard = Shard(max_size=3)

        shard.put("key1", "value1")
        shard.put("key2", "value2")
        shard.put("key3", "value3")

        # 访问 key1，使其变为最近使用
        shard.get("key1", ttl=3600)

        # 添加新 key，应该淘汰 key2
        shard.put("key4", "value4")

        assert shard.get("key1", ttl=3600) == "value1"
        assert shard.get("key2", ttl=3600) is None
        assert shard.get("key3", ttl=3600) == "value3"
        assert shard.get("key4", ttl=3600) == "value4"

    def test_shard_stats(self):
        """测试分片统计"""
        shard = Shard(max_size=10)

        shard.put("key1", "value1")
        shard.put("key2", "value2")

        stats = shard.get_stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 10


class TestShardedCache:
    """测试分片缓存"""

    def test_sharded_cache_basic(self):
        """测试分片缓存基本功能"""
        cache = ShardedCache(max_size=100, num_shards=4)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None

    def test_sharded_cache_stats(self):
        """测试分片缓存统计"""
        cache = ShardedCache(max_size=100, num_shards=4)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # 命中一次
        cache.get("key1")
        # 未命中一次
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats["total_size"] == 2
        assert stats["max_size"] == 100
        assert stats["num_shards"] == 4
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_sharded_cache_clear(self):
        """测试清空缓存"""
        cache = ShardedCache(max_size=100, num_shards=4)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

        stats = cache.get_stats()
        assert stats["total_size"] == 0
        # 注意：clear 不清除统计信息

    def test_sharded_cache_concurrent_access(self):
        """测试并发访问"""
        cache = ShardedCache(max_size=1000, num_shards=16)
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
