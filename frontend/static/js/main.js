let currentPreviewPath = '';
let searchResults = []; // Store search results globally

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
        searchResults = results; // Update global results
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

    // 文件类型 - 只有过滤器选中时才应用
    const selectedTypes = Array.from(document.querySelectorAll('.file-type-btn.active')).map(btn => btn.dataset.type);
    if (selectedTypes.length > 0) {
        filters.file_types = selectedTypes;
    }

    // 文件大小
    const minSize = document.getElementById('minSize').value;
    const maxSize = document.getElementById('maxSize').value;
    if (minSize) filters.size_min = parseFloat(minSize) * 1024 * 1024; // 转换为字节
    if (maxSize) filters.size_max = parseFloat(maxSize) * 1024 * 1024; // 转换为字节
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
        resultsContainer.innerHTML = '<div class="p-4 text-center text-muted"><i class="bi bi-search me-2"></i>未找到匹配的文件</div>';
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
        const scorePercent = Math.min(parseFloat(result.score), 100.0).toFixed(2);
        const lastModified = result.modified_time ? new Date(result.modified_time).toLocaleString() : '未知';
        const snippet = result.snippet || '';

        html += `
        <div class="result-card card mb-3">
            <div class="card-body" style="cursor: pointer;" onclick="togglePreview(${index})">
                <div class="d-flex align-items-start">
                    <div class="file-icon me-3 mt-1"><i class="${icon} fs-4"></i></div>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between align-items-center">
                            <h5 class="card-title mb-1 text-primary">${fileName}</h5>
                            <span class="badge bg-light text-dark border score-badge">匹配度: ${scorePercent}%</span>
                        </div>
                        <div class="file-path text-muted small mb-2"><i class="bi bi-folder2-open me-1"></i>${result.path}</div>
                        
                        <!-- Snippet Display -->
                        ${snippet ? `<div class="search-snippet p-2 bg-light rounded border-start border-4 border-primary mb-2" style="font-size: 0.9rem; color: #555;">${snippet}</div>` : ''}
                        
                        <div class="d-flex justify-content-between align-items-center mt-2">
                            <small class="text-muted"><i class="bi bi-clock me-1"></i>修改时间: ${lastModified}</small>
                            <button class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); togglePreview(${index})">
                                <i class="bi bi-eye me-1"></i>预览
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div id="preview-${index}" class="preview-content border-top p-3 bg-light" style="display: none;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="bi bi-file-text me-2"></i>文件预览</h6>
                    <button class="btn btn-sm btn-outline-secondary" onclick="event.stopPropagation(); closePreview(${index})">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
                <div class="preview-text bg-white p-3 border rounded" style="max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-family: monospace;">加载中...</div>
            </div>
        </div>
        `;
    });

    resultsContainer.innerHTML = html;
}

function getFileIcon(filePath) {
    const ext = filePath.toLowerCase().split('.').pop();
    const iconMap = {
        'pdf': 'bi bi-file-earmark-pdf text-danger',
        'doc': 'bi bi-file-earmark-word text-primary',
        'docx': 'bi bi-file-earmark-word text-primary',
        'xls': 'bi bi-file-earmark-excel text-success',
        'xlsx': 'bi bi-file-earmark-excel text-success',
        'ppt': 'bi bi-file-earmark-ppt text-warning',
        'pptx': 'bi bi-file-earmark-ppt text-warning',
        'txt': 'bi bi-file-earmark-text text-secondary',
        'py': 'bi bi-file-earmark-code text-info',
        'js': 'bi bi-file-earmark-code text-warning',
        'html': 'bi bi-file-earmark-code text-danger',
        'css': 'bi bi-file-earmark-code text-primary',
        'json': 'bi bi-file-earmark-code text-warning',
        'xml': 'bi bi-file-earmark-code text-success',
        'jpg': 'bi bi-file-earmark-image text-info',
        'jpeg': 'bi bi-file-earmark-image text-info',
        'png': 'bi bi-file-earmark-image text-info',
        'gif': 'bi bi-file-earmark-image text-info',
        'zip': 'bi bi-file-earmark-zip text-secondary',
        'rar': 'bi bi-file-earmark-zip text-secondary',
        '7z': 'bi bi-file-earmark-zip text-secondary'
    };
    return iconMap[ext] || 'bi bi-file-earmark text-secondary';
}

