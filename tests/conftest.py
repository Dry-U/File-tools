import pytest
import tempfile
import shutil
import sys
import os
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock
from typing import Generator, List, Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.utils.config_loader import ConfigLoader


@pytest.fixture
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_config():
    """创建临时配置用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock config
        config = Mock(spec=ConfigLoader)

        # Setup basic config values
        config_data = {
            'system': {
                'data_dir': tmpdir
            },
            'index': {
                'tantivy_path': f'{tmpdir}/tantivy',
                'hnsw_path': f'{tmpdir}/hnsw',
                'metadata_path': f'{tmpdir}/metadata'
            },
            'search': {
                'text_weight': 0.5,
                'vector_weight': 0.5,
                'max_results': 10
            },
            'embedding': {
                'enabled': False
            },
            'ai_model': {
                'enabled': False,
                'interface_type': 'api',
                'api_url': 'http://localhost:8080/v1/chat/completions',
                'context_size': 4096,
                'request_timeout': 30
            },
            'chat_history': {
                'db_path': f'{tmpdir}/chat_history.db'
            },
            'file_scanner': {
                'scan_paths': [tmpdir],
                'batch_size': 100,
                'max_file_size': 100 * 1024 * 1024
            },
            'monitor': {
                'enabled': False
            }
        }

        # Setup mock methods
        def get_side_effect(section, key=None, default=None):
            if key is None:
                return config_data.get(section, default or {})
            return config_data.get(section, {}).get(key, default)

        config.get.side_effect = get_side_effect
        config.getint.side_effect = lambda section, key, default=0: int(config_data.get(section, {}).get(key, default))
        config.getfloat.side_effect = lambda section, key, default=0.0: float(config_data.get(section, {}).get(key, default))
        config.getboolean.side_effect = lambda section, key, default=False: bool(config_data.get(section, {}).get(key, default))

        yield config


@pytest.fixture
def generate_test_data(tmp_path):
    """生成测试数据文件"""
    def _generate(count):
        data_dir = tmp_path / "test_data"
        data_dir.mkdir(exist_ok=True)

        for i in range(count):
            file_path = data_dir / f"doc_{i}.txt"
            file_path.write_text(f"This is test document {i} with some content for searching.", encoding='utf-8')

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
            "modified": 1700000000
        },
        {
            "path": "/test/doc2.txt",
            "filename": "doc2.txt",
            "content": "This document discusses machine learning concepts.",
            "file_type": "txt",
            "size": 2048,
            "modified": 1700000100
        },
        {
            "path": "/test/report.pdf",
            "filename": "report.pdf",
            "content": "Annual report for 2024 with financial data.",
            "file_type": "pdf",
            "size": 10240,
            "modified": 1700000200
        }
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
            "highlights": ["Python programming"]
        },
        {
            "path": "/test/doc2.txt",
            "filename": "doc2.txt",
            "content": "Machine learning basics",
            "score": 0.85,
            "file_type": "txt",
            "highlights": ["Machine learning"]
        }
    ]


@pytest.fixture
def mock_search_engine():
    """模拟搜索引擎"""
    mock = MagicMock()
    mock.search.return_value = [
        {
            "path": "/test/doc1.txt",
            "filename": "doc1.txt",
            "content": "Test content",
            "score": 0.9,
            "file_type": "txt"
        }
    ]
    return mock


@pytest.fixture
def mock_file_scanner():
    """模拟文件扫描器"""
    mock = MagicMock()
    mock.scan_and_index.return_value = {"indexed": 10, "errors": 0}
    mock.index_file.return_value = True
    mock.remove_file.return_value = True
    return mock


@pytest.fixture
def mock_index_manager():
    """模拟索引管理器"""
    mock = MagicMock()
    mock.add_document.return_value = True
    mock.remove_document.return_value = True
    mock.search_text.return_value = []
    mock.search_vector.return_value = []
    return mock
