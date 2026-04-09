#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试自定义异常模块"""

from backend.core.exceptions import (
    ConfigValidationError,
    FileAccessError,
    FileToolsError,
    IndexCorruptedError,
    PathTraversalError,
    RAGError,
    SearchError,
    SecurityError,
    handle_exception,
    is_retriable_error,
)


class TestFileToolsError:
    """测试基础异常类"""

    def test_basic_exception(self):
        """测试基础异常"""
        err = FileToolsError("Test error")
        assert "Test error" in str(err)
        assert err.message == "Test error"
        assert err.error_code == "UNKNOWN_ERROR"
        assert err.details == {}

    def test_exception_with_code(self):
        """测试带错误代码的异常"""
        err = FileToolsError("Test error", error_code="TEST_001")
        assert err.error_code == "TEST_001"
        assert "TEST_001" in str(err)

    def test_exception_with_details(self):
        """测试带详细信息的异常"""
        err = FileToolsError("Test error", details={"key": "value"})
        assert err.details == {"key": "value"}

    def test_to_dict(self):
        """测试转换为字典"""
        err = FileToolsError(
            "Test error", error_code="TEST_001", details={"key": "value"}
        )
        d = err.to_dict()
        assert d["error"] is True
        assert d["error_code"] == "TEST_001"
        assert d["message"] == "Test error"
        assert d["details"] == {"key": "value"}


class TestSpecificExceptions:
    """测试特定异常类"""

    def test_path_traversal_error(self):
        """测试路径遍历错误"""
        err = PathTraversalError("/etc/passwd")
        assert "路径遍历尝试" in str(err)
        assert err.error_code == "PATH_TRAVERSAL"
        assert err.details["path"] == "/etc/passwd"

    def test_config_validation_error(self):
        """测试配置验证错误"""
        errors = [{"field": "api_key", "message": "不能为空"}]
        err = ConfigValidationError("配置验证失败", validation_errors=errors)
        assert err.error_code == "CONFIG_VALIDATION_FAILED"
        assert err.details["validation_errors"] == errors

    def test_index_corrupted_error(self):
        """测试索引损坏错误"""
        err = IndexCorruptedError("索引已损坏")
        assert err.error_code == "INDEX_CORRUPTED"

    def test_search_error(self):
        """测试搜索错误"""
        err = SearchError("查询解析失败")
        assert "查询解析失败" in str(err)
        assert err.error_code == "SEARCH_ERROR"

    def test_rag_error(self):
        """测试 RAG 错误"""
        err = RAGError("模型调用失败")
        assert "模型调用失败" in str(err)
        assert err.error_code == "RAG_ERROR"

    def test_file_access_error(self):
        """测试文件访问错误"""
        err = FileAccessError("/test.txt")
        assert "无法访问文件" in str(err)
        assert err.error_code == "FILE_ACCESS_ERROR"
        assert err.details["file_path"] == "/test.txt"

    def test_security_error(self):
        """测试安全错误"""
        err = SecurityError("非法字符 detected")
        assert err.error_code == "SECURITY_ERROR"


class TestIsRetriableError:
    """测试可重试错误判断"""

    def test_retriable_error_timeout(self):
        """测试超时错误可重试"""
        err = FileToolsError("Timeout", error_code="TIMEOUT")
        assert is_retriable_error(err) is True

    def test_retriable_error_connection(self):
        """测试连接错误可重试"""
        err = ConnectionError("Connection failed")
        assert is_retriable_error(err) is True

    def test_non_retriable_error(self):
        """测试不可重试错误"""
        err = FileToolsError("Some error", error_code="PATH_TRAVERSAL")
        assert is_retriable_error(err) is False


class TestHandleException:
    """测试异常处理函数"""

    def test_handle_file_tools_error(self):
        """处理 FileToolsError"""
        err = FileToolsError("Test", error_code="TEST_001")
        result = handle_exception(err)
        assert result["error"] is True
        assert result["error_code"] == "TEST_001"
        assert result["message"] == "Test"

    def test_handle_generic_exception(self):
        """处理普通异常"""
        err = ValueError("Something wrong")
        result = handle_exception(err)
        assert result["error"] is True
        assert result["error_code"] == "INTERNAL_ERROR"
        assert "Something wrong" in result["message"]
