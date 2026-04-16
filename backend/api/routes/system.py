"""
系统/健康检查相关路由
"""

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import (
    get_config_loader,
    get_file_scanner,
    get_index_manager,
)
from backend.api.dependencies import (
    get_rate_limiter as rate_limiter_dependency,
)
from backend.api.models import HealthCheckResponse
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.utils.network import get_client_ip

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
    limiter=Depends(rate_limiter_dependency),
):
    """重建文件索引（同步版本，保留向后兼容）"""
    # 限流检查
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
    with _rebuild_lock:
        if _rebuild_progress_state["in_progress"]:
            raise HTTPException(
                status_code=409, detail="重建任务正在进行中，请稍后再试"
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

# 保护 _rebuild_progress_state 的线程锁（使用 RLock 防止回调中同线程重入死锁）
_rebuild_lock = threading.RLock()


@router.get("/rebuild-progress")
async def get_rebuild_progress():
    """获取当前重建索引的进度状态"""
    with _rebuild_lock:
        return {
            "in_progress": _rebuild_progress_state["in_progress"],
            "progress": _rebuild_progress_state["progress"],
            "current_file": _rebuild_progress_state["current_file"],
            "files_scanned": _rebuild_progress_state["files_scanned"],
            "files_indexed": _rebuild_progress_state["files_indexed"],
            "error": _rebuild_progress_state["error"],
        }


@router.get("/rebuild-index/stream")
async def rebuild_index_stream(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_scanner=Depends(get_file_scanner),
    limiter=Depends(rate_limiter_dependency),
):
    """重建文件索引（带进度流式返回）"""
    import asyncio
    import json
    import queue

    from fastapi.responses import StreamingResponse

    # 限流检查
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
    with _rebuild_lock:
        if _rebuild_progress_state["in_progress"]:
            raise HTTPException(
                status_code=409, detail="重建任务正在进行中，请稍后再试"
            )

    # 用于线程间通信的队列
    progress_queue = queue.Queue()

    async def event_generator():
        """SSE事件生成器"""
        keepalive_interval = 5  # 每5秒发送一次 keepalive

        with _rebuild_lock:
            _rebuild_progress_state["in_progress"] = True
            _rebuild_progress_state["progress"] = 0
            _rebuild_progress_state["current_file"] = ""
            _rebuild_progress_state["files_scanned"] = 0
            _rebuild_progress_state["files_indexed"] = 0
            _rebuild_progress_state["error"] = None

        def progress_callback(progress):
            """进度回调函数 - 发送进度到队列并更新全局状态"""
            try:
                progress_queue.put_nowait(("progress", progress))
            except queue.Full:
                pass
            # 同步更新全局进度状态，以便轮询端点也能获取
            with _rebuild_lock:
                _rebuild_progress_state["progress"] = progress
                # 从 file_scanner 的统计信息中获取已扫描/已索引数
                try:
                    if hasattr(file_scanner, 'scan_stats'):
                        _rebuild_progress_state["files_scanned"] = file_scanner.scan_stats.get("total_files_scanned", 0)
                        _rebuild_progress_state["files_indexed"] = file_scanner.scan_stats.get("total_files_indexed", 0)
                except Exception:
                    pass

        try:
            original_callback = file_scanner.progress_callback
            file_scanner.progress_callback = progress_callback

            loop = asyncio.get_event_loop()
            scan_task = loop.run_in_executor(None, file_scanner.scan_and_index)

            scan_done = False
            last_yield_time = time.time()
            while not scan_done:
                # 不再阻塞等待断开检测，直接处理进度
                # 如果客户端断开，yield会自然失败

                # 检查任务是否完成
                if scan_task.done():
                    scan_done = True
                    break

                # 处理队列中的进度消息
                try:
                    while True:
                        item = progress_queue.get_nowait()
                        if item[0] == "progress":
                            progress = item[1]
                            with _rebuild_lock:
                                _rebuild_progress_state["progress"] = progress
                            try:
                                progress_data = {
                                    "status": "progress",
                                    "progress": progress,
                                }
                                yield f"data: {json.dumps(progress_data)}\n\n"
                                last_yield_time = time.time()
                            except Exception:
                                # 客户端已断开，发送最终状态后退出
                                logger.info("SSE: 客户端已断开，发送最终状态")
                                with _rebuild_lock:
                                    _rebuild_progress_state["in_progress"] = False
                                disconnected_data = {
                                    "status": "disconnected",
                                    "progress": _rebuild_progress_state["progress"],
                                    "files_scanned": _rebuild_progress_state.get(
                                        "files_scanned", 0
                                    ),
                                    "files_indexed": _rebuild_progress_state.get(
                                        "files_indexed", 0
                                    ),
                                }
                                yield f"data: {json.dumps(disconnected_data)}\n\n"
                                return
                except queue.Empty:
                    pass

                # 定期发送 keepalive 保持连接活跃
                current_time = time.time()
                if current_time - last_yield_time >= keepalive_interval:
                    try:
                        keepalive_data = {
                            "status": "keepalive",
                            "progress": _rebuild_progress_state["progress"],
                        }
                        yield f"data: {json.dumps(keepalive_data)}\n\n"
                        last_yield_time = current_time
                    except Exception:
                        # 客户端已断开
                        logger.info("SSE: keepalive发送时客户端断开")
                        return

                await asyncio.sleep(0.05)  # 减少等待时间，更快响应

                # 检查是否被取消
                with _rebuild_lock:
                    if not _rebuild_progress_state["in_progress"]:
                        if _rebuild_progress_state.get("error") == "用户取消":
                            cancelled_data = {
                                "status": "cancelled",
                                "progress": _rebuild_progress_state["progress"],
                                "files_scanned": _rebuild_progress_state.get("files_scanned", 0),
                                "files_indexed": _rebuild_progress_state.get("files_indexed", 0),
                            }
                            yield f"data: {json.dumps(cancelled_data)}\n\n"
                            logger.info("SSE: 发送取消消息到客户端")
                            return

            # 获取扫描结果
            stats = None
            try:
                logger.info("SSE: 准备获取扫描结果...")
                stats = scan_task.result()
                logger.info(f"SSE: 获取到扫描结果: {stats}")
            except Exception as e:
                logger.error(f"SSE: 获取扫描结果异常: {str(e)}")
                # 发送错误消息后让异常继续传播到外层
                with _rebuild_lock:
                    _rebuild_progress_state["error"] = str(e)
                    _rebuild_progress_state["in_progress"] = False
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
                return  # 显式返回，避免继续执行

            with _rebuild_lock:
                _rebuild_progress_state["progress"] = 100
                _rebuild_progress_state["files_scanned"] = stats.get(
                    "total_files_scanned", 0
                )
                _rebuild_progress_state["files_indexed"] = stats.get(
                    "total_files_indexed", 0
                )
                _rebuild_progress_state["in_progress"] = False

            # 发送成功消息
            success_data = {"status": "success", "progress": 100, **stats}
            success_msg = f"data: {json.dumps(success_data)}\n\n"
            logger.info(f"SSE: 发送成功消息, data={success_data}")
            try:
                yield success_msg
                # 多次 flush 确保消息被发送（WebView2需要更多flush）
                await asyncio.sleep(0.1)
                await asyncio.sleep(0.05)
                await asyncio.sleep(0)
                logger.info("SSE: 成功消息已发送")
            except Exception as e:
                logger.warning(f"SSE: 发送成功消息时客户端已断开: {e}")

        except Exception as e:
            logger.error(f"重建索引错误: {str(e)}")
            try:
                with _rebuild_lock:
                    _rebuild_progress_state["error"] = str(e)
                    _rebuild_progress_state["in_progress"] = False
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
            except Exception:
                pass  # 避免在错误处理中再次抛出异常

        finally:
            try:
                file_scanner.progress_callback = original_callback
                with _rebuild_lock:
                    _rebuild_progress_state["in_progress"] = False
            except Exception:
                pass  # 避免在 finally 中抛出异常

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
            "Transfer-Encoding": "chunked",
        },
    )


