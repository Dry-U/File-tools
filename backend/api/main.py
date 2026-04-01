"""
FastAPI 应用主文件 - 初始化和生命周期管理
"""

import time
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from collections import OrderedDict

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi import Request

from backend.utils.logger import get_logger
from backend.api.routes.system import get_version

logger = get_logger(__name__)


# 请求限流器 - 防止接口被滥用
class RateLimiter:
    """基于内存的请求限流器（使用 OrderedDict 实现 LRU 清理）"""

    # 默认配置
    DEFAULT_MAX_ENTRIES = 10000  # 最大条目数，防止内存无限增长
    DEFAULT_CLEANUP_INTERVAL = 300  # 5 分钟清理一次（降低频率）

    def __init__(self, max_entries: Optional[int] = None):
        self._requests = OrderedDict()  # 使用 OrderedDict 支持 LRU 清理
        self._max_entries = max_entries or self.DEFAULT_MAX_ENTRIES
        self._cleanup_interval = self.DEFAULT_CLEANUP_INTERVAL
        self._last_cleanup = time.time()
        # 限流器指标统计
        self._allowed_count = 0
        self._rejected_count = 0
        # 后台清理线程
        self._stop_cleanup = threading.Event()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动后台清理线程"""

        def cleanup_loop():
            while not self._stop_cleanup.is_set():
                try:
                    self._stop_cleanup.wait(self._cleanup_interval)
                    if self._stop_cleanup.is_set():
                        break
                    self._periodic_cleanup()
                except Exception as e:
                    logger.warning(f"限流器清理线程异常：{e}")

        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info(f"限流器后台清理线程已启动，间隔 {self._cleanup_interval}秒")

    def _periodic_cleanup(self):
        """定期清理过期条目（后台线程调用）"""
        now = time.time()
        # 清理所有过期条目（使用 60 秒窗口）
        self._cleanup_expired(now, window=60)
        logger.debug(f"限流器清理完成，当前条目数：{len(self._requests)}")

    def shutdown(self):
        """关闭限流器，停止清理线程"""
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=2)
            self._cleanup_thread = None
        logger.info("限流器已关闭")

    def is_allowed(self, key: str, max_requests: int = 10, window: int = 60) -> bool:
        """检查是否允许请求"""
        # 验证参数
        if window <= 0:
            return False
        if max_requests <= 0:
            return False

        now = time.time()

        # 定期清理过期记录
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired(now, window)

        # 限制总条目数，防止内存泄漏
        if len(self._requests) >= self._max_entries:
            # 紧急清理：移除最旧的条目
            self._emergency_cleanup()

        if key not in self._requests:
            self._requests[key] = []

        # 移除窗口期外的请求记录
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

        # 检查是否超过限制
        if len(self._requests[key]) >= max_requests:
            self._rejected_count += 1
            return False

        self._requests[key].append(now)
        # 移动到末尾（标记为最近访问）
        self._requests.move_to_end(key)
        self._allowed_count += 1
        return True

    def _cleanup_expired(self, now: float, window: int):
        """清理过期的请求记录"""
        expired_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if now - t < window]
            if not self._requests[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del self._requests[key]
        self._last_cleanup = now

    def _emergency_cleanup(self):
        """紧急清理：当条目数超过限制时，移除最旧的 50% 条目"""
        if not self._requests:
            return

        # 计算每个键的最后访问时间
        key_last_access = []
        for key, timestamps in self._requests.items():
            if timestamps:
                key_last_access.append((key, max(timestamps)))
            else:
                key_last_access.append((key, 0))

        # 按最后访问时间排序
        key_last_access.sort(key=lambda x: x[1])

        # 移除最旧的 50% 条目
        keys_to_remove = len(key_last_access) // 2
        for i in range(keys_to_remove):
            del self._requests[key_last_access[i][0]]

    def get_metrics(self) -> dict:
        """获取限流器指标"""
        total = self._allowed_count + self._rejected_count
        return {
            "allowed": self._allowed_count,
            "rejected": self._rejected_count,
            "total": total,
            "hit_rate": self._allowed_count / total if total > 0 else 1.0,
            "current_entries": len(self._requests),
            "max_entries": self._max_entries,
        }


# 全局限流器实例（将在应用启动时根据配置初始化）
rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config_loader=None):
    """获取或初始化限流器"""
    global rate_limiter
    if rate_limiter is None and config_loader:
        try:
            max_entries = config_loader.getint(
                "security", "rate_limiter.max_entries", 10000
            )
            rate_limiter = RateLimiter(max_entries=max_entries)
        except Exception:
            rate_limiter = RateLimiter()
    elif rate_limiter is None:
        rate_limiter = RateLimiter()
    return rate_limiter


# 创建 FastAPI 应用
app = FastAPI(
    title="智能文件检索与问答系统 - Web API",
    description="基于 Python 和 FastAPI 的文件智能管理工具 Web 接口",
    version=get_version(),
)


# 安全响应头中间件
@app.middleware("http")
async def add_security_headers(request, call_next):
    """添加安全响应头"""
    response = await call_next(request)

    # 防止 MIME 类型嗅探
    response.headers["X-Content-Type-Options"] = "nosniff"

    # 防止点击劫持
    response.headers["X-Frame-Options"] = "DENY"

    # 内容安全策略
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )

    # XSS 保护（对旧版浏览器）
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer 策略
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化核心组件（优化启动速度）"""
    import asyncio

    # 存储主事件循环，供后台线程回调使用
    app.state.main_loop = asyncio.get_event_loop()

    try:
        start_time = time.time()
        logger.info("开始初始化应用组件...")

        # 设置全局应用引用
        from backend.api import dependencies

        dependencies.set_app(app)

        # 首先初始化配置加载器
        from backend.utils.config_loader import ConfigLoader

        config_loader = ConfigLoader()
        app.state.config_loader = config_loader

        # 初始化限流器
        get_rate_limiter(config_loader)
        logger.info("限流器初始化完成")

        # 使用线程池并行初始化独立组件
        def init_index_manager():
            from backend.core.index_manager import IndexManager

            if not hasattr(app.state, "index_manager"):
                app.state.index_manager = IndexManager(config_loader)
            return app.state.index_manager

        def init_search_engine():
            from backend.core.search_engine import SearchEngine

            if not hasattr(app.state, "search_engine"):
                app.state.search_engine = SearchEngine(
                    app.state.index_manager, config_loader
                )

        def init_file_scanner():
            from backend.core.file_scanner import FileScanner

            if not hasattr(app.state, "file_scanner"):
                app.state.file_scanner = FileScanner(
                    config_loader, None, app.state.index_manager
                )
            return app.state.file_scanner

        # 第 1 阶段：并行初始化核心索引组件（这些组件相互依赖）
        # 使用 try-except 包装每个初始化，实现优雅降级
        try:
            index_manager = init_index_manager()
        except Exception as e:
            logger.error(f"索引管理器初始化失败：{e}")
            raise  # 索引是核心组件，失败时不能继续

        try:
            init_search_engine()
        except Exception as e:
            logger.error(f"搜索引擎初始化失败：{e}")
            raise  # 搜索是核心功能，失败时不能继续

        try:
            file_scanner = init_file_scanner()
        except Exception as e:
            logger.error(f"文件扫描器初始化失败：{e}")
            raise  # 文件扫描是核心功能，失败时不能继续

        # 初始化文件监控器
        if not hasattr(app.state, "file_monitor"):
            from backend.core.file_monitor import FileMonitor

            app.state.file_monitor = FileMonitor(
                config_loader, index_manager, file_scanner
            )
            if config_loader.getboolean("monitor", "enabled", False):
                app.state.file_monitor.start_monitoring()
                logger.info("文件监控已启动")

        # 第 2 阶段：延迟初始化 RAG 管道（在后台线程中进行）
        # 这样应用可以更快启动，RAG 功能在需要时才完全就绪
        app.state.rag_pipeline = None
        app.state.rag_initializing = False
        app.state.rag_ready_event = asyncio.Event()
        # 添加初始化锁，防止竞态条件
        app.state.rag_init_lock = asyncio.Lock()

        def init_rag_pipeline():
            """后台初始化 RAG 管道（支持优雅降级）"""
            try:
                app.state.rag_initializing = True
                from backend.core.model_manager import ModelManager
                from backend.core.rag_pipeline import RAGPipeline

                model_manager = ModelManager(config_loader)
                app.state.rag_pipeline = RAGPipeline(
                    model_manager, config_loader, app.state.search_engine
                )
                app.state.rag_status = "ready"
                app.state.rag_error = None
                logger.info("RAG 管道后台初始化完成")
                # 通知等待的协程 RAG 已就绪
                asyncio.run_coroutine_threadsafe(_set_rag_ready(), app.state.main_loop)
            except Exception as e:
                logger.error(f"RAG 管道初始化失败：{e}")
                app.state.rag_pipeline = None
                app.state.rag_status = "error"
                app.state.rag_error = str(e)
            finally:
                app.state.rag_initializing = False

        async def _set_rag_ready():
            """设置 RAG 就绪事件"""
            app.state.rag_ready_event.set()

        # 如果 AI 功能启用，在后台线程初始化 RAG
        if config_loader.getboolean("ai_model", "enabled", False):
            import threading

            rag_thread = threading.Thread(target=init_rag_pipeline, daemon=True)
            rag_thread.start()
            logger.info("RAG 管道后台初始化已启动")

        # 如果需要，处理模式更新
        if getattr(index_manager, "schema_updated", False):
            logger.info("检测到索引模式更新，自动重建并扫描索引...")
            stats = file_scanner.scan_and_index()
            logger.info(f"自动重建索引完成：{stats}")

        init_time = time.time() - start_time
        logger.info(f"Web 应用初始化成功，耗时 {init_time:.2f}秒")
        app.state.initialized = True
    except Exception as e:
        logger.error(f"初始化 Web 应用时出错：{str(e)}")
        app.state.initialized = False
        raise

    yield

    """应用停止时清理资源"""
    logger.info("正在关闭应用，清理资源...")

    # 停止文件监控
    if hasattr(app.state, "file_monitor") and app.state.file_monitor:
        try:
            app.state.file_monitor.stop_monitoring()
            logger.info("文件监控已停止")
        except Exception as e:
            logger.error(f"停止文件监控时出错：{e}")

    # 关闭 RAG Pipeline
    if hasattr(app.state, "rag_pipeline") and app.state.rag_pipeline:
        try:
            if (
                hasattr(app.state.rag_pipeline, "model_manager")
                and app.state.rag_pipeline.model_manager
            ):
                app.state.rag_pipeline.model_manager.close()
                logger.info("RAG Pipeline 已关闭")
        except Exception as e:
            logger.error(f"关闭 RAG Pipeline 时出错：{e}")

    # 关闭索引管理器
    if hasattr(app.state, "index_manager") and app.state.index_manager:
        try:
            app.state.index_manager.close()
            logger.info("索引管理器已关闭")
        except Exception as e:
            logger.error(f"关闭索引管理器时出错：{e}")

    # 关闭 ChatHistoryDB
    if hasattr(app.state, "rag_pipeline") and app.state.rag_pipeline:
        try:
            if (
                hasattr(app.state.rag_pipeline, "chat_db")
                and app.state.rag_pipeline.chat_db
            ):
                app.state.rag_pipeline.chat_db.close()
                logger.info("ChatHistoryDB 已关闭")
        except Exception as e:
            logger.error(f"关闭 ChatHistoryDB 时出错：{e}")

    # 关闭限流器
    if hasattr(app.state, "rate_limiter") and app.state.rate_limiter:
        try:
            app.state.rate_limiter.shutdown()
            logger.info("限流器已关闭")
        except Exception as e:
            logger.error(f"关闭限流器时出错：{e}")

    logger.info("应用关闭完成")


