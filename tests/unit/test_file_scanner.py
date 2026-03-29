import pytest
from unittest.mock import Mock

from backend.core.file_scanner import FileScanner


@pytest.fixture
def mock_scanner():
    config = Mock()
    # Mock getlist to return common extensions
    # Note: config.getlist might need to be mocked to return a list
    config.getlist.return_value = ["pdf", "doc", "docx", "txt", "md"]
    config.getint.return_value = 10
    # 配置 config.get 返回字符串，防止生成 MagicMock 目录
    config.get.return_value = "./data"

    scanner = FileScanner(config)
    # Mock config access inside FileScanner if it uses direct access or other methods
    return scanner


def test_file_scanner_should_index(mock_scanner, tmp_path):
    """测试文件过滤"""
    # 创建临时PDF文件
    valid_file = tmp_path / "test.pdf"
    valid_file.write_text("test content")

    # 创建临时EXE文件
    invalid_file = tmp_path / "test.exe"
    invalid_file.write_text("test content")

    assert mock_scanner._should_index(str(valid_file)) is True
    assert mock_scanner._should_index(str(invalid_file)) is False  # 非目标扩展


def test_is_system_file(mock_scanner):
    """测试系统文件检测"""
    # In Windows/Linux, paths might differ, but logic usually checks for '.' prefix or specific dirs
    # Assuming _is_system_file checks for dot prefix in parts

    system_path = "/path/to/.hidden/file"  # 隐藏文件
    assert mock_scanner._is_system_file(system_path) is True

    normal_path = "/path/to/normal.txt"
    assert mock_scanner._is_system_file(normal_path) is False
