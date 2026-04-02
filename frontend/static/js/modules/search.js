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
        const allTypeBtns = document.querySelectorAll('.file-type-btn');
        
        // 展开复合类型（如 ppt,pptx → .ppt,.pptx）
        const types = [];
        activeTypeBtns.forEach(btn => {
            const typeStr = btn.dataset.type;
            if (typeStr.includes(',')) {
                typeStr.split(',').forEach(t => types.push('.' + t.trim()));
            } else {
                types.push('.' + typeStr);
            }
        });
        
        if (activeTypeBtns.length === 0) {
            // 全不选时显示提示并返回空结果
            resultsContainer.innerHTML = `
                <div class="text-center text-warning mt-5">
                    <i class="bi bi-exclamation-triangle display-4"></i>
                    <p class="mt-3">请至少选择一种文件类型</p>
                </div>
            `;
            return;
        }
        
        if (activeTypeBtns.length < allTypeBtns.length) {
            // 部分选择时应用过滤器
            filters.file_types = types;
        }
        // 如果全部选择，则不设置 file_types 过滤器（搜索所有类型）

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

            if (response.status === 429) {
                resultsContainer.innerHTML = `
                    <div class="text-center text-warning mt-5">
                        <i class="bi bi-clock display-4"></i>
                        <p class="mt-3">请求过于频繁，请稍后再试</p>
                    </div>
                `;
                return;
            }

            if (response.status === 503) {
                resultsContainer.innerHTML = `
                    <div class="text-center text-warning mt-5">
                        <i class="bi bi-hourglass-split display-4"></i>
                        <p class="mt-3">系统正在初始化，请稍后重试</p>
                    </div>
                `;
                return;
            }

            if (response.status === 500) {
                resultsContainer.innerHTML = `
                    <div class="text-center text-danger mt-5">
                        <i class="bi bi-exclamation-triangle display-4"></i>
                        <p class="mt-3">服务器内部错误，请稍后重试或查看日志</p>
                    </div>
                `;
                return;
            }

            if (!response.ok) throw new Error('搜索请求失败');

            const results = await response.json();
            renderSearchResults(results, resultsContainer);

        } catch (error) {
            console.error('Search error:', error);
            const isNetworkError = error.message === 'Failed to fetch' || error.name === 'TypeError';
            const errorMsg = isNetworkError
                ? '网络连接失败，请检查服务是否运行'
                : '搜索出错，请稍后重试';
            resultsContainer.innerHTML = `
                <div class="text-center text-danger mt-5">
                    <i class="bi bi-${isNetworkError ? 'wifi-off' : 'exclamation-circle'} display-4"></i>
                    <p class="mt-3">${FileToolsUtils.escapeHtml(errorMsg)}</p>
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
            // snippet 包含高亮HTML标签，不应转义；只处理null/undefined情况
            const safeSnippet = result.snippet ? result.snippet : '...';
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
        modalContent.innerHTML = '<div class="text-center text-muted p-4">正在加载文件内容...</div>';
        FileToolsUtils.showModal(modalEl);

        try {
            const response = await fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });

            if (response.status === 404) {
                modalContent.innerHTML = '<div class="text-warning p-3"><i class="bi bi-file-earmark-x me-2"></i>文件不存在或已被删除</div>';
                return;
            }

            if (response.status === 403) {
                modalContent.innerHTML = '<div class="text-warning p-3"><i class="bi bi-shield-lock me-2"></i>无权访问此文件（路径不在允许范围内）</div>';
                return;
            }

            if (response.status === 413) {
                modalContent.innerHTML = '<div class="text-warning p-3"><i class="bi bi-file-earmark-break me-2"></i>文件过大，无法预览</div>';
                return;
            }

            if (!response.ok) throw new Error('预览请求失败');

            const data = await response.json();
            let content = data.content || '文件内容为空';

            // 处理内容格式：PDF/DOCX解析后的纯文本需要适当处理
            if (content && typeof content === 'string') {
                // 检查是否为Markdown文件（根据路径判断）
                const isMarkdown = path && (path.endsWith('.md') || path.endsWith('.markdown'));
                
                if (isMarkdown && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                    // 使用marked.js渲染Markdown，并使用DOMPurify防止XSS攻击
                    const rawHtml = marked.parse(content);
                    modalContent.innerHTML = DOMPurify.sanitize(rawHtml, {
                        ALLOWED_TAGS: ['h1','h2','h3','h4','h5','h6','p','br','hr','ul','ol','li',
                                       'blockquote','pre','code','em','strong','a','img','table',
                                       'thead','tbody','tr','th','td','div','span'],
                        ALLOWED_ATTR: ['href','src','alt','title','class','id']
                    });
                } else if (isMarkdown && typeof marked !== 'undefined') {
                    // DOMPurify不可用时，使用textContent降级
                    modalContent.textContent = content;
                } else {
                    // 处理换行，保持段落格式
                    content = content.replace(/\n{3,}/g, '\n\n');
                    // 使用textContent和<pre>标签保持格式同时防止XSS
                    modalContent.textContent = content;
                }
            } else {
                modalContent.innerHTML = '<div class="text-muted">文件内容为空</div>';
            }

        } catch (error) {
            console.error('Preview error:', error);
            const isNetworkError = error.message === 'Failed to fetch' || error.name === 'TypeError';
            const errorMsg = isNetworkError
                ? '网络连接失败'
                : '无法预览文件内容';
            modalContent.innerHTML = `<div class="text-danger p-3"><i class="bi bi-${isNetworkError ? 'wifi-off' : 'exclamation-circle'} me-2"></i>${FileToolsUtils.escapeHtml(errorMsg)}</div>`;
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
        // 同步更新 aria-pressed 状态
        const isActive = btn.classList.contains('active');
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
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