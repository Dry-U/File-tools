"""
搜索相关路由
"""

import os
import numpy as np
from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends

from backend.api.models import SearchRequest, SearchResult
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.utils.network import get_client_ip, is_valid_ip
from backend.api.dependencies import get_search_engine, get_config_loader, get_rate_limiter, get_index_manager
from backend.core.constants import ALLOWED_MIME_TYPES, MAX_PREVIEW_LENGTH

logger = get_logger(__name__)
router = APIRouter()


@router.post("/search", response_model=List[SearchResult])
async def search(
    request: SearchRequest,
    http_request: Request,
    search_engine=Depends(get_search_engine),
    config_loader: ConfigLoader = Depends(get_config_loader)
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
    limiter = get_rate_limiter()
    if config_loader.getboolean('security', 'rate_limiter.enabled', True):
        # 获取客户端IP（使用安全方式）
        client_ip = get_client_ip(http_request, config_loader)
        max_req = config_loader.getint(
            'security', 'rate_limiter.search_limit', 20)
        window = config_loader.getint(
            'security', 'rate_limiter.search_window', 60)
        if not limiter.is_allowed(f"search:{client_ip}", max_requests=max_req, window=window):
            raise HTTPException(status_code=429, detail="搜索过于频繁，请稍后再试")

    try:
        query = request.query
        filters = request.filters or {}

        if not query:
            raise HTTPException(status_code=400, detail="查询不能为空")

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
                    if key == 'score':
                        converted_value = min(float(converted_value), 100.0)
                    result_dict[key] = converted_value
                return result_dict
            elif hasattr(obj, 'isoformat'):  # datetime对象
                return obj.isoformat()
            else:
                return obj

        formatted_results = []
        for result in results:
            converted_result = convert_types(result)
            if isinstance(converted_result, dict):
                formatted_results.append({
                    "file_name": os.path.basename(str(converted_result.get("path", ""))),
                    "path": str(converted_result.get("path", "")),
                    "score": converted_result.get("score", 0.0),
                    "snippet": converted_result.get("snippet", "")
                })

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
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """预览文件内容，带有路径遍历保护"""
    from backend.api.dependencies import is_path_allowed

    try:
        body = await request.json()
        path = body.get("path", "")

        if not path:
            return {"content": "错误：未提供文件路径"}

        # 验证路径是否在允许的目录内
        # is_path_allowed 已经处理了路径标准化和安全检查
        if not is_path_allowed(path, config_loader):
            # 注意：is_path_allowed 内部已经记录了安全警告
            return {"content": "错误：文件路径超出允许范围"}

        # 路径已经由 is_path_allowed 验证和标准化，无需再次标准化
        # 但为了安全起见，我们使用 Path 对象
        normalized_path = Path(path).resolve()

        # 安全日志：不记录完整路径
        safe_name = normalized_path.name
        logger.info(f"尝试预览文件: {safe_name}")

        # 检查路径是否为目录
        if normalized_path.is_dir():
            return {"content": "错误：无法预览目录"}

        # 检查文件是否存在
        if not normalized_path.exists():
            logger.warning(f"预览文件不存在")
            return {"content": "错误：文件不存在"}

        # 检查文件大小以防止加载过大文件
        max_preview_size = config_loader.getint(
            'interface', 'max_preview_size', 5242880)  # 默认5MB
        try:
            file_size = normalized_path.stat().st_size
            if file_size > max_preview_size:
                return {"content": f"文件过大（超过{max_preview_size/1024/1024:.0f}MB），无法预览"}
        except (OSError, IOError):
            return {"content": "错误：无法读取文件信息"}

        # MIME 类型检查
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(normalized_path))
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"不支持的 MIME 类型: {mime_type}")
            return {"content": f"错误：不支持的文件类型 ({mime_type})"}

        # 首先尝试从索引管理器获取内容（支持PDF/DOCX等）
        try:
            content = index_manager.get_document_content(str(normalized_path))
            if content:
                return {"content": content}
        except Exception as e:
            logger.debug(f"从索引获取内容失败: {e}")

        # 回退到直接读取文本文件
        try:
            with open(normalized_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 限制预览长度
                if len(content) > MAX_PREVIEW_LENGTH:
                    content = content[:MAX_PREVIEW_LENGTH] + f"\n\n[内容过长，仅显示前{MAX_PREVIEW_LENGTH}字符]"
                return {"content": content}
        except UnicodeDecodeError:
            return {"content": "无法预览：文件编码不支持或不是文本文件"}
        except PermissionError:
            logger.warning(f"无权限读取文件")
            return {"content": "错误：无权限读取文件"}
        except Exception as e:
            # 安全日志：不泄露文件路径
            logger.error(f"读取文件失败: {e}")
            return {"content": "错误：读取文件失败"}

    except Exception as e:
        logger.error(f"预览文件时出错")
        return {"content": "错误：预览处理失败"}
