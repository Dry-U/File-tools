import pytest
import tempfile
import shutil
import sys
import os
from pathlib import Path
from unittest.mock import Mock

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.utils.config_loader import ConfigLoader

@pytest.fixture
def temp_config():
    """Create a temporary configuration for testing"""
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
    """Fixture to generate test data files"""
    def _generate(count):
        data_dir = tmp_path / "test_data"
        data_dir.mkdir(exist_ok=True)
        
        for i in range(count):
            file_path = data_dir / f"doc_{i}.txt"
            file_path.write_text(f"This is test document {i} with some content for searching.", encoding='utf-8')
            
        return str(data_dir)
    
    return _generate
