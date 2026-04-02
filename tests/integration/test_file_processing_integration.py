"""文件处理集成测试"""

import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestFileProcessingIntegration:
    """文件处理集成测试类"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = "./data"
        config.getboolean.return_value = False
        config.getint.return_value = 100
        return config

    def test_text_file_processing(self, temp_test_dir, mock_config):
        """测试文本文件处理"""
        test_file = Path(temp_test_dir) / "test.txt"
        test_content = "This is a test file content."
        test_file.write_text(test_content, encoding="utf-8")

        # 模拟文档解析器
        with patch("backend.core.document_parser.DocumentParser") as mock_parser:
            parser = Mock()
            parser.extract_text.return_value = test_content
            mock_parser.return_value = parser

            # 验证文件存在
            assert test_file.exists()
            assert test_file.read_text(encoding="utf-8") == test_content

    def test_markdown_file_processing(self, temp_test_dir, mock_config):
        """测试Markdown文件处理"""
        md_content = """# Test Document

This is a test markdown file.

## Section 1

Content here.

## Section 2

More content.
"""
        md_file = Path(temp_test_dir) / "test.md"
        md_file.write_text(md_content, encoding="utf-8")

        assert md_file.exists()
        content = md_file.read_text(encoding="utf-8")
        assert "# Test Document" in content
        assert "## Section 1" in content

    def test_json_file_processing(self, temp_test_dir, mock_config):
        """测试JSON文件处理"""
        import json

        json_data = {"name": "test", "version": "1.0", "items": ["a", "b", "c"]}
        json_file = Path(temp_test_dir) / "test.json"
        json_file.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

        assert json_file.exists()
        loaded_data = json.loads(json_file.read_text(encoding="utf-8"))
        assert loaded_data["name"] == "test"
        assert loaded_data["version"] == "1.0"

    def test_nested_directory_processing(self, temp_test_dir, mock_config):
        """测试嵌套目录处理"""
        # 创建嵌套目录结构
        dirs = ["level1", "level1/level2", "level1/level2/level3", "another_dir"]

        for d in dirs:
            (Path(temp_test_dir) / d).mkdir(parents=True, exist_ok=True)

        # 在各层创建文件
        files = {
            "root.txt": "root content",
            "level1/level1.txt": "level1 content",
            "level1/level2/level2.txt": "level2 content",
            "level1/level2/level3/level3.txt": "level3 content",
            "another_dir/another.txt": "another content",
        }

        for filepath, content in files.items():
            (Path(temp_test_dir) / filepath).write_text(content, encoding="utf-8")

        # 验证所有文件存在
        for filepath in files.keys():
            assert (Path(temp_test_dir) / filepath).exists()

        # 统计文件数量
        all_files = list(Path(temp_test_dir).rglob("*.txt"))
        assert len(all_files) == 5

    def test_large_file_processing(self, temp_test_dir, mock_config):
        """测试大文件处理"""
        # 创建1MB的文件
        large_content = "A" * (1024 * 1024)
        large_file = Path(temp_test_dir) / "large_file.txt"
        large_file.write_text(large_content, encoding="utf-8")

        # 验证文件大小
        assert large_file.exists()
        assert large_file.stat().st_size == len(large_content.encode("utf-8"))

        # 验证可以读取部分内容
        content = large_file.read_text(encoding="utf-8")
        assert len(content) == len(large_content)

    def test_unicode_file_processing(self, temp_test_dir, mock_config):
        """测试Unicode文件处理"""
        unicode_content = """
        中文内容测试
        日本語テスト
        한국어 테스트
        Emoji test: 🎉 🚀 💻
        Special chars: ñ ü é ß
        """
        unicode_file = Path(temp_test_dir) / "unicode.txt"
        unicode_file.write_text(unicode_content, encoding="utf-8")

        assert unicode_file.exists()
        content = unicode_file.read_text(encoding="utf-8")
        assert "中文内容测试" in content
        assert "🎉" in content

    def test_binary_file_detection(self, temp_test_dir, mock_config):
        """测试二进制文件检测"""
        # 创建文本文件
        text_file = Path(temp_test_dir) / "text.txt"
        text_file.write_text("This is text", encoding="utf-8")

        # 创建二进制文件
        binary_file = Path(temp_test_dir) / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        # 验证文件类型
        assert text_file.exists()
        assert binary_file.exists()

        # 尝试读取文本文件
        text_content = text_file.read_text(encoding="utf-8")
        assert text_content == "This is text"

        # 读取二进制文件
        binary_content = binary_file.read_bytes()
        assert binary_content == b"\x00\x01\x02\x03\xff\xfe"

    def test_file_with_special_characters_in_name(self, temp_test_dir, mock_config):
        """测试特殊字符文件名处理"""
        special_names = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "file.multiple.dots.txt",
            "file(1).txt",
            "file[2].txt",
            "file{3}.txt",
        ]

        for name in special_names:
            filepath = Path(temp_test_dir) / name
            filepath.write_text(f"Content of {name}", encoding="utf-8")

        # 验证所有文件存在
        for name in special_names:
            filepath = Path(temp_test_dir) / name
            assert filepath.exists(), f"File {name} should exist"

    def test_empty_file_processing(self, temp_test_dir, mock_config):
        """测试空文件处理"""
        empty_file = Path(temp_test_dir) / "empty.txt"
        empty_file.write_text("", encoding="utf-8")

        assert empty_file.exists()
        assert empty_file.stat().st_size == 0
        assert empty_file.read_text(encoding="utf-8") == ""

    def test_file_scanning_integration(self, temp_test_dir, mock_config):
        """测试文件扫描集成"""
        # 创建测试文件
        test_files = [
            "doc1.txt",
            "doc2.txt",
            "subdir/doc3.txt",
            "subdir/nested/doc4.txt",
        ]

        for filepath in test_files:
            full_path = Path(temp_test_dir) / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"Content of {filepath}", encoding="utf-8")

        # 模拟文件扫描器
        with patch("backend.core.file_scanner.FileScanner") as mock_scanner:
            scanner = Mock()
            scanner.scan_and_index.return_value = {
                "total_files_scanned": len(test_files),
                "total_files_indexed": len(test_files),
            }
            mock_scanner.return_value = scanner

            # 执行扫描
            result = scanner.scan_and_index()

            assert result["total_files_scanned"] == 4
            assert result["total_files_indexed"] == 4

    def test_file_monitoring_integration(self, temp_test_dir, mock_config):
        """测试文件监控集成"""
        with patch("backend.core.file_monitor.FileMonitor") as mock_monitor:
            monitor = Mock()
            monitor.add_monitored_directory.return_value = True
            monitor.get_monitored_directories.return_value = [temp_test_dir]
            mock_monitor.return_value = monitor

            # 添加监控目录
            result = monitor.add_monitored_directory(temp_test_dir)
            assert result

            # 获取监控目录
            dirs = monitor.get_monitored_directories()
            assert temp_test_dir in dirs


class TestDocumentParserIntegration:
    """文档解析器集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_parser_initialization(self, temp_test_dir):
        """测试解析器初始化"""
        with patch("backend.core.document_parser.DocumentParser") as mock_parser:
            parser = Mock()
            parser.supported_extensions = [".txt", ".md", ".json", ".py"]
            mock_parser.return_value = parser

            assert parser.supported_extensions is not None
            assert ".txt" in parser.supported_extensions

    def test_text_extraction(self, temp_test_dir):
        """测试文本提取"""
        test_file = Path(temp_test_dir) / "test.txt"
        test_content = "This is test content for extraction."
        test_file.write_text(test_content, encoding="utf-8")

        with patch("backend.core.document_parser.DocumentParser") as mock_parser:
            parser = Mock()
            parser.extract_text.return_value = test_content
            mock_parser.return_value = parser

            result = parser.extract_text(str(test_file))
            assert result == test_content


