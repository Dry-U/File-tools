"""
API 请求/响应模型定义
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str
    filters: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    """搜索结果模型"""
    file_name: str
    path: str
    score: float
    snippet: str


class ChatRequest(BaseModel):
    """对话请求模型"""
    query: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """对话响应模型"""
    answer: str
    sources: List[Dict[str, Any]]


class PreviewRequest(BaseModel):
    """文件预览请求模型"""
    path: str


class PreviewResponse(BaseModel):
    """文件预览响应模型"""
    content: str


class ConfigUpdateRequest(BaseModel):
    """配置更新请求模型"""
    ai_model: Optional[Dict[str, Any]] = None
    rag: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    """健康检查响应模型"""
    status: str
    initialized: bool
    timestamp: float
    components: Dict[str, Any]


class DirectoryPath(BaseModel):
    """目录路径请求模型"""
    path: str


class DirectoryResponse(BaseModel):
    """目录响应模型"""
    status: str
    message: str
    path: Optional[str] = None
    needs_rebuild: bool = False


class BrowseResponse(BaseModel):
    """浏览目录响应模型"""
    status: str
    path: Optional[str] = None
    canceled: bool = False


class DirectoryInfo(BaseModel):
    """目录信息模型"""
    path: str
    exists: bool
    is_scanning: bool
    is_monitoring: bool
    file_count: int


class DirectoriesListResponse(BaseModel):
    """目录列表响应模型"""
    directories: list
