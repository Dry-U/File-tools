/**
 * FileTools - 事件绑定模块
 * 将所有内联事件处理器替换为JavaScript事件监听器
 * 解决CSP（内容安全策略）问题
 */

const FileToolsEventBindings = (function() {
    'use strict';

    let isBound = false;
    let isInitialized = false;

    /**
     * 绑定所有事件监听器
     */
    function bindAllEvents() {
        if (isBound) return;
        isBound = true;
        console.log('Binding event listeners...');

        // 1. 文件类型切换按钮
        document.querySelectorAll('.file-type-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                if (typeof toggleFileType === 'function') {
                    toggleFileType(this);
                }
            });
        });

        // 2. 重建索引按钮
        const rebuildBtn = document.querySelector('.rebuild-btn');
        if (rebuildBtn) {
            rebuildBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('Rebuild button clicked');
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.showRebuildModal) {
                    FileToolsSettings.showRebuildModal();
                } else if (typeof showRebuildModal === 'function') {
                    showRebuildModal();
                } else {
                    console.error('showRebuildModal function not found');
                }
            });
        }

        // 3. 新建对话按钮
        const newChatBtn = document.querySelector('.new-chat-btn');
        if (newChatBtn) {
            newChatBtn.addEventListener('click', function() {
                if (typeof resetChat === 'function') {
                    resetChat();
                }
            });
        }

        // 4. 侧边栏切换按钮
        const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
        if (sidebarToggleBtn) {
            sidebarToggleBtn.addEventListener('click', function() {
                if (typeof toggleSidebar === 'function') {
                    toggleSidebar();
                }
            });
        }

        // 5. 模式切换标签
        const tabSearch = document.getElementById('tab-search');
        const tabChat = document.getElementById('tab-chat');

        function handleTabKeyboard(event) {
            const tabs = [tabSearch, tabChat].filter(t => t);
            const currentIndex = tabs.findIndex(t => t === document.activeElement);

            if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                event.preventDefault();
                let nextIndex;
                if (event.key === 'ArrowRight') {
                    nextIndex = (currentIndex + 1) % tabs.length;
                } else {
                    nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                }
                tabs[nextIndex].focus();
            } else if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                if (typeof switchMode === 'function') {
                    const mode = tabs[currentIndex] === tabSearch ? 'search' : 'chat';
                    switchMode(mode);
                }
            } else if (event.key === 'Home') {
                event.preventDefault();
                tabs[0].focus();
            } else if (event.key === 'End') {
                event.preventDefault();
                tabs[tabs.length - 1].focus();
            }
        }

        if (tabSearch) {
            tabSearch.addEventListener('click', function() {
                if (typeof switchMode === 'function') {
                    switchMode('search');
                }
            });
            tabSearch.addEventListener('keydown', handleTabKeyboard);
        }
        if (tabChat) {
            tabChat.addEventListener('click', function() {
                if (typeof switchMode === 'function') {
                    switchMode('chat');
                }
            });
            tabChat.addEventListener('keydown', handleTabKeyboard);
        }

        // 6. 设置按钮
        const settingsBtn = document.querySelector('.settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', function() {
                if (typeof openSettingsModal === 'function') {
                    openSettingsModal();
                }
            });
        }

        // 6.5 历史记录列表事件委托
        const historyList = document.getElementById('historyList');
        if (historyList) {
            historyList.addEventListener('click', function(e) {
                const deleteBtn = e.target.closest('.history-item-delete');
                if (deleteBtn) {
                    e.stopPropagation();
                    const sessionId = deleteBtn.dataset.sessionId;
                    if (sessionId && typeof FileToolsChat !== 'undefined' && FileToolsChat.deleteSession) {
                        FileToolsChat.deleteSession(sessionId, e);
                    }
                    return;
                }
                
                // 点击历史记录项切换会话
                const historyItem = e.target.closest('.history-item');
                if (historyItem && !e.target.closest('.history-item-delete')) {
                    const sessionId = historyItem.dataset.sessionId;
                    if (sessionId && typeof FileToolsChat !== 'undefined' && FileToolsChat.switchToSession) {
                        FileToolsChat.switchToSession(sessionId);
                    }
                }
            });
        }

        // 7. 搜索按钮
        const searchBtn = document.querySelector('.search-btn');
        if (searchBtn) {
            searchBtn.addEventListener('click', function() {
                if (typeof performSearch === 'function') {
                    performSearch();
                }
            });
        }

        // 8. 发送消息按钮
        const sendBtn = document.querySelector('.chat-send-btn');
        if (sendBtn) {
            sendBtn.addEventListener('click', function() {
                if (typeof sendMessage === 'function') {
                    sendMessage();
                }
            });
        }

        // 9. 设置模态框中的按钮
        // 测试连接按钮
        const testConnBtn = document.getElementById('testConnectionBtn');
        if (testConnBtn) {
            testConnBtn.onclick = null;
            testConnBtn.addEventListener('click', function() {
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.testAPIConnection) {
                    FileToolsSettings.testAPIConnection();
                } else if (typeof testAPIConnection === 'function') {
                    testAPIConnection();
                }
            });
        }

        // 添加目录按钮
        const addDirBtn = document.getElementById('addDirectoryBtn');
        if (addDirBtn) {
            addDirBtn.onclick = null;
            addDirBtn.addEventListener('click', function() {
                if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.browseAndAddDirectory) {
                    FileToolsDirectory.browseAndAddDirectory();
                } else if (typeof browseAndAddDirectory === 'function') {
                    browseAndAddDirectory();
                }
            });
        }

        // 目录删除按钮事件委托
        document.querySelectorAll('.directory-list').forEach(list => {
            list.addEventListener('click', function(e) {
                const deleteBtn = e.target.closest('.directory-delete');
                if (deleteBtn) {
                    e.stopPropagation();
                    const path = deleteBtn.dataset.path;
                    if (path && typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.removeDirectory) {
                        FileToolsDirectory.removeDirectory(path);
                    }
                }
            });
        });

        // GitHub按钮
        const githubBtn = document.getElementById('githubBtn');
        if (githubBtn) {
            githubBtn.onclick = null;
            githubBtn.addEventListener('click', function(event) {
                if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.openExternalLink) {
                    FileToolsUtils.openExternalLink('https://github.com/Dry-U/File-tools', event);
                } else if (typeof openExternalLink === 'function') {
                    openExternalLink('https://github.com/Dry-U/File-tools', event);
                }
            });
        }

        // Report Issue按钮
        const issueBtn = document.getElementById('issueBtn');
        if (issueBtn) {
            issueBtn.onclick = null;
            issueBtn.addEventListener('click', function(event) {
                if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.openExternalLink) {
                    FileToolsUtils.openExternalLink('https://github.com/Dry-U/File-tools/issues', event);
                } else if (typeof openExternalLink === 'function') {
                    openExternalLink('https://github.com/Dry-U/File-tools/issues', event);
                }
            });
        }

        // 恢复默认按钮
        const resetSettingsBtn = document.getElementById('resetSettingsBtn');
        if (resetSettingsBtn) {
            resetSettingsBtn.onclick = null;
            resetSettingsBtn.addEventListener('click', function() {
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.resetSettings) {
                    FileToolsSettings.resetSettings();
                } else if (typeof resetSettings === 'function') {
                    resetSettings();
                }
            });
        }

        // 保存设置按钮
        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        if (saveSettingsBtn) {
            saveSettingsBtn.onclick = null;
            saveSettingsBtn.addEventListener('click', function() {
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.saveSettings) {
                    FileToolsSettings.saveSettings();
                } else if (typeof saveSettings === 'function') {
                    saveSettings();
                }
            });
        }


        // 注意：重建索引确认按钮 (rebuildConfirmBtn) 是动态创建的
        // 它的事件绑定在 FileToolsSettings.showRebuildModal() 函数中完成
        // 不需要在这里绑定

        // 确认重置按钮
        const confirmResetBtn = document.getElementById('confirmResetBtn');
        if (confirmResetBtn) {
            confirmResetBtn.onclick = null;
            confirmResetBtn.addEventListener('click', function() {
                // 直接调用全局函数，避免 FileToolsSettings 命名空间可能未初始化的问题
                if (typeof confirmReset === 'function') {
                    confirmReset();
                } else if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.confirmReset) {
                    FileToolsSettings.confirmReset();
                }
            });
        }

        // 确认删除目录按钮
        const confirmDirectoryDeleteBtn = document.getElementById('confirmDirectoryDeleteBtn');
        if (confirmDirectoryDeleteBtn) {
            confirmDirectoryDeleteBtn.onclick = null;
            confirmDirectoryDeleteBtn.addEventListener('click', function() {
                if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.doDeleteDirectory && FileToolsDirectory.pendingDeletePath) {
                    FileToolsDirectory.doDeleteDirectory(FileToolsDirectory.pendingDeletePath);
                } else if (typeof doDeleteDirectory === 'function' && typeof pendingDeletePath !== 'undefined') {
                    doDeleteDirectory(pendingDeletePath);
                }
            });
        }

        // 确认添加目录按钮（在添加目录模态框中）
        const confirmAddDirectoryBtn = document.getElementById('confirmAddDirectoryBtn');
        if (confirmAddDirectoryBtn) {
            confirmAddDirectoryBtn.onclick = null;
            confirmAddDirectoryBtn.addEventListener('click', async function() {
                const inputEl = document.getElementById('addDirectoryPathInput');
                if (inputEl) {
                    const path = inputEl.value.trim();
                    if (!path) {
                        if (typeof FileToolsUtils !== 'undefined' && FileToolsUtils.showToast) {
                            FileToolsUtils.showToast('请输入目录路径', 'warning');
                        }
                        return;
                    }
                    // 隐藏模态框并调用添加目录函数
                    const modalEl = document.getElementById('addDirectoryModal');
                    if (modalEl && typeof FileToolsUtils !== 'undefined' && FileToolsUtils.hideModal) {
                        FileToolsUtils.hideModal(modalEl);
                    }
                    if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.addDirectoryByPath) {
                        await FileToolsDirectory.addDirectoryByPath(path);
                    } else if (typeof addDirectoryByPath === 'function') {
                        await addDirectoryByPath(path);
                    }
                }
            });
        }

        // 添加目录后重建确认弹窗的确定按钮
        const confirmAddDirRebuildBtn = document.getElementById('confirmAddDirRebuildBtn');
        if (confirmAddDirRebuildBtn) {
            confirmAddDirRebuildBtn.onclick = null;
            confirmAddDirRebuildBtn.addEventListener('click', function() {
                // 隐藏 addDirRebuildModal
                const modalEl = document.getElementById('addDirRebuildModal');
                if (modalEl && typeof FileToolsUtils !== 'undefined' && FileToolsUtils.hideModal) {
                    FileToolsUtils.hideModal(modalEl);
                }
                // 显示重建索引弹窗
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.showRebuildModal) {
                    FileToolsSettings.showRebuildModal();
                } else if (typeof showRebuildModal === 'function') {
                    showRebuildModal();
                }
            });
        }

        // 浏览目录按钮（在添加目录模态框中）
        const browseDirectoryBtn = document.getElementById('browseDirectoryBtn');
        if (browseDirectoryBtn) {
            browseDirectoryBtn.onclick = null;
            browseDirectoryBtn.addEventListener('click', async function() {
                if (window.TauriAPI) {
                    try {
                        const result = await window.TauriAPI.selectDirectory();
                        if (!result.canceled && result.success && result.path) {
                            const inputEl = document.getElementById('addDirectoryPathInput');
                            if (inputEl) {
                                inputEl.value = result.path;
                            }
                        }
                    } catch (e) {
                        console.warn('Tauri browse failed:', e);
                    }
                }
            });
        }

        // 初始化删除目录模态框事件
        if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.initDeleteModalEvents) {
            FileToolsDirectory.initDeleteModalEvents();
        } else if (typeof initDeleteModalEvents === 'function') {
            initDeleteModalEvents();
        }

        // 移除所有剩余的onclick属性（备用方案）
        document.querySelectorAll('[onclick]').forEach(element => {
            element.onclick = null;
        });

        // 移除所有剩余的oninput属性（备用方案）
        document.querySelectorAll('[oninput]').forEach(element => {
            element.oninput = null;
        });

        // 10. 自动调整输入框高度
        const textarea = document.getElementById('userInput');
        if (textarea) {
            textarea.oninput = null;
            textarea.addEventListener('input', function() {
                if (typeof autoResize === 'function') {
                    autoResize(this);
                }
            });
        }

        // 11. API Key 显示/隐藏按钮
        const toggleApiKeyBtn = document.getElementById('toggleApiKeyBtn');
        if (toggleApiKeyBtn) {
            toggleApiKeyBtn.addEventListener('click', function() {
                const apiKeyInput = document.getElementById('apiKeyInput');
                const icon = this.querySelector('i');
                if (apiKeyInput) {
                    if (apiKeyInput.type === 'password') {
                        apiKeyInput.type = 'text';
                        icon.className = 'bi bi-eye-slash';
                    } else {
                        apiKeyInput.type = 'password';
                        icon.className = 'bi bi-eye';
                    }
                }
            });
        }

        // 12. 绑定滑块输入事件
        const sliderIds = ['tempRange', 'topPRange', 'topKRange', 'minPRange', 'repeatPenaltyRange', 'freqPenaltyRange', 'presencePenaltyRange'];
        sliderIds.forEach(sliderId => {
            const slider = document.getElementById(sliderId);
            if (slider) {
                slider.oninput = null;
                const valueElementId = sliderId.replace('Range', 'Value');
                slider.addEventListener('input', function() {
                    const valueElement = document.getElementById(valueElementId);
                    if (valueElement) {
                        valueElement.innerText = this.value;
                    }
                });
            }
        });

        console.log('All event listeners bound successfully');
    }

    /**
     * 移除所有内联事件处理器
     */
    function removeInlineEventHandlers() {
        // 移除所有onclick属性
        document.querySelectorAll('[onclick]').forEach(element => {
            element.onclick = null;
        });

        // 移除所有oninput属性
        document.querySelectorAll('[oninput]').forEach(element => {
            element.oninput = null;
        });

        // 移除所有onerror属性（从script标签）
        document.querySelectorAll('script[onerror]').forEach(script => {
            script.onerror = null;
        });

        console.log('Inline event handlers removed');
    }

    /**
     * 初始化事件绑定模块
     */
    function init() {
        if (isInitialized) return;
        isInitialized = true;
        removeInlineEventHandlers();
        bindAllEvents();
    }

    // 公共API
    return {
        init,
        bindAllEvents,
        removeInlineEventHandlers
    };
})();

// 全局暴露函数
const initEventBindings = FileToolsEventBindings.init;
const bindAllEvents = FileToolsEventBindings.bindAllEvents;
const removeInlineEventHandlers = FileToolsEventBindings.removeInlineEventHandlers;