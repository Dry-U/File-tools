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