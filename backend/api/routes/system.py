"""
系统/健康检查相关路由
"""

import os
import time
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends

from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.api.dependencies import (
    get_config_loader,
    get_index_manager,
    get_file_scanner,
    get_rate_limiter,
)
from backend.utils.network import get_client_ip
from backend.api.models import HealthCheckResponse

logger = get_logger(__name__)
router = APIRouter()


def get_version() -> str:
    """获取应用版本号

    优先级:
    1. 环境变量 FILETOOLS_VERSION (CI构建时注入)
    2. 包元数据 (importlib.metadata)
    3. VERSION 文件
    4. 默认版本 "0.1.0"
    """
    # 1. 检查环境变量 (CI构建时注入)
    env_version = os.environ.get("FILETOOLS_VERSION")
    if env_version:
        return env_version.strip()

    # 2. 尝试从包元数据读取
    try:
        from importlib.metadata import version as get_pkg_version

        return get_pkg_version("file-tools")
    except Exception:
        pass

    # 3. 尝试读取 VERSION 文件
    try:
        version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass

    # 4. 默认版本
    return "0.1.0"


@router.post("/rebuild-index")
async def rebuild_index(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_scanner=Depends(get_file_scanner),
):
    """重建文件索引（同步版本，保留向后兼容）"""
    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean("security", "rate_limiter.enabled", True):
        client_ip = get_client_ip(request, config_loader)
        max_req = config_loader.getint("security", "rate_limiter.rebuild_limit", 1)
        window = config_loader.getint("security", "rate_limiter.rebuild_window", 600)
        if not limiter.is_allowed(
            f"rebuild:{client_ip}", max_requests=max_req, window=window
        ):
            raise HTTPException(
                status_code=429, detail="重建索引过于频繁，请10分钟后再试"
            )

    try:
        logger.info("开始重建索引...")
        stats = file_scanner.scan_and_index()
        logger.info(f"索引重建完成: {stats}")
        return {
            "status": "success",
            "message": "索引重建完成",
            "files_scanned": stats.get("total_files_scanned", 0),
            "files_indexed": stats.get("total_files_indexed", 0),
        }
    except Exception as e:
        logger.error(f"重建索引错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重建索引失败: {str(e)}")


# 重建进度状态（模块级全局变量）
_rebuild_progress_state = {
    "in_progress": False,
    "progress": 0,
    "current_file": "",
    "files_scanned": 0,
    "files_indexed": 0,
    "error": None,
}


@router.get("/rebuild-progress")
async def get_rebuild_progress():
    """获取当前重建索引的进度状态"""
    return {
        "in_progress": _rebuild_progress_state["in_progress"],
        "progress": _rebuild_progress_state["progress"],
        "current_file": _rebuild_progress_state["current_file"],
        "files_scanned": _rebuild_progress_state["files_scanned"],
        "files_indexed": _rebuild_progress_state["files_indexed"],
        "error": _rebuild_progress_state["error"],
    }


@router.post("/rebuild-index/stream")
async def rebuild_index_stream(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_scanner=Depends(get_file_scanner),
):
    """重建文件索引（带进度流式返回）"""
    from fastapi.responses import StreamingResponse
    import json
    import asyncio

    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean("security", "rate_limiter.enabled", True):
        client_ip = get_client_ip(request, config_loader)
        max_req = config_loader.getint("security", "rate_limiter.rebuild_limit", 1)
        window = config_loader.getint("security", "rate_limiter.rebuild_window", 600)
        if not limiter.is_allowed(
            f"rebuild:{client_ip}", max_requests=max_req, window=window
        ):
            raise HTTPException(
                status_code=429, detail="重建索引过于频繁，请10分钟后再试"
            )

    # 检查是否已有重建任务在进行
    if _rebuild_progress_state["in_progress"]:
        raise HTTPException(status_code=409, detail="重建任务正在进行中，请稍后再试")

    async def event_generator():
        """SSE事件生成器"""
        # 重置进度状态
        _rebuild_progress_state["in_progress"] = True
        _rebuild_progress_state["progress"] = 0
        _rebuild_progress_state["current_file"] = ""
        _rebuild_progress_state["files_scanned"] = 0
        _rebuild_progress_state["files_indexed"] = 0
        _rebuild_progress_state["error"] = None

        def progress_callback(progress):
            """进度回调函数"""
            _rebuild_progress_state["progress"] = progress

        try:
            # 设置进度回调
            original_callback = file_scanner.progress_callback
            file_scanner.progress_callback = progress_callback

            # 在线程池中执行耗时的扫描操作
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(None, file_scanner.scan_and_index)

            # 扫描完成，更新最终状态
            _rebuild_progress_state["progress"] = 100
            _rebuild_progress_state["files_scanned"] = stats.get(
                "total_files_scanned", 0
            )
            _rebuild_progress_state["files_indexed"] = stats.get(
                "total_files_indexed", 0
            )
            _rebuild_progress_state["in_progress"] = False

            # 发送完成事件
            yield f"data: {json.dumps({'status': 'success', 'progress': 100, **stats})}\n\n"

        except Exception as e:
            logger.error(f"重建索引错误: {str(e)}")
            _rebuild_progress_state["error"] = str(e)
            _rebuild_progress_state["in_progress"] = False
            yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"

        finally:
            # 恢复原始回调
            file_scanner.progress_callback = original_callback

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
        },
    )


