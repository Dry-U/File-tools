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
    const resetModal = new bootstrap.Modal(document.getElementById('resetConfirmModal'));
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
        verifySsl: document.getElementById('verifySslCheck').checked
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
        const noChangeModal = new bootstrap.Modal(document.getElementById('noChangesModal'));
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
            }
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
    const initialContainer = document.getElementById('chat-initial-container');
    const welcomeText = document.getElementById('chat-welcome-text');
    const chatContainer = document.getElementById('chatContainer');
    const inputWrapper = document.getElementById('chat-input-wrapper');

    initialContainer.classList.add('h-100', 'justify-content-center');
    welcomeText.style.display = 'block';
    chatContainer.style.display = 'none';
    inputWrapper.style.background = 'none';

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
    const historyList = document.querySelector('#sidebar-chat-content .list-group');
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
        // Escape for HTML attribute
        const sessionIdAttr = escapeHtml(session.session_id);
        // For inline onclick, use JSON.stringify for proper JS string escaping
        const sessionIdJs = JSON.stringify(session.session_id).slice(1, -1);
        return `
        <div class="list-group-item bg-transparent text-light border-0 px-2 py-2 small ${session.session_id === currentSessionId ? 'active' : ''}"
             style="cursor: pointer;"
             data-session-id="${sessionIdAttr}"
             onclick="if(!event.target.closest('.delete-btn')) switchToSession('${sessionIdJs}')">
            <div class="d-flex align-items-center">
                <i class="bi bi-chat-left-text me-2"></i>
                <div class="flex-grow-1 text-truncate">
                    <div class="text-truncate">${escapeHtml(session.title)}</div>
                    <small class="text-muted">${formatDate(session.created_at)} · ${session.message_count}条消息</small>
                </div>
                <button class="btn btn-link btn-sm text-danger delete-btn p-1 ms-2" style="display: none;"
                        onclick="deleteSession('${sessionIdJs}', event)"
                        title="删除会话">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `}).join('');

    // 添加悬停显示删除按钮的效果
    historyList.querySelectorAll('.list-group-item').forEach(item => {
        item.addEventListener('mouseenter', () => {
            const deleteBtn = item.querySelector('.delete-btn');
            if (deleteBtn) deleteBtn.style.display = 'block';
        });
        item.addEventListener('mouseleave', () => {
            const deleteBtn = item.querySelector('.delete-btn');
            if (deleteBtn) deleteBtn.style.display = 'none';
        });
    });
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
        const initialContainer = document.getElementById('chat-initial-container');
        const welcomeText = document.getElementById('chat-welcome-text');
        const chatContainer = document.getElementById('chatContainer');
        const inputWrapper = document.getElementById('chat-input-wrapper');

        // Always switch to chat view when loading a session
        initialContainer.classList.remove('h-100', 'justify-content-center');
        welcomeText.style.display = 'none';
        chatContainer.style.display = 'block';
        inputWrapper.style.background = 'rgba(33, 37, 41, 0.95)';

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
    const initialContainer = document.getElementById('chat-initial-container');
    const welcomeText = document.getElementById('chat-welcome-text');
    const chatContainer = document.getElementById('chatContainer');
    const inputWrapper = document.getElementById('chat-input-wrapper');

    initialContainer.classList.add('h-100', 'justify-content-center');
    welcomeText.style.display = 'block';
    chatContainer.style.display = 'none';
    inputWrapper.style.background = 'none';

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
});

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
    const container = document.getElementById('search-content-container');
    const headerText = document.getElementById('search-header-text');
    const resultsContainer = document.getElementById('resultsContainer');

    container.classList.remove('justify-content-center');
    container.classList.add('pt-5');
    headerText.style.display = 'none';
    resultsContainer.style.display = 'block';

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
        results.forEach(result => {
            const iconClass = getFileIcon(result.file_name);
            const safePath = JSON.stringify(result.path).slice(1, -1);
            html += `
                <div class="card bg-transparent border-secondary search-result-card" onclick="previewFile('${safePath}')" style="cursor: pointer;">
                    <div class="card-body p-3">
                        <div class="d-flex w-100 justify-content-between align-items-start mb-2">
                            <h6 class="card-title mb-0 text-primary text-break pe-3">
                                <i class="bi ${iconClass} me-2"></i>${result.file_name}
                            </h6>
                            <span class="badge bg-secondary bg-opacity-25 text-light border border-secondary border-opacity-50 flex-shrink-0">
                                匹配度: ${result.score.toFixed(2)}
                            </span>
                        </div>
                        <p class="card-text small text-muted mb-2 text-break" style="display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;">
                            ${result.snippet || '...'}
                        </p>
                        <small class="text-muted d-block text-truncate">
                            <i class="bi bi-folder2-open me-1"></i>${result.path}
                        </small>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        resultsContainer.innerHTML = html;

    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = `
            <div class="text-center text-danger mt-5">
                <i class="bi bi-exclamation-circle display-4"></i>
                <p class="mt-3">搜索出错: ${error.message}</p>
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
    modalTitle.innerText = path.split(/[\\/]/).pop(); // Show filename
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
    const initialContainer = document.getElementById('chat-initial-container');
    const welcomeText = document.getElementById('chat-welcome-text');
    const chatContainer = document.getElementById('chatContainer');
    const inputWrapper = document.getElementById('chat-input-wrapper');

    initialContainer.classList.remove('h-100', 'justify-content-center');
    welcomeText.style.display = 'none';
    chatContainer.style.display = 'block';
    inputWrapper.style.background = '';

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

function addMessage(text, type, isLoading = false) {
    const container = document.getElementById('chatContainer');
    const div = document.createElement('div');
    div.className = 'message-row ' + type;
    const id = 'msg-' + Date.now();
    div.id = id;

    const icon = type === 'user' ? 'bi-person' : 'bi-robot';
    const avatarClass = type === 'user' ? 'avatar-user' : 'avatar-ai';

    // 处理换行符
    const formattedText = escapeHtml(text).replace(/\n/g, '<br>');

    div.innerHTML = `
        <div class="message-avatar ${avatarClass}"><i class="bi ${icon}"></i></div>
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
    const id = 'loading-' + Date.now();
    div.id = id;

    div.innerHTML = `
        <div class="message-avatar avatar-ai"><i class="bi bi-robot"></i></div>
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

// 绑定回车事件
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
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                performSearch();
            }
        });
    }
});
