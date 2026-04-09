#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日志功能测试"""

import logging
import sys
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.utils.logger import LogContext, LoggerConfig, LogLevel, setup_logger


class TestLoggerConfig:
    """测试日志配置类"""

    def test_logger_config_with_dict(self):
        """测试使用字典初始化日志配置"""
        config_dict = {
            "system": {
                "log_level": "WARNING",
                "data_dir": "./custom_data",
                "log_max_size": 50,
                "log_backup_count": 3,
            }
        }

        config = LoggerConfig(config_dict)

        assert config.log_level == "WARNING"
        # 注意: 架构使用 AppPaths 获取标准日志目录，而不是配置中的路径
        # 这是为了避免相对路径问题
        from backend.utils.app_paths import get_app_paths

        app_paths = get_app_paths()
        expected_log_dir = str(app_paths.log_dir)
        assert config.log_dir == expected_log_dir
        assert config.log_max_size == 50


class TestLogContext:
    """测试日志上下文"""

    def test_log_context_creation(self):
        """测试日志上下文创建"""
        context = LogContext(
            user_id="user123",
            session_id="session456",
            request_id="req789",
            module="test_module",
        )

        assert context.user_id == "user123"
        assert context.session_id == "session456"
        assert context.request_id == "req789"

    def test_log_context_defaults(self):
        """测试日志上下文默认值"""
        context = LogContext()

        assert context.user_id is None
        assert context.session_id is None
        assert context.request_id is None


class TestSetupLogger:
    """测试日志初始化"""

    def test_setup_logger_basic(self):
        """测试基本日志初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()

            logger = setup_logger("test_basic", log_dir=str(log_dir))

            assert logger is not None
            # 验证logger被成功创建即可


class TestLogLevelEnum:
    """测试日志级别枚举"""

    def test_log_level_values(self):
        """测试日志级别值"""
        assert LogLevel.DEBUG.value == logging.DEBUG
        assert LogLevel.INFO.value == logging.INFO
        assert LogLevel.WARNING.value == logging.WARNING
        assert LogLevel.ERROR.value == logging.ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
