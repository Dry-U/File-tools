/**
 * Tauri API 封装
 * 系统对话框、外部链接
 * 注意：窗口控制已改用原生边框 (decorations: true)
 */

(function() {
    'use strict';

    // 检测 Tauri 环境
    const isTauri = typeof window.__TAURI__ !== 'undefined' && window.__TAURI__;

    console.log('[TauriAPI] Tauri 环境:', isTauri);

    if (!isTauri) {
        console.warn('[TauriAPI] 非 Tauri 环境，部分功能不可用');
    }

    // Tauri invoke 封装
    async function tauriInvoke(cmd, args = {}) {
        if (!isTauri) {
            throw new Error('Tauri 环境不可用');
        }
        return await window.__TAURI__.core.invoke(cmd, args);
    }

    const TauriAPI = {
        // 打开外部链接
        openExternal: async function(url) {
            // Tauri v2 API
            if (window.__TAURI__ && window.__TAURI__.shell) {
                return await window.__TAURI__.shell.open(url);
            }
            // Tauri v1 API (fallback)
            if (window.__TAURI__ && window.__TAURI__.plugin && window.__TAURI__.plugin.shell) {
                const { open } = window.__TAURI__.plugin.shell;
                return await open(url);
            }
            throw new Error('Tauri shell API not available');
        },

        // 选择目录
        selectDirectory: async function() {
            const { open } = window.__TAURI__.dialog;
            const result = await open({
                directory: true,
                multiple: false
            });
            if (result) {
                return { success: true, path: result, canceled: false };
            }
            return { success: true, canceled: true };
        },

        // 调用 Rust IPC 命令
        invoke: async function(cmd, args = {}) {
            if (!isTauri) {
                throw new Error('Tauri 环境不可用');
            }
            try {
                return await window.__TAURI__.core.invoke(cmd, args);
            } catch (error) {
                console.error(`[TauriAPI] 命令 ${cmd} 执行失败:`, error);
                throw error;
            }
        },

        // 获取后端状态
        getBackendStatus: async function() {
            if (!isTauri) {
                return { status: 'unknown', error: '非 Tauri 环境' };
            }
            try {
                return await window.__TAURI__.core.invoke('get_backend_status');
            } catch (error) {
                console.error('[TauriAPI] 获取后端状态失败:', error);
                return { status: 'error', error: error.message };
            }
        },

        // 后端状态事件监听
        backendEvents: {
            _listeners: {},

            /**
             * 监听后端事件
             * @param {string} eventName - 事件名: 'backend-status-changed' | 'backend-started' | 'backend-start-error'
             * @param {function} callback - 回调函数
             * @returns {function} 取消监听函数
             */
            listen: function(eventName, callback) {
                if (!isTauri) {
                    console.warn('[TauriAPI] 非 Tauri 环境，无法监听后端事件');
                    return () => {};
                }

                const unlisten = window.__TAURI__.event.listen(eventName, (event) => {
                    console.log(`[TauriAPI] 后端事件: ${eventName}`, event.payload);
                    callback(event.payload);
                });

                // 存储取消函数
                if (!this._listeners[eventName]) {
                    this._listeners[eventName] = [];
                }
                this._listeners[eventName].push(unlisten);

                // 返回取消监听函数
                return () => {
                    const listeners = this._listeners[eventName] || [];
                    const index = listeners.indexOf(unlisten);
                    if (index > -1) {
                        listeners.splice(index, 1);
                    }
                    unlisten();
                };
            },

            /**
             * 监听后端启动成功
             * @param {function} callback
             * @returns {function} 取消监听函数
             */
            onBackendStarted: function(callback) {
                return this.listen('backend-started', callback);
            },

            /**
             * 监听后端启动错误
             * @param {function} callback - 接收错误信息字符串
             * @returns {function} 取消监听函数
             */
            onBackendError: function(callback) {
                return this.listen('backend-start-error', (errorMsg) => {
                    console.error('[TauriAPI] 后端启动错误:', errorMsg);
                    callback(errorMsg);
                });
            },

            /**
             * 监听后端状态变化
             * @param {function} callback - 接收状态字符串 (starting/running/stopping/stopped/failed/error)
             * @returns {function} 取消监听函数
             */
            onBackendStatusChanged: function(callback) {
                return this.listen('backend-status-changed', (status) => {
                    console.log(`[TauriAPI] 后端状态变化: ${status}`);
                    callback(status);
                });
            },

            /**
             * 初始化后端事件监听（自动设置常用监听）
             * @param {Object} handlers - { onStarted, onError, onStatusChanged }
             */
            init: function(handlers = {}) {
                if (!isTauri) {
                    console.warn('[TauriAPI] 非 Tauri 环境，跳过后端事件监听初始化');
                    return;
                }

                console.log('[TauriAPI] 初始化后端事件监听...');

                if (handlers.onStarted) {
                    this.onBackendStarted(handlers.onStarted);
                }
                if (handlers.onError) {
                    this.onBackendError(handlers.onError);
                }
                if (handlers.onStatusChanged) {
                    this.onBackendStatusChanged(handlers.onStatusChanged);
                }

                console.log('[TauriAPI] 后端事件监听初始化完成');
            }
        }
    };

    // 暴露到全局
    window.TauriAPI = TauriAPI;
    // isTauri 可能在其他地方已定义，避免覆盖错误
    try {
        if (!window.isTauri) {
            window.isTauri = isTauri;
        }
    } catch (e) {
        // 如果赋值失败（只读属性），使用 defineProperty
        try {
            Object.defineProperty(window, 'isTauri', {
                value: isTauri,
                writable: true,
                configurable: true
            });
        } catch (e2) {
            console.warn('[TauriAPI] 无法设置 isTauri:', e2);
        }
    }

    console.log('[TauriAPI] 初始化完成');
})();
