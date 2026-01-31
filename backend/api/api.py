"""
FastAPI web application for file tools system
This provides a web-based interface that can be packaged as an executable
Refactored to use FastAPI dependency injection for thread safety
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import os
from typing import Optional
import asyncio
from pathlib import Path

# Import core modules only when needed to avoid heavy dependencies at startup
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Initialize main FastAPI application
app = FastAPI(
    title="智能文件检索与问答系统 - Web API",
    description="基于Python和FastAPI的文件智能管理工具Web接口",
    version="1.0.0"
)


# ============================================================================
# DEPENDENCY INJECTION: Thread-safe component access
# ============================================================================

def get_config_loader():
    """Dependency for ConfigLoader (per-request singleton)"""
    if not hasattr(app.state, 'config_loader'):
        app.state.config_loader = ConfigLoader()
    return app.state.config_loader


def get_index_manager(config_loader: ConfigLoader = Depends(get_config_loader)):
    """Dependency for IndexManager"""
    if not hasattr(app.state, 'index_manager'):
        from backend.core.index_manager import IndexManager
        app.state.index_manager = IndexManager(config_loader)
    return app.state.index_manager


def get_search_engine(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager)
):
    """Dependency for SearchEngine"""
    if not hasattr(app.state, 'search_engine'):
        from backend.core.search_engine import SearchEngine
        app.state.search_engine = SearchEngine(index_manager, config_loader)
    return app.state.search_engine


def get_file_scanner(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager)
):
    """Dependency for FileScanner"""
    if not hasattr(app.state, 'file_scanner'):
        from backend.core.file_scanner import FileScanner
        app.state.file_scanner = FileScanner(config_loader, None, index_manager)
    return app.state.file_scanner


def get_rag_pipeline(
    config_loader: ConfigLoader = Depends(get_config_loader),
    search_engine = Depends(get_search_engine)
):
    """Dependency for RAGPipeline (optional, returns None if disabled)"""
    if not hasattr(app.state, 'rag_pipeline'):
        if config_loader.getboolean('ai_model', 'enabled', False):
            from backend.core.model_manager import ModelManager
            from backend.core.rag_pipeline import RAGPipeline
            model_manager = ModelManager(config_loader)
            app.state.rag_pipeline = RAGPipeline(model_manager, config_loader, search_engine)
            logger.info("RAG Pipeline initialized")
        else:
            app.state.rag_pipeline = None
    return app.state.rag_pipeline


def get_file_monitor(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager = Depends(get_index_manager),
    file_scanner = Depends(get_file_scanner)
):
    """Dependency for FileMonitor"""
    if not hasattr(app.state, 'file_monitor'):
        from backend.core.file_monitor import FileMonitor
        app.state.file_monitor = FileMonitor(config_loader, index_manager, file_scanner)
        if config_loader.getboolean('monitor', 'enabled', False):
            app.state.file_monitor.start_monitoring()
            logger.info("文件监控已启动")
    return app.state.file_monitor


# ============================================================================
# PATH VALIDATION HELPER
# ============================================================================

def is_path_allowed(path: str, config_loader: ConfigLoader) -> bool:
    """
    Validate that a path is within allowed scan directories to prevent path traversal attacks.
    Returns True if path is allowed, False otherwise.
    """
    if not path:
        return False

    # Normalize path
    path = path.strip('"').strip("'")
    normalized_path = os.path.normpath(path)

    # Check for path traversal patterns
    if ".." in normalized_path or normalized_path.startswith("//"):
        logger.warning(f"Path contains illegal characters: {normalized_path}")
        return False

    # Get allowed paths from config
    scan_paths = config_loader.get('file_scanner', 'scan_paths', '')
    if not scan_paths:
        # If no scan paths configured, deny access for security
        logger.warning("No scan paths configured, denying all file access")
        return False

    # Build list of allowed directories
    allowed_paths = []
    for sp in scan_paths.split(';'):
        sp = sp.strip()
        if sp and os.path.isdir(sp):
            allowed_paths.append(os.path.abspath(sp))

    # Check if normalized path is within any allowed directory
    file_path_abs = os.path.abspath(normalized_path)
    for allowed_path in allowed_paths:
        if file_path_abs.startswith(allowed_path):
            return True

    logger.warning(f"Path not in allowed directories: {normalized_path}")
    return False


# ============================================================================
# LIFECYCLE EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize core components when application starts"""
    try:
        config_loader = get_config_loader()

        # Pre-initialize all dependencies by accessing them once
        # This ensures all components are ready before first request
        get_index_manager(config_loader)
        get_search_engine()
        get_file_scanner()
        get_file_monitor()

        # Initialize RAG pipeline (optional)
        get_rag_pipeline()

        # Handle schema update if needed
        index_manager = get_index_manager(config_loader)
        if getattr(index_manager, 'schema_updated', False):
            logger.info("检测到索引模式更新，自动重建并扫描索引...")
            file_scanner = get_file_scanner()
            stats = file_scanner.scan_and_index()
            logger.info(f"自动重建索引完成: {stats}")

        logger.info("Web application initialized successfully")
        app.state.initialized = True
    except Exception as e:
        logger.error(f"Error initializing web application: {str(e)}")
        app.state.initialized = False
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup when application stops"""
    if hasattr(app.state, 'file_monitor') and app.state.file_monitor:
        app.state.file_monitor.stop_monitoring()


# ============================================================================
# ROUTE HANDLERS
# ============================================================================

@app.get("/favicon.ico")
async def favicon():
    """Serve favicon.ico"""
    favicon_path = Path("frontend/static/favicon.ico")
    if favicon_path.exists():
        return HTMLResponse(content=favicon_path.read_bytes(), media_type="image/x-icon")
    return HTMLResponse(content=b"", status_code=204)


@app.get("/")
async def read_root():
    """Serve the main HTML page"""
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
    search_engine = Depends(get_search_engine)
):
    """Perform a search using the search engine"""
    try:
        body = await request.json()
        query = body.get("query", "")
        filters = body.get("filters", {})

        if not query:
            raise HTTPException(status_code=400, detail="查询关键词不能为空")

        # Perform search with filters
        results = search_engine.search(query, filters)

        # Format results for web response - convert numpy types to native Python types
        def convert_types(obj):
            """Convert numpy types to native Python types for JSON serialization"""
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
                    # Ensure score doesn't exceed 100
                    if key == 'score':
                        converted_value = min(float(converted_value), 100.0)
                    result_dict[key] = converted_value
                return result_dict
            elif hasattr(obj, 'isoformat'):  # datetime objects
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
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@api_router.post("/preview")
async def preview_file(
    request: Request,
    index_manager = Depends(get_index_manager),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """Preview file content with path traversal protection"""
    try:
        body = await request.json()
        path = body.get("path", "")

        if not path:
            return {"content": "错误：未提供文件路径"}

        # Validate path is within allowed directories
        if not is_path_allowed(path, config_loader):
            logger.warning(f"Blocked path traversal attempt: {path}")
            return {"content": "错误：文件路径超出允许范围"}

        # Normalize path
        path = path.strip('"').strip("'")
        normalized_path = os.path.normpath(path)

        logger.info(f"尝试预览文件: {normalized_path}")

        # Check file exists
        if not os.path.exists(normalized_path):
            logger.error(f"文件不存在: {normalized_path}")
            return {"content": f"错误：文件不存在 ({normalized_path})"}

        # Check file size to prevent loading huge files
        if os.path.getsize(normalized_path) > 5 * 1024 * 1024:  # 5MB limit
            return {"content": "文件过大（超过5MB），无法预览"}

        # Try to get content from IndexManager first (supports PDF/DOCX etc.)
        content = index_manager.get_document_content(normalized_path)
        if content:
            return {"content": content}

        # Fallback: try DocumentParser
        try:
            from backend.core.document_parser import DocumentParser
            parser = DocumentParser(config_loader)
            content = parser.extract_text(normalized_path)
            if content and not content.startswith("错误"):
                return {"content": content}
        except Exception as e:
            logger.warning(f"Direct parsing failed: {str(e)}")

        # Final fallback: read text files
        ext = os.path.splitext(normalized_path)[1].lower()
        text_exts = ['.txt', '.md', '.csv', '.json', '.xml', '.py', '.js',
                      '.html', '.css', '.sql', '.log', '.bat', '.sh',
                      '.yaml', '.yml', '.ini', '.conf']
        if ext in text_exts:
            with open(normalized_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)  # Limit content to 5000 chars
            return {"content": content}

        return {"content": f"不支持预览 {ext} 格式的文件，且该文件未被索引内容"}
    except FileNotFoundError:
        logger.error("Preview error: File not found")
        return {"content": "预览失败: 文件不存在"}
    except PermissionError:
        logger.error("Preview error: Permission denied")
        return {"content": "预览失败: 没有权限访问文件"}
    except Exception as e:
        logger.error(f"Preview error: {str(e)}")
        return {"content": f"预览失败: {str(e)}"}


@api_router.post("/rebuild-index")
async def rebuild_index(
    index_manager = Depends(get_index_manager),
    file_scanner = Depends(get_file_scanner)
):
    """Rebuild the search index"""
    try:
        logger.info("开始重建索引...")
        try:
            if index_manager:
                logger.info("先删除旧索引目录并重新初始化索引...")
                ok = index_manager.rebuild_index()
                if not ok:
                    logger.warning("重建索引目录失败，继续执行全量扫描以覆盖旧数据")
            else:
                logger.warning("IndexManager 未初始化，无法删除旧索引目录")
        except Exception as e:
            logger.error(f"删除旧索引目录失败: {str(e)}")

        # Log scan paths to verify configuration
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
        logger.error(f"Index rebuild error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(e)}")


@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    if hasattr(app.state, 'initialized') and app.state.initialized:
        return {"status": "healthy", "message": "Web API is running and fully initialized"}
    return {"status": "starting", "message": "Web API is starting up"}


@api_router.post("/chat")
async def chat(
    request: Request,
    rag_pipeline = Depends(get_rag_pipeline),
    config_loader: ConfigLoader = Depends(get_config_loader)
):
    """Chat with the RAG system"""
    if not rag_pipeline:
        if not config_loader.getboolean('ai_model', 'enabled', False):
            return {"answer": "AI问答功能未启用。请在配置文件中设置 ai_model.enabled = true。", "sources": []}
        raise HTTPException(status_code=500, detail="RAG pipeline not initialized")

    try:
        body = await request.json()
        query = body.get("query", "")
        session_id = body.get("session_id")

        if not query:
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        result = rag_pipeline.query(query, session_id=session_id)
        return result
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# Include API router with /api prefix
app.include_router(api_router, prefix="/api")

# Mount static files directory
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


if __name__ == "__main__":
    # For development
    uvicorn.run(app, host="127.0.0.1", port=8000)
