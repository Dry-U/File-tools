// 监听模式切换，显示/隐藏对应设置面板
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

// API提供商变更时自动填充默认URL
function onProviderChange() {
    const provider = document.getElementById('apiProviderSelect').value;
    const urlInput = document.getElementById('apiUrlInput');
    const modelInput = document.getElementById('modelNameInput');

    const defaults = {
        'siliconflow': {
            url: 'https://api.siliconflow.cn/v1/chat/completions',
            model: 'deepseek-ai/DeepSeek-V2.5'
        },
        'deepseek': {
            url: 'https://api.deepseek.com/v1/chat/completions',
            model: 'deepseek-chat'
        },
        'custom': {
            url: '',
            model: ''
        }
    };

    if (defaults[provider]) {
        urlInput.value = defaults[provider].url;
        modelInput.value = defaults[provider].model;
    }
}

// 测试API连接
async function testAPIConnection() {
    const btn = document.querySelector('button[onclick="testAPIConnection()"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i>测试中...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/model/test');
        const result = await response.json();

        if (result.status === 'ok') {
            alert(`连接成功！\n模式: ${result.mode}\n模型: ${result.model}`);
        } else {
            alert(`连接失败: ${result.error || '未知错误'}`);
        }
    } catch (error) {
        alert(`测试出错: ${error.message}`);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// 恢复默认设置 (显示弹窗)
function resetSettings() {
    const resetModalEl = document.getElementById('resetConfirmModal');
    const resetModal = new bootstrap.Modal(resetModalEl);
    resetModalEl.addEventListener('hidden.bs.modal', function disposeModal() {
        resetModal.dispose();
        resetModalEl.removeEventListener('hidden.bs.modal', disposeModal);
    });
    resetModal.show();
}

// 显示重建索引确认弹窗
function showRebuildModal() {
    const rebuildModalEl = document.getElementById('rebuildIndexModal');

    // Reset Modal State
    document.getElementById('rebuildModalBody').innerHTML = `
        <p class="mb-0 small">确定要重建文件索引吗？<br>这可能需要一些时间。</p>
    `;
    document.getElementById('rebuildModalFooter').innerHTML = `
        <button type="button" class="btn btn-sm btn-outline-secondary border-0" data-bs-dismiss="modal">取消</button>
        <button type="button" class="btn btn-sm btn-primary px-3" onclick="confirmRebuild()">确定</button>
    `;
    document.getElementById('rebuildCloseBtn').style.display = 'block';

    const rebuildModal = new bootstrap.Modal(rebuildModalEl);
    rebuildModalEl.addEventListener('hidden.bs.modal', function disposeModal() {
        rebuildModal.dispose();
        rebuildModalEl.removeEventListener('hidden.bs.modal', disposeModal);
    });
    rebuildModal.show();
}

// 确认重建索引 (执行逻辑)
async function confirmRebuild() {
    // Update UI to loading state
    const modalBody = document.getElementById('rebuildModalBody');
    const modalFooter = document.getElementById('rebuildModalFooter');
    const closeBtn = document.getElementById('rebuildCloseBtn');

    closeBtn.style.display = 'none'; // Prevent closing
    modalFooter.style.display = 'none'; // Hide buttons
    
    modalBody.innerHTML = `
        <div class="spinner-border text-primary mb-3" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <p class="mb-0 small text-muted">正在重建索引，请稍候...</p>
    `;

    try {
        const response = await fetch('/api/rebuild-index', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
            modalBody.innerHTML = `
                <i class="bi bi-check-circle-fill text-success display-4 mb-3"></i>
                <p class="mb-0 small">索引重建完成</p>
                <p class="small text-muted mt-1">扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}</p>
            `;
        } else {
            throw new Error(data.detail || '未知错误');
        }
    } catch (error) {
        console.error('Error rebuilding index:', error);
        modalBody.innerHTML = `
            <i class="bi bi-x-circle-fill text-danger display-4 mb-3"></i>
            <p class="mb-0 small">索引重建失败</p>
            <p class="small text-muted mt-1">${error.message || '请求失败'}</p>
        `;
    } finally {
        // Restore close capability
        closeBtn.style.display = 'block';
        modalFooter.style.display = 'flex';
        modalFooter.innerHTML = `
            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
        `;
    }
}

// 确认重置 (执行逻辑)
function confirmReset() {
    // Sampling
    document.getElementById('tempRange').value = 0.7;
    document.getElementById('tempValue').innerText = '0.7';
    
    document.getElementById('topPRange').value = 0.9;
    document.getElementById('topPValue').innerText = '0.9';
    
    document.getElementById('topKInput').value = 40;
    
    document.getElementById('minPRange').value = 0.05;
    document.getElementById('minPValue').innerText = '0.05';
    
    document.getElementById('maxTokensInput').value = 2048;
    document.getElementById('seedInput').value = -1;

    // Penalty
    document.getElementById('repeatPenaltyRange').value = 1.1;
    document.getElementById('repeatPenaltyValue').innerText = '1.1';
    
    document.getElementById('freqPenaltyRange').value = 0.0;
    document.getElementById('freqPenaltyValue').innerText = '0.0';

    document.getElementById('presencePenaltyRange').value = 0.0;
    document.getElementById('presencePenaltyValue').innerText = '0.0';

    // 关闭确认弹窗
    const resetModalEl = document.getElementById('resetConfirmModal');
    const modal = bootstrap.Modal.getInstance(resetModalEl);
    modal.hide();
}

// Settings State Management
let initialSettings = {};

// Load settings from backend when modal opens
async function loadSettings() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            if (config.ai_model) {
                // 设置模式
                const isApiMode = config.ai_model.mode === 'api';
                document.getElementById('modeAPI').checked = isApiMode;
                document.getElementById('modeLocal').checked = !isApiMode;
                document.getElementById('localSettings').style.display = isApiMode ? 'none' : 'block';
                document.getElementById('apiSettings').style.display = isApiMode ? 'block' : 'none';

                // 本地模式配置
                if (config.ai_model.local) {
                    document.getElementById('localUrlInput').value = config.ai_model.local.api_url ?? 'http://localhost:8000/v1/chat/completions';
                }

                // API模式配置
                if (config.ai_model.api) {
                    document.getElementById('apiProviderSelect').value = config.ai_model.api.provider ?? 'siliconflow';
                    document.getElementById('apiUrlInput').value = config.ai_model.api.api_url ?? '';
                    document.getElementById('apiKeyInput').value = config.ai_model.api.api_key ?? '';
                    document.getElementById('modelNameInput').value = config.ai_model.api.model_name ?? '';
                }

                // 安全配置
                if (config.ai_model.security) {
                    document.getElementById('verifySslCheck').checked = config.ai_model.security.verify_ssl ?? true;
                }

                // 采样参数
                if (config.ai_model.sampling) {
                    document.getElementById('tempRange').value = config.ai_model.sampling.temperature ?? 0.7;
                    document.getElementById('tempValue').innerText = config.ai_model.sampling.temperature ?? 0.7;
                    document.getElementById('topPRange').value = config.ai_model.sampling.top_p ?? 0.9;
                    document.getElementById('topPValue').innerText = config.ai_model.sampling.top_p ?? 0.9;
                    document.getElementById('topKInput').value = config.ai_model.sampling.top_k ?? 40;
                    document.getElementById('minPRange').value = config.ai_model.sampling.min_p ?? 0.05;
                    document.getElementById('minPValue').innerText = config.ai_model.sampling.min_p ?? 0.05;
                    document.getElementById('maxTokensInput').value = config.ai_model.sampling.max_tokens ?? 2048;
                    document.getElementById('seedInput').value = config.ai_model.sampling.seed ?? -1;
                }

                // 惩罚参数
                if (config.ai_model.penalties) {
                    document.getElementById('repeatPenaltyRange').value = config.ai_model.penalties.repeat_penalty ?? 1.1;
                    document.getElementById('repeatPenaltyValue').innerText = config.ai_model.penalties.repeat_penalty ?? 1.1;
                    document.getElementById('freqPenaltyRange').value = config.ai_model.penalties.frequency_penalty ?? 0.0;
                    document.getElementById('freqPenaltyValue').innerText = config.ai_model.penalties.frequency_penalty ?? 0.0;
                    document.getElementById('presencePenaltyRange').value = config.ai_model.penalties.presence_penalty ?? 0.0;
                    document.getElementById('presencePenaltyValue').innerText = config.ai_model.penalties.presence_penalty ?? 0.0;
                }
            }
        }
    } catch (error) {
        console.error('Load settings error:', error);
    }
}

