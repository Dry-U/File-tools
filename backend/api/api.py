"""
智能文件检索与问答系统 - FastAPI Web 服务

提供 Web 界面和 API 接口，可打包为桌面应用
使用依赖注入实现线程安全
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
import os
from typing import Optional
import asyncio
from pathlib import Path
from functools import wraps
import time
from pydantic import BaseModel


# 请求限流器 - 防止接口被滥用
class RateLimiter:
    """基于内存的请求限流器"""

    # 默认配置
    DEFAULT_MAX_ENTRIES = 10000  # 最大条目数，防止内存无限增长
    DEFAULT_CLEANUP_INTERVAL = 3600  # 1小时清理一次

    def __init__(self, max_entries: int = None):
        self._requests = {}
        self._max_entries = max_entries or self.DEFAULT_MAX_ENTRIES
        self._cleanup_interval = self.DEFAULT_CLEANUP_INTERVAL
        self._last_cleanup = time.time()

    def is_allowed(self, key: str, max_requests: int = 10, window: int = 60) -> bool:
        """检查是否允许请求"""
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
            return False

        self._requests[key].append(now)
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
        """紧急清理：当条目数超过限制时，移除最旧的50%条目"""
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

        # 移除最旧的50%条目
        keys_to_remove = len(key_last_access) // 2
        for i in range(keys_to_remove):
            del self._requests[key_last_access[i][0]]


# 全局限流器实例（将在应用启动时根据配置初始化）
rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config_loader=None):
    """获取或初始化限流器"""
    global rate_limiter
    if rate_limiter is None and config_loader:
        try:
            max_entries = config_loader.getint('security', 'rate_limiter.max_entries', 10000)
            rate_limiter = RateLimiter(max_entries=max_entries)
        except Exception:
            rate_limiter = RateLimiter()
    elif rate_limiter is None:
        rate_limiter = RateLimiter()
    return rate_limiter

from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="智能文件检索与问答系统 - Web API",
    description="基于Python和FastAPI的文件智能管理工具Web接口",
    version="1.0.0"
)


# ============================================================================
# 依赖注入 - 线程安全的组件访问
# ============================================================================

def get_config_loader():
    """获取配置加载器（单例）"""
    if not hasattr(app.state, 'config_loader'):
        app.state.config_loader = ConfigLoader()
    return app.state.config_loader


def get_index_manager(config_loader: ConfigLoader = Depends(get_config_loader)):
    """获取索引管理器"""
    if not hasattr(app.state, 'index_manager'):
        from backend.core.index_manager import IndexManager
        app.state.index_manager = IndexManager(config_loader)
    return app.state.index_manager


def get_search_engine(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager)
):
    """获取搜索引擎"""
    if not hasattr(app.state, 'search_engine'):
        from backend.core.search_engine import SearchEngine
        app.state.search_engine = SearchEngine(index_manager, config_loader)
    return app.state.search_engine


def get_file_scanner(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager)
):
    """获取文件扫描器"""
    if not hasattr(app.state, 'file_scanner'):
        from backend.core.file_scanner import FileScanner
        app.state.file_scanner = FileScanner(config_loader, None, index_manager)
    return app.state.file_scanner


def get_rag_pipeline(
    config_loader: ConfigLoader = Depends(get_config_loader),
    search_engine = Depends(get_search_engine)
):
    """获取RAG管道（可选，禁用时返回None）"""
    if not hasattr(app.state, 'rag_pipeline'):
        if config_loader.getboolean('ai_model', 'enabled', False):
            from backend.core.model_manager import ModelManager
            from backend.core.rag_pipeline import RAGPipeline
            model_manager = ModelManager(config_loader)
            app.state.rag_pipeline = RAGPipeline(model_manager, config_loader, search_engine)
            logger.info("RAG管道初始化完成")
        else:
            app.state.rag_pipeline = None
    return app.state.rag_pipeline


def get_file_monitor(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager),
    file_scanner = Depends(get_file_scanner)
):
    """获取文件监控器"""
    if not hasattr(app.state, 'file_monitor'):
        from backend.core.file_monitor import FileMonitor
        app.state.file_monitor = FileMonitor(config_loader, index_manager, file_scanner)
        if config_loader.getboolean('monitor', 'enabled', False):
            app.state.file_monitor.start_monitoring()
            logger.info("文件监控已启动")
    return app.state.file_monitor


# ============================================================================
# 路径安全验证
# ============================================================================

def is_path_allowed(path: str, config_loader: ConfigLoader) -> bool:
    """检查路径是否在允许范围内，防止路径遍历攻击"""
    if not path:
        return False

    # 标准化路径
    path = path.strip('"').strip("'")
    normalized_path = os.path.normpath(path)

    # 检查非法字符
    if ".." in normalized_path or normalized_path.startswith("//"):
        logger.warning(f"路径包含非法字符: {normalized_path}")
        return False

    # 获取允许的扫描路径
    scan_paths = config_loader.get('file_scanner', 'scan_paths', '')
    if not scan_paths:
        logger.warning("未配置扫描路径，拒绝所有文件访问")
        return False

    # 构建允许的路径列表
    allowed_paths = []
    if isinstance(scan_paths, str):
        path_list = [p.strip() for p in scan_paths.split(';') if p.strip()]
    elif isinstance(scan_paths, list):
        path_list = scan_paths
    else:
        path_list = []

    for sp in path_list:
        sp = str(sp).strip()
        if sp and os.path.isdir(sp):
            allowed_paths.append(os.path.abspath(sp))

    # 检查路径是否在允许范围内
    file_path_abs = os.path.abspath(normalized_path)
    for allowed_path in allowed_paths:
        if file_path_abs.startswith(allowed_path):
            return True

    logger.warning(f"路径不在允许范围内: {normalized_path}")
    return False


# ============================================================================
# LIFECYCLE EVENTS
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化核心组件（优化启动速度）"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        start_time = time.time()
        logger.info("开始初始化应用组件...")

        # 首先初始化配置加载器
        config_loader = get_config_loader()

        # 初始化限流器
        get_rate_limiter(config_loader)
        logger.info("限流器初始化完成")

        # 使用线程池并行初始化独立组件
        def init_index_manager():
            from backend.core.index_manager import IndexManager
            if not hasattr(app.state, 'index_manager'):
                app.state.index_manager = IndexManager(config_loader)
            return app.state.index_manager

        def init_search_engine():
            from backend.core.search_engine import SearchEngine
            if not hasattr(app.state, 'search_engine'):
                app.state.search_engine = SearchEngine(app.state.index_manager, config_loader)

        def init_file_scanner():
            from backend.core.file_scanner import FileScanner
            if not hasattr(app.state, 'file_scanner'):
                app.state.file_scanner = FileScanner(config_loader, None, app.state.index_manager)
            return app.state.file_scanner

        # 第1阶段：并行初始化核心索引组件（这些组件相互依赖）
        index_manager = init_index_manager()
        init_search_engine()
        file_scanner = init_file_scanner()

        # 初始化文件监控器
        if not hasattr(app.state, 'file_monitor'):
            from backend.core.file_monitor import FileMonitor
            app.state.file_monitor = FileMonitor(config_loader, index_manager, file_scanner)
            if config_loader.getboolean('monitor', 'enabled', False):
                app.state.file_monitor.start_monitoring()
                logger.info("文件监控已启动")

        # 第2阶段：延迟初始化RAG管道（在后台线程中进行）
        # 这样应用可以更快启动，RAG功能在需要时才完全就绪
        app.state.rag_pipeline = None
        app.state.rag_initializing = False

        def init_rag_pipeline():
            """后台初始化RAG管道"""
            try:
                app.state.rag_initializing = True
                from backend.core.model_manager import ModelManager
                from backend.core.rag_pipeline import RAGPipeline
                model_manager = ModelManager(config_loader)
                app.state.rag_pipeline = RAGPipeline(model_manager, config_loader, app.state.search_engine)
                logger.info("RAG管道后台初始化完成")
            except Exception as e:
                logger.error(f"RAG管道初始化失败: {e}")
            finally:
                app.state.rag_initializing = False

        # 如果AI功能启用，在后台线程初始化RAG
        if config_loader.getboolean('ai_model', 'enabled', False):
            import threading
            rag_thread = threading.Thread(target=init_rag_pipeline, daemon=True)
            rag_thread.start()
            logger.info("RAG管道后台初始化已启动")

        # 如果需要，处理模式更新
        if getattr(index_manager, 'schema_updated', False):
            logger.info("检测到索引模式更新，自动重建并扫描索引...")
            stats = file_scanner.scan_and_index()
            logger.info(f"自动重建索引完成: {stats}")

        init_time = time.time() - start_time
        logger.info(f"Web应用初始化成功，耗时 {init_time:.2f}秒")
        app.state.initialized = True
    except Exception as e:
        logger.error(f"初始化Web应用时出错: {str(e)}")
        app.state.initialized = False
        raise

    yield

    """应用停止时清理资源"""
    logger.info("正在关闭应用，清理资源...")

    # 停止文件监控
    if hasattr(app.state, 'file_monitor') and app.state.file_monitor:
        try:
            app.state.file_monitor.stop_monitoring()
            logger.info("文件监控已停止")
        except Exception as e:
            logger.error(f"停止文件监控时出错: {e}")

    # 关闭RAG Pipeline
    if hasattr(app.state, 'rag_pipeline') and app.state.rag_pipeline:
        try:
            if hasattr(app.state.rag_pipeline, 'model_manager') and app.state.rag_pipeline.model_manager:
                app.state.rag_pipeline.model_manager.close()
                logger.info("RAG Pipeline已关闭")
        except Exception as e:
            logger.error(f"关闭RAG Pipeline时出错: {e}")

    # 关闭索引管理器
    if hasattr(app.state, 'index_manager') and app.state.index_manager:
        try:
            app.state.index_manager.close()
            logger.info("索引管理器已关闭")
        except Exception as e:
            logger.error(f"关闭索引管理器时出错: {e}")

    # 关闭ChatHistoryDB
    if hasattr(app.state, 'rag_pipeline') and app.state.rag_pipeline:
        try:
            if hasattr(app.state.rag_pipeline, 'chat_db') and app.state.rag_pipeline.chat_db:
                app.state.rag_pipeline.chat_db.close()
                logger.info("ChatHistoryDB已关闭")
        except Exception as e:
            logger.error(f"关闭ChatHistoryDB时出错: {e}")

    logger.info("应用关闭完成")

# Set lifespan handler
app.router.lifespan_context = lifespan


# ============================================================================
# ERROR HANDLING
# ============================================================================

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    logger.error(f"请求验证错误: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数验证失败", "errors": exc.errors()}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误"}
    )

# ============================================================================
# ROUTE HANDLERS
# ============================================================================
@app.get("/favicon.ico")
async def favicon():
    """提供favicon图标"""
    favicon_path = Path("frontend/static/favicon.ico")
    if favicon_path.exists():
        return HTMLResponse(content=favicon_path.read_bytes(), media_type="image/x-icon")
    return HTMLResponse(content=b"", status_code=204)


@app.get("/")
async def read_root():
    """提供主HTML页面"""
    frontend_path = Path("frontend/index.html")
    if frontend_path.exists():
        return HTMLResponse(content=frontend_path.read_text(encoding='utf-8'))
    return {"message": "Frontend not found", "docs_url": "/docs"}


# Create a separate API router for all API endpoints
from fastapi import APIRouter
api_router = APIRouter()


@api_router.post("/search")
async def search(
    request: Request,
    search_engine = Depends(get_search_engine),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """使用搜索引擎执行搜索"""
    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean('security', 'rate_limiter.enabled', True):
        client_ip = request.client.host if request.client else "unknown"
        max_req = config_loader.getint('security', 'rate_limiter.search_limit', 20)
        window = config_loader.getint('security', 'rate_limiter.search_window', 60)
        if not limiter.is_allowed(f"search:{client_ip}", max_requests=max_req, window=window):
            raise HTTPException(status_code=429, detail="搜索过于频繁，请稍后再试")

    try:
        body = await request.json()
        query = body.get("query", "")
        filters = body.get("filters", {})

        if not query:
            raise HTTPException(status_code=400, detail="查询关键词不能为空")

        # 使用过滤器执行搜索
        results = search_engine.search(query, filters)

        # 格式化结果以进行Web响应 - 将numpy类型转换为原生Python类型
        def convert_types(obj):
            """将numpy类型转换为原生Python类型以便JSON序列化"""
            import numpy as np
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
                    "score": float(converted_result.get("score", 0.0)),
                    "modified_time": converted_result.get("modified_time") or converted_result.get("modified"),
                    "snippet": converted_result.get("snippet", "")
                })
            else:
                formatted_results.append({
                    "file_name": "",
                    "path": "",
                    "score": 0.0,
                    "modified_time": None,
                    "snippet": ""
                })

        return formatted_results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@api_router.post("/preview")
async def preview_file(
    request: Request,
    index_manager = Depends(get_index_manager),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """预览文件内容，带有路径遍历保护"""
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
        if os.path.getsize(normalized_path) > 5 * 1024 * 1024:  # 5MB限制
            return {"content": "文件过大（超过5MB），无法预览"}

        # 首先尝试从索引管理器获取内容（支持PDF/DOCX等）
        content = index_manager.get_document_content(normalized_path)
        if content:
            return {"content": content}

        # 备选：尝试文档解析器
        try:
            from backend.core.document_parser import DocumentParser
            parser = DocumentParser(config_loader)
            content = parser.extract_text(normalized_path)
            if content and not content.startswith("错误"):
                return {"content": content}
        except Exception as e:
            logger.warning(f"直接解析失败: {str(e)}")

        # 最终备选：读取文本文件
        ext = os.path.splitext(normalized_path)[1].lower()
        text_exts = ['.txt', '.md', '.csv', '.json', '.xml', '.py', '.js',
                      '.html', '.css', '.sql', '.log', '.bat', '.sh',
                      '.yaml', '.yml', '.ini', '.conf']
        if ext in text_exts:
            with open(normalized_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)  # 限制内容为5000字符
            return {"content": content}

        return {"content": f"不支持预览 {ext} 格式的文件，且该文件未被索引内容"}
    except FileNotFoundError:
        logger.error("预览错误: 文件不存在")
        return {"content": "预览失败: 文件不存在"}
    except PermissionError:
        logger.error("预览错误: 权限被拒绝")
        return {"content": "预览失败: 没有权限访问文件"}
    except Exception as e:
        logger.error(f"预览错误: {str(e)}")
        return {"content": f"预览失败: {str(e)}"}


@api_router.post("/rebuild-index")
async def rebuild_index(
    request: Request,
    index_manager = Depends(get_index_manager),
    file_scanner = Depends(get_file_scanner),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """重建搜索索引"""
    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean('security', 'rate_limiter.enabled', True):
        client_ip = request.client.host if request.client else "unknown"
        max_req = config_loader.getint('security', 'rate_limiter.rebuild_limit', 1)
        window = config_loader.getint('security', 'rate_limiter.rebuild_window', 600)
        if not limiter.is_allowed(f"rebuild:{client_ip}", max_requests=max_req, window=window):
            raise HTTPException(status_code=429, detail="索引重建过于频繁，请10分钟后再试")

    try:
        logger.info("开始重建索引...")
        try:
            if index_manager:
                logger.info("先删除旧索引目录并重新初始化索引...")
                ok = index_manager.rebuild_index()
                if not ok:
                    logger.warning("重建索引目录失败，继续执行全量扫描以覆盖旧数据")
            else:
                logger.warning("索引管理器未初始化，无法删除旧索引目录")
        except Exception as e:
            logger.error(f"删除旧索引目录失败: {str(e)}")

        # 记录扫描路径以验证配置
        scan_paths = getattr(file_scanner, 'scan_paths', 'Unknown')
        logger.info(f"扫描路径: {scan_paths}")
        logger.info(f"扫描路径数量: {len(scan_paths) if scan_paths != 'Unknown' else 0}")

        for i, path in enumerate(scan_paths):
            path_exists = os.path.exists(path)
            path_isdir = os.path.isdir(path) if path_exists else False
            logger.info(f"路径[{i}]: {path}, 存在: {path_exists}, 是目录: {path_isdir}")

            if path_exists and path_isdir:
                try:
                    file_count = sum(len(files) for _, _, files in os.walk(path))
                    logger.info(f"路径[{i}] 包含 {file_count} 个文件")
                except Exception as e:
                    logger.error(f"无法访问路径[{i}] 内容: {str(e)}")

        logger.info(f"排除模式: {getattr(file_scanner, 'exclude_patterns', 'Unknown')}")
        logger.info(f"目标扩展名: {getattr(file_scanner, 'all_extensions', 'Unknown')}")

        logger.info("调用 file_scanner.scan_and_index()")
        stats = file_scanner.scan_and_index()
        logger.info(f"scan_and_index 返回结果: {stats}")

        logger.info(f"索引重建完成: 扫描 {stats.get('total_files_scanned', 0)} 个文件，索引 {stats.get('total_files_indexed', 0)} 个文件")

        return {
            "status": "success",
            "files_scanned": stats.get("total_files_scanned", 0),
            "files_indexed": stats.get("total_files_indexed", 0),
            "message": f"索引重建完成: 扫描 {stats.get('total_files_scanned', 0)} 个文件，索引 {stats.get('total_files_indexed', 0)} 个文件"
        }
    except Exception as e:
        logger.error(f"索引重建错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(e)}")


@api_router.get("/health")
async def health_check():
    """健康检查端点"""
    if hasattr(app.state, 'initialized') and app.state.initialized:
        return {"status": "healthy", "message": "Web API正在运行且已完全初始化"}
    return {"status": "starting", "message": "Web API正在启动中"}


@api_router.post("/chat")
async def chat(
    request: Request,
    rag_pipeline = Depends(get_rag_pipeline),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """与RAG系统进行对话"""
    # 限流检查
    limiter = get_rate_limiter()
    if config_loader.getboolean('security', 'rate_limiter.enabled', True):
        client_ip = request.client.host if request.client else "unknown"
        max_req = config_loader.getint('security', 'rate_limiter.chat_limit', 10)
        window = config_loader.getint('security', 'rate_limiter.chat_window', 60)
        if not limiter.is_allowed(f"chat:{client_ip}", max_requests=max_req, window=window):
            raise HTTPException(status_code=429, detail="对话过于频繁，请稍后再试")

    # 检查RAG管道是否就绪，如果正在初始化则等待
    if not rag_pipeline:
        if not config_loader.getboolean('ai_model', 'enabled', False):
            return {"answer": "AI问答功能未启用。请在配置文件中设置 ai_model.enabled = true。", "sources": []}

        # 如果正在后台初始化，等待最多10秒
        if getattr(app.state, 'rag_initializing', False):
            import asyncio
            wait_time = 0
            while getattr(app.state, 'rag_initializing', False) and wait_time < 10:
                await asyncio.sleep(0.5)
                wait_time += 0.5
            if app.state.rag_pipeline:
                rag_pipeline = app.state.rag_pipeline
            else:
                raise HTTPException(status_code=503, detail="RAG管道正在初始化中，请稍后再试")
        else:
            raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        body = await request.json()
        query = body.get("query", "")
        session_id = body.get("session_id")

        if not query:
            raise HTTPException(status_code=400, detail="查询不能为空")

        result = rag_pipeline.query(query, session_id=session_id)
        return result
    except Exception as e:
        logger.error(f"对话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")


@api_router.get("/sessions")
async def get_sessions(
    rag_pipeline = Depends(get_rag_pipeline)
):
    """获取所有聊天会话列表"""
    if not rag_pipeline:
        return {"sessions": []}

    try:
        sessions = rag_pipeline.get_all_sessions()
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"获取会话错误: {str(e)}")
        return {"sessions": []}


@api_router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    rag_pipeline = Depends(get_rag_pipeline)
):
    """删除特定会话"""
    if not rag_pipeline:
        raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        success = rag_pipeline.clear_session(session_id)
        if success:
            return {"status": "success", "message": "会话已删除"}
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        logger.error(f"删除会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@api_router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    rag_pipeline = Depends(get_rag_pipeline)
):
    """获取特定会话的消息列表"""
    if not rag_pipeline:
        raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        messages = rag_pipeline.chat_db.get_session_messages(session_id)
        return {"session_id": session_id, "messages": messages}
    except Exception as e:
        logger.error(f"获取会话消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话消息失败: {str(e)}")


@api_router.post("/config")
async def update_config(
    request: Request,
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """更新配置并保存到文件"""
    try:
        body = await request.json()

        # 验证配置数据
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="配置数据必须是JSON对象")

        def flatten_dict(d: dict, parent_key: str = '', sep: str = '.') -> dict:
            """将嵌套字典扁平化为点号分隔的键"""
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        # 支持的配置节
        valid_sections = {
            'ai_model': {'flat': True},  # 使用扁平化键
            'rag': {'flat': True}
        }

        # 更新配置
        updated_sections = []
        for section, values in body.items():
            if section in valid_sections and isinstance(values, dict):
                # 扁平化嵌套对象
                flattened = flatten_dict(values)
                for key, value in flattened.items():
                    config_loader.set(section, key, value)
                updated_sections.append(section)

        # 保存配置到文件
        if updated_sections:
            success = config_loader.save()
            if success:
                # 如果AI模型配置变更，触发RAGPipeline重新初始化
                if 'ai_model' in updated_sections:
                    try:
                        if hasattr(app.state, 'rag_pipeline') and app.state.rag_pipeline:
                            # 调用reload_model_manager强制重新创建ModelManager
                            app.state.rag_pipeline.reload_model_manager()
                            logger.info("RAGPipeline ModelManager已重新加载")
                    except Exception as e:
                        logger.warning(f"重新加载ModelManager时出错: {e}")
                        # 出错时清除rag_pipeline，下次请求时会重新创建
                        app.state.rag_pipeline = None

                return {
                    "status": "success",
                    "message": "配置已保存",
                    "updated_sections": updated_sections
                }
            else:
                raise HTTPException(status_code=500, detail="保存配置文件失败")
        else:
            return {
                "status": "warning",
                "message": "没有有效的配置项需要更新"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新配置错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


def _migrate_old_config(config_loader: ConfigLoader):
    """向后兼容：将旧配置迁移到新结构"""
    # 检查是否有旧配置
    old_interface_type = config_loader.get("ai_model", "interface_type", None)
    old_api_url = config_loader.get("ai_model", "api_url", None)
    old_api_key = config_loader.get("ai_model", "api_key", None)
    old_api_model = config_loader.get("ai_model", "api_model", None)

    if old_interface_type:
        # 迁移到新模式
        new_mode = "api" if old_interface_type == "api" else "local"
        config_loader.set("ai_model", "mode", new_mode)

        if old_api_url:
            if new_mode == "api":
                config_loader.set("ai_model", "api.api_url", old_api_url)
            else:
                config_loader.set("ai_model", "local.api_url", old_api_url)

        if old_api_key and new_mode == "api":
            config_loader.set("ai_model", "api.api_key", old_api_key)

        if old_api_model and new_mode == "api":
            config_loader.set("ai_model", "api.model_name", old_api_model)

        # 删除旧配置
        # 注意：这里假设ConfigLoader支持删除操作，如果不支持需要修改
        logger.info("配置已从旧版本迁移到新结构")


@api_router.get("/config")
async def get_config(
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """获取当前配置"""
    try:
        # 向后兼容：检查并迁移旧配置
        _migrate_old_config(config_loader)

        # 新配置结构 - 支持local/api模式
        mode = config_loader.get("ai_model", "mode", "local")
        provider = config_loader.get("ai_model", "api.provider", "siliconflow")

        # 获取多provider keys
        keys = {
            "siliconflow": config_loader.get("ai_model", "api.keys.siliconflow", ""),
            "deepseek": config_loader.get("ai_model", "api.keys.deepseek", ""),
            "custom": config_loader.get("ai_model", "api.keys.custom", "")
        }

        # 向后兼容：如果没有新结构，从旧配置加载
        if not any(keys.values()):
            old_key = config_loader.get("ai_model", "api.api_key", "")
            if old_key:
                keys[provider] = old_key

        config = {
            "ai_model": {
                "enabled": config_loader.getboolean("ai_model", "enabled", False),
                "mode": mode,
                "system_prompt": config_loader.get("ai_model", "system_prompt", ""),
                "local": {
                    "api_url": config_loader.get("ai_model", "local.api_url", "http://localhost:8000/v1/chat/completions"),
                    "max_context": config_loader.getint("ai_model", "local.max_context", 4096),
                    "max_tokens": config_loader.getint("ai_model", "local.max_tokens", 512),
                },
                "api": {
                    "provider": provider,
                    "api_url": config_loader.get("ai_model", "api.api_url", "https://api.siliconflow.cn/v1/chat/completions"),
                    "api_key": keys.get(provider, ""),  # 当前provider的key
                    "model_name": config_loader.get("ai_model", "api.model_name", "deepseek-ai/DeepSeek-V2.5"),
                    "max_context": config_loader.getint("ai_model", "api.max_context", 8192),
                    "max_tokens": config_loader.getint("ai_model", "api.max_tokens", 2048),
                    "keys": keys  # 所有provider的keys
                },
                "security": {
                    "verify_ssl": config_loader.getboolean("ai_model", "security.verify_ssl", True),
                    "timeout": config_loader.getint("ai_model", "security.timeout", 120),
                    "retry_count": config_loader.getint("ai_model", "security.retry_count", 2),
                },
                # 采样参数
                "sampling": {
                    "temperature": config_loader.getfloat("ai_model", "sampling.temperature", 0.7),
                    "top_p": config_loader.getfloat("ai_model", "sampling.top_p", 0.9),
                    "top_k": config_loader.getint("ai_model", "sampling.top_k", 40),
                    "min_p": config_loader.getfloat("ai_model", "sampling.min_p", 0.05),
                    "max_tokens": config_loader.getint("ai_model", "sampling.max_tokens", 2048),
                    "seed": config_loader.getint("ai_model", "sampling.seed", -1)
                },
                # 惩罚参数
                "penalties": {
                    "repeat_penalty": config_loader.getfloat("ai_model", "penalties.repeat_penalty", 1.1),
                    "frequency_penalty": config_loader.getfloat("ai_model", "penalties.frequency_penalty", 0.0),
                    "presence_penalty": config_loader.getfloat("ai_model", "penalties.presence_penalty", 0.0)
                }
            },
            "rag": {
                "max_history_turns": config_loader.getint("rag", "max_history_turns", 3),
                "max_history_chars": config_loader.getint("rag", "max_history_chars", 1000),
            }
        }
        return config
    except Exception as e:
        logger.error(f"获取配置错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@api_router.get("/model/test")
async def test_model_connection(
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """测试模型API连接"""
    try:
        from backend.core.model_manager import ModelManager

        model_manager = ModelManager(config_loader)
        result = model_manager.test_connection()
        model_manager.close()

        return result
    except Exception as e:
        logger.error(f"测试连接错误: {str(e)}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# DIRECTORY MANAGEMENT API
# ============================================================================

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


def _estimate_file_count(path: str, max_count: int = 9999) -> int:
    """估算目录中的文件数量"""
    try:
        path_obj = Path(path)
        if not path_obj.exists() or not path_obj.is_dir():
            return 0

        count = 0
        for item in path_obj.rglob('*'):
            if item.is_file():
                count += 1
                if count >= max_count:
                    return max_count
        return count
    except Exception:
        return 0


@api_router.get("/directories")
async def get_directories(
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor = Depends(get_file_monitor)
) -> DirectoriesListResponse:
    """获取当前管理的目录列表"""
    try:
        # 获取扫描路径
        scan_paths = config_loader.get('file_scanner', 'scan_paths', [])
        if isinstance(scan_paths, str):
            scan_paths = [p.strip() for p in scan_paths.split(';') if p.strip()]

        # 获取监控目录
        monitored_dirs = file_monitor.get_monitored_directories() if file_monitor else []

        # 合并所有目录（去重）
        all_paths = set()
        for path in scan_paths:
            all_paths.add(os.path.abspath(str(path)))
        for path in monitored_dirs:
            all_paths.add(os.path.abspath(str(path)))

        # 构建目录信息列表
        directories = []
        for path in sorted(all_paths):
            exists = os.path.exists(path) and os.path.isdir(path)
            is_scanning = path in [os.path.abspath(str(p)) for p in scan_paths]
            is_monitoring = path in [os.path.abspath(str(p)) for p in monitored_dirs]
            file_count = _estimate_file_count(path) if exists else 0

            directories.append({
                "path": path,
                "exists": exists,
                "is_scanning": is_scanning,
                "is_monitoring": is_monitoring,
                "file_count": file_count
            })

        return {"directories": directories}
    except Exception as e:
        logger.error(f"获取目录列表错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取目录列表失败: {str(e)}")


@api_router.post("/directories")
async def add_directory(
    request: DirectoryPath,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor = Depends(get_file_monitor),
    file_scanner = Depends(get_file_scanner)
) -> DirectoryResponse:
    """添加新目录（同时添加为扫描路径和监控目录）"""
    try:
        path = request.path.strip('"').strip("'")
        expanded_path = os.path.abspath(os.path.expanduser(path))

        # 验证路径
        if not os.path.exists(expanded_path):
            raise HTTPException(status_code=400, detail=f"路径不存在: {expanded_path}")
        if not os.path.isdir(expanded_path):
            raise HTTPException(status_code=400, detail=f"路径不是目录: {expanded_path}")

        # 检查是否已存在
        scan_paths = config_loader.get('file_scanner', 'scan_paths', [])
        if isinstance(scan_paths, str):
            scan_paths = [p.strip() for p in scan_paths.split(';') if p.strip()]

        existing_paths = [os.path.abspath(str(p)) for p in scan_paths]
        if expanded_path in existing_paths:
            return {
                "status": "success",
                "message": "目录已在列表中",
                "path": expanded_path,
                "needs_rebuild": False
            }

        # 添加到扫描路径
        config_loader.add_scan_path(expanded_path)

        # 更新 file_scanner 的扫描路径
        if file_scanner:
            if hasattr(file_scanner, 'scan_paths'):
                if expanded_path not in file_scanner.scan_paths:
                    file_scanner.scan_paths.append(expanded_path)

        # 添加到监控目录
        if file_monitor:
            file_monitor.add_monitored_directory(expanded_path)

        # 更新配置中的监控目录
        monitor_dirs = config_loader.get('monitor', 'directories', [])
        if isinstance(monitor_dirs, str):
            monitor_dirs = [d.strip() for d in monitor_dirs.split(';') if d.strip()]

        if expanded_path not in [os.path.abspath(str(d)) for d in monitor_dirs]:
            monitor_dirs.append(expanded_path)
            config_loader.set('monitor', 'directories', monitor_dirs)

        # 保存配置
        config_loader.save()

        return {
            "status": "success",
            "message": "目录已添加",
            "path": expanded_path,
            "needs_rebuild": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加目录错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加目录失败: {str(e)}")


@api_router.delete("/directories")
async def remove_directory(
    request: DirectoryPath,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor = Depends(get_file_monitor)
) -> DirectoryResponse:
    """删除目录（同时从扫描路径和监控目录中移除）"""
    try:
        path = request.path.strip('"').strip("'")
        expanded_path = os.path.abspath(os.path.expanduser(path))

        # 从扫描路径中移除
        config_loader.remove_scan_path(expanded_path)

        # 从监控目录中移除
        if file_monitor:
            file_monitor.remove_monitored_directory(expanded_path)

        # 更新配置中的监控目录
        monitor_dirs = config_loader.get('monitor', 'directories', [])
        if isinstance(monitor_dirs, str):
            monitor_dirs = [d.strip() for d in monitor_dirs.split(';') if d.strip()]

        monitor_dirs = [d for d in monitor_dirs if os.path.abspath(str(d)) != expanded_path]
        config_loader.set('monitor', 'directories', monitor_dirs)

        # 保存配置
        config_loader.save()

        return {
            "status": "success",
            "message": "目录已删除",
            "path": expanded_path,
            "needs_rebuild": False
        }
    except Exception as e:
        logger.error(f"删除目录错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除目录失败: {str(e)}")


@api_router.post("/directories/browse")
async def browse_directory() -> BrowseResponse:
    """打开系统文件对话框选择目录"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        # 创建隐藏的Tk窗口
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # 打开目录选择对话框
        selected_path = filedialog.askdirectory(parent=root, title="选择要添加的目录")

        # 销毁Tk窗口
        root.destroy()

        if selected_path:
            return {
                "status": "success",
                "path": os.path.abspath(selected_path),
                "canceled": False
            }
        else:
            return {
                "status": "success",
                "canceled": True
            }
    except Exception as e:
        logger.error(f"打开目录选择对话框错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"打开目录选择对话框失败: {str(e)}")


# 使用/api前缀包含API路由
app.include_router(api_router, prefix="/api")

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


if __name__ == "__main__":
    # 用于开发
    uvicorn.run(app, host="127.0.0.1", port=8000)
