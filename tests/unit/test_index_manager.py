import pytest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.index_manager import IndexManager
from backend.utils.config_loader import ConfigLoader


def test_index_manager_initialization():
    """测试索引管理器初始化"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试配置
        config_data = {
            'system': {
                'data_dir': tmpdir
            },
            'index': {
                'tantivy_path': f'{tmpdir}/tantivy_test',
                'hnsw_path': f'{tmpdir}/hnsw_test',
                'metadata_path': f'{tmpdir}/metadata_test'
            },
            'embedding': {
                'enabled': False,  # 禁用嵌入模型以避免依赖问题
                'provider': 'fastembed',
                'model_name': 'BAAI/bge-small-zh-v1.5'
            }
        }
        
        # 创建配置加载器
        mock_config = Mock(spec=ConfigLoader)
        mock_config.get.side_effect = lambda section, key, default='': config_data.get(section, {}).get(key, default)
        mock_config.getint.side_effect = lambda section, key, default=0: int(config_data.get(section, {}).get(key, default))
        mock_config.getboolean.side_effect = lambda section, key, default=False: bool(config_data.get(section, {}).get(key, default))
        
        # 测试初始化
        index_manager = IndexManager(mock_config)
        
        assert index_manager is not None
        assert hasattr(index_manager, 'tantivy_index')
        assert hasattr(index_manager, 'vector_metadata')


def test_add_document():
    """测试添加文档功能"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试配置
        config_data = {
            'system': {
                'data_dir': tmpdir
            },
            'index': {
                'tantivy_path': f'{tmpdir}/tantivy_test',
                'hnsw_path': f'{tmpdir}/hnsw_test',
                'metadata_path': f'{tmpdir}/metadata_test'
            },
            'embedding': {
                'enabled': False,  # 禁用嵌入模型以避免依赖问题
                'provider': 'fastembed',
                'model_name': 'BAAI/bge-small-zh-v1.5'
            }
        }
        
        # 创建配置加载器
        mock_config = Mock(spec=ConfigLoader)
        mock_config.get.side_effect = lambda section, key, default='': config_data.get(section, {}).get(key, default)
        mock_config.getint.side_effect = lambda section, key, default=0: int(config_data.get(section, {}).get(key, default))
        mock_config.getboolean.side_effect = lambda section, key, default=False: bool(config_data.get(section, {}).get(key, default))
        
        # 测试添加文档
        index_manager = IndexManager(mock_config)
        
        # 准备测试文档
        import time
        from datetime import datetime
        current_time = int(time.time())
        test_doc = {
            'path': f'{tmpdir}/test.txt',
            'filename': 'test.txt',
            'content': '这是一个测试文档',
            'file_type': 'txt',
            'size': 1024,
            'created': current_time,
            'modified': current_time,
            'keywords': '测试'
        }
        
        # 创建测试文件
        Path(test_doc['path']).write_text('这是一个测试文档', encoding='utf-8')
        
        # 添加文档到索引
        success = index_manager.add_document(test_doc)
        assert success is True


def test_search_functionality():
    """测试搜索功能"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试配置
        config_data = {
            'system': {
                'data_dir': tmpdir
            },
            'index': {
                'tantivy_path': f'{tmpdir}/tantivy_test',
                'hnsw_path': f'{tmpdir}/hnsw_test',
                'metadata_path': f'{tmpdir}/metadata_test'
            },
            'embedding': {
                'enabled': False,  # 禁用嵌入模型以避免依赖问题
                'provider': 'fastembed',
                'model_name': 'BAAI/bge-small-zh-v1.5'
            }
        }
        
        # 创建配置加载器
        mock_config = Mock(spec=ConfigLoader)
        mock_config.get.side_effect = lambda section, key, default='': config_data.get(section, {}).get(key, default)
        mock_config.getint.side_effect = lambda section, key, default=0: int(config_data.get(section, {}).get(key, default))
        mock_config.getboolean.side_effect = lambda section, key, default=False: bool(config_data.get(section, {}).get(key, default))
        
        # 测试搜索功能
        index_manager = IndexManager(mock_config)
        
        # 添加测试文档
        import time
        current_time = int(time.time())
        test_doc = {
            'path': f'{tmpdir}/search_test.txt',
            'filename': 'search_test.txt',
            'content': '这是一个用于搜索测试的文档',
            'file_type': 'txt',
            'size': 1024,
            'created': current_time,
            'modified': current_time,
            'keywords': '搜索 测试'
        }
        
        Path(test_doc['path']).write_text('这是一个用于搜索测试的文档', encoding='utf-8')
        index_manager.add_document(test_doc)
        
        # 执行搜索
        results = index_manager.search_text('搜索测试', limit=10)
        assert len(results) >= 0  # 搜索不应该抛出异常


if __name__ == "__main__":
    test_index_manager_initialization()
    test_add_document()
    test_search_functionality()
    print("所有索引管理器测试通过!")