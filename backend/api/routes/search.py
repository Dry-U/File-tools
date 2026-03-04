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
from backend.api.dependencies import get_search_engine, get_config_loader, get_rate_limiter, get_index_manager

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
        # 获取客户端IP
        client_ip = http_request.client.host if http_request.client else "unknown"
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
        if not is_path_allowed(path, config_loader):
            logger.warning(f"阻止路径遍历尝试: {path}")
            return {"content": "错误：文件路径超出允许范围"}

        # 标准化路径
        path = path.strip('"').strip("'")
        normalized_path = os.path.normpath(path)

        logger.info(f"尝试预览文件: {normalized_path}")

        # 检查文件是否存在
        if not os.path.exists(normalized_path):
            logger.error(f"文件不存在: {normalized_path}")
            return {"content": f"错误：文件不存在 ({normalized_path})"}

        # 检查文件大小以防止加载过大文件
        max_preview_size = config_loader.getint(
            'interface', 'max_preview_size', 5242880)  # 默认5MB
        if os.path.getsize(normalized_path) > max_preview_size:
            return {"content": "文件过大（超过5MB），无法预览"}

        # 首先尝试从索引管理器获取内容（支持PDF/DOCX等）
        content = index_manager.get_document_content(normalized_path)
        if content:
            return {"content": content}

        # 回退到直接读取文本文件
        try:
            with open(normalized_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 限制预览长度
                max_length = 10000
                if len(content) > max_length:
                    content = content[:max_length] + "\n\n[内容过长，仅显示前10000字符]"
                return {"content": content}
        except UnicodeDecodeError:
            return {"content": "无法预览：文件编码不支持或不是文本文件"}
        except Exception as e:
            logger.error(f"读取文件失败: {normalized_path} - {e}")
            return {"content": f"错误：读取文件失败 - {str(e)}"}

    except Exception as e:
        logger.error(f"预览文件时出错: {str(e)}")
        return {"content": f"错误：{str(e)}"}