function getCurrentSettings() {
    const isApiMode = document.getElementById('modeAPI').checked;
    return {
        mode: isApiMode ? 'api' : 'local',
        // 本地模式配置
        localUrl: document.getElementById('localUrlInput').value,
        // API模式配置
        apiProvider: document.getElementById('apiProviderSelect').value,
        apiUrl: document.getElementById('apiUrlInput').value,
        apiKey: document.getElementById('apiKeyInput').value,
        modelName: document.getElementById('modelNameInput').value,
        // 安全配置
        verifySsl: document.getElementById('verifySslCheck').checked,
        // 采样参数
        sampling: {
            temperature: parseFloat(document.getElementById('tempRange').value),
            top_p: parseFloat(document.getElementById('topPRange').value),
            top_k: parseInt(document.getElementById('topKInput').value),
            min_p: parseFloat(document.getElementById('minPRange').value),
            max_tokens: parseInt(document.getElementById('maxTokensInput').value),
            seed: parseInt(document.getElementById('seedInput').value)
        },
        // 惩罚参数
        penalties: {
            repeat_penalty: parseFloat(document.getElementById('repeatPenaltyRange').value),
            frequency_penalty: parseFloat(document.getElementById('freqPenaltyRange').value),
            presence_penalty: parseFloat(document.getElementById('presencePenaltyRange').value)
        }
    };
}

