"""
pytest 配置文件 - 测试环境和 fixtures

包含：
- CI 环境兼容配置（tantivy/hnswlib mock）
- 统一的 mock 配置工厂
- 并发测试支持
- 共享 fixtures
"""

import concurrent.futures
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, Mock

import pytest

# 添加项目根目录到Python路径（只需在顶层 conftest.py 中添加一次）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# CI 环境下 tantivy/hnswlib 的 Rust 编译库可能使用不可用的 CPU 指令集（如 AVX-512），
# 导致 import 时发生 Illegal instruction 崩溃（Python 无法捕获）。
# 在 CI 或显式设置 CI_MOCK_NATIVE 时，用 mock 替代原生模块。
_CI_ENV = (
    os.environ.get("CI", "") == "true" or os.environ.get("CI_MOCK_NATIVE", "") == "true"
)
if _CI_ENV:
    for _mod_name in ["tantivy", "tantivy.tantivy", "hnswlib"]:
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = MagicMock()

from backend.utils.config_loader import ConfigLoader
from tests.factories import MockConfigFactory


class MockSearchEngineFactory:
    """搜索引擎 Mock 工厂"""

    @staticmethod
    def create_basic(search_results: List[Dict] = None) -> Mock:
        """创建基础搜索引擎 Mock"""
        engine = Mock()
        engine.search.return_value = search_results or [
            {
                "path": "/test/doc1.txt",
                "filename": "doc1.txt",
                "content": "Test content",
                "score": 0.9,
                "file_type": "txt",
                "highlights": ["Test"],
            }
        ]
        engine.search_text.return_value = []
        engine.search_vector.return_value = []
        return engine

    @staticmethod
    def create_with_results(results: List[Dict]) -> Mock:
        """创建带有指定结果的搜索引擎 Mock"""
        engine = Mock()
        engine.search.return_value = results
        return engine

    @staticmethod
    def create_empty() -> Mock:
        """创建返回空结果的搜索引擎 Mock"""
        engine = Mock()
        engine.search.return_value = []
        engine.search_text.return_value = []
        engine.search_vector.return_value = []
        return engine


class MockRAGPipelineFactory:
    """RAG 管道 Mock 工厂"""

    @staticmethod
    def create_basic(answer: str = "Test answer", sources: List[str] = None) -> Mock:
        """创建基础 RAG Mock"""
        pipeline = Mock()
        pipeline.query.return_value = {
            "answer": answer,
            "sources": sources or ["/test/doc.txt"],
            "documents": [],
        }
        pipeline.get_all_sessions.return_value = []
        pipeline.clear_session.return_value = True
        return pipeline

    @staticmethod
    def create_with_sessions(sessions: List[Dict]) -> Mock:
        """创建带有会话列表的 RAG Mock"""
        pipeline = Mock()
        pipeline.query.return_value = {"answer": "OK", "sources": []}
        pipeline.get_all_sessions.return_value = sessions
        return pipeline


class MockIndexManagerFactory:
    """索引管理器 Mock 工厂"""

    @staticmethod
    def create_basic() -> Mock:
        """创建基础索引管理器 Mock"""
        manager = Mock()
        manager.add_document.return_value = True
        manager.remove_document.return_value = True
        manager.search_text.return_value = []
        manager.search_vector.return_value = []
        manager.get_document_content.return_value = "Test document content"
        manager.rebuild_index.return_value = True
        return manager

    @staticmethod
    def create_with_documents(docs: List[Dict]) -> Mock:
        """创建带有文档的索引管理器 Mock"""
        manager = Mock()
        manager.add_document.return_value = True
        manager.remove_document.return_value = True
        manager.search_text.return_value = docs
        manager.search_vector.return_value = []
        manager.get_document_content.return_value = docs[0]["content"] if docs else ""
        return manager


# =============================================================================
# 辅助函数
# =============================================================================


def run_concurrent_test(
    func: Callable,
    args_list: List[tuple],
    max_workers: int = 4,
    timeout: float = 10.0,
) -> List[Any]:
    """
    运行并发测试的辅助函数

    Args:
        func: 要并发执行的函数
        args_list: 参数列表，每个元素是一个 tuple
        max_workers: 最大工作线程数
        timeout: 超时时间（秒）

    Returns:
        函数执行结果列表
    """
    results = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_args = {executor.submit(func, *args): args for args in args_list}

        for future in concurrent.futures.as_completed(future_to_args, timeout=timeout):
            args = future_to_args[future]
            try:
                results.append(future.result())
            except Exception as e:
                errors.append((args, e))

    if errors:
        raise AssertionError(
            f"并发测试失败 {len(errors)}/{len(args_list)} 个线程出错: {errors}"
        )

    return results


