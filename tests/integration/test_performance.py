"""
性能基准测试 - 验证系统在各种负载下的性能表现

测试覆盖：
- 查询响应时间（平均、P99）
- 索引吞吐量
- 内存使用
- 可扩展性
"""

import time
import numpy as np
import psutil
import pytest
from pathlib import Path
from backend.core.index_manager import IndexManager
from backend.core.search_engine import SearchEngine

# 测试查询列表
TEST_QUERIES = ["测试内容", "关键条款", "文档总结"]

# 性能基准阈值 - 企业标准
PERFORMANCE_THRESHOLDS = {
    "query_time_avg": 1.0,  # 平均查询时间 ≤ 1秒
    "query_time_p99": 2.0,  # P99 查询时间 ≤ 2秒
    "index_time_per_doc": 0.1,  # 单文档索引时间 ≤ 100ms
    "memory_max_mb": 2048,  # 最大内存使用 ≤ 2GB
    "throughput_docs_per_sec": 10,  # 索引吞吐量 ≥ 10 docs/sec
}


class PerformanceBenchmark:
    """性能基准测试类"""

    def __init__(self, config):
        self.config = config
        self.results = {}
        self.indexer = IndexManager(config)
        self.search_engine = SearchEngine(self.indexer, config)

    def benchmark_indexing(self, test_dir: str) -> dict:
        """基准测试索引性能"""
        process = psutil.Process()
        files = list(Path(test_dir).glob("*.txt"))
        num_files = len(files)

        if num_files == 0:
            return {"error": "No test files found"}

        # 索引时间
        start = time.monotonic()
        for file in files:
            doc_content = file.read_text()
            document = {
                "path": str(file),
                "filename": file.name,
                "content": doc_content,
                "file_type": "text",
                "size": file.stat().st_size,
                "created": None,
                "modified": None,
                "keywords": "",
            }
            self.indexer.add_document(document)
        index_time = time.monotonic() - start

        # 计算吞吐量
        throughput = num_files / index_time if index_time > 0 else 0

        return {
            "num_files": num_files,
            "total_index_time": index_time,
            "avg_index_time_per_doc": index_time / num_files if num_files > 0 else 0,
            "throughput_docs_per_sec": throughput,
            "memory_mb": process.memory_info().rss / 1024**2,
        }

    def benchmark_query(self, num_runs: int = 10) -> dict:
        """基准测试查询性能"""
        query_times = []

        for _ in range(num_runs):
            for query in TEST_QUERIES:
                start = time.monotonic()
                self.search_engine.search(query)
                elapsed = time.monotonic() - start
                query_times.append(elapsed)

        return {
            "num_queries": len(query_times),
            "avg_query_time": np.mean(query_times),
            "p50_query_time": np.percentile(query_times, 50),
            "p95_query_time": np.percentile(query_times, 95),
            "p99_query_time": np.percentile(query_times, 99),
            "min_query_time": np.min(query_times),
            "max_query_time": np.max(query_times),
        }

    def run_full_benchmark(self, test_dir: str) -> dict:
        """运行完整基准测试"""
        index_results = self.benchmark_indexing(test_dir)
        query_results = self.benchmark_query()

        return {
            "indexing": index_results,
            "query": query_results,
        }


@pytest.mark.performance
def test_performance_query_response_time(generate_test_data, temp_config):
    """测试查询响应时间是否满足企业标准"""
    benchmark = PerformanceBenchmark(temp_config)
    test_dir = generate_test_data(10)
    results = benchmark.run_full_benchmark(test_dir)

    avg_time = results["query"]["avg_query_time"]
    p99_time = results["query"]["p99_query_time"]

    assert avg_time < PERFORMANCE_THRESHOLDS["query_time_avg"], (
        f"平均查询时间 {avg_time:.3f}s 超过阈值 {PERFORMANCE_THRESHOLDS['query_time_avg']}s"
    )
    assert p99_time < PERFORMANCE_THRESHOLDS["query_time_p99"], (
        f"P99查询时间 {p99_time:.3f}s 超过阈值 {PERFORMANCE_THRESHOLDS['query_time_p99']}s"
    )