// Capture settings when modal opens
const settingsModalEl = document.getElementById('settingsModal');
settingsModalEl.addEventListener('show.bs.modal', async event => {
    await loadSettings();
    initialSettings = getCurrentSettings();
});

async function saveSettings() {
    const currentSettings = getCurrentSettings();
    if (JSON.stringify(initialSettings) === JSON.stringify(currentSettings)) {
        // Show reminder
        const noChangeModalEl = document.getElementById('noChangesModal');
        const noChangeModal = new bootstrap.Modal(noChangeModalEl);
        noChangeModalEl.addEventListener('hidden.bs.modal', function disposeModal() {
            noChangeModal.dispose();
            noChangeModalEl.removeEventListener('hidden.bs.modal', disposeModal);
        });
        noChangeModal.show();
        return;
    }

    // Prepare config data for backend - 使用嵌套对象结构
    const configData = {
        ai_model: {
            mode: currentSettings.mode,
            local: {
                api_url: currentSettings.localUrl
            },
            api: {
                provider: currentSettings.apiProvider,
                api_url: currentSettings.apiUrl,
                api_key: currentSettings.apiKey,
                model_name: currentSettings.modelName
            },
            security: {
                verify_ssl: currentSettings.verifySsl,
                timeout: 120,
                retry_count: 2
            },
            // 采样和惩罚参数
            sampling: currentSettings.sampling,
            penalties: currentSettings.penalties
        },
        rag: {
            max_history_turns: 3,
            max_history_chars: 1000
        }
    };

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(configData)
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            // Update initial settings to current after successful save
            initialSettings = currentSettings;
            // Close modal
            const modal = bootstrap.Modal.getInstance(settingsModalEl);
            modal.hide();
            // Show success message (optional)
            showToast('设置已保存');
        } else {
            throw new Error(data.detail || '保存失败');
        }
    } catch (error) {
        console.error('Save settings error:', error);
        showToast('保存失败: ' + error.message, 'error');
    }
}