async function togglePreview(index) {
    const previewDiv = document.getElementById(`preview-${index}`);
    const result = searchResults[index];
    
    if (!result) return;

    if (previewDiv.style.display === 'block') {
        previewDiv.style.display = 'none';
        return;
    }

    // Show loading state
    const previewText = previewDiv.querySelector('.preview-text');
    previewText.innerHTML = '<div class="text-center py-3"><span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>正在加载文件内容...</div>';
    previewDiv.style.display = 'block';

    try {
        const response = await fetch('/api/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ path: result.path })
        });

        if (!response.ok) {
            throw new Error(`预览失败: ${response.status}`);
        }

        const data = await response.json();
        // Check if content is empty or error
        if (data.content && (data.content.startsWith('错误') || data.content.startsWith('不支持'))) {
             previewText.innerHTML = `<div class="alert alert-warning mb-0">${data.content}</div>`;
        } else if (!data.content) {
             previewText.innerHTML = `<div class="alert alert-info mb-0">该文件内容为空或无法提取文本内容。</div>`;
        } else {
             previewText.textContent = data.content;
        }
    } catch (error) {
        previewText.innerHTML = `<div class="alert alert-danger mb-0">预览失败: ${error.message}</div>`;
    }
}

function closePreview(index) {
    document.getElementById(`preview-${index}`).style.display = 'none';
}

function toggleAdvancedFilter() {
    const panel = document.getElementById('advancedFilterPanel');
    const btn = document.getElementById('advancedFilterBtn');
    const willShow = panel.style.display === 'none';
    panel.style.display = willShow ? 'block' : 'none';
    if (panel.style.display === 'block') {
        btn.classList.remove('btn-outline-primary');
        btn.classList.add('btn-primary');
        btn.classList.add('active');
        updateStatus('高级筛选已开启');
    } else {
        btn.classList.remove('btn-primary');
        btn.classList.remove('active');
        btn.classList.add('btn-outline-primary');
        updateStatus('高级筛选已关闭');
    }
}

async function rebuildIndex() {
    // Create modal dialog
    const modalHtml = `
    <div class="modal fade" id="rebuildModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-arrow-repeat me-2"></i>重建索引</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>重建索引将重新扫描所有文件，可能需要较长时间。</p>
                    <p class="text-warning"><i class="bi bi-exclamation-triangle me-2"></i>确定要继续吗？</p>
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
    statusText.innerHTML = '正在重建索引... <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

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
        // 更新按钮样式
        if (this.classList.contains('active')) {
            this.classList.remove('btn-outline-primary');
            this.classList.add('btn-primary');
        } else {
            this.classList.remove('btn-primary');
            this.classList.add('btn-outline-primary');
        }
        const q = document.getElementById('searchInput').value.trim();
        if (q) {
            performSearch();
        }
    });
});

// Chat functionality
function handleChatKeyPress(event) {
    if (event.key === 'Enter') {
        sendChatMessage();
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    // Clear input
    input.value = '';

    // Add user message
    appendMessage('user', message);

    // Show loading
    const loadingId = appendMessage('system', '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>正在思考...');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query: message })
        });

        if (!response.ok) {
            throw new Error(`请求失败: ${response.status}`);
        }

        const data = await response.json();
        
        // Remove loading message
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();

        // Format answer with sources
        let answerHtml = data.answer.replace(/\n/g, '<br>');
        if (data.sources && data.sources.length > 0) {
            answerHtml += '<div class="source-list"><strong>参考来源:</strong><br>';
            data.sources.forEach(source => {
                answerHtml += `<span class="source-item"><i class="bi bi-file-earmark-text me-1"></i>${source}</span>`;
            });
            answerHtml += '</div>';
        }

        appendMessage('system', answerHtml);

    } catch (error) {
        // Remove loading message
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();
        
        appendMessage('system', `<span class="text-danger">错误: ${error.message}</span>`);
    }
}

function appendMessage(type, content) {
    const container = document.getElementById('chatContainer');
    const id = 'msg-' + Date.now();
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${type}-message`;
    msgDiv.id = id;
    
    msgDiv.innerHTML = `
        <div class="message-content">
            ${content}
        </div>
    `;
    
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
    
    return id;
}

// Initialize with focus on search input
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('searchInput').focus();
    const panel = document.getElementById('advancedFilterPanel');
    const btn = document.getElementById('advancedFilterBtn');
    if (panel && btn) {
        const visible = panel.style.display !== 'none';
        if (visible) {
            btn.classList.remove('btn-outline-primary');
            btn.classList.add('btn-primary');
            btn.classList.add('active');
        } else {
            btn.classList.remove('btn-primary');
            btn.classList.remove('active');
            btn.classList.add('btn-outline-primary');
        }
    }
});
