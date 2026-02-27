// 监听模式切换，显示/隐藏对应设置面板
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[name="aiMode"]').forEach(function(radio) {
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
});

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// 打开外部链接（在浏览器中打开）
function openExternalLink(url) {
    // 在桌面应用中，使用 window.open 或 pywebview 的 API
    if (window.pywebview && window.pywebview.api) {
        // 如果 pywebview API 可用，使用它打开链接
        window.pywebview.api.open_external_link(url);
    } else {
        // 否则使用普通 window.open
        window.open(url, '_blank');
    }
}

// 显示测试结果弹窗
function showTestResultModal(title, message, isSuccess) {
    const modalEl = document.getElementById('testResultModal');
    const titleEl = document.getElementById('testResultTitle');
    const bodyEl = document.getElementById('testResultBody');

    if (!modalEl || !titleEl || !bodyEl) return;

    const iconClass = isSuccess ? 'bi-check-circle-fill text-success' : 'bi-x-circle-fill text-danger';
    titleEl.innerHTML = `<i class="bi ${isSuccess ? 'bi-check-circle' : 'bi-x-circle'} me-2"></i>${title}`;
    bodyEl.innerHTML = `
        <div class="mb-3">
            <i class="bi ${iconClass}" style="font-size: 48px;"></i>
        </div>
        <p class="mb-0 small">${message}</p>
    `;

    showModal(modalEl);
}

// ============================================================================
// DIRECTORY MANAGEMENT
// ============================================================================

// 目录数据
let directoriesData = { directories: [] };

// 加载目录列表
async function loadDirectories() {
    try {
        const response = await fetch('/api/directories');
        if (!response.ok) {
            console.warn('Failed to load directories, HTTP status:', response.status);
            return;
        }
        directoriesData = await response.json();
        renderDirectories();
    } catch (error) {
        console.error('Load directories error:', error);
    }
}