// Toast notification helper
function showToast(message, type = 'success') {
    const iconMap = {
        'success': 'bi-check-circle-fill',
        'error': 'bi-x-circle-fill',
        'warning': 'bi-exclamation-triangle-fill',
        'info': 'bi-info-circle-fill'
    };

    const bgMap = {
        'success': 'bg-success',
        'error': 'bg-danger',
        'warning': 'bg-warning text-dark',
        'info': 'bg-info text-dark'
    };
    // Create toast element
    const toastEl = document.createElement('div');
    const bgClass = bgMap[type] || 'bg-success';
    const iconClass = iconMap[type] || 'bi-check-circle-fill';
    const isDark = type === 'success' || type === 'error';
    const btnCloseClass = isDark ? 'btn-close-white' : '';

    toastEl.className = `toast align-items-center text-white ${bgClass} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body d-flex align-items-center">
                <i class="bi ${iconClass} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close ${btnCloseClass} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    // Add to container
    let toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }

    toastContainer.appendChild(toastEl);

    // Initialize and show toast
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();

    // Remove from DOM after hidden
    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

// 状态管理
let currentMode = 'search'; // 'search' or 'chat'

// 会话管理
let currentSessionId = localStorage.getItem('chat_session_id') || generateSessionId();

// 生成会话ID
function generateSessionId() {
    const newId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('chat_session_id', newId);
    return newId;
}

// 格式化日期
function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diff = now - date;

    // 小于1小时显示"X分钟前"
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return minutes < 1 ? '刚刚' : `${minutes}分钟前`;
    }
    // 小于24小时显示"X小时前"
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours}小时前`;
    }
    // 否则显示日期
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

// 模式切换逻辑
function switchMode(mode) {
    currentMode = mode;
    
    // 1. 更新 Tab 样式
    document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`tab-${mode}`).classList.add('active');

    // 2. 切换侧边栏内容
    const searchSidebar = document.getElementById('sidebar-search-content');
    const chatSidebar = document.getElementById('sidebar-chat-content');
    
    if (mode === 'search') {
        searchSidebar.style.display = 'block';
        chatSidebar.style.display = 'none';
    } else {
        searchSidebar.style.display = 'none';
        chatSidebar.style.display = 'block';
    }

    // 3. 切换主视图
    const searchView = document.getElementById('view-search');
    const chatView = document.getElementById('view-chat');

    if (mode === 'search') {
        searchView.style.setProperty('display', 'flex', 'important');
        chatView.style.setProperty('display', 'none', 'important');
    } else {
        searchView.style.setProperty('display', 'none', 'important');
        chatView.style.setProperty('display', 'flex', 'important');
    }
}

// 文件类型切换
function toggleFileType(btn) {
    btn.classList.toggle('active');
}

// 侧边栏切换逻辑
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const btn = document.getElementById('sidebarToggleBtn');
    const isMobile = window.innerWidth <= 768;

    if (isMobile) {
        sidebar.classList.toggle('show');
    } else {
        sidebar.classList.toggle('collapsed');
    }

    // 更新图标
    const isVisible = isMobile ? sidebar.classList.contains('show') : !sidebar.classList.contains('collapsed');

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

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

function fillInput(text) {
    const input = document.getElementById('userInput');
    input.value = text;
    input.focus();
}

