#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试性能指标收集模块"""

import pytest
import time
from backend.utils.metrics import Counter, Histogram, Gauge, MetricsCollector, timed


class TestCounter:
    """测试计数器"""

    def test_counter_basic(self):
        """测试计数器基本功能"""
        counter = Counter("test_counter", "Test counter")

        counter.inc()
        assert counter.get() == 1

        counter.inc(5)
        assert counter.get() == 6

    def test_counter_with_labels(self):
        """测试带标签的计数器"""
        counter = Counter("test_counter", "Test counter", labels=["method", "status"])

        counter.inc(1, method="GET", status="200")
        counter.inc(1, method="GET", status="200")
        counter.inc(1, method="POST", status="201")

        assert counter.get(method="GET", status="200") == 2
        assert counter.get(method="POST", status="201") == 1
        assert counter.get(method="DELETE", status="404") == 0


class TestHistogram:
    """测试直方图"""

    def test_histogram_basic(self):
        """测试直方图基本功能"""
        hist = Histogram(
            "test_histogram", "Test histogram", buckets=[0.1, 0.5, 1.0, 2.0]
        )

        hist.observe(0.05)
        hist.observe(0.3)
        hist.observe(0.7)
        hist.observe(1.5)

        # 检查统计
        stats = hist.get_stats()
        assert stats["count"] == 4
        assert stats["sum"] == pytest.approx(2.55, 0.01)

    def test_histogram_buckets(self):
        """测试直方图桶分布"""
        hist = Histogram(
            "test_histogram", "Test histogram", buckets=[0.1, 0.5, 1.0, 2.0]
        )

        hist.observe(0.05)  # 桶 0
        hist.observe(0.3)  # 桶 1
        hist.observe(0.7)  # 桶 2
        hist.observe(1.5)  # 桶 3

        stats = hist.get_stats()
        buckets = stats["buckets"]

        # 检查每个桶的计数（注意：每个桶包含其边界内的值）
        assert buckets[0.1] == 1  # 0.05
        assert buckets[0.5] == 1  # 0.3
        assert buckets[1.0] == 1  # 0.7
        assert buckets[2.0] == 1  # 1.5


class TestGauge:
    """测试仪表盘"""

    def test_gauge_basic(self):
        """测试仪表盘基本功能"""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.set(100)
        assert gauge.get() == 100

        gauge.inc(10)
        assert gauge.get() == 110

        gauge.dec(20)
        assert gauge.get() == 90


class TestMetricsCollector:
    """测试指标收集器"""

    def test_collector_initialization(self):
        """测试收集器初始化"""
        collector = MetricsCollector()

        # 验证默认指标存在
        assert hasattr(collector, "search_duration")
        assert hasattr(collector, "search_results")
        assert hasattr(collector, "files_indexed")
        assert hasattr(collector, "rag_queries")

    def test_collector_get_summary(self):
        """测试获取指标摘要"""
        collector = MetricsCollector()

        # 使用默认指标
        collector.search_results.inc(10)
        collector.files_indexed.inc(5)

        summary = collector.get_summary()

        assert "search_results" in summary
        assert "files_indexed" in summary


class TestTimedDecorator:
    """测试定时装饰器"""

    def test_timed_decorator(self):
        """测试定时装饰器"""
        collector = MetricsCollector()

        @timed(collector.search_duration, status="success")
        def slow_function():
            time.sleep(0.01)
            return "done"

        result = slow_function()

        assert result == "done"

    def test_timed_decorator_with_exception(self):
        """测试定时装饰器处理异常"""
        collector = MetricsCollector()

        @timed(collector.search_duration, status="error")
        def failing_function():
            time.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()
