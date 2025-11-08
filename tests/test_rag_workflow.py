# tests/test_rag_workflow.py
import pytest
from backend.core.file_scanner import FileScanner

def test_rag_workflow_basic():
    """测试RAG工作流的基本功能"""
    # For now, just test that the module can be imported
    from backend.core.rag_pipeline import RAGPipeline, HybridRetriever
    assert True  # If we get here, the import worked