function resetChat() {
    // Reset UI state
    const welcomeContainer = document.getElementById('chat-welcome-container');
    const chatContainer = document.getElementById('chatContainer');
    const inputArea = document.getElementById('chat-input-area');

    welcomeContainer.style.display = 'flex';
    chatContainer.style.display = 'none';
    inputArea.style.background = 'transparent';

    // Clear messages
    const messages = document.querySelectorAll('.message-row');
    messages.forEach(msg => msg.remove());

    // Generate new session ID
    currentSessionId = generateSessionId();

    // Reload history list
    loadChatHistory();
}

// 加载历史会话列表
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

// 渲染历史记录列表
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
        const sessionIdAttr = escapeHtml(session.session_id);
        const sessionIdJs = JSON.stringify(session.session_id).slice(1, -1);
        const isActive = session.session_id === currentSessionId ? 'active' : '';
        return `
        <div class="history-item ${isActive}"
             data-session-id="${sessionIdAttr}"
             onclick="if(!event.target.closest('.history-item-delete')) switchToSession('${sessionIdJs}')">
            <i class="bi bi-chat-left-text history-item-icon"></i>
            <div class="history-item-content">
                <div class="history-item-title">${escapeHtml(session.title)}</div>
                <div class="history-item-meta">${formatDate(session.created_at)} · ${session.message_count}条消息</div>
            </div>
            <button class="history-item-delete"
                    onclick="deleteSession('${sessionIdJs}', event)"
                    title="删除会话">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `}).join('');
}

// 切换到指定会话
async function switchToSession(sessionId) {
    if (!sessionId) {
        console.error('switchToSession: sessionId is empty');
        return;
    }

    currentSessionId = sessionId;
    localStorage.setItem('chat_session_id', sessionId);

    // Reset chat UI first
    resetChatUI();

    // Load session messages from server
    const success = await loadSessionMessages(sessionId);

    // If loading failed or no messages, stay on initial page
    // Otherwise the UI is already updated by loadSessionMessages

    // Reload history to update active state
    loadChatHistory();
}

// 加载指定会话的消息
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

        // Show chat container even if no messages (user can start new conversation in this session)
        const welcomeContainer = document.getElementById('chat-welcome-container');
        const chatContainer = document.getElementById('chatContainer');
        const inputArea = document.getElementById('chat-input-area');

        // Always switch to chat view when loading a session
        welcomeContainer.style.display = 'none';
        chatContainer.style.display = 'flex';
        inputArea.style.background = 'linear-gradient(to top, var(--llama-bg) 60%, transparent)';

        // Render messages if any
        messages.forEach(msg => {
            if (msg.role === 'user') {
                addMessage(msg.content, 'user');
            } else if (msg.role === 'assistant') {
                addMessage(msg.content, 'ai');
            }
        });

        // Scroll to bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return true;
    } catch (error) {
        console.error('加载会话消息失败:', error);
        return false;
    }
}

// 存储待删除的sessionId
let sessionToDelete = null;

// 删除会话
function deleteSession(sessionId, event) {
    event.stopPropagation(); // 防止触发切换会话

    if (!sessionId) return;

    sessionToDelete = sessionId;

    // 显示Bootstrap模态框
    const modalEl = document.getElementById('deleteSessionModal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modalEl.addEventListener('hidden.bs.modal', function disposeModal() {
            modal.dispose();
            modalEl.removeEventListener('hidden.bs.modal', disposeModal);
        });
        modal.show();
    } else {
        // Fallback to confirm if modal not found
        if (confirm('确定要删除这个会话吗？')) {
            executeDeleteSession(sessionId);
        }
    }
}

// 执行删除会话
async function executeDeleteSession(sessionId) {
    if (!sessionId) return;

    try {
        const response = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // If deleted session is current session, create new one
            if (sessionId === currentSessionId) {
                currentSessionId = generateSessionId();
                resetChatUI();
            }
            // Reload history list
            loadChatHistory();
        } else {
            console.error('删除会话失败');
            showToast('删除会话失败', 'error');
        }
    } catch (error) {
        console.error('删除会话错误:', error);
        showToast('删除会话错误: ' + error.message, 'error');
    } finally {
        sessionToDelete = null;
    }
}