@router.delete("/rebuild-index")
async def cancel_rebuild_index(
    request: Request,
    file_scanner=Depends(get_file_scanner),
):
    """取消正在进行的重建索引任务"""
    with _rebuild_lock:
        if not _rebuild_progress_state["in_progress"]:
            return {"status": "success", "message": "没有正在进行的重建任务"}

    try:
        file_scanner.stop_scan()

        with _rebuild_lock:
            _rebuild_progress_state["in_progress"] = False
            _rebuild_progress_state["progress"] = 0
            _rebuild_progress_state["error"] = "用户取消"
            files_scanned = _rebuild_progress_state["files_scanned"]
            files_indexed = _rebuild_progress_state["files_indexed"]

        return {
            "status": "success",
            "message": "重建任务已取消",
            "files_scanned": files_scanned,
            "files_indexed": files_indexed,
        }
    except Exception as e:
        logger.error(f"取消重建索引错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消重建失败: {str(e)}")


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


# 更新检查缓存（避免频繁调用 GitHub API）
_update_cache: dict = {}
_UPDATE_CACHE_TTL = 300  # 5 分钟缓存


@router.get("/check-update")
async def check_update():
    """检查 GitHub Releases 是否有新版本

    返回最新版本信息及当前版本与最新版本的比较结果。
    结果缓存5分钟以避免频繁调用 GitHub API 被限流。
    """
    import time

    import requests
    from packaging import version as pkg_version

    # 检查缓存
    now = time.time()
    if _update_cache and now - _update_cache.get("_timestamp", 0) < _UPDATE_CACHE_TTL:
        return _update_cache.get("data", {})

    current = get_version()
    repo = "Dry-U/File-tools"

    try:
        # 调用 GitHub API 获取最新 release
        response = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        latest_version = data.get("tag_name", "").lstrip("v")
        download_url = data.get("html_url", "")
        release_notes = data.get("body", "")[:500]  # 限制长度

        # 比较版本
        try:
            is_update_available = pkg_version.parse(latest_version) > pkg_version.parse(
                current
            )
        except Exception:
            # 版本解析失败，简单比较字符串
            is_update_available = latest_version != current

        result = {
            "current_version": current,
            "latest_version": latest_version,
            "is_update_available": is_update_available,
            "download_url": download_url,
            "release_notes": release_notes,
            "repo": repo,
        }

        # 更新缓存
        _update_cache["_timestamp"] = now
        _update_cache["data"] = result

        return result
    except requests.RequestException as e:
        logger.warning(f"检查更新失败: {e}")
        raise HTTPException(status_code=503, detail="无法连接到更新服务器")
    except Exception as e:
        logger.error(f"检查更新异常: {e}")
        raise HTTPException(status_code=500, detail="检查更新失败")


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


