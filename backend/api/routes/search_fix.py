"""
搜索相关路由
"""

import errno
import os
import sys

from fastapi import APIRouter

from backend.core.constants import MAX_PREVIEW_LENGTH
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


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