// 绑定删除确认按钮事件
document.addEventListener('DOMContentLoaded', function() {
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', function() {
            if (sessionToDelete) {
                executeDeleteSession(sessionToDelete);
                // 关闭模态框
                const modalEl = document.getElementById('deleteSessionModal');
                if (modalEl) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }
            }
        });
    }
});

// 重置聊天UI（不清除会话ID）
function resetChatUI() {
    const welcomeContainer = document.getElementById('chat-welcome-container');
    const chatContainer = document.getElementById('chatContainer');
    const inputArea = document.getElementById('chat-input-area');

    welcomeContainer.style.display = 'flex';
    chatContainer.style.display = 'none';
    inputArea.style.background = 'transparent';

    // Clear messages
    const messages = document.querySelectorAll('.message-row');
    messages.forEach(msg => msg.remove());
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 页面加载时获取历史记录
document.addEventListener('DOMContentLoaded', async () => {
    await loadChatHistory();
    await checkSystemHealth();
    initDatePickers();
});

// 初始化日期选择器
function initDatePickers() {
    const dateFrom = document.getElementById('dateFrom');
    const dateTo = document.getElementById('dateTo');
    const dateFromDisplay = document.getElementById('dateFromDisplay');
    const dateToDisplay = document.getElementById('dateToDisplay');

    // 辅助函数：格式化并显示日期
    function formatAndDisplayDate(inputEl, displayEl, defaultText) {
        if (inputEl.value) {
            const date = new Date(inputEl.value);
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            // 使用完整格式：YYYY年MM月DD日
            const formattedDate = `${year}年${month}月${day}日`;
            displayEl.textContent = formattedDate;
            displayEl.classList.add('has-value');
            console.log(`Date updated: ${inputEl.id} = ${inputEl.value}, display = ${formattedDate}`);
        } else {
            displayEl.textContent = defaultText;
            displayEl.classList.remove('has-value');
        }
    }

    if (dateFrom && dateFromDisplay) {
        // 点击wrapper区域触发日期选择器
        const wrapperFrom = dateFrom.closest('.date-picker-wrapper');
        if (wrapperFrom) {
            wrapperFrom.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                try {
                    dateFrom.showPicker();
                    console.log('DateFrom picker opened');
                } catch(err) {
                    console.log('showPicker failed, trying click');
                    dateFrom.click();
                }
            });
        }

        // 日期改变时更新显示
        dateFrom.addEventListener('change', function() {
            console.log('DateFrom changed:', this.value);
            formatAndDisplayDate(dateFrom, dateFromDisplay, '开始日期');
        });

        // 也监听input事件
        dateFrom.addEventListener('input', function() {
            console.log('DateFrom input:', this.value);
            formatAndDisplayDate(dateFrom, dateFromDisplay, '开始日期');
        });
    }

    if (dateTo && dateToDisplay) {
        // 点击wrapper区域触发日期选择器
        const wrapperTo = dateTo.closest('.date-picker-wrapper');
        if (wrapperTo) {
            wrapperTo.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                try {
                    dateTo.showPicker();
                    console.log('DateTo picker opened');
                } catch(err) {
                    console.log('showPicker failed, trying click');
                    dateTo.click();
                }
            });
        }

        // 日期改变时更新显示
        dateTo.addEventListener('change', function() {
            console.log('DateTo changed:', this.value);
            formatAndDisplayDate(dateTo, dateToDisplay, '结束日期');
        });

        // 也监听input事件
        dateTo.addEventListener('input', function() {
            console.log('DateTo input:', this.value);
            formatAndDisplayDate(dateTo, dateToDisplay, '结束日期');
        });
    }
}

