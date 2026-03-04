import tempfile
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.utils.config_loader import ConfigLoader


def test_config_loader_initialization():
    """测试配置加载器初始化"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.yaml"
        
        # 创建测试配置文件
        test_config = {
            'system': {
                'app_name': 'Test App',
                'data_dir': './test_data'
            },
            'file_scanner': {
                'scan_paths': [str(Path(tmpdir) / 'test_scan')],
                'max_file_size': 50
            }
        }
        
        import yaml
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(test_config, f, allow_unicode=True, default_flow_style=False)
        
        # 测试加载配置
        config_loader = ConfigLoader(str(config_path))
        
        assert config_loader.get('system', 'app_name') == 'Test App'
        assert config_loader.getint('file_scanner', 'max_file_size') == 50


def test_config_loader_defaults():
    """测试配置加载器默认值"""
    config_loader = ConfigLoader()

    # 测试默认值 - 现在ConfigLoader会创建默认配置，所以我们要测试一个不存在的键
    assert config_loader.get('nonexistent', 'nonexistent_key', 'Default') == 'Default'
    assert config_loader.getint('nonexistent', 'max_file_size', 100) == 100


def test_config_loader_update():
    """测试配置更新功能"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.yaml"
        
        # 创建初始配置
        initial_config = {
            'system': {
                'app_name': 'Initial App',
                'data_dir': './initial_data'
            }
        }
        
        import yaml
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(initial_config, f, allow_unicode=True, default_flow_style=False)
        
        config_loader = ConfigLoader(str(config_path))
        
        # 测试更新配置
        updates = {
            'system': {
                'app_name': 'Updated App',
                'log_level': 'DEBUG'
            }
        }
        
        success = config_loader.update_config(updates)
        assert success is True
        
        assert config_loader.get('system', 'app_name') == 'Updated App'
        assert config_loader.get('system', 'log_level') == 'DEBUG'


if __name__ == "__main__":
    test_config_loader_initialization()
    test_config_loader_defaults()
    test_config_loader_update()
    print("所有配置加载器测试通过!")