def assert_thread_safe(
    func: Callable, args_list: List[tuple], repetitions: int = 3
) -> None:
    """
    验证函数线程安全的辅助函数

    Args:
        func: 要测试的函数
        args_list: 参数列表
        repetitions: 重复次数（确保结果一致）
    """
    # 运行多次验证结果一致性
    results = []
    for _ in range(repetitions):
        result = run_concurrent_test(func, args_list)
        results.append(result)

    # 验证所有结果一致
    first = results[0]
    for i, r in enumerate(results[1:], 1):
        assert r == first, (
            f"线程安全测试失败: 第 0 次和第 {i} 次运行结果不一致。"
            f"结果0: {first}, 结果{i}: {r}"
        )


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_config_loader():
    """自动重置ConfigLoader单例，确保每个测试使用独立配置"""
    ConfigLoader.reset_instance()
    yield
    ConfigLoader.reset_instance()


# 导出工厂实例
mock_config = MockConfigFactory()
mock_search = MockSearchEngineFactory()
mock_rag = MockRAGPipelineFactory()
mock_index = MockIndexManagerFactory()


@pytest.fixture
def temp_config(tmp_path):
    """创建临时配置用于测试 - 使用 pytest 的 tmp_path fixture"""
    # 使用 pytest 的 tmp_path 获取临时目录，更现代且自动清理
    config = MockConfigFactory.create_config(
        {
            "system": {"data_dir": str(tmp_path)},
            "index": {
                "tantivy_path": str(tmp_path / "tantivy"),
                "hnsw_path": str(tmp_path / "hnsw"),
                "metadata_path": str(tmp_path / "metadata"),
            },
            "chat_history": {"db_path": str(tmp_path / "chat_history.db")},
            "file_scanner": {
                "scan_paths": [str(tmp_path / "documents")],
                "max_file_size": 100 * 1024 * 1024,
            },
        }
    )
    yield config


@pytest.fixture
def mock_config_loader():
    """统一格式的 Mock 配置加载器"""
    return MockConfigFactory.create_config()


@pytest.fixture
def mock_config_minimal():
    """最小配置 - 仅包含必需字段"""
    return MockConfigFactory.create_minimal_config()


@pytest.fixture
def mock_config_for_search():
    """搜索专用配置"""
    return MockConfigFactory.create_search_config()


@pytest.fixture
def mock_config_for_rag():
    """RAG 专用配置"""
    return MockConfigFactory.create_rag_config()


@pytest.fixture
def generate_test_data(tmp_path):
    """生成测试数据文件"""

    def _generate(count):
        data_dir = tmp_path / "test_data"
        data_dir.mkdir(exist_ok=True)

        for i in range(count):
            file_path = data_dir / f"doc_{i}.txt"
            file_path.write_text(
                f"This is test document {i} with some content for searching.",
                encoding="utf-8",
            )

        return str(data_dir)

    return _generate


@pytest.fixture
def mock_embedding_model():
    """模拟嵌入模型"""
    mock = MagicMock()
    mock.embed.return_value = [[0.1] * 384]  # 384维向量
    mock.embed_query.return_value = [0.1] * 384
    return mock


@pytest.fixture
def mock_llm():
    """模拟语言模型"""
    mock = MagicMock()
    mock.generate.return_value = "这是一个测试回答"
    mock.generate_stream.return_value = iter(["这", "是", "一个", "测试", "回答"])
    return mock


@pytest.fixture
def test_db_path(tmp_path):
    """临时测试数据库路径"""
    return str(tmp_path / "test.db")


@pytest.fixture
def sample_documents() -> List[Dict[str, Any]]:
    """样本文档数据"""
    return [
        {
            "path": "/test/doc1.txt",
            "filename": "doc1.txt",
            "content": "This is a test document about Python programming.",
            "file_type": "txt",
            "size": 1024,
            "modified": 1700000000,
        },
        {
            "path": "/test/doc2.txt",
            "filename": "doc2.txt",
            "content": "This document discusses machine learning concepts.",
            "file_type": "txt",
            "size": 2048,
            "modified": 1700000100,
        },
        {
            "path": "/test/report.pdf",
            "filename": "report.pdf",
            "content": "Annual report for 2024 with financial data.",
            "file_type": "pdf",
            "size": 10240,
            "modified": 1700000200,
        },
    ]


