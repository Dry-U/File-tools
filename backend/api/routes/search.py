"""
搜索相关路由
"""

import os
import sys
import errno
import numpy as np
from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends

from backend.api.models import SearchRequest, SearchResult
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.utils.network import get_client_ip
from backend.api.dependencies import (
    get_search_engine,
    get_config_loader,
    get_rate_limiter as rate_limiter_dependency,
    get_index_manager,
    get_resolve_path_if_allowed,
    get_is_path_allowed,
)
from backend.core.constants import ALLOWED_MIME_TYPES, MAX_PREVIEW_LENGTH

logger = get_logger(__name__)
router = APIRouter()


def _format_file_size(size_bytes: int) -> str:
    """将字节大小格式化为人类可读字符串"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _detect_language(file_ext: str, file_path: str) -> str:
    """根据文件扩展名和路径检测编程语言类型"""
    ext_to_language = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".r": "r",
        ".m": "matlab",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".ps1": "powershell",
        ".sql": "sql",
        ".html": "html",
        ".htm": "html",
        ".xml": "xml",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".conf": "ini",
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".log": "text",
        ".csv": "csv",
        ".lua": "lua",
        ".perl": "perl",
        ".pl": "perl",
        ".vim": "vim",
        ".dockerfile": "dockerfile",
        ".makefile": "makefile",
        ".cmake": "cmake",
    }

    # 检查文件名特殊匹配
    lower_path = file_path.lower()
    if "dockerfile" in lower_path:
        return "dockerfile"
    if "makefile" in lower_path or "cmake" in lower_path:
        return "makefile"
    if ".gitignore" in lower_path:
        return "gitignore"

    return ext_to_language.get(file_ext.lower(), "text")


def safe_read_file(path: str, max_length: int = MAX_PREVIEW_LENGTH) -> str:
    """使用 O_NOFOLLOW 标志安全读取文件，防止符号链接攻击

    Args:
        path: 文件路径
        max_length: 最大读取长度

    Returns:
        文件内容

    Raises:
        OSError: 如果文件不存在或无权限
        PermissionError: 如果权限不足
        UnicodeDecodeError: 如果文件编码不支持
    """
    try:
        # Windows 不支持 O_NOFOLLOW，直接使用 O_RDONLY
        open_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW") and sys.platform != "win32":
            open_flags |= os.O_NOFOLLOW
        fd = os.open(path, open_flags)
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            # 获取文件总长度以检查是否超过限制
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0)
            content = f.read(max_length)
            # 如果文件内容超过最大长度，添加提示
            if file_size > max_length:
                content += f"\n\n[内容过长，仅显示前{max_length}字符]"
            return content
    except OSError as e:
        if e.errno == errno.ELOOP:  # 检测到符号链接
            logger.warning(f"检测到符号链接，拒绝访问: {os.path.basename(path)}")
            raise PermissionError(f"不允许访问符号链接: {os.path.basename(path)}")
        raise


@router.post("/search", response_model=List[SearchResult])
async def search(
    request: SearchRequest,
    http_request: Request,
    search_engine=Depends(get_search_engine),
    config_loader: ConfigLoader = Depends(get_config_loader),
    limiter=Depends(rate_limiter_dependency),
    is_path_allowed_fn=Depends(get_is_path_allowed),
):
    """使用搜索引擎执行搜索

    Args:
        request: 搜索请求，包含查询字符串和可选过滤器

    Returns:
        搜索结果列表

    Raises:
        HTTPException: 当搜索失败或限流触发时
    """
    # 限流检查
    if config_loader.getboolean("security", "rate_limiter.enabled", True):
        # 获取客户端IP（使用安全方式）
        client_ip = get_client_ip(http_request, config_loader)
        max_req = config_loader.getint("security", "rate_limiter.search_limit", 20)
        window = config_loader.getint("security", "rate_limiter.search_window", 60)
        if not limiter.is_allowed(
            f"search:{client_ip}", max_requests=max_req, window=window
        ):
            raise HTTPException(status_code=429, detail="搜索过于频繁，请稍后再试")

    try:
        query = request.query
        filters = request.filters or {}

        if not query:
            raise HTTPException(status_code=400, detail="查询不能为空")

        if len(query) > 500:
            raise HTTPException(status_code=400, detail="查询长度不能超过500字符")

        results = search_engine.search(query, filters)

        # 转换结果为JSON可序列化的格式
        def convert_types(obj):
            if isinstance(obj, float):
                return obj
            if isinstance(obj, int):
                return obj
            if isinstance(obj, str):
                return obj
            if obj is None:
                return None
            if isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.ndarray):
                return [convert_types(item) for item in obj]
            elif isinstance(obj, (list, tuple)):
                return [convert_types(item) for item in obj]
            elif isinstance(obj, dict):
                result_dict = {}
                for key, value in obj.items():
                    converted_value = convert_types(value)
                    # 确保分数不超过100
                    if key == "score":
                        try:
                            # 先检查是否是数字类型
                            if converted_value is None:
                                score = 0.0
                            elif isinstance(converted_value, (int, float, str)):
                                # 只有数字和字符串可以尝试转换为float
                                score = float(converted_value)
                            else:
                                # 其他类型（如字典、列表）使用默认值
                                score = 0.0
                            converted_value = min(score, 100.0)
                        except (TypeError, ValueError):
                            # 如果转换失败，使用默认值0.0
                            converted_value = 0.0
                    result_dict[key] = converted_value
                return result_dict
            elif hasattr(obj, "isoformat"):  # datetime对象
                return obj.isoformat()
            else:
                return obj

        formatted_results = []
        for result in results:
            converted_result = convert_types(result)
            if isinstance(converted_result, dict):
                file_path = str(converted_result.get("path", ""))
                # 过滤掉不在允许路径内的文件
                if not is_path_allowed_fn(file_path, config_loader):
                    logger.debug(f"搜索结果过滤（路径不在允许范围内）: {file_path}")
                    continue
                formatted_results.append(
                    {
                        "file_name": os.path.basename(file_path),
                        "path": file_path,
                        "score": converted_result.get("score", 0.0),
                        "snippet": converted_result.get("snippet", ""),
                    }
                )

        return formatted_results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索错误: {str(e)}")
        raise HTTPException(status_code=500, detail="搜索处理失败，请稍后重试") from e


@router.post("/preview")
async def preview_file(
    request: Request,
    index_manager=Depends(get_index_manager),
    config_loader: ConfigLoader = Depends(get_config_loader),
    resolve_path_if_allowed_fn=Depends(get_resolve_path_if_allowed),
):
    """预览文件内容，带有路径遍历保护"""
    try:
        body = await request.json()
        path = body.get("path", "")

        if not path:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {"code": "PATH_REQUIRED", "message": "未提供文件路径"}
                },
            )

        # 验证路径是否在允许的目录内，并获取解析后的路径（避免 TOCTOU）
        normalized_path = resolve_path_if_allowed_fn(path, config_loader)
        if normalized_path is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "PATH_NOT_ALLOWED",
                        "message": "文件路径超出允许范围",
                    }
                },
            )

        # normalized_path 已经是 resolve_path_if_allowed 返回的解析后路径
        safe_name = normalized_path.name
        logger.info(f"尝试预览文件: {safe_name}")

        # 检查路径是否为目录
        if normalized_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "IS_DIRECTORY", "message": "无法预览目录"}},
            )

        # 检查文件是否存在
        if not normalized_path.exists():
            logger.warning("预览文件不存在")
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FILE_NOT_FOUND", "message": "文件不存在"}},
            )

        # 检查文件大小以防止加载过大文件
        max_preview_size = config_loader.getint(
            "interface", "max_preview_size", 5242880
        )  # 默认5MB
        try:
            file_size = normalized_path.stat().st_size
            if file_size > max_preview_size:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": {
                            "code": "FILE_TOO_LARGE",
                            "message": f"文件过大（超过{max_preview_size / 1024 / 1024:.0f}MB），无法预览",
                        }
                    },
                )
        except (OSError, IOError) as e:
            logger.error(f"无法读取文件信息: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {"code": "FILE_INFO_ERROR", "message": "无法读取文件信息"}
                },
            )

        # MIME 类型检查
        import mimetypes

        mime_type, _ = mimetypes.guess_type(str(normalized_path))
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"不支持的 MIME 类型: {mime_type}")
            raise HTTPException(
                status_code=415,
                detail={
                    "error": {
                        "code": "UNSUPPORTED_TYPE",
                        "message": f"不支持的文件类型 ({mime_type})",
                    }
                },
            )

        # 获取文件信息
        file_stat = normalized_path.stat()
        file_size = file_stat.st_size
        file_ext = normalized_path.suffix.lower()

        # 首先尝试从索引管理器获取内容（支持PDF/DOCX等）
        content = None
        try:
            content = index_manager.get_document_content(str(normalized_path))
        except Exception as e:
            logger.debug(f"从索引获取内容失败: {e}")

        # 回退到直接读取文本文件
        if not content:
            try:
                content = safe_read_file(str(normalized_path), MAX_PREVIEW_LENGTH)
            except Exception:
                raise

        # 计算内容统计信息
        if content:
            content_length = len(content)
            line_count = content.count('\n') + 1
            is_truncated = content_length >= MAX_PREVIEW_LENGTH

            # 检测文件类型用于语法高亮
            language = _detect_language(file_ext, str(normalized_path))

            return {
                "content": content,
                "metadata": {
                    "file_name": safe_name,
                    "file_size": file_size,
                    "file_size_formatted": _format_file_size(file_size),
                    "content_length": content_length,
                    "line_count": line_count,
                    "is_truncated": is_truncated,
                    "max_preview_length": MAX_PREVIEW_LENGTH,
                    "truncated_at": MAX_PREVIEW_LENGTH if is_truncated else None,
                    "language": language,
                    "file_extension": file_ext,
                    "mime_type": mime_type,
                }
            }

        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "EMPTY_CONTENT", "message": "无法读取文件内容"}}
        )

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail={
                "error": {
                    "code": "ENCODING_ERROR",
                    "message": "文件编码不支持或不是文本文件",
                }
            },
        )
    except PermissionError as e:
        if "符号链接" in str(e):
            logger.warning(f"拒绝符号链接访问: {normalized_path.name}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "SYMLINK_DENIED",
                        "message": "不允许访问符号链接",
                    }
                },
            )
        else:
            logger.warning(f"无权限读取文件: {normalized_path.name}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "无权限读取文件",
                    }
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览文件时出错: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "PREVIEW_ERROR", "message": "预览处理失败"}},
        ) from e
