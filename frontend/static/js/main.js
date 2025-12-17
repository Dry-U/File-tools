// 监听模式切换，显示/隐藏 API 设置
document.querySelectorAll('input[name="aiMode"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const apiSettings = document.getElementById('apiSettings');
        if (document.getElementById('modeAPI').checked) {
            apiSettings.style.display = 'block';
        } else {
            apiSettings.style.display = 'none';
        }
    });
});

// 恢复默认设置 (显示弹窗)
function resetSettings() {
    const resetModal = new bootstrap.Modal(document.getElementById('resetConfirmModal'));
    resetModal.show();
}

// 显示重建索引确认弹窗
function showRebuildModal() {
    const rebuildModal = new bootstrap.Modal(document.getElementById('rebuildIndexModal'));
    rebuildModal.show();
}

// 确认重建索引 (执行逻辑)
async function confirmRebuild() {
    // 关闭确认弹窗
    const rebuildModalEl = document.getElementById('rebuildIndexModal');
    const modal = bootstrap.Modal.getInstance(rebuildModalEl);
    modal.hide();

    try {
        const response = await fetch('/api/rebuild-index', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
            alert(data.message || '索引重建完成');
        } else {
            alert('索引重建失败: ' + (data.detail || '未知错误'));
        }
    } catch (error) {
        console.error('Error rebuilding index:', error);
        alert('索引重建请求失败');
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

function getCurrentSettings() {
    return {
        temp: document.getElementById('tempRange').value,
        topP: document.getElementById('topPRange').value,
        topK: document.getElementById('topKInput').value,
        minP: document.getElementById('minPRange').value,
        maxTokens: document.getElementById('maxTokensInput').value,
        seed: document.getElementById('seedInput').value,
        repeatPenalty: document.getElementById('repeatPenaltyRange').value,
        freqPenalty: document.getElementById('freqPenaltyRange').value,
        presencePenalty: document.getElementById('presencePenaltyRange').value,
        mode: document.querySelector('input[name="aiMode"]:checked').id,
        apiUrl: document.getElementById('apiUrlInput').value,
        apiKey: document.getElementById('apiKeyInput').value,
        modelName: document.getElementById('modelNameInput').value
    };
}

// Capture settings when modal opens
const settingsModalEl = document.getElementById('settingsModal');
settingsModalEl.addEventListener('show.bs.modal', event => {
    initialSettings = getCurrentSettings();
});

function saveSettings() {
    const currentSettings = getCurrentSettings();
    if (JSON.stringify(initialSettings) === JSON.stringify(currentSettings)) {
        // Show reminder
        const noChangeModal = new bootstrap.Modal(document.getElementById('noChangesModal'));
        noChangeModal.show();
    } else {
        // Save logic would go here (e.g., save to localStorage or backend config)
        // For now, just close modal
        const modal = bootstrap.Modal.getInstance(settingsModalEl);
        modal.hide();
    }
}

// 状态管理
let currentMode = 'search'; // 'search' or 'chat'

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
}

async function performSearch() {
    const input = document.getElementById('searchInput');
    const query = input.value.trim();
    if (!query) return;

    // Transition UI
    const container = document.getElementById('search-content-container');
    const headerText = document.getElementById('search-header-text');
    const resultsContainer = document.getElementById('resultsContainer');

    container.classList.remove('justify-content-center', 'h-100');
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
            body: JSON.stringify({ query: query })
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

        let html = '<div class="list-group list-group-flush">';
        results.forEach(result => {
            const iconClass = getFileIcon(result.file_name);
            html += `
                <a href="#" class="list-group-item list-group-item-action bg-transparent border-secondary text-light mb-2 rounded" onclick="previewFile('${result.path.replace(/\\/g, '\\\\')}')">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1 text-primary"><i class="bi ${iconClass} me-2"></i>${result.file_name}</h6>
                        <small class="text-muted">${result.score.toFixed(2)}</small>
                    </div>
                    <p class="mb-1 small text-muted">${result.snippet || '...'}</p>
                    <small class="text-muted">路径: ${result.path}</small>
                </a>
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
    // Implement preview logic if needed, or just alert path
    // For now, let's just log it or maybe open in new tab if it was a real link
    console.log('Previewing:', path);
    // You could call /api/preview here
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

    addMessage(text, 'user');
    input.value = '';
    input.style.height = 'auto';

    // Add loading message
    const loadingId = addMessage('正在思考...', 'ai', true);

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query: text })
        });

        const data = await response.json();
        
        // Remove loading message
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();

        if (response.ok) {
            addMessage(data.answer || '没有收到回复', 'ai');
        } else {
            addMessage('出错: ' + (data.detail || '未知错误'), 'ai');
        }
    } catch (error) {
        console.error('Chat error:', error);
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();
        addMessage('网络错误，请稍后重试', 'ai');
    }
}

function addMessage(text, type, isLoading = false) {
    const container = document.getElementById('chatContainer');
    const div = document.createElement('div');
    div.className = 'message-row';
    const id = 'msg-' + Date.now();
    div.id = id;
    
    const icon = type === 'user' ? 'bi-person' : 'bi-robot';
    const avatarClass = type === 'user' ? 'avatar-user' : 'avatar-ai';
    
    div.innerHTML = `
        <div class="message-avatar ${avatarClass}"><i class="bi ${icon}"></i></div>
        <div class="message-content">
            <p>${text}</p>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

// 绑定回车事件
document.getElementById('userInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        performSearch();
    }
});
