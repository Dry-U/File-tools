# tests/test_file_scanner.py
import pytest
from pathlib import Path

def test_file_scanner_should_index(mock_scanner):
    """测试文件过滤"""
    valid_path = str(Path(mock_scanner.scan_paths[0]) / 'test.pdf')
    invalid_path = str(Path(mock_scanner.scan_paths[0]) / 'test.exe')
    
    assert mock_scanner._should_index(valid_path) is True
    assert mock_scanner._should_index(invalid_path) is False  # 非目标扩展

def test_is_system_file(mock_scanner):
    """测试系统文件检测"""
    system_path = '/path/to/.hidden/file'  # 隐藏文件
    assert mock_scanner._is_system_file(system_path) is True
    
    normal_path = '/path/to/normal.txt'
    assert mock_scanner._is_system_file(normal_path) is False
    