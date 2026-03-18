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
        'modules/utils.js',
        'modules/ui.js',
        'modules/search.js',
        'modules/chat.js',
        'modules/directory.js',
        'modules/settings.js',
        'modules/event-bindings.js'
    ];

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
            for (const module of modules) {
                await loadScript('static/js/' + module);
            }
            console.log('All modules loaded successfully');
            initializeApp();
        } catch (error) {
            console.error('Module loading failed:', error);
            showFatalError('模块加载失败，请刷新页面重试');
        }
    }

    /**
     * 显示致命错误
     * @param {string} message - 错误消息
     */
    function showFatalError(message) {
        const container = document.getElementById('app') || document.body;
        container.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;padding:20px;text-align:center;">
                <div style="font-size:48px;margin-bottom:20px;">⚠️</div>
                <h2 style="color:#dc3545;margin-bottom:10px;">出错了</h2>
                <p style="color:#6c757d;">${message}</p>
                <button id="fatalErrorReloadBtn" style="margin-top:20px;padding:10px 20px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;">
                    刷新页面
                </button>
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
     * 初始化应用
     */
    function initializeApp() {
        console.log('Initializing application...');

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
        const savedSessionId = localStorage.getItem('chat_session_id');
        if (savedSessionId && typeof FileToolsChat !== 'undefined') {
            FileToolsChat.setCurrentSessionId(savedSessionId);
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

        console.log('Application initialized');
    }

    // 启动应用
    loadModules();
})();