// 渲染目录列表
function renderDirectories() {
    const container = document.getElementById('directoriesList');
    if (!container) return;

    if (!directoriesData.directories || directoriesData.directories.length === 0) {
        container.innerHTML = `
            <div class="directory-empty">
                <i class="bi bi-folder2-open mb-2" style="font-size: 24px; display: block;"></i>
                暂无管理的目录
            </div>
        `;
        return;
    }

    container.innerHTML = directoriesData.directories.map(function(item) {
        const existsClass = item.exists ? '' : 'exists-false';
        const iconClass = item.exists ? 'bi-folder-fill' : 'bi-folder-x';
        const fileCountText = item.exists ? `约 ${item.file_count} 个文件` : '路径不存在';
        const pathAttr = escapeHtml(item.path).replace(/"/g, '&quot;');
        const pathJs = JSON.stringify(item.path).slice(1, -1);

        return `
            <div class="directory-item ${existsClass}">
                <i class="bi ${iconClass} directory-icon"></i>
                <div class="directory-info">
                    <div class="directory-path" title="${pathAttr}">${escapeHtml(item.path)}</div>
                    <div class="directory-meta">${escapeHtml(fileCountText)}</div>
                </div>
                <button class="directory-delete" onclick="removeDirectory('${pathJs}')" title="删除目录">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;
    }).join('');
}

// 浏览并添加目录
async function browseAndAddDirectory() {
    try {
        // 打开系统对话框
        const result = await fetch('/api/directories/browse', { method: 'POST' });
        const data = await result.json();

        if (data.canceled) return;
        if (!data.path) {
            showToast('未选择目录', 'warning');
            return;
        }

        // 添加目录
        const response = await fetch('/api/directories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: data.path })
        });

        const resultData = await response.json();

        if (response.ok && resultData.status === 'success') {
            showToast('目录已添加', 'success');

            // 询问是否立即重建索引
            if (resultData.needs_rebuild) {
                if (confirm('目录已添加，是否立即重建索引？\n这将扫描新添加目录中的文件。')) {
                    showRebuildModal();
                }
            }

            // 刷新列表
            await loadDirectories();
        } else {
            throw new Error(resultData.detail || '添加失败');
        }
    } catch (error) {
        console.error('Browse and add directory error:', error);
        showToast('添加目录失败: ' + error.message, 'error');
    }
}

// 删除目录
async function removeDirectory(path) {
    if (!path) return;

    if (!confirm('确定要删除这个目录吗？\n该目录将不再被扫描和监控。')) {
        return;
    }

    try {
        const response = await fetch('/api/directories', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            showToast('目录已删除', 'success');
            await loadDirectories();
        } else {
            throw new Error(result.detail || '删除失败');
        }
    } catch (error) {
        console.error('Remove directory error:', error);
        showToast('删除目录失败: ' + error.message, 'error');
    }
}

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
            showTestResultModal('连接成功', `模式: ${result.mode}<br>模型: ${result.model}`, true);
        } else {
            showTestResultModal('连接失败', result.error || '未知错误', false);
        }
    } catch (error) {
        showTestResultModal('测试出错', error.message, false);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// 初始化设置面板 Tab 切换（WebView2 兼容性）
function initSettingsTabs() {
    console.log('Initializing settings tabs...');
    const tabButtons = document.querySelectorAll('#v-pills-tab .nav-link');
    const tabPanes = document.querySelectorAll('#v-pills-tabContent .tab-pane');

    tabButtons.forEach(function(button) {
        // 移除旧的事件监听器（如果有）
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);

        newButton.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            const targetId = this.getAttribute('data-bs-target');
            if (!targetId) return;

            console.log('Tab clicked:', targetId);

            // 移除所有 active 类
            tabButtons.forEach(function(btn) {
                btn.classList.remove('active');
            });
            tabPanes.forEach(function(pane) {
                pane.classList.remove('show', 'active');
            });

            // 添加 active 类到当前按钮
            this.classList.add('active');

            // 显示对应的 pane
            const targetPane = document.querySelector(targetId);
            if (targetPane) {
                targetPane.classList.add('show', 'active');
                console.log('Activated pane:', targetId);
            } else {
                console.error('Target pane not found:', targetId);
            }
        });
    });

    console.log('Settings tabs initialized, found', tabButtons.length, 'tabs');
}

// 打开设置模态框
function openSettingsModal() {
    console.log('openSettingsModal called');
    const modalEl = document.getElementById('settingsModal');
    if (modalEl) {
        console.log('Settings modal element found, loading settings...');
        // 先加载设置
        loadSettings().then(function() {
            initialSettings = getCurrentSettings();
            console.log('Settings loaded, showing modal...');
            // 同时加载目录列表
            loadDirectories();
            // 初始化 Tab 切换（WebView2 兼容）
            initSettingsTabs();
            showModal(modalEl);
        }).catch(function(err) {
            console.error('Failed to load settings:', err);
            // 即使加载失败也显示模态框
            loadDirectories();
            initSettingsTabs();
            showModal(modalEl);
        });
    } else {
        console.error('Settings modal element not found!');
    }
}

// 恢复默认设置 (显示弹窗)
function resetSettings() {
    const resetModalEl = document.getElementById('resetConfirmModal');
    showModal(resetModalEl);
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

    showModal(rebuildModalEl);
}

// 通用显示模态框函数（带后备方案）
function showModal(modalEl) {
    if (!modalEl) {
        console.error('showModal: modal element is null');
        return;
    }

    console.log('showModal called for:', modalEl.id);

    try {
        // 先尝试使用 Bootstrap Modal（如果可用）
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            console.log('Bootstrap is available, using Bootstrap Modal');
            let modal = bootstrap.Modal.getInstance(modalEl);
            if (!modal) {
                modal = new bootstrap.Modal(modalEl);
            }
            modal.show();
        } else {
            throw new Error('Bootstrap not available');
        }
    } catch (err) {
        console.log('Using fallback modal display:', err.message);
        console.log('Bootstrap modal failed, using fallback:', err);
        // 手动显示
        modalEl.style.display = 'block';
        modalEl.classList.add('show');
        modalEl.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');

        // 添加遮罩层
        let backdrop = document.querySelector('.modal-backdrop');
        if (!backdrop) {
            backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade show';
            document.body.appendChild(backdrop);
        }
    }
}

// 通用隐藏模态框函数（带后备方案）
function hideModal(modalEl) {
    if (!modalEl) return;

    try {
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) {
                modal.hide();
                return;
            }
        }
        throw new Error('Bootstrap not available or no instance');
    } catch (err) {
        // 手动隐藏
        modalEl.style.display = 'none';
        modalEl.classList.remove('show');
        modalEl.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();
    }
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
    hideModal(resetModalEl);
}

// Settings State Management
let initialSettings = {};

// Load settings from backend when modal opens
async function loadSettings() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) {
            console.warn('Failed to load settings, HTTP status:', response.status);
            return;
        }
        const config = await response.json();
        if (!config || !config.ai_model) {
            console.log('No ai_model config found, using defaults');
            return;
        }
        if (config.ai_model) {
                // 设置模式
                const isApiMode = config.ai_model.mode === 'api';
                document.getElementById('modeAPI').checked = isApiMode;
                document.getElementById('modeLocal').checked = !isApiMode;
                document.getElementById('localSettings').style.display = isApiMode ? 'none' : 'block';
                document.getElementById('apiSettings').style.display = isApiMode ? 'block' : 'none';

                // 本地模式配置
                if (config.ai_model.local) {
                    document.getElementById('localUrlInput').value = config.ai_model.local.api_url != null ? config.ai_model.local.api_url : 'http://localhost:8000/v1/chat/completions';
                }

                // API模式配置
                if (config.ai_model.api) {
                    document.getElementById('apiProviderSelect').value = config.ai_model.api.provider != null ? config.ai_model.api.provider : 'siliconflow';
                    document.getElementById('apiUrlInput').value = config.ai_model.api.api_url != null ? config.ai_model.api.api_url : '';
                    document.getElementById('apiKeyInput').value = config.ai_model.api.api_key != null ? config.ai_model.api.api_key : '';
                    document.getElementById('modelNameInput').value = config.ai_model.api.model_name != null ? config.ai_model.api.model_name : '';
                }

                // 安全配置
                if (config.ai_model.security) {
                    document.getElementById('verifySslCheck').checked = config.ai_model.security.verify_ssl != null ? config.ai_model.security.verify_ssl : true;
                }

                // 采样参数
                if (config.ai_model.sampling) {
                    document.getElementById('tempRange').value = config.ai_model.sampling.temperature != null ? config.ai_model.sampling.temperature : 0.7;
                    document.getElementById('tempValue').innerText = config.ai_model.sampling.temperature != null ? config.ai_model.sampling.temperature : 0.7;
                    document.getElementById('topPRange').value = config.ai_model.sampling.top_p != null ? config.ai_model.sampling.top_p : 0.9;
                    document.getElementById('topPValue').innerText = config.ai_model.sampling.top_p != null ? config.ai_model.sampling.top_p : 0.9;
                    document.getElementById('topKInput').value = config.ai_model.sampling.top_k != null ? config.ai_model.sampling.top_k : 40;
                    document.getElementById('minPRange').value = config.ai_model.sampling.min_p != null ? config.ai_model.sampling.min_p : 0.05;
                    document.getElementById('minPValue').innerText = config.ai_model.sampling.min_p != null ? config.ai_model.sampling.min_p : 0.05;
                    document.getElementById('maxTokensInput').value = config.ai_model.sampling.max_tokens != null ? config.ai_model.sampling.max_tokens : 2048;
                    document.getElementById('seedInput').value = config.ai_model.sampling.seed != null ? config.ai_model.sampling.seed : -1;
                }

                // 惩罚参数
                if (config.ai_model.penalties) {
                    document.getElementById('repeatPenaltyRange').value = config.ai_model.penalties.repeat_penalty != null ? config.ai_model.penalties.repeat_penalty : 1.1;
                    document.getElementById('repeatPenaltyValue').innerText = config.ai_model.penalties.repeat_penalty != null ? config.ai_model.penalties.repeat_penalty : 1.1;
                    document.getElementById('freqPenaltyRange').value = config.ai_model.penalties.frequency_penalty != null ? config.ai_model.penalties.frequency_penalty : 0.0;
                    document.getElementById('freqPenaltyValue').innerText = config.ai_model.penalties.frequency_penalty != null ? config.ai_model.penalties.frequency_penalty : 0.0;
                    document.getElementById('presencePenaltyRange').value = config.ai_model.penalties.presence_penalty != null ? config.ai_model.penalties.presence_penalty : 0.0;
                    document.getElementById('presencePenaltyValue').innerText = config.ai_model.penalties.presence_penalty != null ? config.ai_model.penalties.presence_penalty : 0.0;
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

async function saveSettings() {
    console.log('saveSettings called');
    const currentSettings = getCurrentSettings();
    console.log('Current settings:', currentSettings);
    console.log('Initial settings:', initialSettings);
    console.log('Comparison:', JSON.stringify(initialSettings) === JSON.stringify(currentSettings));

    if (JSON.stringify(initialSettings) === JSON.stringify(currentSettings)) {
        // Show reminder
        const noChangeModalEl = document.getElementById('noChangesModal');
        showModal(noChangeModalEl);
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
            hideModal(document.getElementById('settingsModal'));
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

// Toast notification helper - WebView2 compatible
function showToast(message, type) {
    if (type === undefined) type = 'success';
    const iconMap = {
        'success': 'bi-check-circle-fill',
        'error': 'bi-x-circle-fill',
        'warning': 'bi-exclamation-triangle-fill',
        'info': 'bi-info-circle-fill'
    };

    const colorMap = {
        'success': '#198754',
        'error': '#dc3545',
        'warning': '#ffc107',
        'info': '#0dcaf0'
    };

    // Create toast container if not exists
    let toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;
        document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toastEl = document.createElement('div');
    const iconClass = iconMap[type] || 'bi-check-circle-fill';
    const borderColor = colorMap[type] || '#198754';

    toastEl.style.cssText = `
        background-color: var(--llama-input-bg);
        border: 1px solid var(--llama-border);
        border-left: 4px solid ${borderColor};
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        min-width: 280px;
        padding: 12px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        color: var(--llama-text-main);
        font-size: 14px;
        animation: slideIn 0.3s ease;
    `;

    toastEl.innerHTML = `
        <i class="bi ${iconClass}" style="color: ${borderColor}; font-size: 18px;"></i>
        <span style="flex: 1;">${message}</span>
        <button type="button" style="
            background: transparent;
            border: none;
            color: var(--llama-text-sub);
            cursor: pointer;
            padding: 4px;
            font-size: 16px;
        " onclick="this.parentElement.remove()">&times;</button>
    `;

    toastContainer.appendChild(toastEl);

    // Auto remove after 3 seconds
    setTimeout(() => {
        if (toastEl.parentElement) {
            toastEl.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toastEl.remove(), 300);
        }
    }, 3000);
}

// Add CSS animations for toast
const toastStyle = document.createElement('style');
toastStyle.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(toastStyle);

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
    document.querySelectorAll('.nav-tab-btn').forEach(function(btn) { btn.classList.remove('active'); });
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
    messages.forEach(function(msg) { msg.remove(); });

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

    historyList.innerHTML = sessions.map(function(session) {
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
        messages.forEach(function(msg) {
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
        showModal(modalEl);
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
                    hideModal(modalEl);
                }
            }
        });
    }

    // 为所有关闭按钮添加事件
    document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const modalEl = this.closest('.modal');
            if (modalEl) {
                hideModal(modalEl);
            }
        });
    });
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
    messages.forEach(function(msg) { msg.remove(); });
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 页面加载时获取历史记录
document.addEventListener('DOMContentLoaded', async function() {
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
                // 启用指针事件以允许点击
                dateFrom.style.pointerEvents = 'auto';
                try {
                    if (typeof dateFrom.showPicker === 'function') {
                        dateFrom.showPicker();
                    } else {
                        dateFrom.click();
                    }
                } catch(err) {
                    console.log('showPicker failed, falling back to focus');
                    dateFrom.focus();
                }
                // 恢复指针事件
                setTimeout(function() {
                    dateFrom.style.pointerEvents = 'none';
                }, 100);
            });
        }

        // 日期改变时更新显示
        dateFrom.addEventListener('change', function() {
            console.log('DateFrom changed:', this.value);
            formatAndDisplayDate(dateFrom, dateFromDisplay, '开始');
        });
    }

    if (dateTo && dateToDisplay) {
        // 点击wrapper区域触发日期选择器
        const wrapperTo = dateTo.closest('.date-picker-wrapper');
        if (wrapperTo) {
            wrapperTo.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                // 启用指针事件以允许点击
                dateTo.style.pointerEvents = 'auto';
                try {
                    if (typeof dateTo.showPicker === 'function') {
                        dateTo.showPicker();
                    } else {
                        dateTo.click();
                    }
                } catch(err) {
                    console.log('showPicker failed, falling back to focus');
                    dateTo.focus();
                }
                // 恢复指针事件
                setTimeout(function() {
                    dateTo.style.pointerEvents = 'none';
                }, 100);
            });
        }

        // 日期改变时更新显示
        dateTo.addEventListener('change', function() {
            console.log('DateTo changed:', this.value);
            formatAndDisplayDate(dateTo, dateToDisplay, '结束');
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
        filters.file_types = Array.from(activeTypeBtns).map(function(btn) { return '.' + btn.dataset.type; });
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
        results.sort(function(a, b) { return b.score - a.score; });

        let html = '<div class="d-flex flex-column gap-3">';
        results.forEach(function(result, index) {
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
        resultsContainer.querySelectorAll('.search-result-card').forEach(function(card) {
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

    modalTitle.innerText = escapeHtml(path.split(/[\\/]/).pop()); // Show filename
    modalContent.innerText = '正在加载文件内容...';
    showModal(modalEl);

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

function generateMessageId(prefix) {
    if (prefix === undefined) prefix = 'msg';
    return prefix + '-' + Date.now() + '-' + (++messageIdCounter) + '-' + Math.random().toString(36).substr(2, 5);
}

// 防抖函数 - 用于优化频繁触发的事件
function debounce(func, wait, immediate) {
    if (immediate === undefined) immediate = false;
    let timeout;
    const executedFunction = function() {
        var args = Array.prototype.slice.call(arguments);
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(null, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(null, args);
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
    return function executedFunction() {
        var args = Array.prototype.slice.call(arguments);
        if (!inThrottle) {
            func.apply(null, args);
            inThrottle = true;
            setTimeout(function() { inThrottle = false; }, limit);
        }
    };
}

function addMessage(text, type, isLoading) {
    if (isLoading === undefined) isLoading = false;
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

    // 检测是否多行（包含 <br>）
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
                if (debouncedSearch.cancel) {
                    debouncedSearch.cancel();
                }
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
