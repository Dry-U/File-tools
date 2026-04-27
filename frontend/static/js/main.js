/**
 * FileTools - 主入口文件
 * 模块化前端架构，加载所有功能模块并初始化
 * @version 2.0.0
 */

(function() {
    'use strict';

    console.log('FileTools initializing...');

    // 模块加载顺序：utils -> [其他模块] -> event-bindings
    const modules = [
        'modules/tauri-api.js',
        'modules/utils.js',
        'modules/ui.js',
        'modules/search.js',
        'modules/chat.js',
        'modules/directory.js',
        'modules/settings.js',
        'modules/event-bindings.js'
    ];

    // 仅加载 tauri-api.js（供 waitForBackend 使用）
    const tauriModule = 'modules/tauri-api.js';

    function normalizeBackendStatus(statusResult) {
        if (typeof statusResult === 'string') {
            return statusResult;
        }
        if (statusResult && typeof statusResult.status === 'string') {
            return statusResult.status;
        }
        return 'unknown';
    }

    function statusText(status) {
        switch (status) {
            case 'running':
                return '运行中';
            case 'starting':
                return '启动中';
            case 'failed':
                return '失败';
            case 'stopped':
                return '未运行';
            case 'error':
                return '异常';
            case 'timeout':
                return '超时';
            default:
                return '未知';
        }
    }

    function updateBackendStatusUI(rawStatus) {
        const status = normalizeBackendStatus(rawStatus);
        const statusEl = document.getElementById('backend-status');
        const dotEl = document.getElementById('backend-status-dot');
        if (statusEl) {
            statusEl.textContent = statusText(status);
            statusEl.dataset.status = status;
        }
        if (dotEl) {
            dotEl.className = 'status-dot status-' + status;
        }
        return status;
    }

    /**
     * 动态加载 JavaScript 文件
     * @param {string} src - 脚本路径
     * @returns {Promise} 加载完成 Promise
     */
    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = false; // 保持加载顺序
            script.onload = () => {
                console.log(`Module loaded: ${src}`);
                resolve();
            };
            script.onerror = () => {
                console.error(`Failed to load module: ${src}`);
                reject(new Error(`Failed to load: ${src}`));
            };
            document.head.appendChild(script);
        });
    }

    /**
     * 按顺序加载所有模块
     */
    async function loadModules() {
        try {
            // 注意：tauri-api.js 已在 bootstrap 中单独加载，这里跳过
            const modulesToLoad = modules.filter(m => m !== 'modules/tauri-api.js');
            for (const module of modulesToLoad) {
                await loadScript('static/js/' + module);
            }
            console.log('All modules loaded successfully');

            // 端口同步：确保前端连接到后端实际端口
            const redirected = await syncBackendPort();
            if (redirected) {
                // 已触发页面跳转，停止当前页后续初始化避免闪烁和双初始化
                return;
            }

            initializeApp();
        } catch (error) {
            console.error('Module loading failed:', error);
            showFatalError('模块加载失败，请刷新页面重试');
        }
    }

    /**
     * 同步后端端口：若当前窗口端口与后端不一致，则跳转
     */
    async function syncBackendPort() {
        const currentPort = window.location.port;
        try {
            const backendPort = await TauriAPI.getBackendPort();
            if (backendPort && String(backendPort) !== currentPort) {
                const protocol = window.location.protocol;
                const hostname = window.location.hostname;
                const newUrl = `${protocol}//${hostname}:${backendPort}${window.location.pathname}`;
                console.log(`[PortSync] 后端端口 ${backendPort} 与当前 ${currentPort} 不符，跳转至: ${newUrl}`);
                window.location.href = newUrl;
                return true;
            } else {
                console.log(`[PortSync] 端口一致 (${currentPort})，无需跳转`);
                return false;
            }
        } catch (e) {
            console.warn('[PortSync] 端口同步跳过:', e);
            return false;
        }
    }

    /**
     * 显示致命错误
     * @param {string} message - 错误消息
     */
    function showFatalError(message) {
        console.error('[App] Fatal error:', message);

        // 直接操作 document.body 完全替换内容
        document.body.innerHTML = `
            <div style="position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#1a1a2e;padding:20px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
                <div style="font-size:64px;margin-bottom:24px;">⚠️</div>
                <h2 style="color:#e74c3c;margin-bottom:12px;font-size:24px;">出错了</h2>
                <p style="color:#a0a0a0;max-width:400px;line-height:1.6;">${message}</p>
                <div style="margin-top:24px;padding:12px 24px;background:#3498db;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;" id="fatalErrorReloadBtn">
                    刷新页面
                </div>
                <p style="color:#666;margin-top:16px;font-size:12px;">如果问题持续存在，请检查后端服务是否正常运行</p>
            </div>
        `;
        // 添加事件绑定
        const reloadBtn = document.getElementById('fatalErrorReloadBtn');
        if (reloadBtn) {
            reloadBtn.addEventListener('click', function() {
                location.reload();
            });
        }
    }

    /**
     * 等待后端就绪
     * @returns {Promise<boolean>} 后端是否就绪
     */
    async function waitForBackend() {
        const maxWait = 60; // 60秒超时
        const checkInterval = 1000; // 1秒轮询间隔

        console.log('[App] 等待后端启动...');

        // 显示"正在启动后端服务..."提示
        const loadingTip = document.getElementById('backend-loading-tip');
        const loadingBar = document.getElementById('loading-bar');

        // 初始等待 2 秒，让页面和 Tauri API 完全初始化
        console.log('[App] 等待 Tauri API 初始化...');
        await new Promise(r => setTimeout(r, 2000));

        for (let i = 0; i < maxWait; i++) {
            let isReady = false;

            // 方法1: Tauri IPC 状态检测
            if (typeof TauriAPI !== 'undefined' && TauriAPI.getBackendStatus) {
                try {
                    const statusResult = await TauriAPI.getBackendStatus();
                    // Rust 返回字符串：'starting' | 'running' | 'stopped' | 'timeout' | 'error'
                    const status = typeof statusResult === 'string' ? statusResult : statusResult.status;
                    console.log(`[App] 后端状态 (IPC): ${status}`);
                    if (status === 'running') {
                        isReady = true;
                    }
                } catch (e) {
                    console.warn(`[App] IPC 状态检测失败 (${i + 1}/${maxWait}):`, e.message);
                }
            }

            // 方法2: HTTP 健康检查（同时尝试，双重保险）
            if (!isReady) {
                try {
                    const res = await fetch('/api/health', {
                        cache: 'no-cache',
                        signal: AbortSignal.timeout(3000)
                    });
                    if (res.ok) {
                        const data = await res.json();
                        console.log(`[App] 后端状态 (HTTP): ${data.status}`);
                        if (data.status === 'healthy') {
                            isReady = true;
                        }
                    } else {
                        console.warn(`[App] HTTP 健康检查失败: ${res.status}`);
                    }
                } catch (e) {
                    console.warn(`[App] HTTP 健康检测失败 (${i + 1}/${maxWait}):`, e.message);
                }
            }

            if (isReady) {
                console.log('[App] 后端已就绪');
                return true;
            }

            // 更新进度条和提示文字
            if (loadingBar) {
                loadingBar.style.width = Math.min((i / maxWait) * 100, 90) + '%';
            }
            if (loadingTip) {
                const secs = maxWait - i;
                loadingTip.textContent = `请稍候（${secs}秒）`;
            }

            await new Promise(r => setTimeout(r, checkInterval));
        }

        console.warn('[App] 后端启动超时（60秒）');
        return false;
    }

    /**
     * 初始化应用
     */
    function initializeApp() {
        console.log('Initializing application...');

        // 显示主界面（后端已就绪）
        const loadingEl = document.getElementById('backend-loading');
        const appEl = document.getElementById('app-container');
        if (loadingEl) loadingEl.style.display = 'none';
        if (appEl) appEl.style.display = '';

        // 检查核心模块是否可用
        if (typeof FileToolsUtils === 'undefined') {
            console.error('Core utilities module not loaded');
            showFatalError('核心模块加载失败');
            return;
        }

        // 初始化各模块
        if (typeof FileToolsUI !== 'undefined') {
            FileToolsUI.init();
        }

        if (typeof FileToolsSearch !== 'undefined') {
            FileToolsSearch.init();
        }

        if (typeof FileToolsChat !== 'undefined') {
            FileToolsChat.init();
        }

        // 初始化后端事件监听
        initBackendEventListeners();

        // 初始化事件绑定（必须在其他模块初始化后）
        if (typeof FileToolsEventBindings !== 'undefined') {
            FileToolsEventBindings.init();
        }

        // 检查DOM是否已经加载完成
        if (document.readyState === 'loading') {
            // DOM还在加载中，等待DOMContentLoaded事件
            document.addEventListener('DOMContentLoaded', function() {
                console.log('DOMContentLoaded triggered');
                initAfterDOMReady();
            });
        } else {
            // DOM已经加载完成，直接初始化
            console.log('DOM already loaded, initializing...');
            initAfterDOMReady();
        }

        // 从 localStorage 恢复会话 ID
        let savedSessionId = null;
        try {
            savedSessionId = localStorage.getItem('chat_session_id');
        } catch (e) {
            console.warn('localStorage not available:', e);
        }
        if (savedSessionId && typeof FileToolsChat !== 'undefined') {
            FileToolsChat.setCurrentSessionId(savedSessionId);
        }
    }

    /**
     * 初始化后端事件监听
     */
    function initBackendEventListeners() {
        if (typeof TauriAPI !== 'undefined' && TauriAPI.backendEvents) {
            TauriAPI.backendEvents.init({
                onStarted: function() {
                    console.log('[App] 后端已启动');
                    // 隐藏后端启动中的加载提示
                    const loadingEl = document.getElementById('backend-loading');
                    if (loadingEl) {
                        loadingEl.style.display = 'none';
                    }
                    // 显示主界面
                    const appContainer = document.getElementById('app-container');
                    if (appContainer) {
                        appContainer.style.display = '';
                    }
                },
                onError: function(errorMsg) {
                    console.error('[App] 后端启动失败:', errorMsg);
                    // 显示错误提示
                    if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.showToast) {
                        FileToolsUtils.showToast('后端启动失败: ' + errorMsg, 'error');
                    } else {
                        alert('后端启动失败: ' + errorMsg);
                    }
                },
                onStatusChanged: function(status) {
                    console.log('[App] 后端状态:', status);
                    updateBackendStatusUI(status);
                }
            });

            // 查询当前后端状态，避免错过初始状态事件
            queryBackendStatus();
        }
    }

    /**
     * 查询后端当前状态
     */
    async function queryBackendStatus() {
        if (typeof TauriAPI !== 'undefined' && TauriAPI.getBackendStatus) {
            try {
                const statusResult = await TauriAPI.getBackendStatus();
                console.log('[App] 后端状态查询结果:', statusResult);
                const status = updateBackendStatusUI(statusResult);

                // 如果后端未运行，显示提示
                if (status === 'stopped' || status === 'error' || status === 'failed') {
                    const loadingEl = document.getElementById('backend-loading');
                    if (loadingEl) {
                        loadingEl.style.display = 'none';
                    }
                    if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.showToast) {
                        FileToolsUtils.showToast('后端未运行，请检查配置', 'warning');
                    }
                }
            } catch (error) {
                console.error('[App] 查询后端状态失败:', error);
            }
        }
    }

    /**
     * DOM加载完成后初始化
     */
    function initAfterDOMReady() {
        if (typeof FileToolsChat !== 'undefined') {
            FileToolsChat.loadChatHistory();
        }

        // 初始化侧边栏按钮
        if (typeof FileToolsUI !== 'undefined') {
            FileToolsUI.initSidebarToggleBtn();
        }

        checkIndexMigrationNotice();

        console.log('Application initialized');
    }

    async function checkIndexMigrationNotice() {
        try {
            const noticeKey = 'index_migration_notice_ack_v1';
            const res = await fetch('/api/config', { method: 'GET', cache: 'no-cache' });
            if (!res.ok) return;
            const config = await res.json();
            const notice = (config && config.migration_notice) ? String(config.migration_notice).trim() : '';
            if (!notice) return;
            const lastAckNotice = localStorage.getItem(noticeKey);
            if (lastAckNotice === notice) return;
            localStorage.setItem(noticeKey, notice);
            if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.showToast) {
                FileToolsUtils.showToast(notice, 'warning');
            } else {
                console.warn('[App] 索引迁移提示:', notice);
            }
        } catch (e) {
            console.warn('[App] 检查索引迁移提示失败:', e);
        }
    }

    // 启动应用：先加载 tauri-api，等待后端就绪，再加载所有模块
    (async function bootstrap() {
        // 1. 先加载 tauri-api.js（供后端检测使用）
        try {
            await loadScript('static/js/' + tauriModule);
        } catch (e) {
            console.error('[App] tauri-api.js 加载失败:', e);
            showFatalError('核心模块加载失败，请刷新页面重试');
            return;
        }

        // 2. 显示 loading 指示器
        const loadingEl = document.getElementById('backend-loading');
        if (loadingEl) loadingEl.style.display = '';

        // 3. 等待后端就绪（最多60秒）
        const backendReady = await waitForBackend();

        if (!backendReady) {
            // 超时后显示错误
            if (loadingEl) loadingEl.style.display = 'none';
            showFatalError('后端启动超时（60秒），请检查配置或重启应用');
            return;
        }

        // 4. 后端就绪后，加载所有模块
        await loadModules();
    })();
})();
