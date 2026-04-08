/**
 * FileTools - UI 模块
 * 提供 UI 相关功能，包括侧边栏、模式切换、日期选择器等
 */

const FileToolsUI = (function() {
    'use strict';

    // 当前模式
    let currentMode = 'search';

    /**
     * 切换模式（搜索/聊天）
     * @param {string} mode - 模式: 'search' 或 'chat'
     */
    function switchMode(mode) {
        currentMode = mode;

        // 更新 Tab 样式
        document.querySelectorAll('.nav-tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        const tabBtn = document.getElementById(`tab-${mode}`);
        if (tabBtn) tabBtn.classList.add('active');

        // 切换侧边栏内容
        const searchSidebar = document.getElementById('sidebar-search-content');
        const chatSidebar = document.getElementById('sidebar-chat-content');

        if (searchSidebar && chatSidebar) {
            if (mode === 'search') {
                searchSidebar.style.display = 'block';
                chatSidebar.style.display = 'none';
            } else {
                searchSidebar.style.display = 'none';
                chatSidebar.style.display = 'block';
            }
        }

        // 切换主视图
        const searchView = document.getElementById('view-search');
        const chatView = document.getElementById('view-chat');

        if (searchView && chatView) {
            if (mode === 'search') {
                searchView.style.setProperty('display', 'flex', 'important');
                chatView.style.setProperty('display', 'none', 'important');
            } else {
                searchView.style.setProperty('display', 'none', 'important');
                chatView.style.setProperty('display', 'flex', 'important');
            }
        }
    }

    /**
     * 切换侧边栏
     */
    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const btn = document.getElementById('sidebarToggleBtn');
        if (!sidebar || !btn) return;

        const isMobile = window.innerWidth <= 768;

        if (isMobile) {
            sidebar.classList.toggle('show');
        } else {
            sidebar.classList.toggle('collapsed');
        }

        // 更新图标
        const isVisible = isMobile ? sidebar.classList.contains('show') : !sidebar.classList.contains('collapsed');
        updateSidebarToggleIcon(btn, isVisible);
    }

    /**
     * 更新侧边栏切换按钮图标
     * @param {HTMLElement} btn - 按钮元素
     * @param {boolean} isVisible - 侧边栏是否可见
     */
    function updateSidebarToggleIcon(btn, isVisible) {
        if (isVisible) {
            // 显示收起图标
            btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6" style="width: 24px; height: 24px;">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15M12 9l-3 3m0 0 3 3m-3-3h12.75" />
                </svg>
            `;
        } else {
            // 显示展开图标
            btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6" style="width: 24px; height: 24px;">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 9V5.25A2.25 2.25 0 0 1 10.5 3h6a2.25 2.25 0 0 1 2.25 2.25v13.5A2.25 2.25 0 0 1 16.5 21h-6a2.25 2.25 0 0 1-2.25-2.25V15M12 9l3 3m0 0-3 3m3-3H2.25" />
                </svg>
            `;
        }
    }

    /**
     * 初始化侧边栏按钮图标
     */
    function initSidebarToggleBtn() {
        const sidebar = document.getElementById('sidebar');
        const btn = document.getElementById('sidebarToggleBtn');
        if (!sidebar || !btn) return;

        const isMobile = window.innerWidth <= 768;
        const isCollapsed = isMobile ? !sidebar.classList.contains('show') : sidebar.classList.contains('collapsed');

        updateSidebarToggleIcon(btn, !isCollapsed);
    }

    /**
     * 初始化日期选择器
     */
    function initDatePickers() {
        const dateFrom = document.getElementById('dateFrom');
        const dateTo = document.getElementById('dateTo');
        const dateFromDisplay = document.getElementById('dateFromDisplay');
        const dateToDisplay = document.getElementById('dateToDisplay');

        function formatAndDisplayDate(inputEl, displayEl, defaultText) {
            if (inputEl.value) {
                const date = new Date(inputEl.value);
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const formattedDate = `${year}年${month}月${day}日`;
                displayEl.textContent = formattedDate;
                displayEl.classList.add('has-value');
            } else {
                displayEl.textContent = defaultText;
                displayEl.classList.remove('has-value');
            }
        }

        function setupDatePicker(inputEl, displayEl, defaultText) {
            if (!inputEl) return;

            const wrapper = inputEl.closest('.date-picker-wrapper');
            if (wrapper) {
                wrapper.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    inputEl.style.pointerEvents = 'auto';
                    try {
                        if (typeof inputEl.showPicker === 'function') {
                            inputEl.showPicker();
                        } else {
                            inputEl.click();
                        }
                    } catch (err) {
                        inputEl.focus();
                    }
                    setTimeout(() => {
                        inputEl.style.pointerEvents = 'none';
                    }, 100);
                });
            }

            inputEl.addEventListener('change', function() {
                formatAndDisplayDate(inputEl, displayEl, defaultText);
            });
        }

        setupDatePicker(dateFrom, dateFromDisplay, '开始');
        setupDatePicker(dateTo, dateToDisplay, '结束');
    }

    /**
     * 健康检查（带重试和轮询）
     */
    async function checkSystemHealth(maxRetries = 12, interval = 5000) {
        let retryCount = 0;

        while (retryCount < maxRetries) {
            try {
                const response = await fetchWithTimeout('/api/health', {}, 5000);
                const health = await response.json();

                if (health.status === 'healthy') {
                    FileToolsUtils.showToast('系统已就绪', 'success');
                    return true;
                } else if (health.status === 'starting' || health.status === 'degraded') {
                    retryCount++;
                    if (retryCount === 1) {
                        FileToolsUtils.showToast('系统正在初始化，请稍候...', 'info');
                    }
                } else {
                    FileToolsUtils.showToast('系统状态异常: ' + (health.message || '未知错误'), 'warning');
                    return false;
                }
            } catch (error) {
                retryCount++;
                if (retryCount === 1) {
                    console.log('等待后端服务启动...');
                }
            }

            // 等待后重试
            if (retryCount < maxRetries) {
                await new Promise(resolve => setTimeout(resolve, interval));
            }
        }

        // 超过最大重试次数
        FileToolsUtils.showToast('后端启动超时，请检查日志', 'error');
        return false;
    }

    /**
     * 获取当前模式
     * @returns {string} 当前模式
     */
    function getCurrentMode() {
        return currentMode;
    }

    /**
     * 初始化 UI 模块事件监听
     */
    function init() {
        // 初始化侧边栏按钮
        initSidebarToggleBtn();

        // 初始化日期选择器
        initDatePickers();

        // 健康检查
        checkSystemHealth();

        // 窗口大小改变时更新侧边栏按钮
        window.addEventListener('resize', function() {
            initSidebarToggleBtn();
        });
    }

    // 公共 API
    return {
        switchMode,
        toggleSidebar,
        initSidebarToggleBtn,
        initDatePickers,
        checkSystemHealth,
        getCurrentMode,
        init
    };
})();

// 全局暴露函数（向后兼容）
const switchMode = FileToolsUI.switchMode;
const toggleSidebar = FileToolsUI.toggleSidebar;
const initSidebarToggleBtn = FileToolsUI.initSidebarToggleBtn;
const initDatePickers = FileToolsUI.initDatePickers;
const checkSystemHealth = FileToolsUI.checkSystemHealth;