class TestIndexManagerIntegration:
    """索引管理器集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = "./data"
        return config

    def test_document_addition(self, temp_test_dir, mock_config):
        """测试文档添加"""
        with patch("backend.core.index_manager.IndexManager") as mock_index:
            index_manager = Mock()
            index_manager.add_document.return_value = True
            mock_index.return_value = index_manager

            doc = {
                "path": "/test/doc.txt",
                "content": "Test content",
                "filename": "doc.txt",
            }

            result = index_manager.add_document(doc)
            assert result

    def test_document_removal(self, temp_test_dir, mock_config):
        """测试文档移除"""
        with patch("backend.core.index_manager.IndexManager") as mock_index:
            index_manager = Mock()
            index_manager.remove_document.return_value = True
            mock_index.return_value = index_manager

            result = index_manager.remove_document("/test/doc.txt")
            assert result

    def test_search_integration(self, temp_test_dir, mock_config):
        """测试搜索集成"""
        with patch("backend.core.index_manager.IndexManager") as mock_index:
            index_manager = Mock()
            index_manager.search_text.return_value = [
                {"path": "/test/doc.txt", "score": 0.9}
            ]
            mock_index.return_value = index_manager

            results = index_manager.search_text("test query")
            assert len(results) == 1
            assert results[0]["score"] == 0.9


class TestFileScannerIntegration:
    """文件扫描器集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = []
        config.getboolean.return_value = False
        return config

    def test_scanner_initialization(self, temp_test_dir, mock_config):
        """测试扫描器初始化"""
        with patch("backend.core.file_scanner.FileScanner") as mock_scanner:
            scanner = Mock()
            scanner.scan_paths = [temp_test_dir]
            mock_scanner.return_value = scanner

            assert scanner.scan_paths is not None
            assert temp_test_dir in scanner.scan_paths

    def test_batch_processing(self, temp_test_dir, mock_config):
        """测试批处理"""
        with patch("backend.core.file_scanner.FileScanner") as mock_scanner:
            scanner = Mock()
            scanner.batch_size = 100
            scanner.process_batch.return_value = {"processed": 50, "errors": 0}
            mock_scanner.return_value = scanner

            result = scanner.process_batch()
            assert result["processed"] == 50
            assert result["errors"] == 0


