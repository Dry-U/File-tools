# tests/conftest.py
import pytest
import tempfile
import os
import sys
from pathlib import Path

# Add the project root to sys.path to allow imports from backend
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.config_loader import ConfigLoader
from backend.core.file_scanner import FileScanner
from backend.core.index_manager import IndexManager
from backend.core.search_engine import SearchEngine
from backend.core.model_manager import ModelManager
from backend.core.rag_pipeline import HybridRetriever
from backend.core.vector_engine import VectorEngine

@pytest.fixture(scope="session")
def temp_config():
    """临时配置fixture"""
    config_data = {
        'system': {'data_dir': tempfile.mkdtemp()},
        'file_scanner': {'scan_paths': [tempfile.mkdtemp()]},
        'model': {'model_dir': tempfile.mkdtemp()}
    }
    config_path = Path(tempfile.mkdtemp()) / 'test_config.yaml'
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(config_data, f)
    yield ConfigLoader(str(config_path))
    # 清理
    os.remove(config_path)

@pytest.fixture
def mock_scanner(temp_config):
    """模拟FileScanner"""
    return FileScanner(temp_config)

@pytest.fixture
def mock_indexer(temp_config):
    """模拟SmartIndexer"""
    return SmartIndexer(temp_config)

@pytest.fixture
def mock_rag(temp_config):
    """模拟RAGPipeline（简化模型）"""
    model_manager = ModelManager(temp_config)
    vector_engine = VectorEngine(temp_config)
    retriever = HybridRetriever(temp_config, vector_engine)
    from backend.core.rag_pipeline import RAGPipeline
    return RAGPipeline(model_manager, temp_config, retriever)

@pytest.fixture
def generate_test_data(tmp_path):
    """生成测试数据目录fixture"""
    def _generate(scale: int):
        test_dir = tmp_path / f"scale_{scale}"
        test_dir.mkdir()
        for i in range(scale):
            file_path = test_dir / f"test_{i}.txt"
            with open(file_path, 'w') as f:
                f.write(f"测试内容 {i}")
        return str(test_dir)
    return _generate