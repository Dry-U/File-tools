#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件监控功能测试"""
import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.file_monitor import FileMonitor, FileChangeHandler


@pytest.fixture
def mock_config():
    """创建模拟配置"""
    config = Mock()
    config.get.side_effect = lambda section, key, default=None: {
        ('monitor', 'directories', ''): '',
        ('monitor', 'enabled', True): True,
        ('monitor', 'debounce_time', 0.5): 0.1,
        ('monitor', 'ignored_patterns', '.git;.svn'): '.git;.svn;__pycache__',
    }.get((section, key, default), default)
    config.getboolean.return_value = True
    config.getfloat.return_value = 0.1
    return config


class TestFileMonitorInitialization:
    """测试文件监控器初始化"""

    def test_file_monitor_init(self):
        """测试监控器初始化"""
        # 使用真实的配置字典
        config = {
            'monitor': {
                'directories': '',
                'enabled': True,
                'debounce_time': 0.1,
                'ignored_patterns': '.git;.svn',
                'refresh_interval': 1,
            }
        }
        mock_index_manager = Mock()
        monitor = FileMonitor(config, mock_index_manager)

        assert monitor is not None
        assert monitor.index_manager == mock_index_manager


class TestFileChangeHandler:
    """测试文件变更处理器"""

    def test_handler_creation(self):
        """测试处理器创建"""
        mock_monitor = Mock()
        ignored_patterns = ['.git', '__pycache__']
        handler = FileChangeHandler(mock_monitor, ignored_patterns)

        assert handler is not None
        assert handler.file_monitor == mock_monitor

    def test_on_created_event(self):
        """测试创建事件处理"""
        mock_monitor = Mock()
        handler = FileChangeHandler(mock_monitor, [])

        event = Mock()
        event.src_path = "/test/file.txt"
        event.is_directory = False

        handler.on_created(event)

        mock_monitor.process_event.assert_called_once_with(event)

    def test_on_modified_event(self):
        """测试修改事件处理"""
        mock_monitor = Mock()
        handler = FileChangeHandler(mock_monitor, [])

        event = Mock()
        event.src_path = "/test/file.txt"
        event.is_directory = False

        handler.on_modified(event)

        mock_monitor.process_event.assert_called_once_with(event)


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
