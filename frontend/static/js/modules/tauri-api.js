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
            console.log('[TauriAPI] openExternal 被调用, URL:', url, 'isTauri:', isTauri);
            // 优先使用自定义 Rust 命令打开外部链接
            if (isTauri && window.__TAURI__) {
                try {
                    console.log('[TauriAPI] 使用 open_external_url 命令打开:', url);
                    await window.__TAURI__.core.invoke('open_external_url', { url });
                    console.log('[TauriAPI] open_external_url 完成');
                    return true;
                } catch (err) {
                    console.error('[TauriAPI] open_external_url 失败:', err);
                    // 降级到 window.open
                    console.log('[TauriAPI] 降级到 window.open');
                    window.open(url, '_blank', 'noopener,noreferrer');
                    return true;
                }
            }
            // 非 Tauri 环境，使用 window.open
            console.log('[TauriAPI] 使用 window.open 打开:', url);
            window.open(url, '_blank', 'noopener,noreferrer');
            return true;
        },

        // 选择目录（直接调用 Rust 命令，返回选择的路径）
        selectDirectory: async function() {
            if (!isTauri) {
                console.warn('[TauriAPI] 非 Tauri 环境');
                throw new Error('非 Tauri 环境');
            }

            try {
                // 直接调用 Rust 命令，blocking_pick_folder 在后台线程运行
                // 返回 Option<String>：Some(path) 或 None（取消）
                const path = await window.__TAURI__.core.invoke('pick_directory');
                if (path) {
                    console.log('[TauriAPI] 目录已选择:', path);
                    return { success: true, path: path, canceled: false };
                } else {
                    console.log('[TauriAPI] 目录选择已取消');
                    return { success: true, canceled: true };
                }
            } catch (e) {
                console.error('[TauriAPI] pick_directory 失败:', e);
                throw e;
            }
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

        // 获取后端实际端口
        getBackendPort: async function() {
            if (!isTauri) {
                return 18642; // 非 Tauri 环境返回默认端口
            }
            try {
                return await window.__TAURI__.core.invoke('get_backend_port');
            } catch (error) {
                console.error('[TauriAPI] 获取后端端口失败:', error);
                return 18642;
            }
        },

        // 后端状态事件监听
        backendEvents: {
            _listeners: {},
            _warnedUnavailable: false,
            _warnedListenFailures: {},

            /**
             * 监听后端事件
             * @param {string} eventName - 事件名: 'backend-status-changed' | 'backend-started' | 'backend-start-error'
             * @param {function} callback - 回调函数
             * @returns {function} 取消监听函数
             */
            listen: function(eventName, callback) {
                if (!isTauri) {
                    // 非 Tauri 环境下属于正常情况，静默降级避免刷屏
                    return () => {};
                }

                const eventApi = window.__TAURI__ && window.__TAURI__.event;
                if (!eventApi || typeof eventApi.listen !== 'function') {
                    if (!this._warnedUnavailable) {
                        // 只在 debug 时提示一次即可（否则会在浏览器/降级环境刷屏）
                        if (console && typeof console.debug === 'function') {
                            console.debug('[TauriAPI] 事件监听 API 不可用，已自动降级为轮询/直连方式');
                        }
                        this._warnedUnavailable = true;
                    }
                    return () => {};
                }

                let unlisten = null;
                const unlistenPromise = eventApi.listen(eventName, (event) => {
                    console.log(`[TauriAPI] 后端事件: ${eventName}`, event.payload);
                    callback(event.payload);
                }).catch((err) => {
                    // 某些运行时下会以 undefined reject，属于“事件不可用”而非真正异常
                    const errMsg = (err && err.message) ? err.message : '';
                    if (!this._warnedListenFailures[eventName]) {
                        // 降级是预期行为：改为 debug 一次，避免用户误以为是错误
                        if (console && typeof console.debug === 'function') {
                            if (errMsg) {
                                console.debug(`[TauriAPI] 事件监听不可用 (${eventName})，已自动降级:`, errMsg);
                            } else {
                                console.debug(`[TauriAPI] 事件监听不可用 (${eventName})，已自动降级`);
                            }
                        }
                        this._warnedListenFailures[eventName] = true;
                    }
                    return null;
                });

                // 支持后续取消监听（即便 listen 是异步返回）
                unlistenPromise.then((fn) => {
                    if (typeof fn === 'function') {
                        unlisten = fn;
                    }
                });

                return () => {
                    if (typeof unlisten === 'function') {
                        try {
                            unlisten();
                        } catch (e) {
                            console.warn('[TauriAPI] 取消事件监听失败:', e);
                        }
                    }
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
                    // 非 Tauri 环境静默跳过
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
