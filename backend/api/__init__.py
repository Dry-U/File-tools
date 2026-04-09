"""
智能文件检索与问答系统 - FastAPI Web 服务

提供 Web 界面和 API 接口，可打包为桌面应用
使用依赖注入实现线程安全
"""

from backend.api.dependencies import (
    get_config_loader,
    get_file_monitor,
    get_file_scanner,
    get_index_manager,
    get_rag_pipeline,
    get_search_engine,
    is_path_allowed,
)
from backend.api.main import RateLimiter, app, get_rate_limiter

__all__ = [
    "app",
    "get_rate_limiter",
    "RateLimiter",
    "get_config_loader",
    "get_index_manager",
    "get_search_engine",
    "get_file_scanner",
    "get_rag_pipeline",
    "get_file_monitor",
    "is_path_allowed",
]