@router.get("/health")
async def health_check(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager=Depends(get_index_manager),
) -> HealthCheckResponse:
    """健康检查端点，返回系统状态和各组件健康情况"""
    try:
        # 获取各组件状态
        components: Dict[str, Any] = {}

        # 检查索引管理器
        try:
            index_health = index_manager.get_index_stats()
            components["index_manager"] = {
                "status": "healthy",
                "indexed_documents": index_health.get("indexed_count", 0),
            }
        except Exception as e:
            components["index_manager"] = {"status": "unhealthy", "error": str(e)}

        # 检查RAG管道（支持优雅降级状态）
        try:
            rag_status = getattr(request.app.state, "rag_status", "unknown")
            rag_error = getattr(request.app.state, "rag_error", None)

            if rag_status == "ready":
                components["rag_pipeline"] = {"status": "ready", "enabled": True}
            elif rag_status == "error":
                components["rag_pipeline"] = {
                    "status": "error",
                    "enabled": True,
                    "error": rag_error or "未知错误",
                    "message": "AI功能暂时不可用，其他功能正常",
                }
            elif getattr(request.app.state, "rag_initializing", False):
                components["rag_pipeline"] = {"status": "initializing", "enabled": True}
            else:
                enabled = config_loader.getboolean("ai_model", "enabled", False)
                components["rag_pipeline"] = {"status": "disabled", "enabled": enabled}
        except Exception as e:
            components["rag_pipeline"] = {"status": "error", "error": str(e)}

        # 整体状态
        all_healthy = all(
            c.get("status") in ["healthy", "ready", "disabled"]
            for c in components.values()
        )

        health_status = "healthy" if all_healthy else "degraded"

        return HealthCheckResponse(
            status=health_status,
            initialized=getattr(request.app.state, "initialized", False),
            timestamp=time.time(),
            components=components,
        )
    except Exception as e:
        logger.error(f"健康检查错误: {str(e)}")
        raise HTTPException(status_code=500, detail="健康检查失败") from e


@router.get("/health/ready")
async def readiness_check(request: Request):
    """就绪检查 - 用于Kubernetes等环境的就绪探针"""
    if getattr(request.app.state, "initialized", False):
        return {"ready": True}
    else:
        raise HTTPException(status_code=503, detail="服务尚未就绪")


@router.get("/health/live")
async def liveness_check():
    """存活检查 - 用于Kubernetes等环境的存活探针"""
    return {"alive": True}


@router.get("/version")
async def version_check():
    """获取应用版本信息"""
    return {
        "version": get_version(),
        "name": "file-tools",
        "description": "智能文件检索与问答系统",
    }


@router.get("/initialization-status")
async def initialization_status(request: Request):
    """获取应用初始化状态（前端轮询使用）

    返回各组件的初始化进度和状态，前端可在启动时轮询此端点
    展示加载进度，避免用户在系统未就绪时操作。
    """
    initialized = getattr(request.app.state, "initialized", False)
    components: Dict[str, Any] = {}

    # 索引管理器状态
    try:
        index_manager = None
        if hasattr(request.app.state, "index_manager"):
            index_manager = request.app.state.index_manager
        if index_manager and getattr(index_manager, "index_ready", False):
            try:
                stats = index_manager.get_index_stats()
                components["index"] = {
                    "status": "ready",
                    "tantivy_docs": stats.get("tantivy_docs", 0),
                    "vector_docs": stats.get("vector_docs", 0),
                }
            except Exception:
                components["index"] = {"status": "ready"}
        else:
            components["index"] = {"status": "initializing"}
    except Exception:
        components["index"] = {"status": "initializing"}

    # RAG 管道状态
    try:
        rag_status = getattr(request.app.state, "rag_status", "unknown")
        rag_error = getattr(request.app.state, "rag_error", None)
        components["rag"] = {"status": rag_status, "error": rag_error}
    except Exception:
        components["rag"] = {"status": "unknown"}

    # 文件监控状态
    try:
        monitor = getattr(request.app.state, "file_monitor", None)
        if monitor and getattr(monitor, "_running", False):
            components["monitor"] = {"status": "running"}
        elif monitor:
            components["monitor"] = {"status": "stopped"}
        else:
            components["monitor"] = {"status": "disabled"}
    except Exception:
        components["monitor"] = {"status": "unknown"}

    return {
        "initialized": initialized,
        "components": components,
        "version": get_version(),
    }