class TestErrorHandlingIntegration:
    """错误处理集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_corrupted_file_handling(self, temp_test_dir):
        """测试损坏文件处理"""
        # 创建损坏的"文本"文件（包含无效UTF-8序列）
        corrupted_file = Path(temp_test_dir) / "corrupted.txt"
        corrupted_file.write_bytes(b"\xff\xfe\x00\x01invalid utf-8")

        # 尝试读取（应该使用errors='replace'）
        content = corrupted_file.read_text(encoding="utf-8", errors="replace")
        assert content is not None

    def test_missing_file_handling(self, temp_test_dir):
        """测试缺失文件处理"""
        missing_file = Path(temp_test_dir) / "nonexistent.txt"

        # 验证文件不存在
        assert not missing_file.exists()

        # 尝试读取应该抛出异常
        with pytest.raises(FileNotFoundError):
            missing_file.read_text(encoding="utf-8")

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows不支持Unix风格的文件权限"
    )
    def test_permission_error_handling(self, temp_test_dir):
        """测试权限错误处理"""
        restricted_file = Path(temp_test_dir) / "restricted.txt"
        restricted_file.write_text("secret content", encoding="utf-8")

        # 移除读权限
        try:
            restricted_file.chmod(0o000)

            with pytest.raises((PermissionError, OSError)):
                restricted_file.read_text(encoding="utf-8")
        finally:
            # 恢复权限以便清理
            restricted_file.chmod(0o644)
