# tests/test_file_scanner.py
import pytest
from pathlib import Path

def test_file_scanner_should_index(mock_scanner, tmp_path):
    """测试文件过滤"""
    # 创建临时PDF文件
    valid_file = tmp_path / 'test.pdf'
    valid_file.write_text('test content')
    
    # 创建临时EXE文件
    invalid_file = tmp_path / 'test.exe'
    invalid_file.write_text('test content')

    assert mock_scanner._should_index(str(valid_file)) is True
    assert mock_scanner._should_index(str(invalid_file)) is False  # 非目标扩展

def test_is_system_file(mock_scanner):
    """测试系统文件检测"""
    system_path = '/path/to/.hidden/file'  # 隐藏文件
    assert mock_scanner._is_system_file(system_path) is True

    normal_path = '/path/to/normal.txt'
    assert mock_scanner._is_system_file(normal_path) is False