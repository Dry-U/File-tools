# src/utils/config_loader.py
import yaml
from typing import Dict, Any
from pathlib import Path

class ConfigLoader:
    """加载和验证配置文件的类"""
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        self._validate_config(config)
        return config
    
    def _validate_config(self, config: Dict[str, Any]):
        required_keys = ['system', 'file_scanner', 'model']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config section: {key}")
    
    def get(self, section: str, key: str = None, default: Any = None) -> Any:
        if key:
            return self.config.get(section, {}).get(key, default)
        return self.config.get(section, {})