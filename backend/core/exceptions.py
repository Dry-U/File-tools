#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自定义异常层级模块

定义 File-tools 应用的所有自定义异常，提供清晰的错误分类和处理机制。
"""

from typing import Optional, Any, Dict


class FileToolsError(Exception):
    """
    应用基础异常类

    所有 File-tools 异常的基类，提供统一的错误处理接口。
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式，便于序列化"""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


# ============================================================================
# 安全相关异常
# ============================================================================


class SecurityError(FileToolsError):
    """安全相关异常基类"""

    def __init__(self, message: str, error_code: str = "SECURITY_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class PathTraversalError(SecurityError):
    """路径遍历攻击检测"""

    def __init__(self, path: str, **kwargs):
        super().__init__(
            f"检测到路径遍历尝试: {path}",
            error_code="PATH_TRAVERSAL",
            details={"path": path},
            **kwargs,
        )


class AuthenticationError(SecurityError):
    """认证失败"""

    def __init__(self, message: str = "认证失败", **kwargs):
        super().__init__(message, error_code="AUTH_FAILED", **kwargs)


class RateLimitExceeded(SecurityError):
    """请求频率超限"""

    def __init__(self, limit: int, window: int, **kwargs):
        super().__init__(
            f"请求过于频繁，限制: {limit}/{window}秒",
            error_code="RATE_LIMIT_EXCEEDED",
            details={"limit": limit, "window": window},
            **kwargs,
        )


# ============================================================================
# 配置相关异常
# ============================================================================


class ConfigError(FileToolsError):
    """配置相关异常基类"""

    def __init__(self, message: str, error_code: str = "CONFIG_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class ConfigNotFoundError(ConfigError):
    """配置文件未找到"""

    def __init__(self, path: str, **kwargs):
        super().__init__(
            f"配置文件未找到: {path}",
            error_code="CONFIG_NOT_FOUND",
            details={"path": path},
            **kwargs,
        )


class ConfigValidationError(ConfigError):
    """配置验证失败"""

    def __init__(
        self, message: str, validation_errors: Optional[list] = None, **kwargs
    ):
        super().__init__(
            message,
            error_code="CONFIG_VALIDATION_FAILED",
            details={"validation_errors": validation_errors or []},
            **kwargs,
        )


class ConfigEncryptionError(ConfigError):
    """配置加密/解密失败"""

    def __init__(self, message: str = "配置加密失败", **kwargs):
        super().__init__(message, error_code="CONFIG_ENCRYPTION_ERROR", **kwargs)


# ============================================================================
# 索引相关异常
# ============================================================================


class IndexError(FileToolsError):
    """索引相关异常基类"""

    def __init__(self, message: str, error_code: str = "INDEX_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class IndexNotFoundError(IndexError):
    """索引未找到"""

    def __init__(self, index_path: str, **kwargs):
        super().__init__(
            f"索引未找到: {index_path}",
            error_code="INDEX_NOT_FOUND",
            details={"index_path": index_path},
            **kwargs,
        )


class IndexCorruptedError(IndexError):
    """索引损坏"""

    def __init__(self, message: str = "索引文件损坏", **kwargs):
        super().__init__(message, error_code="INDEX_CORRUPTED", **kwargs)


class IndexLockedError(IndexError):
    """索引被锁定"""

    def __init__(self, message: str = "索引被其他进程锁定", **kwargs):
        super().__init__(message, error_code="INDEX_LOCKED", **kwargs)


class DocumentIndexingError(IndexError):
    """文档索引失败"""

    def __init__(self, document_path: str, reason: str = "", **kwargs):
        super().__init__(
            f"文档索引失败: {document_path}" + (f" - {reason}" if reason else ""),
            error_code="DOCUMENT_INDEXING_FAILED",
            details={"document_path": document_path, "reason": reason},
            **kwargs,
        )


# ============================================================================
# 搜索相关异常
# ============================================================================


class SearchError(FileToolsError):
    """搜索相关异常基类"""

    def __init__(self, message: str, error_code: str = "SEARCH_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class QueryParsingError(SearchError):
    """查询解析失败"""

    def __init__(self, query: str, reason: str = "", **kwargs):
        super().__init__(
            f"查询解析失败: {query}" + (f" - {reason}" if reason else ""),
            error_code="QUERY_PARSE_ERROR",
            details={"query": query, "reason": reason},
            **kwargs,
        )


class VectorSearchError(SearchError):
    """向量搜索失败"""

    def __init__(self, message: str = "向量搜索失败", **kwargs):
        super().__init__(message, error_code="VECTOR_SEARCH_ERROR", **kwargs)


# ============================================================================
# 文件扫描相关异常
# ============================================================================


class FileScannerError(FileToolsError):
    """文件扫描相关异常基类"""

    def __init__(self, message: str, error_code: str = "FILE_SCANNER_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class FileAccessError(FileScannerError):
    """文件访问失败"""

    def __init__(self, file_path: str, reason: str = "", **kwargs):
        super().__init__(
            f"无法访问文件: {file_path}" + (f" - {reason}" if reason else ""),
            error_code="FILE_ACCESS_ERROR",
            details={"file_path": file_path, "reason": reason},
            **kwargs,
        )


class FileParseError(FileScannerError):
    """文件解析失败"""

    def __init__(self, file_path: str, parser: str = "", reason: str = "", **kwargs):
        super().__init__(
            f"文件解析失败: {file_path}" + (f" ({parser})" if parser else ""),
            error_code="FILE_PARSE_ERROR",
            details={"file_path": file_path, "parser": parser, "reason": reason},
            **kwargs,
        )


class FileTooLargeError(FileScannerError):
    """文件过大"""

    def __init__(self, file_path: str, size: int, max_size: int, **kwargs):
        size_mb = size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        super().__init__(
            f"文件过大 ({size_mb:.1f}MB > {max_mb:.1f}MB): {file_path}",
            error_code="FILE_TOO_LARGE",
            details={"file_path": file_path, "size": size, "max_size": max_size},
            **kwargs,
        )


# ============================================================================
# RAG 相关异常
# ============================================================================


class RAGError(FileToolsError):
    """RAG相关异常基类"""

    def __init__(self, message: str, error_code: str = "RAG_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class ModelNotAvailableError(RAGError):
    """模型不可用"""

    def __init__(self, model_name: str = "", **kwargs):
        message = "AI模型不可用"
        if model_name:
            message += f": {model_name}"
        super().__init__(
            message,
            error_code="MODEL_NOT_AVAILABLE",
            details={"model_name": model_name},
            **kwargs,
        )


class GenerationError(RAGError):
    """文本生成失败"""

    def __init__(self, message: str = "文本生成失败", **kwargs):
        super().__init__(message, error_code="GENERATION_ERROR", **kwargs)


class ContextExceededError(RAGError):
    """上下文长度超限"""

    def __init__(self, current_length: int, max_length: int, **kwargs):
        super().__init__(
            f"上下文长度超限 ({current_length} > {max_length})",
            error_code="CONTEXT_EXCEEDED",
            details={"current_length": current_length, "max_length": max_length},
            **kwargs,
        )


class SessionNotFoundError(RAGError):
    """会话未找到"""

    def __init__(self, session_id: str, **kwargs):
        super().__init__(
            f"会话未找到: {session_id}",
            error_code="SESSION_NOT_FOUND",
            details={"session_id": session_id},
            **kwargs,
        )


# ============================================================================
# 外部服务相关异常
# ============================================================================


class ExternalServiceError(FileToolsError):
    """外部服务相关异常基类"""

    def __init__(
        self, message: str, error_code: str = "EXTERNAL_SERVICE_ERROR", **kwargs
    ):
        super().__init__(message, error_code=error_code, **kwargs)


class APIError(ExternalServiceError):
    """API调用失败"""

    def __init__(self, endpoint: str, status_code: Optional[int] = None, **kwargs):
        message = f"API调用失败: {endpoint}"
        if status_code:
            message += f" (HTTP {status_code})"
        super().__init__(
            message,
            error_code="API_ERROR",
            details={"endpoint": endpoint, "status_code": status_code},
            **kwargs,
        )


class TimeoutError(ExternalServiceError):
    """操作超时"""

    def __init__(self, operation: str, timeout: float, **kwargs):
        super().__init__(
            f"操作超时: {operation} ({timeout}s)",
            error_code="TIMEOUT",
            details={"operation": operation, "timeout": timeout},
            **kwargs,
        )


# ============================================================================
# 资源相关异常
# ============================================================================


class ResourceError(FileToolsError):
    """资源相关异常基类"""

    def __init__(self, message: str, error_code: str = "RESOURCE_ERROR", **kwargs):
        super().__init__(message, error_code=error_code, **kwargs)


class InsufficientMemoryError(ResourceError):
    """内存不足"""

    def __init__(self, required: int, available: int, **kwargs):
        super().__init__(
            f"内存不足 (需要 {required}MB, 可用 {available}MB)",
            error_code="INSUFFICIENT_MEMORY",
            details={"required_mb": required, "available_mb": available},
            **kwargs,
        )


class DiskSpaceError(ResourceError):
    """磁盘空间不足"""

    def __init__(self, path: str, required: int, available: int, **kwargs):
        super().__init__(
            f"磁盘空间不足: {path} (需要 {required}MB, 可用 {available}MB)",
            error_code="DISK_SPACE_ERROR",
            details={"path": path, "required_mb": required, "available_mb": available},
            **kwargs,
        )


# ============================================================================
# 实用函数
# ============================================================================


def handle_exception(exc: Exception) -> Dict[str, Any]:
    """
    统一异常处理函数

    将任何异常转换为标准化的错误响应字典
    """
    if isinstance(exc, FileToolsError):
        return exc.to_dict()

    return {
        "error": True,
        "error_code": "INTERNAL_ERROR",
        "message": str(exc),
        "details": {"type": type(exc).__name__},
    }


def is_retriable_error(exc: Exception) -> bool:
    """
    判断错误是否可重试

    用于实现重试逻辑
    """
    retriable_codes = {
        "TIMEOUT",
        "API_ERROR",
        "EXTERNAL_SERVICE_ERROR",
        "INDEX_LOCKED",
        "FILE_ACCESS_ERROR",
    }

    if isinstance(exc, FileToolsError):
        return exc.error_code in retriable_codes

    return isinstance(exc, (ConnectionError, TimeoutError))
