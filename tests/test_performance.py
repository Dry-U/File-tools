# tests/test_performance.py
import time
import numpy as np
import psutil
import pytest
from src.core.smart_indexer import SmartIndexer
from src.core.hybrid_retriever import HybridRetriever
from src.core.vector_engine import VectorEngine

TEST_QUERIES = ["测试内容", "关键条款", "文档总结"]

class PerformanceBenchmark:
    def __init__(self, config):
        self.config = config
        self.results = {}
        self.indexer = SmartIndexer(config)
        self.vector_engine = VectorEngine(config)
        self.retriever = HybridRetriever(config, self.vector_engine)

    def test_scalability(self, scale: int, test_dir: str):
        """测试可扩展性：索引时间、查询时间、内存"""
        process = psutil.Process()

        # 索引时间
        start = time.monotonic()
        for file in Path(test_dir).glob('*.txt'):
            self.indexer.add_change(str(file), 'update')
        self.indexer.process_changes()
        index_time = time.monotonic() - start

        # 查询时间
        query_times = []
        for query in TEST_QUERIES:
            start = time.monotonic()
            self.retriever.search(query, top_k=5)
            query_times.append(time.monotonic() - start)

        # 内存使用
        mem_usage = process.memory_info().rss / 1024**2  # MB

        self.results[f"scale_{scale}"] = {
            'index_time': index_time,
            'avg_query_time': np.mean(query_times),
            'p99_query_time': np.percentile(query_times, 99),
            'max_memory': mem_usage
        }
        return self.results

@pytest.mark.performance
def test_performance_scalability(generate_test_data, temp_config):
    benchmark = PerformanceBenchmark(temp_config)
    for scale in [1000, 10000]:  # 简化；文档有100_000但本地测试慢
        test_dir = generate_test_data(scale)
        results = benchmark.test_scalability(scale, test_dir)
        
        # 断言性能约束（基于文档5.2）
        assert results[f"scale_{scale}"]['avg_query_time'] < 0.3  # ≤300ms
        assert results[f"scale_{scale}"]['index_time'] < 60  # 假设<1min
        assert results[f"scale_{scale}"]['max_memory'] < 6000  # <6GB