@pytest.fixture
def sample_search_results() -> List[Dict[str, Any]]:
    """样本搜索结果"""
    return [
        {
            "path": "/test/doc1.txt",
            "filename": "doc1.txt",
            "content": "Python programming guide",
            "score": 0.95,
            "file_type": "txt",
            "highlights": ["Python programming"],
        },
        {
            "path": "/test/doc2.txt",
            "filename": "doc2.txt",
            "content": "Machine learning basics",
            "score": 0.85,
            "file_type": "txt",
            "highlights": ["Machine learning"],
        },
    ]


@pytest.fixture
def mock_search_engine():
    """模拟搜索引擎 - 使用工厂模式"""
    return MockSearchEngineFactory.create_basic()


@pytest.fixture
def mock_search_engine_with_results(sample_search_results):
    """模拟搜索引擎 - 带有预设搜索结果"""
    return MockSearchEngineFactory.create_with_results(sample_search_results)


@pytest.fixture
def mock_search_engine_empty():
    """模拟搜索引擎 - 返回空结果"""
    return MockSearchEngineFactory.create_empty()


@pytest.fixture
def mock_file_scanner():
    """模拟文件扫描器"""
    mock = MagicMock()
    mock.scan_and_index.return_value = {"indexed": 10, "errors": 0}
    mock.index_file.return_value = True
    mock.remove_file.return_value = True
    mock.scan_paths = ["./test"]
    return mock


@pytest.fixture
def mock_index_manager():
    """模拟索引管理器 - 使用工厂模式"""
    return MockIndexManagerFactory.create_basic()


@pytest.fixture
def mock_index_manager_with_docs(sample_documents):
    """模拟索引管理器 - 带有预设文档"""
    return MockIndexManagerFactory.create_with_documents(sample_documents)


@pytest.fixture
def mock_rag_pipeline():
    """模拟 RAG 管道"""
    return MockRAGPipelineFactory.create_basic()


@pytest.fixture
def mock_rag_pipeline_with_sessions():
    """模拟 RAG 管道 - 带有预设会话"""
    sessions = [
        {"session_id": "sess1", "title": "Session 1", "message_count": 5},
        {"session_id": "sess2", "title": "Session 2", "message_count": 10},
    ]
    return MockRAGPipelineFactory.create_with_sessions(sessions)


# =============================================================================
# 边界值测试数据
# =============================================================================


@pytest.fixture
def edge_case_search_queries() -> List[str]:
    """边界值搜索查询 - 各种极端情况"""
    return [
        "",  # 空字符串
        "a",  # 单字符
        "中",  # 单个中文字符
        " " * 100,  # 大量空格
        "a" * 1000,  # 超长查询
        "中" * 500,  # 超长中文查询
        "Python\nC++\nJava",  # 包含换行符
        "Tab\there",  # 包含 Tab
        "<script>alert('xss')</script>",  # XSS 攻击尝试
        "../../../etc/passwd",  # 路径遍历
        "\x00Null",  # 空字节注入
        "中文English混合123",  # 中英混合
        "!@#$%^&*()_+-=[]{}|;':\",./<>?",  # 特殊字符
        "   前导空格",  # 前导空格
        "尾部空格   ",  # 尾部空格
        "  前后空格  ",  # 前后空格
        None,  # None 值（需要特殊处理）
    ]


@pytest.fixture
def edge_case_document_paths() -> List[str]:
    """边界值文档路径"""
    return [
        "/test/doc.txt",
        "/test/doc with spaces.txt",
        "/test/中文文件名.txt",
        "/test/dir/../doc.txt",  # 路径遍历
        "/test/dir/./doc.txt",  # 路径简化
        "/test//double/slash.txt",  # 双斜杠
        "/test\\windows\\path.txt",  # Windows 路径
        "/very/long/path/" + "a" * 200 + ".txt",  # 超长路径
        "/test/unicode_\u4e2d\u6587.txt",  # Unicode
        "/test/hidden_.txt",  # 隐藏文件
        "/test/.hidden.txt",  # 点文件
    ]


@pytest.fixture
def edge_case_file_sizes() -> List[int]:
    """边界值文件大小"""
    return [
        0,  # 空文件
        1,  # 最小文件
        512,  # 512 字节
        1024,  # 1KB
        1024 * 100,  # 100KB
        1024 * 1024,  # 1MB
        1024 * 1024 * 10,  # 10MB
        1024 * 1024 * 50,  # 50MB
        1024 * 1024 * 100,  # 100MB (最大限制)
        1024 * 1024 * 101,  # 超过最大限制
    ]


@pytest.fixture
def edge_case_scores() -> List[float]:
    """边界值分数"""
    return [
        0.0,  # 最小分数
        0.001,  # 接近零
        0.5,  # 中等分数
        0.999,  # 接近一
        1.0,  # 最大分数
        -0.001,  # 负数（不应出现）
        1.5,  # 超过一（不应出现）
        float("inf"),  # 无穷大
        float("-inf"),  # 负无穷
        float("nan"),  # 非数字
    ]