@router.post("/shutdown")
async def shutdown_app(request: Request):
    """优雅关闭应用（供 Rust 端调用）

    此端点用于 Tauri 后端向 Python 后端发送优雅关闭信号。
    收到请求后执行清理逻辑，然后终止进程。
    """
    import os

    logger.info("收到关闭请求，开始执行清理...")

    # 执行与应用 lifespan 相同的清理逻辑
    try:
        # 停止文件监控
        if (
            hasattr(request.app.state, "file_monitor")
            and request.app.state.file_monitor
        ):
            try:
                request.app.state.file_monitor.stop_monitoring()
                logger.info("文件监控已停止")
            except Exception as e:
                logger.error(f"停止文件监控时出错: {e}")

        # 关闭文件扫描器
        if (
            hasattr(request.app.state, "file_scanner")
            and request.app.state.file_scanner
        ):
            try:
                request.app.state.file_scanner.close()
                logger.info("文件扫描器已关闭")
            except Exception as e:
                logger.error(f"关闭文件扫描器时出错: {e}")

        # 关闭索引管理器
        if (
            hasattr(request.app.state, "index_manager")
            and request.app.state.index_manager
        ):
            try:
                request.app.state.index_manager.close()
                logger.info("索引管理器已关闭")
            except Exception as e:
                logger.error(f"关闭索引管理器时出错: {e}")

        # 关闭 RAG Pipeline
        if (
            hasattr(request.app.state, "rag_pipeline")
            and request.app.state.rag_pipeline
        ):
            try:
                if (
                    hasattr(request.app.state.rag_pipeline, "model_manager")
                    and request.app.state.rag_pipeline.model_manager
                ):
                    request.app.state.rag_pipeline.model_manager.close()
                logger.info("RAG Pipeline 已关闭")
            except Exception as e:
                logger.error(f"关闭 RAG Pipeline 时出错: {e}")

        # 关闭限流器
        if (
            hasattr(request.app.state, "rate_limiter")
            and request.app.state.rate_limiter
        ):
            try:
                request.app.state.rate_limiter.shutdown()
                logger.info("限流器已关闭")
            except Exception as e:
                logger.error(f"关闭限流器时出错: {e}")

        logger.info("清理完成，正在终止进程...")

        # 返回成功响应后再终止进程
        # 使用 os._exit(0) 立即终止，不执行任何清理（已在上方完成）
        os._exit(0)

    except Exception as e:
        logger.error(f"关闭时发生异常: {e}")
        # 即使异常也尝试保存关键索引数据
        try:
            if (
                hasattr(request.app.state, "index_manager")
                and request.app.state.index_manager
            ):
                request.app.state.index_manager.close()
                logger.info("紧急保存索引完成")
        except Exception:
            pass
        os._exit(1)