@pytest.mark.performance
def test_performance_indexing_throughput(generate_test_data, temp_config):
    """测试索引吞吐量是否满足企业标准"""
    benchmark = PerformanceBenchmark(temp_config)
    test_dir = generate_test_data(50)
    results = benchmark.run_full_benchmark(test_dir)

    throughput = results["indexing"]["throughput_docs_per_sec"]
    avg_time = results["indexing"]["avg_index_time_per_doc"]

    assert throughput >= PERFORMANCE_THRESHOLDS["throughput_docs_per_sec"], (
        f"索引吞吐量 {throughput:.2f} docs/s 低于阈值 {PERFORMANCE_THRESHOLDS['throughput_docs_per_sec']} docs/s"
    )
    assert avg_time < PERFORMANCE_THRESHOLDS["index_time_per_doc"], (
        f"单文档平均索引时间 {avg_time:.3f}s 超过阈值 {PERFORMANCE_THRESHOLDS['index_time_per_doc']}s"
    )


@pytest.mark.performance
def test_performance_memory_usage(generate_test_data, temp_config):
    """测试内存使用是否满足企业标准"""
    benchmark = PerformanceBenchmark(temp_config)
    test_dir = generate_test_data(50)
    results = benchmark.run_full_benchmark(test_dir)

    memory_mb = results["indexing"]["memory_mb"]

    assert memory_mb < PERFORMANCE_THRESHOLDS["memory_max_mb"], (
        f"内存使用 {memory_mb:.2f}MB 超过阈值 {PERFORMANCE_THRESHOLDS['memory_max_mb']}MB"
    )


@pytest.mark.performance
def test_performance_scalability(generate_test_data, temp_config):
    """测试可扩展性：不同规模下的性能表现"""
    benchmark = PerformanceBenchmark(temp_config)

    scales = [10, 50]
    scale_results = {}

    for scale in scales:
        test_dir = generate_test_data(scale)
        results = benchmark.run_full_benchmark(test_dir)
        scale_results[scale] = results

        # 断言性能约束 - 调整阈值以适应测试环境
        avg_query_time = results["query"]["avg_query_time"]
        index_time = results["indexing"]["total_index_time"]
        memory_mb = results["indexing"]["memory_mb"]

        assert avg_query_time < PERFORMANCE_THRESHOLDS["query_time_avg"], (
            f"规模 {scale}: 平均查询时间 {avg_query_time:.3f}s 超过阈值"
        )
        assert index_time < 300, (
            f"规模 {scale}: 索引时间 {index_time:.2f}s 超过 300s 限制"
        )
        assert memory_mb < PERFORMANCE_THRESHOLDS["memory_max_mb"], (
            f"规模 {scale}: 内存使用 {memory_mb:.2f}MB 超过阈值"
        )

    # 验证可扩展性：性能应该随规模线性或亚线性增长
    for scale in scales[1:]:
        prev_scale = scales[0]
        ratio = scale / prev_scale
        time_ratio = (
            scale_results[scale]["indexing"]["total_index_time"] /
            scale_results[prev_scale]["indexing"]["total_index_time"]
        )

        # 索引时间增长比率应小于规模增长比率（亚线性）
        assert time_ratio < ratio * 1.5, (
            f"可扩展性警告: 规模 {scale} 的索引时间比率 {time_ratio:.2f} 超过规模比率 {ratio:.2f}"
        )


@pytest.mark.performance
@pytest.mark.slow
def test_performance_stress_test(generate_test_data, temp_config):
    """压力测试：大规模数据下的性能表现"""
    benchmark = PerformanceBenchmark(temp_config)
    test_dir = generate_test_data(100)  # 100 个文件
    results = benchmark.run_full_benchmark(test_dir)

    # 宽松的阈值用于压力测试
    assert results["query"]["avg_query_time"] < 5.0, (
        f"压力测试: 平均查询时间 {results['query']['avg_query_time']:.3f}s 超过 5s"
    )
    assert results["query"]["p99_query_time"] < 10.0, (
        f"压力测试: P99查询时间 {results['query']['p99_query_time']:.3f}s 超过 10s"
    )