// 健康检查
async function checkSystemHealth() {
    try {
        const response = await fetch('/api/health');
        const health = await response.json();

        if (health.status === 'starting') {
            showToast('系统正在初始化，请稍候...', 'info');
        } else if (health.status !== 'healthy') {
            showToast('系统状态异常: ' + health.message, 'warning');
        }
    } catch (error) {
        console.error('Health check error:', error);
        showToast('无法连接到后端服务', 'error');
    }
}

async function performSearch() {
    const input = document.getElementById('searchInput');
    const query = input.value.trim();
    if (!query) return;

    // Gather filters
    const filters = {};

    // 1. File Types
    const activeTypeBtns = document.querySelectorAll('.file-type-btn.active');
    if (activeTypeBtns.length > 0) {
        filters.file_types = Array.from(activeTypeBtns).map(btn => '.' + btn.dataset.type);
    }

    // 2. File Size (MB -> Bytes)
    const minSizeInput = document.getElementById('minSize').value;
    if (minSizeInput) {
        filters.size_min = parseFloat(minSizeInput) * 1024 * 1024;
    }
    const maxSizeInput = document.getElementById('maxSize').value;
    if (maxSizeInput) {
        filters.size_max = parseFloat(maxSizeInput) * 1024 * 1024;
    }

    // 3. Date Range
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;
    if (dateFrom) {
        filters.date_from = dateFrom;
    }
    if (dateTo) {
        filters.date_to = dateTo;
    }

    // 4. Search Options
    filters.search_content = document.getElementById('searchContent').checked;

    // Transition UI
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
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                query: query,
                filters: filters
            })
        });

        if (!response.ok) {
            throw new Error('Search failed');
        }

        const results = await response.json();
        
        if (results.length === 0) {
            resultsContainer.innerHTML = `
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
            const iconClass = getFileIcon(result.file_name);
            // 使用 escapeHtml 转义所有动态内容，防止 XSS
            const safeFileName = escapeHtml(result.file_name);
            const safeSnippet = escapeHtml(result.snippet || '...');
            const safePathDisplay = escapeHtml(result.path);
            // 使用 data 属性存储路径，避免 XSS 风险
            const pathAttr = escapeHtml(result.path).replace(/"/g, '&quot;');
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
        resultsContainer.innerHTML = html;

        // 使用事件委托绑定点击事件，避免 XSS 风险
        resultsContainer.querySelectorAll('.search-result-card').forEach(card => {
            card.addEventListener('click', function() {
                const path = this.getAttribute('data-path');
                if (path) {
                    previewFile(path);
                }
            });
        });

    } catch (error) {
        console.error('Search error:', error);
        const safeErrorMessage = escapeHtml(error.message);
        resultsContainer.innerHTML = `
            <div class="text-center text-danger mt-5">
                <i class="bi bi-exclamation-circle display-4"></i>
                <p class="mt-3">搜索出错: ${safeErrorMessage}</p>
            </div>
        `;
    }
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
        case 'pdf': return 'bi-file-pdf';
        case 'doc':
        case 'docx': return 'bi-file-word';
        case 'txt': return 'bi-file-text';
        case 'md': return 'bi-markdown';
        case 'py': return 'bi-file-code';
        case 'js': return 'bi-filetype-js';
        case 'html': return 'bi-filetype-html';
        case 'css': return 'bi-filetype-css';
        default: return 'bi-file-earmark';
    }
}

async function previewFile(path) {
    const modalEl = document.getElementById('previewModal');
    const modalTitle = document.getElementById('previewModalTitle');
    const modalContent = document.getElementById('previewModalContent');

    // Show modal first with loading state
    const modal = new bootstrap.Modal(modalEl);

    // 添加隐藏事件监听器以释放资源
    modalEl.addEventListener('hidden.bs.modal', function disposeModal() {
        modal.dispose();
        modalEl.removeEventListener('hidden.bs.modal', disposeModal);
    });

    modalTitle.innerText = escapeHtml(path.split(/[\\/]/).pop()); // Show filename
    modalContent.innerText = '正在加载文件内容...';
    modal.show();

    try {
        const response = await fetch('/api/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: path })
        });

        if (!response.ok) {
            throw new Error('Failed to load file');
        }

        const data = await response.json();
        modalContent.innerText = data.content || '文件内容为空';

    } catch (error) {
        console.error('Preview error:', error);
        modalContent.innerText = '无法预览文件: ' + error.message;
    }
}

async function sendMessage() {
    const input = document.getElementById('userInput');
    const text = input.value.trim();
    if (!text) return;

    // Transition UI
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

    // 添加AI加载消息（带加载动画）
    const loadingId = addLoadingMessage();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: text,
                session_id: currentSessionId
            })
        });

        const data = await response.json();

        // 移除加载消息
        removeLoadingMessage(loadingId);

        if (response.ok) {
            addMessage(data.answer || '没有收到回复', 'ai');
        } else {
            addMessage('出错: ' + (data.detail || '未知错误'), 'ai');
        }
    } catch (error) {
        console.error('Chat error:', error);
        removeLoadingMessage(loadingId);
        addMessage('网络错误，请稍后重试', 'ai');
    }
}

let loadingMessages = {};
let messageIdCounter = 0;

function generateMessageId(prefix = 'msg') {
    return `${prefix}-${Date.now()}-${++messageIdCounter}-${Math.random().toString(36).substr(2, 5)}`;
}

// 防抖函数 - 用于优化频繁触发的事件
function debounce(func, wait, immediate = false) {
    let timeout;
    const executedFunction = function(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
    executedFunction.cancel = function() {
        if (timeout) {
            clearTimeout(timeout);
            timeout = null;
        }
    };
    return executedFunction;
}

// 节流函数 - 用于限制函数执行频率
function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

function addMessage(text, type, isLoading = false) {
    const container = document.getElementById('chatContainer');
    const div = document.createElement('div');
    div.className = 'message-row ' + type;
    const id = generateMessageId('msg');
    div.id = id;

    const avatarClass = type === 'user' ? 'avatar-user' : 'avatar-ai';
    const avatarIcon = type === 'user'
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z"/></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M6 12.796V3.204L11.481 8 6 12.796zm.659.753 5.48-4.796a1 1 0 0 0 0-1.506L6.66 2.451C6.011 1.885 5 2.345 5 3.204v9.592a1 1 0 0 0 1.659.753z"/></svg>';

    // 处理换行符
    const formattedText = escapeHtml(text).replace(/\n/g, '<br>');

    div.innerHTML = `
        <div class="message-avatar ${avatarClass}">${avatarIcon}</div>
        <div class="message-content">
            <p>${formattedText}</p>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

// 添加加载消息（带动画）
function addLoadingMessage() {
    const container = document.getElementById('chatContainer');
    const div = document.createElement('div');
    div.className = 'message-row ai';
    const id = generateMessageId('loading');
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

// 移除加载消息
function removeLoadingMessage(id) {
    const loadingEl = document.getElementById(id);
    if (loadingEl) {
        loadingEl.remove();
        delete loadingMessages[id];
    }
}

// 防抖处理的搜索函数（300ms延迟）
const debouncedSearch = debounce(performSearch, 300);

// 绑定回车事件和实时搜索
document.addEventListener('DOMContentLoaded', function() {
    const userInput = document.getElementById('userInput');
    const searchInput = document.getElementById('searchInput');

    if (userInput) {
        userInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    if (searchInput) {
        // 回车立即搜索
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                // 取消防抖搜索，立即执行
                debouncedSearch.cancel?.();
                performSearch();
            }
        });

        // 输入防抖搜索（输入停止300ms后搜索）
        searchInput.addEventListener('input', function(e) {
            const query = e.target.value.trim();
            if (query.length >= 2) { // 至少2个字符才触发实时搜索
                debouncedSearch();
            }
        });
    }
});
