/**
 * FileTools - 工具函数模块
 * 提供通用工具函数，包括 HTML 转义、防抖节流、日期格式化等
 */

const FileToolsUtils = (function() {
    'use strict';

    let messageIdCounter = 0;

    /**
     * HTML 转义，防止 XSS 攻击
     * @param {string} text - 原始文本
     * @returns {string} 转义后的 HTML
     */
    function escapeHtml(text) {
        if (typeof text !== 'string') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 生成唯一消息 ID
     * @param {string} prefix - ID 前缀
     * @returns {string} 唯一 ID
     */
    function generateMessageId(prefix) {
        if (prefix === undefined) prefix = 'msg';
        return prefix + '-' + Date.now() + '-' + (++messageIdCounter) + '-' + Math.random().toString(36).substr(2, 5);
    }

    /**
     * 格式化日期
     * @param {string|Date} date - 日期字符串或 Date 对象
     * @returns {string} 格式化后的日期
     */
    function formatDate(date) {
        const d = new Date(date);
        const now = new Date();
        const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));

        if (diffDays === 0) return '今天';
        if (diffDays === 1) return '昨天';
        if (diffDays < 7) return `${diffDays}天前`;
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    }

    /**
     * 获取文件图标类名
     * @param {string} filename - 文件名
     * @returns {string} Bootstrap Icons 类名
     */
    function getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const iconMap = {
            'pdf': 'bi-file-pdf',
            'doc': 'bi-file-word',
            'docx': 'bi-file-word',
            'txt': 'bi-file-text',
            'md': 'bi-markdown',
            'py': 'bi-file-code',
            'js': 'bi-filetype-js',
            'html': 'bi-filetype-html',
            'css': 'bi-filetype-css',
            'xls': 'bi-file-excel',
            'xlsx': 'bi-file-excel',
            'ppt': 'bi-file-ppt',
            'pptx': 'bi-file-ppt',
            'json': 'bi-filetype-json',
            'xml': 'bi-filetype-xml',
            'zip': 'bi-file-zip',
            'rar': 'bi-file-zip',
            'png': 'bi-file-image',
            'jpg': 'bi-file-image',
            'jpeg': 'bi-file-image',
            'gif': 'bi-file-image'
        };
        return iconMap[ext] || 'bi-file-earmark';
    }

    /**
     * 防抖函数 - 用于优化频繁触发的事件
     * @param {Function} func - 要执行的函数
     * @param {number} wait - 等待时间（毫秒）
     * @param {boolean} immediate - 是否立即执行
     * @returns {Function} 防抖后的函数
     */
    function debounce(func, wait, immediate) {
        if (immediate === undefined) immediate = false;
        let timeout;
        const executedFunction = function () {
            var args = Array.prototype.slice.call(arguments);
            const later = function () {
                timeout = null;
                if (!immediate) func.apply(null, args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func.apply(null, args);
        };
        executedFunction.cancel = function () {
            if (timeout) {
                clearTimeout(timeout);
                timeout = null;
            }
        };
        return executedFunction;
    }

    /**
     * 节流函数 - 用于限制函数执行频率
     * @param {Function} func - 要执行的函数
     * @param {number} limit - 限制时间（毫秒）
     * @returns {Function} 节流后的函数
     */
    function throttle(func, limit) {
        let inThrottle;
        return function executedFunction() {
            var args = Array.prototype.slice.call(arguments);
            if (!inThrottle) {
                func.apply(null, args);
                inThrottle = true;
                setTimeout(function () { inThrottle = false; }, limit);
            }
        };
    }

    /**
     * 显示 Toast 消息
     * @param {string} message - 消息内容
     * @param {string} type - 类型: success, error, warning, info
     */
    function showToast(message, type) {
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0`;
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');

        // 添加关闭按钮
        const closeBtnId = 'toast-close-' + Date.now();
        toastEl.innerHTML = `
            <div class="toast-body">
                <span>${escapeHtml(message)}</span>
                <button type="button" id="${closeBtnId}" class="toast-close-btn" aria-label="关闭">×</button>
            </div>
        `;

        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        container.appendChild(toastEl);

        let bootstrapToast = null;

        // 绑定关闭按钮点击事件
        const closeBtn = document.getElementById(closeBtnId);
        if (closeBtn) {
            closeBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                // 如果有 Bootstrap Toast 实例，先 hide
                if (bootstrapToast) {
                    bootstrapToast.hide();
                }
                removeToast();
            });
        }

        const removeToast = () => {
            if (toastEl.parentNode) {
                toastEl.parentNode.removeChild(toastEl);
            }
        };

        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            bootstrapToast = new bootstrap.Toast(toastEl, { delay: 3000 });
            bootstrapToast.show();
            toastEl.addEventListener('hidden.bs.toast', removeToast);
            setTimeout(removeToast, 3500);
        } else {
            // 后备方案：手动实现关闭功能
            toastEl.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;padding:10px 15px;border-radius:4px;min-width:250px;max-width:400px;display:flex;opacity:1;visibility:visible;';
            toastEl.style.background = type === 'error' ? '#dc3545' : type === 'success' ? '#198754' : '#0d6efd';

            setTimeout(removeToast, 3000);
        }
    }

    /**
     * 通用显示模态框函数（带后备方案）
     * @param {HTMLElement} modalEl - 模态框元素
     */
    function showModal(modalEl) {
        if (!modalEl) {
            console.error('showModal: modal element is null');
            return;
        }

        console.log('showModal called for:', modalEl.id);

        try {
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                console.log('Bootstrap is available, using Bootstrap Modal');
                let modal = bootstrap.Modal.getInstance(modalEl);
                if (!modal) {
                    modal = new bootstrap.Modal(modalEl);
                }
                modal.show();
            } else {
                throw new Error('Bootstrap not available');
            }
        } catch (err) {
            console.log('Using fallback modal display:', err.message);
            modalEl.style.display = 'block';
            modalEl.classList.add('show');
            modalEl.setAttribute('aria-hidden', 'false');
            document.body.classList.add('modal-open');

            let backdrop = document.querySelector('.modal-backdrop');
            if (!backdrop) {
                backdrop = document.createElement('div');
                backdrop.className = 'modal-backdrop fade show';
                document.body.appendChild(backdrop);
            }
        }
    }

    /**
     * 通用隐藏模态框函数（带后备方案）
     * @param {HTMLElement} modalEl - 模态框元素
     */
    function hideModal(modalEl) {
        if (!modalEl) return;

        // 在隐藏模态框前，先移除焦点，避免 aria-hidden 焦点警告
        // 如果当前焦点元素在即将被隐藏的模态框内，先 blur 它
        try {
            const activeEl = document.activeElement;
            if (activeEl && modalEl.contains(activeEl)) {
                activeEl.blur();
            }
        } catch (e) {
            // 忽略 blur 错误
        }

        try {
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                const modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) {
                    modal.hide();
                    return;
                }
            }
            throw new Error('Bootstrap not available or no instance');
        } catch (err) {
            modalEl.style.display = 'none';
            modalEl.classList.remove('show');
            modalEl.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('modal-open');
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    }

    /**
     * 打开外部链接（在浏览器中打开）
     * @param {string} url - 链接地址
     * @param {Event} event - 事件对象
     * @returns {boolean} false
     */
    async function openExternalLink(url, event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        // 使用 Tauri API
        if (window.TauriAPI) {
            try {
                await window.TauriAPI.openExternal(url);
                showToast('已在浏览器中打开链接', 'info');
                return false;
            } catch (e) {
                console.warn('Tauri API call failed:', e);
            }
        }

        // 降级：使用 window.open
        const newWindow = window.open(url, '_blank', 'noopener,noreferrer');
        if (!newWindow) {
            window.location.href = url;
        }
        return false;
    }

    /**
     * 显示测试结果弹窗
     * @param {string} title - 标题
     * @param {string} message - 消息内容
     * @param {boolean} isSuccess - 是否成功
     */
    function showTestResultModal(title, message, isSuccess) {
        const modalEl = document.getElementById('testResultModal');
        const titleEl = document.getElementById('testResultTitle');
        const bodyEl = document.getElementById('testResultBody');

        if (!modalEl || !titleEl || !bodyEl) return;

        const safeTitle = escapeHtml(title);
        const safeMessage = escapeHtml(message);
        const iconClass = isSuccess ? 'bi-check-circle-fill text-success' : 'bi-x-circle-fill text-danger';
        titleEl.innerHTML = `<i class="bi ${isSuccess ? 'bi-check-circle' : 'bi-x-circle'} me-2"></i>${safeTitle}`;
        bodyEl.innerHTML = `
            <div class="mb-3">
                <i class="bi ${iconClass}" style="font-size: 48px;"></i>
            </div>
            <p class="mb-0 small">${safeMessage}</p>
        `;

        showModal(modalEl);
    }

    /**
     * 生成会话 ID
     * @returns {string} 会话 ID
     */
    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 带超时的 fetch 请求
     * @param {string} url - 请求 URL
     * @param {Object} options - fetch 选项
     * @param {number} timeout - 超时时间（毫秒）
     * @returns {Promise<Response>} 响应对象
     */
    async function fetchWithTimeout(url, options = {}, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error(`请求超时 (${timeout}ms): ${url}`);
            }
            throw error;
        }
    }

    // 公共 API
    return {
        escapeHtml,
        generateMessageId,
        formatDate,
        getFileIcon,
        debounce,
        throttle,
        showToast,
        showModal,
        hideModal,
        openExternalLink,
        showTestResultModal,
        generateSessionId,
        fetchWithTimeout
    };
})();

// 为了保持向后兼容，将主要函数暴露到全局作用域
const escapeHtml = FileToolsUtils.escapeHtml;
const generateMessageId = FileToolsUtils.generateMessageId;
const formatDate = FileToolsUtils.formatDate;
const getFileIcon = FileToolsUtils.getFileIcon;
const debounce = FileToolsUtils.debounce;
const throttle = FileToolsUtils.throttle;
const showToast = FileToolsUtils.showToast;
const showModal = FileToolsUtils.showModal;
const hideModal = FileToolsUtils.hideModal;
const openExternalLink = FileToolsUtils.openExternalLink;
const showTestResultModal = FileToolsUtils.showTestResultModal;
const generateSessionId = FileToolsUtils.generateSessionId;
const fetchWithTimeout = FileToolsUtils.fetchWithTimeout;