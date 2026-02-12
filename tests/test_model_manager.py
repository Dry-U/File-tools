#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模型管理器功能测试"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.model_manager import ModelManager


@pytest.fixture
def mock_config_wsl():
    """创建WSL配置的Mock"""
    config = Mock()
    config.get.side_effect = lambda section, key, default=None: {
        ('ai_model', 'interface_type', 'wsl'): 'wsl',
        ('ai_model', 'api_url', 'http://localhost:8000/v1/chat/completions'): 'http://localhost:8000/v1/chat/completions',
        ('ai_model', 'api_key', ''): '',
        ('ai_model', 'api_format', 'openai_chat'): 'openai_chat',
        ('ai_model', 'api_model', 'wsl'): 'wsl',
        ('ai_model', 'system_prompt', ''): '',
    }.get((section, key, default), default)
    config.getint.side_effect = lambda section, key, default=0: {
        ('ai_model', 'request_timeout', 60): 60,
        ('ai_model', 'max_tokens', 2048): 2048,
    }.get((section, key, default), default)
    config.getboolean.return_value = True
    return config


class TestModelManagerInitialization:
    """测试模型管理器初始化"""

    def test_init_wsl_interface(self, mock_config_wsl):
        """测试WSL接口初始化"""
        manager = ModelManager(mock_config_wsl)

        assert manager is not None
        assert manager.interface_type == 'wsl'
        assert manager.api_url == 'http://localhost:8000/v1/chat/completions'
        assert manager.request_timeout == 60

    def test_init_with_defaults(self):
        """测试使用默认值的初始化"""
        config = Mock()
        config.get.side_effect = lambda section, key, default=None: default
        config.getint.side_effect = lambda section, key, default=0: default
        config.getboolean.return_value = False

        manager = ModelManager(config)

        assert manager.interface_type == 'wsl'
        assert manager.api_url == 'http://localhost:8000/v1/chat/completions'


class TestModelManagerGenerate:
    """测试生成方法"""

    def test_generate_disabled_model(self, mock_config_wsl):
        """测试禁用模型的生成"""
        mock_config_wsl.getboolean.return_value = False

        manager = ModelManager(mock_config_wsl)
        results = list(manager.generate("test prompt"))

        # 禁用模型时应返回模拟响应
        assert len(results) == 1


class TestModelManagerNormalization:
    """测试文本规范化"""

    def test_normalize_text_with_chinese(self):
        """测试中文文本规范化"""
        from backend.core.model_manager import _normalize_text

        text = "这是一个中文测试"
        result = _normalize_text(text)
        assert result == text

    def test_normalize_text_empty(self):
        """测试空文本规范化"""
        from backend.core.model_manager import _normalize_text

        assert _normalize_text('') == ''
        assert _normalize_text(None) is None


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
