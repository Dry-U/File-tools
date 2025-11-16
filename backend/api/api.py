"""
FastAPI web application for the file tools system
This provides a web-based interface that can be packaged as an executable
"""
from fastapi import FastAPI, HTTPException, Request
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

# Initialize the main FastAPI application
app = FastAPI(
    title="智能文件检索与问答系统 - Web API",
    description="基于Python和FastAPI的文件智能管理工具Web接口",
    version="1.0.0"
)

# Initialize logger
logger = get_logger(__name__)

# Global variables for core components
search_engine = None
file_scanner = None
index_manager = None

@app.on_event("startup")
async def startup_event():
    """Initialize core components when the application starts"""
    global search_engine, file_scanner, index_manager

    try:
        # Load configuration
        config_loader = ConfigLoader()

        # Import core modules only when needed to avoid loading heavy dependencies at startup
        from backend.core.index_manager import IndexManager
        from backend.core.search_engine import SearchEngine
        from backend.core.file_scanner import FileScanner

        # Initialize index manager
        index_manager = IndexManager(config_loader)

        # Initialize search engine
        search_engine = SearchEngine(index_manager, config_loader)

        # Initialize file scanner
        file_scanner = FileScanner(config_loader, None, index_manager)

        logger.info("Web application initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing web application: {str(e)}")
        raise


@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    frontend_path = Path("frontend/index.html")
    if frontend_path.exists():
        return HTMLResponse(content=frontend_path.read_text(encoding='utf-8'))
    else:
        return {"message": "Frontend not found", "docs_url": "/docs"}


# Create a separate API router for all API endpoints
from fastapi import APIRouter
api_router = APIRouter()

@api_router.post("/search")
async def search(request: Request):
    """Perform a search using the search engine"""
    global search_engine
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search engine not initialized")

    try:
        # Parse the request body
        body = await request.json()
        query = body.get("query", "")
        filters = body.get("filters", {})

        if not query:
            raise HTTPException(status_code=400, detail="查询关键词不能为空")

        # Perform the search with filters
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
            # 确保converted_result是字典类型
            if isinstance(converted_result, dict):
                formatted_results.append({
                    "file_name": os.path.basename(str(converted_result.get("path", ""))),
                    "path": str(converted_result.get("path", "")),
                    "score": float(converted_result.get("score", 0.0)),
                    "modified_time": converted_result.get("modified_time") or converted_result.get("modified")
                })
            else:
                # 如果不是字典，使用默认值
                formatted_results.append({
                    "file_name": "",
                    "path": "",
                    "score": 0.0,
                    "modified_time": None
                })

        return formatted_results
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@api_router.post("/preview")
async def preview_file(request: Request):
    """Preview file content"""
    try:
        # 从请求体获取路径
        body = await request.json()
        path = body.get("path", "")

        if not path:
            return {"content": "错误：未提供文件路径"}

        # 验证路径安全性，防止路径遍历攻击
        import os
        # 解析并规范路径
        normalized_path = os.path.normpath(path)

        # Check file size to prevent loading huge files
        if not os.path.exists(normalized_path):
            return {"content": "错误：文件不存在"}
        if os.path.getsize(normalized_path) > 5 * 1024 * 1024:  # 5MB limit
            return {"content": "文件过大（超过5MB），无法预览"}

        # Get file extension
        ext = os.path.splitext(normalized_path)[1].lower()

        # Preview text-based files
        if ext in ['.txt', '.md', '.csv', '.json', '.xml', '.py', '.js', '.html', '.css', '.sql', '.log']:
            with open(normalized_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(2000)  # Limit content to 2000 chars
            return {"content": content}
        else:
            return {"content": f"不支持预览 {ext} 格式的文件"}
    except FileNotFoundError:
        logger.error(f"Preview error: File not found")
        return {"content": "预览失败: 文件不存在"}
    except PermissionError:
        logger.error(f"Preview error: Permission denied")
        return {"content": "预览失败: 没有权限访问文件"}
    except Exception as e:
        logger.error(f"Preview error: {str(e)}")
        return {"content": f"预览失败: {str(e)}"}


@api_router.post("/rebuild-index")
async def rebuild_index():
    """Rebuild the search index"""
    global file_scanner
    if not file_scanner:
        raise HTTPException(status_code=500, detail="File scanner not initialized")

    try:
        logger.info("开始重建索引...")
        # Log scan paths to verify configuration
        scan_paths = getattr(file_scanner, 'scan_paths', 'Unknown')
        logger.info(f"扫描路径: {scan_paths}")
        logger.info(f"扫描路径数量: {len(scan_paths) if scan_paths != 'Unknown' else 0}")
        
        for i, path in enumerate(scan_paths):
            import os
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
    return {"status": "healthy", "message": "Web API is running"}


# Include the API router with /api prefix
app.include_router(api_router, prefix="/api")

# Mount static files directory
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

if __name__ == "__main__":
    # For development
    uvicorn.run(app, host="127.0.0.1", port=8000)