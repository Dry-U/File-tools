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

# Import core modules only when needed to avoid heavy dependencies at startup
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

# Initialize the FastAPI application
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


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <title>智能文件检索与问答系统</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                min-height: 100vh;
                padding-bottom: 30px;
            }
            .app-header {
                background: linear-gradient(90deg, #3498db, #2c3e50);
                color: white;
                padding: 1.5rem 0;
                margin-bottom: 2rem;
                border-radius: 0 0 10px 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            .card {
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                transition: transform 0.2s;
            }
            .card:hover {
                transform: translateY(-5px);
            }
            .search-container {
                background: white;
                padding: 2rem;
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            }
            .search-input {
                border-radius: 25px;
                padding: 15px 20px;
                border: 2px solid #e9ecef;
                font-size: 1.1rem;
            }
            .search-input:focus {
                border-color: #3498db;
                box-shadow: 0 0 0 0.2rem rgba(52, 152, 219, 0.25);
            }
            .search-btn {
                border-radius: 25px;
                padding: 10px 25px;
                font-size: 1.1rem;
                background: linear-gradient(90deg, #3498db, #2980b9);
                border: none;
            }
            .search-btn:hover {
                background: linear-gradient(90deg, #2980b9, #3498db);
            }
            .result-card {
                margin-bottom: 15px;
                border-left: 4px solid #3498db;
            }
            .file-icon {
                font-size: 1.5rem;
                margin-right: 10px;
                color: #3498db;
            }
            .file-name {
                font-weight: bold;
                color: #2c3e50;
            }
            .file-path {
                color: #7f8c8d;
                font-size: 0.9rem;
            }
            .score-badge {
                background: linear-gradient(90deg, #2ecc71, #27ae60);
            }
            .preview-content {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                margin-top: 15px;
                max-height: 200px;
                overflow-y: auto;
            }
            .controls {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            .control-btn {
                border-radius: 20px;
                padding: 8px 15px;
                font-size: 0.9rem;
            }
            .status-bar {
                background: white;
                padding: 10px 15px;
                border-radius: 5px;
                margin-top: 15px;
                border-left: 4px solid #3498db;
            }
            .file-types {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                margin: 10px 0;
            }
            .file-type-btn {
                border-radius: 20px;
                padding: 5px 12px;
                font-size: 0.8rem;
            }
            .file-type-btn.active {
                background-color: #3498db;
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="app-header text-center">
            <div class="container">
                <h1><i class="fas fa-search me-2"></i>智能文件检索与问答系统</h1>
                <p class="mb-0">基于Python的本地文件智能管理工具</p>
            </div>
        </div>

        <div class="container">
            <!-- Controls -->
            <div class="controls d-flex justify-content-center mb-4">
                <button class="btn btn-outline-primary control-btn" onclick="toggleAdvancedFilter()">
                    <i class="fas fa-filter me-1"></i>高级筛选
                </button>
                <button class="btn btn-outline-success control-btn" onclick="rebuildIndex()">
                    <i class="fas fa-sync me-1"></i>重建索引
                </button>
                <button class="btn btn-outline-info control-btn" onclick="exportResults()">
                    <i class="fas fa-download me-1"></i>导出结果
                </button>
            </div>

            <!-- Advanced Filter Panel -->
            <div class="card mb-4" id="advancedFilterPanel" style="display: none;">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-sliders-h me-2"></i>高级筛选</h5>
                    <button class="btn btn-sm btn-outline-secondary" onclick="toggleAdvancedFilter()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <label class="form-label">文件类型</label>
                            <div class="file-types">
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".txt">文本</button>
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".doc">文档</button>
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".xls">表格</button>
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".pdf">PDF</button>
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".jpg">图片</button>
                                <button class="btn btn-outline-primary btn-sm file-type-btn" data-type=".py">代码</button>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">文件大小范围</label>
                            <div class="d-flex">
                                <input type="number" id="minSize" class="form-control me-2" placeholder="最小(MB)">
                                <input type="number" id="maxSize" class="form-control" placeholder="最大(MB)">
                            </div>
                        </div>
                    </div>
                    <div class="mt-3">
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="caseSensitive">
                            <label class="form-check-label" for="caseSensitive">区分大小写</label>
                        </div>
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="matchWholeWord">
                            <label class="form-check-label" for="matchWholeWord">全词匹配</label>
                        </div>
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="searchContent">
                            <label class="form-check-label" for="searchContent">搜索内容</label>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Search Area -->
            <div class="search-container">
                <div class="input-group mb-3">
                    <input type="text" id="searchInput" class="form-control search-input" placeholder="输入搜索关键词..." onkeypress="handleKeyPress(event)">
                    <button class="btn btn-primary search-btn" type="button" onclick="performSearch()">
                        <i class="fas fa-search me-2"></i>搜索
                    </button>
                </div>
            </div>

            <!-- Status Bar -->
            <div class="status-bar" id="statusBar">
                <span id="statusText">就绪</span>
            </div>

            <!-- Results -->
            <div class="card mt-4" id="resultsCard" style="display: none;">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-list me-2"></i>搜索结果</h5>
                    <span id="resultCount">0 条结果</span>
                </div>
                <div class="card-body p-0" id="resultsContainer">
                    <!-- Results will be displayed here -->
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            let currentPreviewPath = '';
            
            async function performSearch() {
                const query = document.getElementById('searchInput').value.trim();
                if (!query) {
                    // Show error message in status bar
                    updateStatus('请输入搜索关键词');
                    showNotification('请输入搜索关键词', 'warning');
                    return;
                }

                updateStatus('正在搜索: ' + query);
                
                try {
                    const filters = getFilters();
                    const response = await fetch('/api/search', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            query: query,
                            filters: filters
                        })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`搜索失败: ${response.status}`);
                    }
                    
                    const results = await response.json();
                    displayResults(results, query);
                    updateStatus(`找到 ${results.length} 个结果`);
                } catch (error) {
                    const errorMsg = `搜索失败: ${error.message}`;
                    updateStatus(errorMsg);
                    showNotification(errorMsg, 'danger');
                }
            }
            
            function getFilters() {
                const filters = {};
                
                // 文件类型
                const selectedTypes = Array.from(document.querySelectorAll('.file-type-btn.active')).map(btn => btn.dataset.type);
                if (selectedTypes.length > 0) {
                    filters.file_types = selectedTypes;
                }
                
                // 文件大小
                const minSize = document.getElementById('minSize').value;
                const maxSize = document.getElementById('maxSize').value;
                if (minSize) filters.min_size = parseFloat(minSize) * 1024 * 1024; // 转换为字节
                if (maxSize) filters.max_size = parseFloat(maxSize) * 1024 * 1024; // 转换为字节
                
                // 其他选项
                filters.case_sensitive = document.getElementById('caseSensitive')?.checked || false;
                filters.match_whole_word = document.getElementById('matchWholeWord')?.checked || false;
                filters.search_content = document.getElementById('searchContent')?.checked || false;
                
                return filters;
            }
            
            function displayResults(results, query) {
                const resultsContainer = document.getElementById('resultsContainer');
                const resultsCard = document.getElementById('resultsCard');
                const resultCount = document.getElementById('resultCount');
                
                if (!results || results.length === 0) {
                    resultsContainer.innerHTML = '<div class="p-4 text-center text-muted"><i class="fas fa-search me-2"></i>未找到匹配的文件</div>';
                    resultsCard.style.display = 'block';
                    resultCount.textContent = '0 条结果';
                    return;
                }
                
                resultCount.textContent = `${results.length} 条结果`;
                resultsCard.style.display = 'block';
                
                let html = '';
                results.forEach((result, index) => {
                    const icon = getFileIcon(result.path);
                    const fileName = result.file_name || result.path.split('/').pop().split('\\\\').pop();
                    const scorePercent = (result.score * 100).toFixed(2);
                    const lastModified = result.modified_time ? new Date(result.modified_time).toLocaleString() : '未知';
                    
                    html += `
                    <div class="result-card card">
                        <div class="card-body" style="cursor: pointer;" onclick="togglePreview('${index}', '${result.path}', '${query}')">
                            <div class="d-flex align-items-center">
                                <div class="file-icon"><i class="${icon}"></i></div>
                                <div class="flex-grow-1">
                                    <div class="file-name">${fileName}</div>
                                    <div class="file-path">${result.path}</div>
                                    <small class="text-muted">修改时间: ${lastModified}</small>
                                </div>
                                <span class="badge score-badge">${scorePercent}%</span>
                            </div>
                        </div>
                        <div id="preview-${index}" class="preview-content" style="display: none;">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <h6><i class="fas fa-eye me-2"></i>文件预览</h6>
                                <button class="btn btn-sm btn-outline-secondary" onclick="event.stopPropagation(); closePreview('${index}')">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                            <div class="preview-text">加载中...</div>
                        </div>
                    </div>
                    `;
                });
                
                resultsContainer.innerHTML = html;
            }
            
            function getFileIcon(filePath) {
                const ext = filePath.toLowerCase().split('.').pop();
                const iconMap = {
                    'pdf': 'fas fa-file-pdf text-danger',
                    'doc': 'fas fa-file-word text-primary',
                    'docx': 'fas fa-file-word text-primary',
                    'xls': 'fas fa-file-excel text-success',
                    'xlsx': 'fas fa-file-excel text-success',
                    'ppt': 'fas fa-file-powerpoint text-warning',
                    'pptx': 'fas fa-file-powerpoint text-warning',
                    'txt': 'fas fa-file-alt text-info',
                    'py': 'fab fa-python text-warning',
                    'js': 'fab fa-js text-warning',
                    'html': 'fab fa-html5 text-danger',
                    'css': 'fab fa-css3-alt text-primary',
                    'jpg': 'fas fa-file-image text-info',
                    'jpeg': 'fas fa-file-image text-info',
                    'png': 'fas fa-file-image text-info',
                    'gif': 'fas fa-file-image text-info',
                    'zip': 'fas fa-file-archive text-success',
                    'rar': 'fas fa-file-archive text-success',
                    '7z': 'fas fa-file-archive text-success'
                };
                return iconMap[ext] || 'fas fa-file';
            }
            
            async function togglePreview(index, filePath, query) {
                const previewDiv = document.getElementById(`preview-${index}`);
                
                if (previewDiv.style.display === 'block') {
                    previewDiv.style.display = 'none';
                    return;
                }
                
                // Show loading state
                const previewText = previewDiv.querySelector('.preview-text');
                previewText.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>加载中...';
                previewDiv.style.display = 'block';
                
                try {
                    const response = await fetch('/api/preview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ path: filePath })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`预览失败: ${response.status}`);
                    }
                    
                    const data = await response.json();
                    previewText.textContent = data.content;
                } catch (error) {
                    previewText.innerHTML = '<p class="text-danger">预览失败: ' + error.message + '</p>';
                }
            }
            
            function closePreview(index) {
                document.getElementById(`preview-${index}`).style.display = 'none';
            }
            
            function toggleAdvancedFilter() {
                const panel = document.getElementById('advancedFilterPanel');
                panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
            }
            
            async function rebuildIndex() {
                // Create modal dialog
                const modalHtml = `
                <div class="modal fade" id="rebuildModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title"><i class="fas fa-sync-alt me-2"></i>重建索引</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <p>重建索引将重新扫描所有文件，可能需要较长时间。</p>
                                <p class="text-warning"><i class="fas fa-exclamation-triangle me-2"></i>确定要继续吗？</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                                <button type="button" class="btn btn-success" onclick="confirmRebuild()">确认重建</button>
                            </div>
                        </div>
                    </div>
                </div>`;
                
                // Add modal to body if not already present
                if (!document.getElementById('rebuildModal')) {
                    document.body.insertAdjacentHTML('beforeend', modalHtml);
                } else {
                    // Update existing modal
                    const existingModal = document.getElementById('rebuildModal');
                    if (existingModal) {
                        existingModal.outerHTML = modalHtml;
                    } else {
                        document.body.insertAdjacentHTML('beforeend', modalHtml);
                    }
                }
                
                // Show modal
                const modalElement = document.getElementById('rebuildModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show();
            }
            
            async function confirmRebuild() {
                // Close the modal
                const modalElement = document.getElementById('rebuildModal');
                const modal = bootstrap.Modal.getInstance(modalElement);
                modal.hide();
                
                // Show progress indicator
                const statusText = document.getElementById('statusText');
                statusText.innerHTML = '正在重建索引... <i class="fas fa-spinner fa-spin"></i>';
                
                try {
                    const response = await fetch('/api/rebuild-index', {
                        method: 'POST'
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        // Show success message in a Bootstrap alert
                        showNotification(data.message, 'success');
                        updateStatus(data.message);
                    } else {
                        throw new Error(data.message || '未知错误');
                    }
                } catch (error) {
                    const errorMsg = '索引重建失败: ' + error.message;
                    showNotification(errorMsg, 'danger');
                    updateStatus(errorMsg);
                }
            }
            
            function exportResults() {
                // Create modal dialog
                const modalHtml = `
                <div class="modal fade" id="exportModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title"><i class="fas fa-download me-2"></i>导出搜索结果</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <p>导出功能正在开发中...</p>
                                <p class="text-muted">我们将支持导出为CSV、Excel等格式</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            </div>
                        </div>
                    </div>
                </div>`;
                
                // Add modal to body if not already present
                if (!document.getElementById('exportModal')) {
                    document.body.insertAdjacentHTML('beforeend', modalHtml);
                } else {
                    // Update existing modal
                    const existingModal = document.getElementById('exportModal');
                    if (existingModal) {
                        existingModal.outerHTML = modalHtml;
                    } else {
                        document.body.insertAdjacentHTML('beforeend', modalHtml);
                    }
                }
                
                // Show modal
                const modalElement = document.getElementById('exportModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show();
            }
            
            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    performSearch();
                }
            }
            
            function updateStatus(text) {
                document.getElementById('statusText').textContent = text;
            }
            
            function showNotification(message, type) {
                // Remove any existing alerts
                const existingAlerts = document.querySelectorAll('.notification-alert');
                existingAlerts.forEach(alert => alert.remove());
                
                // Create a temporary alert element
                const alertDiv = document.createElement('div');
                alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed notification-alert`;
                alertDiv.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;';
                alertDiv.innerHTML = `
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    ${message}
                `;
                
                document.body.appendChild(alertDiv);
                
                // Auto remove after 5 seconds
                setTimeout(() => {
                    if (alertDiv.parentNode) {
                        alertDiv.parentNode.removeChild(alertDiv);
                    }
                }, 5000);
            }
            
            // Initialize file type buttons
            document.querySelectorAll('.file-type-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    this.classList.toggle('active');
                    this.classList.toggle('btn-primary');
                    this.classList.toggle('btn-outline-primary');
                });
            });

            // Initialize with focus on search input
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('searchInput').focus();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/api/search")
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
                return {key: convert_types(value) for key, value in obj.items()}
            elif hasattr(obj, 'isoformat'):  # datetime对象
                return obj.isoformat()
            else:
                return obj

        formatted_results = []
        for result in results:
            converted_result = convert_types(result)
            formatted_results.append({
                "file_name": os.path.basename(converted_result["path"]),
                "path": converted_result["path"],
                "score": converted_result.get("score", 0.0),
                "modified_time": converted_result.get("modified_time") or converted_result.get("modified")
            })

        return formatted_results
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@app.post("/api/preview")
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


@app.post("/api/rebuild-index")
async def rebuild_index():
    """Rebuild the search index"""
    global file_scanner
    if not file_scanner:
        raise HTTPException(status_code=500, detail="File scanner not initialized")
    
    try:
        stats = file_scanner.scan_and_index()
        return {
            "status": "success",
            "files_scanned": stats.get("files_scanned", 0),
            "files_indexed": stats.get("files_indexed", 0),
            "message": f"索引重建完成: 扫描 {stats.get('files_scanned', 0)} 个文件，索引 {stats.get('files_indexed', 0)} 个文件"
        }
    except Exception as e:
        logger.error(f"Index rebuild error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Web API is running"}


if __name__ == "__main__":
    # For development
    uvicorn.run(app, host="127.0.0.1", port=8000)