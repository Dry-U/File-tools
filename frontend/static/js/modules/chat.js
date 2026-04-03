/**
 * FileTools - 聊天模块
 * 提供聊天功能、会话管理、消息处理等功能
 */

const FileToolsChat = (function() {
    'use strict';

    // 当前会话 ID
    let currentSessionId = generateSessionId();

    // 待删除的会话 ID
    let sessionToDelete = null;

    // 加载状态消息
    let loadingMessages = {};

    /**
     * 生成新的会话 ID
     * @returns {string} 会话 ID
     */
    function generateSessionId() {
        // 使用 crypto.randomUUID() 如果可用（现代浏览器）
        // 否则降级使用时间戳+随机数
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return 'session_' + crypto.randomUUID();
        }
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 发送消息
     */
    async function sendMessage() {
        const input = document.getElementById('userInput');
        const text = input.value.trim();
        if (!text) return;

        // 切换 UI
        const welcomeContainer = document.getElementById('chat-welcome-container');
        const chatContainer = document.getElementById('chatContainer');
        const inputArea = document.getElementById('chat-input-area');

        welcomeContainer.style.display = 'none';
        chatContainer.style.display = 'flex';
        inputArea.style.background = 'linear-gradient(to top, var(--llama-bg) 60%, transparent)';

        // 添加用户消息
        addMessage(text, 'user');
        input.value = '';
        input.style.height = 'auto';

        // 添加 AI 加载消息
        const loadingId = addLoadingMessage();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: text,
                    session_id: currentSessionId
                })
            });

            const data = await response.json();
            removeLoadingMessage(loadingId);

            if (response.ok) {
                addMessage(data.answer || '没有收到回复', 'ai');
                // 刷新历史记录
                loadChatHistory();
            } else {
                addMessage('出错: ' + (data.detail || '未知错误'), 'ai');
            }
        } catch (error) {
            console.error('Chat error:', error);
            removeLoadingMessage(loadingId);
            addMessage('网络错误，请稍后重试', 'ai');
        }
    }

    /**
     * 添加消息到聊天区域
     * @param {string} text - 消息内容
     * @param {string} type - 消息类型: user 或 ai
     */
    function addMessage(text, type) {
        const container = document.getElementById('chatContainer');
        const div = document.createElement('div');
        div.className = 'message-row ' + type;
        const id = FileToolsUtils.generateMessageId('msg');
        div.id = id;

        const avatarClass = type === 'user' ? 'avatar-user' : 'avatar-ai';
        const avatarIcon = type === 'user'
            ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z"/></svg>'
            : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M6 12.796V3.204L11.481 8 6 12.796zm.659.753 5.48-4.796a1 1 0 0 0 0-1.506L6.66 2.451C6.011 1.885 5 2.345 5 3.204v9.592a1 1 0 0 0 1.659.753z"/></svg>';

        // 处理换行符
        const formattedText = FileToolsUtils.escapeHtml(text).replace(/\n/g, '<br>');
        const isMultiline = text.includes('\n');
        const multilineClass = isMultiline ? 'multiline' : '';

        div.innerHTML = `
            <div class="message-avatar ${avatarClass}">${avatarIcon}</div>
            <div class="message-content ${multilineClass}">
                <p>${formattedText}</p>
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return id;
    }

    /**
     * 添加加载消息
     * @returns {string} 加载消息 ID
     */
    function addLoadingMessage() {
        const container = document.getElementById('chatContainer');
        const div = document.createElement('div');
        div.className = 'message-row ai';
        const id = FileToolsUtils.generateMessageId('loading');
        div.id = id;

        div.innerHTML = `
            <div class="message-avatar avatar-ai">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M6 12.796V3.204L11.481 8 6 12.796zm.659.753 5.48-4.796a1 1 0 0 0 0-1.506L6.66 2.451C6.011 1.885 5 2.345 5 3.204v9.592a1 1 0 0 0 1.659.753z"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="loading-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        loadingMessages[id] = div;
        return id;
    }

    /**
     * 移除加载消息
     * @param {string} id - 加载消息 ID
     */
    function removeLoadingMessage(id) {
        const loadingEl = document.getElementById(id);
        if (loadingEl) {
            loadingEl.remove();
            delete loadingMessages[id];
        }
    }

    /**
     * 重置聊天
     */
    function resetChat() {
        const welcomeContainer = document.getElementById('chat-welcome-container');
        const chatContainer = document.getElementById('chatContainer');
        const inputArea = document.getElementById('chat-input-area');

        welcomeContainer.style.display = 'flex';
        chatContainer.style.display = 'none';
        inputArea.style.background = 'transparent';

        // 清除消息
        const messages = document.querySelectorAll('.message-row');
        messages.forEach(msg => msg.remove());

        // 生成新会话 ID
        currentSessionId = generateSessionId();

        // 重新加载历史记录
        loadChatHistory();
    }

    /**
     * 重置聊天 UI（不清除会话 ID）
     */
    function resetChatUI() {
        const welcomeContainer = document.getElementById('chat-welcome-container');
        const chatContainer = document.getElementById('chatContainer');
        const inputArea = document.getElementById('chat-input-area');

        welcomeContainer.style.display = 'flex';
        chatContainer.style.display = 'none';
        inputArea.style.background = 'transparent';

        // 清除消息
        const messages = document.querySelectorAll('.message-row');
        messages.forEach(msg => msg.remove());
    }

    /**
     * 加载历史会话列表
     */
    async function loadChatHistory() {
        try {
            const response = await fetch('/api/sessions');
            const data = await response.json();
            const sessions = data.sessions || [];
            renderHistoryList(sessions);
        } catch (error) {
            console.error('加载历史记录失败:', error);
        }
    }

    /**
     * 渲染历史记录列表
     * @param {Array} sessions - 会话数组
     */
    function renderHistoryList(sessions) {
        const historyList = document.getElementById('historyList');
        if (!historyList) return;

        if (sessions.length === 0) {
            historyList.innerHTML = `
                <div class="text-muted small text-center py-3">
                    <i class="bi bi-inbox me-1"></i>暂无历史记录
                </div>
            `;
            return;
        }

        historyList.innerHTML = sessions.map(session => {
            const sessionIdAttr = FileToolsUtils.escapeHtml(session.session_id);
            const isActive = session.session_id === currentSessionId ? 'active' : '';
            return `
                <div class="history-item ${isActive}"
                     data-session-id="${sessionIdAttr}"
                     role="listitem">
                    <i class="bi bi-chat-left-text history-item-icon"></i>
                    <div class="history-item-content">
                        <div class="history-item-title">${FileToolsUtils.escapeHtml(session.title)}</div>
                        <div class="history-item-meta">${FileToolsUtils.formatDate(session.created_at)} · ${session.message_count}条消息</div>
                    </div>
                    <button class="history-item-delete"
                            data-session-id="${sessionIdAttr}"
                            title="删除会话">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
        }).join('');
    }

    /**
     * 切换到指定会话
     * @param {string} sessionId - 会话 ID
     */
    async function switchToSession(sessionId) {
        if (!sessionId) {
            console.error('switchToSession: sessionId is empty');
            return;
        }

        currentSessionId = sessionId;
        localStorage.setItem('chat_session_id', sessionId);

        resetChatUI();
        await loadSessionMessages(sessionId);
        loadChatHistory();
    }

    /**
     * 加载指定会话的消息
     * @param {string} sessionId - 会话 ID
     * @returns {boolean} 是否成功
     */
    async function loadSessionMessages(sessionId) {
        try {
            if (!sessionId) {
                console.error('loadSessionMessages: sessionId is empty');
                return false;
            }

            const response = await fetch(`/api/sessions/${sessionId}/messages`);
            if (!response.ok) {
                console.error(`加载会话消息失败: HTTP ${response.status}`);
                return false;
            }

            const data = await response.json();
            const messages = data.messages || [];

            const welcomeContainer = document.getElementById('chat-welcome-container');
            const chatContainer = document.getElementById('chatContainer');
            const inputArea = document.getElementById('chat-input-area');

            welcomeContainer.style.display = 'none';
            chatContainer.style.display = 'flex';
            inputArea.style.background = 'linear-gradient(to top, var(--llama-bg) 60%, transparent)';

            messages.forEach(msg => {
                if (msg.role === 'user') {
                    addMessage(msg.content, 'user');
                } else if (msg.role === 'assistant') {
                    addMessage(msg.content, 'ai');
                }
            });

            chatContainer.scrollTop = chatContainer.scrollHeight;
            return true;
        } catch (error) {
            console.error('加载会话消息失败:', error);
            return false;
        }
    }

    /**
     * 删除会话
     * @param {string} sessionId - 会话 ID
     * @param {Event} event - 事件对象
     */
    function deleteSession(sessionId, event) {
        event.stopPropagation();

        if (!sessionId) return;

        sessionToDelete = sessionId;

        const modalEl = document.getElementById('deleteSessionModal');
        if (modalEl) {
            FileToolsUtils.showModal(modalEl);
        } else {
            if (confirm('确定要删除这个会话吗？')) {
                executeDeleteSession(sessionId);
            }
        }
    }

    /**
     * 执行删除会话
     * @param {string} sessionId - 会话 ID
     */
    async function executeDeleteSession(sessionId) {
        if (!sessionId) sessionId = sessionToDelete;
        if (!sessionId) return;

        try {
            const response = await fetch(`/api/sessions/${sessionId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                if (sessionId === currentSessionId) {
                    currentSessionId = generateSessionId();
                    resetChatUI();
                }
                loadChatHistory();
            } else {
                console.error('删除会话失败');
                FileToolsUtils.showToast('删除会话失败', 'error');
            }
        } catch (error) {
            console.error('删除会话错误:', error);
            FileToolsUtils.showToast('删除会话错误: ' + error.message, 'error');
        } finally {
            sessionToDelete = null;
        }
    }

    /**
     * 填充输入框
     * @param {string} text - 要填充的文本
     */
    function fillInput(text) {
        const input = document.getElementById('userInput');
        input.value = text;
        input.focus();
    }

    /**
     * 获取当前会话 ID
     * @returns {string} 当前会话 ID
     */
    function getCurrentSessionId() {
        return currentSessionId;
    }

    /**
     * 设置当前会话 ID
     * @param {string} sessionId - 会话 ID
     */
    function setCurrentSessionId(sessionId) {
        currentSessionId = sessionId;
    }

    /**
     * 初始化聊天模块事件监听
     */
    function init() {
        const userInput = document.getElementById('userInput');

        if (userInput) {
            userInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }

        // 绑定删除确认按钮事件
        const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
        if (confirmDeleteBtn) {
            confirmDeleteBtn.addEventListener('click', function() {
                if (sessionToDelete) {
                    executeDeleteSession(sessionToDelete);
                    const modalEl = document.getElementById('deleteSessionModal');
                    if (modalEl) {
                        FileToolsUtils.hideModal(modalEl);
                    }
                }
            });
        }

        // 为所有关闭按钮添加事件
        document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', function() {
                const modalEl = this.closest('.modal');
                if (modalEl) {
                    FileToolsUtils.hideModal(modalEl);
                }
            });
        });
    }

    // 公共 API
    return {
        sendMessage,
        addMessage,
        resetChat,
        resetChatUI,
        loadChatHistory,
        switchToSession,
        deleteSession,
        executeDeleteSession,
        fillInput,
        getCurrentSessionId,
        setCurrentSessionId,
        init
    };
})();

// 全局暴露函数（向后兼容）
const sendMessage = FileToolsChat.sendMessage;
const addMessage = FileToolsChat.addMessage;
const resetChat = FileToolsChat.resetChat;
const resetChatUI = FileToolsChat.resetChatUI;
const loadChatHistory = FileToolsChat.loadChatHistory;
const switchToSession = FileToolsChat.switchToSession;
const deleteSession = FileToolsChat.deleteSession;
const executeDeleteSession = FileToolsChat.executeDeleteSession;
const fillInput = FileToolsChat.fillInput;
const getCurrentSessionId = FileToolsChat.getCurrentSessionId;
const setCurrentSessionId = FileToolsChat.setCurrentSessionId;
const init = FileToolsChat.init;