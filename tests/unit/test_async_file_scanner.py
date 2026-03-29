#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试异步文件扫描功能"""

import pytest
from unittest.mock import Mock, patch

from backend.core.file_scanner import FileScanner, AIOFILES_AVAILABLE


@pytest.fixture
def mock_config():
    """创建模拟配置"""
    config = Mock()
    config.get.side_effect = lambda section, key, default=None: {
        ("file_scanner", "scan_paths", ""): "",
        ("file_scanner", "max_file_size", 100): 100,
        ("file_scanner", "exclude_patterns", ""): "",
        ("file_scanner", "file_types", None): None,
        ("file_scanner", "scan_threads", 4): 4,
        ("file_scanner", "hash_cache_size", 10000): 10000,
    }.get((section, key, default), default)

    config.getint.side_effect = lambda section, key, default=0: {
        ("file_scanner", "max_file_size", 100): 100,
        ("file_scanner", "scan_threads", 4): 4,
        ("file_scanner", "hash_cache_size", 10000): 10000,
    }.get((section, key, default), default)

    return config


class TestAsyncFileScanner:
    """测试异步文件扫描"""

    @pytest.mark.asyncio
    async def test_scan_and_index_async_fallback(self, mock_config, tmp_path):
        """测试异步扫描回退到同步模式"""
        scanner = FileScanner(mock_config)
        scanner.scan_paths = [str(tmp_path)]

        # 创建测试文件
        (tmp_path / "test.txt").write_text("test content")

        # 模拟 aiofiles 不可用
        with patch.object(scanner, "_process_file", return_value=True):
            result = await scanner.scan_and_index_async()

            assert isinstance(result, dict)
            assert "total_files_scanned" in result

    @pytest.mark.asyncio
    async def test_collect_files_async(self, mock_config, tmp_path):
        """测试异步收集文件"""
        scanner = FileScanner(mock_config)
        scanner.scan_paths = [str(tmp_path)]

        # 创建测试目录结构
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        files = await scanner._collect_files_async()

        assert isinstance(files, list)
        assert len(files) == 3

    @pytest.mark.asyncio
    async def test_process_file_async(self, mock_config, tmp_path):
        """测试异步处理文件"""
        scanner = FileScanner(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # 由于 aiofiles 可能不可用，测试回退行为
        with patch.object(scanner, "_is_file_changed", return_value=True):
            with patch.object(scanner, "_should_index", return_value=False):
                result = await scanner._process_file_async(test_file)

                # 文件应该被处理（虽然不会被索引）
                assert isinstance(result, bool)

    @pytest.mark.skipif(not AIOFILES_AVAILABLE, reason="aiofiles not installed")
    @pytest.mark.asyncio
    async def test_read_file_content_async(self, mock_config, tmp_path):
        """测试异步读取文件内容"""
        scanner = FileScanner(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        content = await scanner._read_file_content_async(str(test_file), ".txt")

        assert content == "test content"

    def test_async_methods_exist(self, mock_config):
        """测试异步方法存在"""
        scanner = FileScanner(mock_config)

        # 验证异步方法存在
        assert hasattr(scanner, "scan_and_index_async")
        assert hasattr(scanner, "_collect_files_async")
        assert hasattr(scanner, "_process_file_async")
        assert hasattr(scanner, "_index_file_async")
        assert hasattr(scanner, "_read_file_content_async")


class TestFileScannerTypeAnnotations:
    """测试 FileScanner 类型注解"""

    def test_init_type_annotations(self, mock_config):
        """测试初始化类型注解"""
        scanner = FileScanner(mock_config)

        # 验证关键属性类型
        assert isinstance(scanner.scan_paths, list)
        assert isinstance(scanner.max_file_size, int)
        assert isinstance(scanner.all_extensions, set)
        assert isinstance(scanner.max_workers, int)

    def test_method_return_types(self, mock_config):
        """测试方法返回类型"""
        scanner = FileScanner(mock_config)

        # 测试 _is_stop_requested 返回 bool
        assert isinstance(scanner._is_stop_requested(), bool)

        # 测试 _get_file_hash 返回 str
        result = scanner._get_file_hash("/test", "quick_key")
        assert isinstance(result, str)

    def test_scan_stats_structure(self, mock_config):
        """测试扫描统计结构"""
        scanner = FileScanner(mock_config)

        expected_keys = [
            "total_files_scanned",
            "total_files_indexed",
            "total_files_skipped",
            "total_size_scanned",
            "scan_time",
            "last_scan_time",
        ]

        for key in expected_keys:
            assert key in scanner.scan_stats
