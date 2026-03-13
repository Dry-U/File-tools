/**
 * FileTools - 搜索模块
 * 提供文件搜索、预览、结果渲染等功能
 */

const FileToolsSearch = (function() {
    'use strict';

    // 防抖处理的搜索函数（300ms延迟）
    const debouncedSearch = FileToolsUtils.debounce(performSearch, 300);

    /**
     * 执行搜索
     */
    async function performSearch() {
        const input = document.getElementById('searchInput');
        const query = input.value.trim();
        if (!query) return;

        // 收集过滤器
        const filters = {};

        // 1. 文件类型
        const activeTypeBtns = document.querySelectorAll('.file-type-btn.active');
        if (activeTypeBtns.length > 0) {
            filters.file_types = Array.from(activeTypeBtns).map(btn => '.' + btn.dataset.type);
        }

        // 2. 文件大小 (MB -> Bytes)
        const minSizeInput = document.getElementById('minSize').value;
        if (minSizeInput) {
            filters.size_min = parseFloat(minSizeInput) * 1024 * 1024;
        }
        const maxSizeInput = document.getElementById('maxSize').value;
        if (maxSizeInput) {
            filters.size_max = parseFloat(maxSizeInput) * 1024 * 1024;
        }

        // 3. 日期范围
        const dateFrom = document.getElementById('dateFrom').value;
        const dateTo = document.getElementById('dateTo').value;
        if (dateFrom) filters.date_from = dateFrom;
        if (dateTo) filters.date_to = dateTo;

        // 4. 搜索选项
        filters.search_content = document.getElementById('searchContent').checked;

        // 切换 UI
        const welcomeContainer = document.getElementById('search-welcome-container');
        const inputArea = document.getElementById('search-input-area');
        const resultsContainer = document.getElementById('resultsContainer');

        welcomeContainer.style.display = 'none';
        resultsContainer.style.display = 'block';
        inputArea.style.background = 'linear-gradient(to top, var(--llama-bg) 60%, transparent)';

        resultsContainer.innerHTML = `
            <div class="text-center text-muted mt-5">
                <div class="spinner-border text-secondary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3">正在搜索...</p>
            </div>
        `;

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, filters })
            });

            if (!response.ok) throw new Error('Search failed');

            const results = await response.json();
            renderSearchResults(results, resultsContainer);

        } catch (error) {
            console.error('Search error:', error);
            const safeErrorMessage = FileToolsUtils.escapeHtml(error.message);
            resultsContainer.innerHTML = `
                <div class="text-center text-danger mt-5">
                    <i class="bi bi-exclamation-circle display-4"></i>
                    <p class="mt-3">搜索出错: ${safeErrorMessage}</p>
                </div>
            `;
        }
    }

    /**
     * 渲染搜索结果
     * @param {Array} results - 搜索结果数组
     * @param {HTMLElement} container - 容器元素
     */
    function renderSearchResults(results, container) {
        if (results.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted mt-5">
                    <i class="bi bi-search display-4 opacity-25"></i>
                    <p class="mt-3">未找到相关文件</p>
                </div>
            `;
            return;
        }

        // 按匹配度降序排序
        results.sort((a, b) => b.score - a.score);

        let html = '<div class="d-flex flex-column gap-3">';
        results.forEach((result, index) => {
            const iconClass = FileToolsUtils.getFileIcon(result.file_name);
            const safeFileName = FileToolsUtils.escapeHtml(result.file_name);
            const safeSnippet = FileToolsUtils.escapeHtml(result.snippet || '...');
            const safePathDisplay = FileToolsUtils.escapeHtml(result.path);
            const pathAttr = FileToolsUtils.escapeHtml(result.path).replace(/"/g, '&quot;');

            html += `
                <div class="card bg-transparent border-secondary search-result-card" data-path="${pathAttr}" data-index="${index}" style="cursor: pointer;">
                    <div class="card-body p-3">
                        <div class="d-flex w-100 justify-content-between align-items-start mb-2">
                            <h6 class="card-title mb-0 text-primary text-break pe-3">
                                <i class="bi ${iconClass} me-2"></i>${safeFileName}
                            </h6>
                            <span class="badge bg-secondary bg-opacity-25 text-light border border-secondary border-opacity-50 flex-shrink-0">
                                匹配度: ${result.score.toFixed(2)}
                            </span>
                        </div>
                        <p class="card-text small text-muted mb-2 text-break" style="display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;">
                            ${safeSnippet}
                        </p>
                        <small class="text-muted d-block text-truncate">
                            <i class="bi bi-folder2-open me-1"></i>${safePathDisplay}
                        </small>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;

        // 使用事件委托绑定点击事件
        container.querySelectorAll('.search-result-card').forEach(card => {
            card.addEventListener('click', () => {
                const path = card.getAttribute('data-path');
                if (path) previewFile(path);
            });
        });
    }

    /**
     * 预览文件
     * @param {string} path - 文件路径
     */
    async function previewFile(path) {
        const modalEl = document.getElementById('previewModal');
        const modalTitle = document.getElementById('previewModalTitle');
        const modalContent = document.getElementById('previewModalContent');

        modalTitle.innerText = FileToolsUtils.escapeHtml(path.split(/[\\/]/).pop());
        modalContent.innerText = '正在加载文件内容...';
        FileToolsUtils.showModal(modalEl);

        try {
            const response = await fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });

            if (!response.ok) throw new Error('Failed to load file');

            const data = await response.json();
            modalContent.innerText = data.content || '文件内容为空';

        } catch (error) {
            console.error('Preview error:', error);
            modalContent.innerText = '无法预览文件: ' + error.message;
        }
    }

    /**
     * 重置搜索 UI
     */
    function resetSearchUI() {
        const welcomeContainer = document.getElementById('search-welcome-container');
        const inputArea = document.getElementById('search-input-area');
        const resultsContainer = document.getElementById('resultsContainer');
        const searchInput = document.getElementById('searchInput');

        if (searchInput) searchInput.value = '';
        if (welcomeContainer) welcomeContainer.style.display = 'flex';
        if (resultsContainer) {
            resultsContainer.style.display = 'none';
            resultsContainer.innerHTML = '';
        }
        if (inputArea) inputArea.style.background = 'transparent';
    }

    /**
     * 切换文件类型按钮
     * @param {HTMLElement} btn - 按钮元素
     */
    function toggleFileType(btn) {
        btn.classList.toggle('active');
    }

    /**
     * 自动调整输入框高度
     * @param {HTMLTextAreaElement} textarea - 文本域元素
     */
    function autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
    }

    /**
     * 初始化搜索模块事件监听
     */
    function init() {
        const searchInput = document.getElementById('searchInput');

        if (searchInput) {
            // 回车立即搜索
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    debouncedSearch.cancel();
                    performSearch();
                }
            });

            // 输入防抖搜索
            searchInput.addEventListener('input', function(e) {
                const query = e.target.value.trim();
                if (query.length >= 2) {
                    debouncedSearch();
                }
            });
        }

        // 绑定模式切换事件
        document.querySelectorAll('input[name="aiMode"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const localSettings = document.getElementById('localSettings');
                const apiSettings = document.getElementById('apiSettings');
                if (document.getElementById('modeAPI').checked) {
                    localSettings.style.display = 'none';
                    apiSettings.style.display = 'block';
                } else {
                    localSettings.style.display = 'block';
                    apiSettings.style.display = 'none';
                }
            });
        });
    }

    // 公共 API
    return {
        performSearch,
        previewFile,
        resetSearchUI,
        toggleFileType,
        autoResize,
        init
    };
})();

// 全局暴露函数（向后兼容）
const performSearch = FileToolsSearch.performSearch;
const previewFile = FileToolsSearch.previewFile;
const toggleFileType = FileToolsSearch.toggleFileType;
const autoResize = FileToolsSearch.autoResize;