# Set lifespan handler
app.router.lifespan_context = lifespan


# 错误处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    logger.error(f"请求验证错误：{exc.errors()}")
    return JSONResponse(
        status_code=422, content={"detail": "请求参数验证失败", "errors": exc.errors()}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常：{str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "内部服务器错误"})


# 静态页面路由
# 打包后需要使用 app_paths 定位前端文件，而非相对路径
def _get_frontend_dir() -> Path:
    """获取前端目录路径（兼容开发和打包环境）"""
    try:
        from backend.utils.app_paths import get_app_paths

        fd = get_app_paths().frontend_dir
        if fd and fd.exists():
            return fd
    except Exception:
        pass
    # 开发环境回退
    return Path("frontend")


@app.get("/favicon.ico")
async def favicon():
    """提供 favicon 图标"""
    favicon_path = _get_frontend_dir() / "static" / "favicon.ico"
    if favicon_path.exists():
        return Response(content=favicon_path.read_bytes(), media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/")
async def read_root():
    """提供主 HTML 页面"""
    frontend_path = _get_frontend_dir() / "index.html"
    if frontend_path.exists():
        return HTMLResponse(content=frontend_path.read_text(encoding="utf-8"))
    return {"message": "Frontend not found", "docs_url": "/docs"}


# 导入并注册 API 路由
from backend.api.routes import search, chat, config, directory, system

app.include_router(search.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(directory.router, prefix="/api")
app.include_router(system.router, prefix="/api")

# 挂载静态文件目录
from fastapi.staticfiles import StaticFiles

_static_dir = _get_frontend_dir() / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
