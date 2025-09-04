# src/utils/config_loader.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置加载器模块 - 负责加载、验证和管理配置"""
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import os

class ConfigLoader:
    """配置加载器类，负责加载、验证和管理配置文件"""
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = Path(config_path).resolve()
        self.config: Dict[str, Any] = {}  # 初始化空配置
        
        # 尝试加载配置文件，如果不存在则创建默认配置
        try:
            self.config = self._load_config()
        except FileNotFoundError:
            self.config = self._create_default_config()
        
        # 验证配置
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件未找到: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 确保配置是字典类型
        if not isinstance(config, dict):
            config = {}
        
        return config
    
    def _create_default_config(self) -> Dict[str, Any]:
        """创建默认配置文件"""
        # 确保配置目录存在
        config_dir = self.config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # 默认配置
        default_config = {
            'system': {
                'app_name': '智能文件检索与问答系统',
                'version': '1.0.0',
                'data_dir': './data',
                'log_level': 'INFO',
                'index_dir': './data/index',
                'cache_dir': './data/cache',
                'temp_dir': './data/temp'
            },
            'file_scanner': {
                'scan_paths': str(Path.home()),
                'exclude_patterns': '.git;.svn;.hg;__pycache__;.idea;.vscode;node_modules;venv;env;.DS_Store;Thumbs.db',
                'max_file_size': 100,  # MB
                'file_types': 'document=.txt,.md,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx;image=.jpg,.jpeg,.png,.gif,.bmp,.tiff;audio=.mp3,.wav,.flac,.ogg;video=.mp4,.avi,.mov,.mkv',
                'scan_threads': 4
            },
            'search': {
                'text_weight': 0.5,
                'vector_weight': 0.5,
                'max_results': 50,
                'highlight': True,
                'cache_ttl': 3600  # 秒
            },
            'monitor': {
                'directories': str(Path.home()),
                'ignored_patterns': '.git;.svn;.hg;__pycache__;.idea;.vscode;node_modules;venv;env;.DS_Store;Thumbs.db',
                'refresh_interval': 1,
                'debounce_time': 0.5
            },
            'model': {
                'enabled': False,
                'model_path': '',
                'embedding_model': 'all-MiniLM-L6-v2',
                'max_tokens': 2048,
                'temperature': 0.7
            },
            'interface': {
                'theme': 'light',
                'font_size': 12,
                'max_preview_size': 5242880,  # 5MB
                'auto_save_settings': True
            }
        }
        
        # 保存默认配置到文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
            
            # 确保配置文件有正确的权限
            if os.name == 'posix':  # Unix-like systems
                os.chmod(self.config_path, 0o600)  # 只有所有者可读写
            
            print(f"已创建默认配置文件: {self.config_path}")
        except Exception as e:
            print(f"创建默认配置文件失败: {str(e)}")
        
        return default_config
    
    def _validate_config(self) -> None:
        """验证配置的有效性"""
        # 确保必要的配置部分存在
        required_sections = ['system', 'file_scanner', 'search', 'monitor']
        
        for section in required_sections:
            if section not in self.config:
                self.config[section] = {}
        
        # 确保数据目录存在
        data_dir = Path(self.get('system', 'data_dir', './data'))
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保索引目录存在
        index_dir = Path(self.get('system', 'index_dir', './data/index'))
        index_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保缓存目录存在
        cache_dir = Path(self.get('system', 'cache_dir', './data/cache'))
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保临时目录存在
        temp_dir = Path(self.get('system', 'temp_dir', './data/temp'))
        temp_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """获取配置值"""
        if section not in self.config:
            return default
        
        if key is None:
            return self.config[section]
        
        return self.config[section].get(key, default)
    
    def getint(self, section: str, key: str, default: int = 0) -> int:
        """获取整数值的配置"""
        value = self.get(section, key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def getfloat(self, section: str, key: str, default: float = 0.0) -> float:
        """获取浮点数值的配置"""
        value = self.get(section, key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def getboolean(self, section: str, key: str, default: bool = False) -> bool:
        """获取布尔值的配置"""
        value = self.get(section, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'y', 't')
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return default
    
    def getlist(self, section: str, key: str, default: list = None, delimiter: str = ';') -> list:
        """获取列表形式的配置"""
        if default is None:
            default = []
        
        value = self.get(section, key, default)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(delimiter) if item.strip()]
        return default
    
    def set(self, section: str, key: str, value: Any) -> None:
        """设置配置值"""
        if section not in self.config:
            self.config[section] = {}
        
        self.config[section][key] = value
    
    def save(self) -> bool:
        """保存配置到文件"""
        try:
            # 确保配置目录存在
            config_dir = self.config_path.parent
            config_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            
            # 确保配置文件有正确的权限
            if os.name == 'posix':  # Unix-like systems
                os.chmod(self.config_path, 0o600)  # 只有所有者可读写
            
            return True
        except Exception as e:
            print(f"保存配置文件失败: {str(e)}")
            return False
    
    def get_path(self, section: str, key: str, default: str = '') -> Path:
        """获取路径形式的配置"""
        path_str = self.get(section, key, default)
        if not path_str:
            return Path()
        
        # 处理用户主目录符号
        if isinstance(path_str, str) and path_str.startswith('~'):
            path_str = os.path.expanduser(path_str)
        
        return Path(path_str).resolve()
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config.copy()
    
    def reload(self) -> bool:
        """重新加载配置文件"""
        try:
            self.config = self._load_config()
            self._validate_config()
            return True
        except Exception as e:
            print(f"重新加载配置文件失败: {str(e)}")
            return False