@pytest.fixture
def edge_case_timestamps() -> List[float]:
    """边界值时间戳"""
    return [
        0.0,  # Unix 纪元开始
        1.0,  # 最小正数
        946684800.0,  # 2000-01-01
        1700000000.0,  # 2023-11-15
        1735689600.0,  # 2025-01-01
        time.time(),  # 当前时间
        time.time() + 86400 * 365 * 10,  # 未来10年
        -1.0,  # 负数（无效）
        float("inf"),  # 无穷大
    ]


@pytest.fixture
def edge_case_user_inputs() -> List[Dict[str, Any]]:
    """边界值用户输入 - 用于负面测试"""
    return [
        # 空输入
        {"query": ""},
        {"query": "   "},
        # None 输入
        {"query": None},
        # 超长输入
        {"query": "x" * 10000},
        # 特殊字符
        {"query": "\x00\x01\x02"},
        {"query": "\uffff\ufffe"},  # Unicode 替换字符
        # SQL 注入尝试
        {"query": "'; DROP TABLE users; --"},
        # 代码注入尝试
        {"query": "{{constructor.constructor('alert(1)')()}}"},
    ]


# =============================================================================
# 并发测试 Fixtures
# =============================================================================


@pytest.fixture
def thread_safe_counter():
    """
    线程安全计数器 - 用于测试并发访问

    返回一个包含计数器和锁的对象
    """

    class Counter:
        def __init__(self):
            self.value = 0
            self._lock = threading.Lock()

        def increment(self):
            with self._lock:
                self.value += 1
                return self.value

        def get(self):
            with self._lock:
                return self.value

        def reset(self):
            with self._lock:
                self.value = 0

    return Counter()


@pytest.fixture
def concurrentExecutor():
    """
    提供一个线程池执行器用于并发测试

    使用方法:
        def test_concurrent(capfd, concurrentExecutor):
            with concurrentExecutor(max_workers=4) as executor:
                futures = [executor.submit(func, arg) for arg in args]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]
    """
    return concurrent.futures.ThreadPoolExecutor


@pytest.fixture
def shared_state_dict():
    """
    提供一个线程安全的共享字典用于测试

    用于测试多个线程同时读写共享状态的场景
    """

    class ThreadSafeDict:
        def __init__(self):
            self._data = {}
            self._lock = threading.RLock()

        def set(self, key, value):
            with self._lock:
                self._data[key] = value

        def get(self, key, default=None):
            with self._lock:
                return self._data.get(key, default)

        def update(self, mapping):
            with self._lock:
                self._data.update(mapping)

        def delete(self, key):
            with self._lock:
                if key in self._data:
                    del self._data[key]

        def keys(self):
            with self._lock:
                return list(self._data.keys())

        def values(self):
            with self._lock:
                return list(self._data.values())

        def items(self):
            with self._lock:
                return list(self._data.items())

        def __len__(self):
            with self._lock:
                return len(self._data)

        def clear(self):
            with self._lock:
                self._data.clear()

    return ThreadSafeDict()


# =============================================================================
# 断言增强
# =============================================================================


class AssertMessages:
    """统一的断言错误消息模板"""

    # 搜索相关
    SEARCH_RESULT_COUNT = "搜索结果数量不符合预期"
    SEARCH_RESULT_TYPE = "搜索结果类型错误"
    SEARCH_SCORE_RANGE = "搜索分数超出有效范围 [0, 1]"
    SEARCH_RESULT_SORTED = "搜索结果未按分数降序排列"

    # 配置相关
    CONFIG_TYPE = "配置值类型错误"
    CONFIG_VALUE = "配置值不符合预期"
    CONFIG_MISSING = "缺少必需的配置项"

    # RAG 相关
    RAG_ANSWER_TYPE = "RAG 回答类型错误"
    RAG_SOURCES_TYPE = "RAG 来源列表类型错误"
    RAG_SESSION_TYPE = "RAG 会话类型错误"

    # 并发相关
    THREAD_SAFE_COUNT = "并发计数不一致，存在线程安全问题"
    CONCURRENT_RESULT = "并发执行结果不一致"
    RACE_CONDITION = "检测到竞态条件"

    # 边界值
    EDGE_CASE_HANDLING = "边界值处理错误"
    INVALID_INPUT_REJECTED = "无效输入未被正确拒绝"
    VALID_INPUT_REJECTED = "有效输入被错误拒绝"


@pytest.fixture
def assert_msg():
    """提供统一断言消息的 fixture"""
    return AssertMessages
