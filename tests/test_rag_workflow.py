# tests/test_rag_workflow.py
import pytest
from src.core.file_scanner import FileScanner

def test_rag_workflow(mock_rag, generate_test_data, mock_scanner, temp_config):
    """测试RAG完整工作流（基于文档10.2）"""
    test_dir = generate_test_data(10)  # 10个测试文件
    scanner = FileScanner(temp_config)
    scanner.scan_and_index()  # 模拟扫描（实际需mock变化）
    
    response = mock_rag.query("测试内容是什么？")
    
    assert "测试内容" in response['answer']  # 假设模型生成相关
    assert len(response['sources']) > 0
    assert all('.txt' in source for source in response['sources'])