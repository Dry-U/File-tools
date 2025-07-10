# tests/conftest.py
import pytest
import tempfile
import os
from pathlib import Path
from src.utils.config_loader import ConfigLoader
from src.core.file_scanner import FileScanner
from src.core.smart_indexer import SmartIndexer
from src.core.rag_pipeline import RAGPipeline
from src.core.model_manager import ModelManager
from src.core.hybrid_retriever import HybridRetriever
from src.core.vector_engine import VectorEngine

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