#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模型管理器功能测试"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.model_manager import ModelManager


@pytest.fixture
def mock_config_wsl():
    """创建WSL配置的Mock"""
    config = Mock()

    def mock_get(_section=None, key=None, default=None):
        """Mock get 方法"""
        if _section == "ai_model":
            if key == "api.api_url":
                return "http://localhost:8000/v1/chat/completions"
            elif key == "api.api_key":
                return ""
            elif key == "api.model_name":
                return "deepseek-ai/DeepSeek-V2.5"
            elif key == "api.system_prompt":
                return ""
            elif key == "mode":
                return "api"
            elif key == "api.provider":
                return "siliconflow"
            elif key == "api.max_tokens":
                return 2048
            elif key == "api.max_context":
                return 8192
        return default

    def mock_getint(_section=None, key=None, default=0):
        """Mock getint 方法"""
        if _section == "ai_model":
            if key == "api.max_tokens":
                return 2048
            elif key == "api.max_context":
                return 8192
        return default

    config.get.side_effect = mock_get
    config.getint.side_effect = mock_getint
    config.getboolean.return_value = True
    return config


class TestModelManagerInitialization:
    """测试模型管理器初始化"""

    def test_init_api_interface(self, mock_config_wsl):
        """测试API接口初始化"""
        manager = ModelManager(mock_config_wsl)

        assert manager is not None
        assert manager.mode.value == "api"
        assert manager.api_url == "http://localhost:8000/v1/chat/completions"
        assert manager.default_max_tokens == 2048

    def test_init_with_defaults(self):
        """测试使用默认值的初始化"""
        config = Mock()

        def mock_get(_section=None, _key=None, default=None):
            return default

        def mock_getint(_section=None, _key=None, default=0):
            return default

        config.get.side_effect = mock_get
        config.getint.side_effect = mock_getint
        config.getboolean.return_value = False

        manager = ModelManager(config)

        assert manager.mode.value == "local"  # 默认模式


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

        assert _normalize_text("") == ""
        # _normalize_text 只接受 str 类型，不接受 None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
