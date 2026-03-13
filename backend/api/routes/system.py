"""
系统/健康检查相关路由
"""

import time
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends

from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.api.dependencies import (
    get_config_loader, get_index_manager, get_file_scanner, get_rate_limiter
)
from backend.api.main import app
from backend.api.models import HealthCheckResponse

logger = get_logger(__name__)
router = APIRouter()


@router.post("/rebuild-index")
async def rebuild_index(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_scanner=Depends(get_file_scanner)
):
    """重建文件索引"""
    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean('security', 'rate_limiter.enabled', True):
        client_ip = request.client.host if request.client else "unknown"
        max_req = config_loader.getint(
            'security', 'rate_limiter.rebuild_limit', 1)
        window = config_loader.getint(
            'security', 'rate_limiter.rebuild_window', 600)
        if not limiter.is_allowed(f"rebuild:{client_ip}", max_requests=max_req, window=window):
            raise HTTPException(
                status_code=429, detail="重建索引过于频繁，请10分钟后再试")

    try:
        logger.info("开始重建索引...")
        stats = file_scanner.scan_and_index()
        logger.info(f"索引重建完成: {stats}")
        return {
            "status": "success",
            "message": "索引重建完成",
            "files_scanned": stats.get('total_files_scanned', 0),
            "files_indexed": stats.get('total_files_indexed', 0)
        }
    except Exception as e:
        logger.error(f"重建索引错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重建索引失败: {str(e)}")


@router.get("/health")
async def health_check(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager=Depends(get_index_manager)
) -> HealthCheckResponse:
    """健康检查端点，返回系统状态和各组件健康情况"""
    try:
        # 获取各组件状态
        components: Dict[str, Any] = {}

        # 检查索引管理器
        try:
            index_health = index_manager.get_index_stats()
            components['index_manager'] = {
                "status": "healthy",
                "indexed_documents": index_health.get('indexed_count', 0)
            }
        except Exception as e:
            components['index_manager'] = {
                "status": "unhealthy",
                "error": str(e)
            }

        # 检查RAG管道（支持优雅降级状态）
        try:
            rag_status = getattr(app.state, 'rag_status', 'unknown')
            rag_error = getattr(app.state, 'rag_error', None)

            if rag_status == "ready":
                components['rag_pipeline'] = {
                    "status": "ready",
                    "enabled": True
                }
            elif rag_status == "error":
                components['rag_pipeline'] = {
                    "status": "error",
                    "enabled": True,
                    "error": rag_error or "未知错误",
                    "message": "AI功能暂时不可用，其他功能正常"
                }
            elif getattr(app.state, 'rag_initializing', False):
                components['rag_pipeline'] = {
                    "status": "initializing",
                    "enabled": True
                }
            else:
                enabled = config_loader.getboolean('ai_model', 'enabled', False)
                components['rag_pipeline'] = {
                    "status": "disabled",
                    "enabled": enabled
                }
        except Exception as e:
            components['rag_pipeline'] = {
                "status": "error",
                "error": str(e)
            }

        # 整体状态
        all_healthy = all(
            c.get("status") in ["healthy", "ready", "disabled"]
            for c in components.values()
        )

        health_status = "healthy" if all_healthy else "degraded"

        return HealthCheckResponse(
            status=health_status,
            initialized=getattr(app.state, 'initialized', False),
            timestamp=time.time(),
            components=components
        )
    except Exception as e:
        logger.error(f"健康检查错误: {str(e)}")
        raise HTTPException(status_code=500, detail="健康检查失败") from e


@router.get("/health/ready")
async def readiness_check():
    """就绪检查 - 用于Kubernetes等环境的就绪探针"""
    if getattr(app.state, 'initialized', False):
        return {"ready": True}
    else:
        raise HTTPException(status_code=503, detail="服务尚未就绪")


@router.get("/health/live")
async def liveness_check():
    """存活检查 - 用于Kubernetes等环境的存活探针"""
    return {"alive": True}
