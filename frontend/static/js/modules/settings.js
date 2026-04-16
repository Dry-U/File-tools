/**
 * FileTools - 设置管理模块
 * 提供设置加载、保存、重置、API 测试等功能
 */

const FileToolsSettings = (function() {
    'use strict';

    let initialSettings = null;
    // 缓存完整的 provider keys，避免切换 provider 后其他 keys 丢失
    let cachedProviderKeys = { siliconflow: '', deepseek: '', custom: '' };

    // API 提供商默认配置
    const API_PROVIDER_DEFAULTS = {
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

    /**
     * 加载设置
     */
    async function loadSettings() {
        try {
            const response = await fetchWithTimeout('/api/config', {}, 10000);
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const config = await response.json();
            applySettingsToUI(config);
        } catch (error) {
            console.error('加载设置失败:', error);
            FileToolsUtils.showToast('加载设置失败: ' + error.message, 'error');
        }
    }

    /**
     * 将设置应用到 UI
     * @param {Object} config - 配置对象
     */
    function applySettingsToUI(config) {
        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) {
                // 处理不同类型的元素
                if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
                    el.value = value;
                } else {
                    // span, div 等显示元素
                    el.innerText = value;
                }
            }
        };

        // AI Mode - 支持嵌套结构
        const mode = config.ai_model?.mode || config.ai_mode || 'local';
        const modeLocal = document.getElementById('modeLocal');
        const modeAPI = document.getElementById('modeAPI');
        const localSettings = document.getElementById('localSettings');
        const apiSettings = document.getElementById('apiSettings');

        if (modeLocal && modeAPI) {
            if (mode === 'api') {
                modeAPI.checked = true;
                if (localSettings) localSettings.style.display = 'none';
                if (apiSettings) apiSettings.style.display = 'block';
            } else {
                modeLocal.checked = true;
                if (localSettings) localSettings.style.display = 'block';
                if (apiSettings) apiSettings.style.display = 'none';
            }
        }

        // API 设置 - 支持嵌套结构
        if (config.ai_model && config.ai_model.api) {
            const apiConfig = config.ai_model.api;
            setValue('apiProviderSelect', apiConfig.provider || 'siliconflow');
            setValue('apiUrlInput', apiConfig.api_url || '');
            setValue('modelNameInput', apiConfig.model_name || '');
            // 从 keys 对象获取当前 provider 的 key
            const keys = apiConfig.keys || {};
            cachedProviderKeys = { ...keys };
            const currentKey = keys[apiConfig.provider] || apiConfig.api_key || '';
            setValue('apiKeyInput', currentKey);
        }

        // 采样参数 - 支持嵌套结构
        if (config.ai_model && (config.ai_model.sampling || config.ai_model.api?.sampling)) {
            const sampling = config.ai_model.sampling || config.ai_model.api?.sampling || {};
            setValue('tempRange', sampling.temperature ?? 0.7);
            setValue('tempValue', sampling.temperature ?? 0.7);
            setValue('topPRange', sampling.top_p ?? 0.9);
            setValue('topPValue', sampling.top_p ?? 0.9);
            setValue('topKRange', sampling.top_k ?? 40);
            setValue('topKValue', sampling.top_k ?? 40);
            setValue('minPRange', sampling.min_p ?? 0.05);
            setValue('minPValue', sampling.min_p ?? 0.05);
            setValue('maxTokensInput', sampling.max_tokens ?? 2048);
            setValue('seedInput', sampling.seed ?? -1);
        }

        // 惩罚参数 - 支持嵌套结构
        if (config.ai_model && (config.ai_model.penalties || config.ai_model.api?.penalties)) {
            const penalties = config.ai_model.penalties || config.ai_model.api?.penalties || {};
            setValue('repeatPenaltyRange', penalties.repeat_penalty ?? 1.1);
            setValue('repeatPenaltyValue', penalties.repeat_penalty ?? 1.1);
            setValue('freqPenaltyRange', penalties.frequency_penalty ?? 0.0);
            setValue('freqPenaltyValue', penalties.frequency_penalty ?? 0.0);
            setValue('presencePenaltyRange', penalties.presence_penalty ?? 0.0);
            setValue('presencePenaltyValue', penalties.presence_penalty ?? 0.0);
        }

        // 本地模型设置 - 支持嵌套结构
        if (config.ai_model && config.ai_model.local) {
            setValue('localApiUrlInput', config.ai_model.local.api_url || 'http://localhost:8000/v1/chat/completions');
        } else if (config.local_model) {
            // 向后兼容
            setValue('localApiUrlInput', config.local_model.api_url || 'http://localhost:8000/v1/chat/completions');
        }

        // RAG 设置
        if (config.rag) {
            setValue('ragTopKInput', config.rag.top_k ?? config.rag.max_history_turns ?? 5);
            setValue('ragContextLengthInput', config.rag.context_length ?? config.rag.max_history_chars ?? 2048);
        }

        // 搜索设置
        if (config.search) {
            setValue('searchTextWeightInput', config.search.text_weight ?? 0.6);
            setValue('searchVectorWeightInput', config.search.vector_weight ?? 0.4);
        }
    }

    /**
     * 获取当前设置
     * @returns {Object} 当前设置对象
     */
    function getCurrentSettings() {
        const getValue = (id, defaultValue = '') => {
            const el = document.getElementById(id);
            return el ? el.value : defaultValue;
        };

        const getFloat = (id, defaultValue = 0) => {
            const val = parseFloat(getValue(id, defaultValue));
            return isNaN(val) ? defaultValue : val;
        };

        const getInt = (id, defaultValue = 0) => {
            const val = parseInt(getValue(id, defaultValue));
            return isNaN(val) ? defaultValue : val;
        };

        const getChecked = (id, defaultValue = true) => {
            const el = document.getElementById(id);
            return el ? el.checked : defaultValue;
        };

        const provider = getValue('apiProviderSelect', 'siliconflow');
        const apiKey = getValue('apiKeyInput', '');

        // 更新当前 provider 的 key 到缓存
        cachedProviderKeys[provider] = apiKey;

        return {
            ai_mode: document.getElementById('modeAPI')?.checked ? 'api' : 'local',
            ai_model: {
                mode: document.getElementById('modeAPI')?.checked ? 'api' : 'local',
                api: {
                    provider: provider,
                    api_url: getValue('apiUrlInput', ''),
                    model_name: getValue('modelNameInput', ''),
                    api_key: apiKey,
                    keys: { ...cachedProviderKeys }
                },
                sampling: {
                    temperature: getFloat('tempRange', 0.7),
                    top_p: getFloat('topPRange', 0.9),
                    top_k: getInt('topKRange', 40),
                    min_p: getFloat('minPRange', 0.05),
                    max_tokens: getInt('maxTokensInput', 2048),
                    seed: getInt('seedInput', -1)
                },
                penalties: {
                    repeat_penalty: getFloat('repeatPenaltyRange', 1.1),
                    frequency_penalty: getFloat('freqPenaltyRange', 0.0),
                    presence_penalty: getFloat('presencePenaltyRange', 0.0)
                }
            },
            local_model: {
                api_url: getValue('localApiUrlInput', 'http://localhost:8000/v1/chat/completions')
            },
            rag: {
                top_k: getInt('ragTopKInput', 5),
                context_length: getInt('ragContextLengthInput', 2048)
            },
            search: {
                text_weight: getFloat('searchTextWeightInput', 0.6),
                vector_weight: getFloat('searchVectorWeightInput', 0.4)
            }
        };
    }

    /**
     * 校验设置字段
     * @returns {string|null} 错误信息，如果校验通过则返回 null
     */
    function validateSettingsFields() {
        const mode = document.getElementById('modeAPI')?.checked ? 'api' : 'local';
        
        if (mode === 'api') {
            const apiUrl = document.getElementById('apiUrlInput')?.value?.trim();
            const modelName = document.getElementById('modelNameInput')?.value?.trim();
            
            if (!apiUrl) {
                return 'API URL 不能为空';
            }
            
            // 检查 URL 格式
            try {
                new URL(apiUrl);
            } catch (e) {
                return 'API URL 格式不正确，请输入完整的 URL（如 https://api.example.com）';
            }
            
            if (!modelName) {
                return '模型名称 不能为空';
            }
        }
        
        return null;
    }

    /**
     * 保存设置
     */
    async function saveSettings() {
        // 防重复点击：检查是否已有保存操作在进行
        const saveBtn = document.getElementById('saveSettingsBtn');
        if (saveBtn && saveBtn.disabled) {
            return; // 已有保存操作进行中，直接返回
        }
        if (saveBtn) saveBtn.disabled = true;

        // 先检查是否有未保存的更改
        if (!hasUnsavedChanges()) {
            if (saveBtn) saveBtn.disabled = false;
            // 没有更改，显示提示弹窗，2秒后自动关闭
            const noChangesModalEl = document.getElementById('noChangesModal');
            if (noChangesModalEl) {
                FileToolsUtils.showModal(noChangesModalEl);
                // 2秒后自动关闭
                setTimeout(function() {
                    FileToolsUtils.hideModal(noChangesModalEl);
                }, 2000);
            }
            return;
        }

        // 字段校验
        const validationError = validateSettingsFields();
        if (validationError) {
            FileToolsUtils.showToast(validationError, 'error');
            return;
        }

        const settings = getCurrentSettings();

        try {
            const response = await fetchWithTimeout('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            }, 15000);

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                FileToolsUtils.hideModal(document.getElementById('settingsModal'));
                setTimeout(function() {
                    FileToolsUtils.showToast('设置已保存', 'success');
                }, 300);
                initialSettings = getCurrentSettings();
                cachedProviderKeys = { ...settings.ai_model.api.keys };
            } else if (response.ok && result.status === 'warning') {
                FileToolsUtils.showToast(result.message || '参数未变更', 'info');
                initialSettings = getCurrentSettings();
                cachedProviderKeys = { ...settings.ai_model.api.keys };
            } else {
                throw new Error(result.detail || '保存失败');
            }
        } catch (error) {
            console.error('保存设置失败:', error);
            FileToolsUtils.showToast('保存设置失败: ' + error.message, 'error');
        } finally {
            // 恢复按钮状态
            if (saveBtn) saveBtn.disabled = false;
        }
    }

    /**
     * 检测配置是否有未保存的更改
     */
    function hasUnsavedChanges() {
        if (!initialSettings) return false;
        const currentSettings = getCurrentSettings();
        return JSON.stringify(currentSettings) !== JSON.stringify(initialSettings);
    }

    /**
     * API 提供商变更时自动填充默认 URL
     */
    function onProviderChange() {
        const provider = document.getElementById('apiProviderSelect').value;
        const urlInput = document.getElementById('apiUrlInput');
        const modelInput = document.getElementById('modelNameInput');
        const keyInput = document.getElementById('apiKeyInput');

        if (API_PROVIDER_DEFAULTS[provider]) {
            urlInput.value = API_PROVIDER_DEFAULTS[provider].url;
            modelInput.value = API_PROVIDER_DEFAULTS[provider].model;
        }
        // 切换时从缓存恢复对应 provider 的 key
        if (keyInput && cachedProviderKeys[provider] !== undefined) {
            keyInput.value = cachedProviderKeys[provider];
        }
    }

    /**
     * 测试 API 连接 - 智能保存逻辑
     * - 配置有变化：测试成功后自动保存
     * - 配置无变化：直接测试
     */
    async function testAPIConnection() {
        const btn = document.getElementById('testConnectionBtn');
        const originalText = btn ? btn.innerHTML : '<i class="bi bi-lightning me-1"></i>测试连接';

        // 获取当前配置
        const currentSettings = getCurrentSettings();

        // 检测配置是否有变化（对比 initialSettings）
        const hasChanges = initialSettings && JSON.stringify(currentSettings) !== JSON.stringify(initialSettings);

        if (btn) {
            if (hasChanges) {
                btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> 保存并测试...';
            } else {
                btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> 测试中...';
            }
            btn.disabled = true;
        }

        try {
            // 如果配置有变化，先保存
            if (hasChanges) {
                const saveResponse = await fetchWithTimeout('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentSettings)
                }, 15000);

                if (!saveResponse.ok) {
                    const errData = await saveResponse.json().catch(() => ({}));
                    throw new Error(errData.detail || '保存配置失败');
                }

                // 更新 initialSettings
                initialSettings = currentSettings;
            }

            // 测试连接
            const response = await fetchWithTimeout('/api/model/test', {}, 15000);
            const result = await response.json();

            if (result.status === 'ok') {
                const message = hasChanges
                    ? `配置已保存<br>模式: ${result.mode}<br>模型: ${result.model}`
                    : `模式: ${result.mode}<br>模型: ${result.model}`;
                showTestResultModalSafe('连接成功', message, true);
            } else {
                showTestResultModalSafe('连接失败', result.error || '未知错误', false);
            }
        } catch (error) {
            console.error('测试连接失败:', error);
            showTestResultModalSafe('测试出错', error.message, false);
        } finally {
            if (btn) {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }
    }

    /**
     * 安全显示测试结果（只用 toast，不弹 modal）
     */
    function showTestResultModalSafe(title, message, isSuccess) {
        console.log('showTestResultModalSafe called:', {title, message, isSuccess});

        // 只使用 toast 显示结果（message 可能是带 <br> 的 HTML，转成纯文本）
        const cleanMessage = message ? message.replace(/<br\s*\/?>/gi, ' ') : '';
        const toastMessage = title + (cleanMessage ? ': ' + cleanMessage : '');
        FileToolsUtils.showToast(toastMessage, isSuccess ? 'success' : 'error');
    }

    /**
     * 统一设置面板 Tab 高度
     * 让所有 tab pane 高度一致，内部独立滚动
     */
    function equalizeTabPanesHeight() {
        const tabContent = document.getElementById('v-pills-tabContent');
        const panes = document.querySelectorAll('#v-pills-tabContent .tab-pane');
        if (!tabContent || panes.length === 0) return;

        // 使用 flexbox 布局，让 tabContent 自适应剩余高度
        tabContent.style.display = 'flex';
        tabContent.style.flexDirection = 'column';

        // 强制所有 pane 高度一致
        panes.forEach(function(pane) {
            pane.style.flex = '1';
            pane.style.minHeight = '0';
            pane.style.overflowY = 'auto';
            pane.style.overflowX = 'hidden';
        });
    }

    /**
     * 初始化设置面板 Tab 切换
     * 注意：每次打开设置模态框后都会调用此函数重新绑定事件
     * 因为 modalBody.innerHTML = originalContent 会销毁之前绑定的事件
     */
    let _tabsInitialized = false;
    function initSettingsTabs() {
        // 标记已初始化（用于 Tab 切换逻辑）
        // 注意：这里的标记不阻止事件重新绑定，因为 innerHTML 会销毁旧事件
        _tabsInitialized = true;
        console.log('Initializing settings tabs...');

        // 使用事件委托绑定 tab 按钮点击
        const tabContainer = document.getElementById('v-pills-tab');
        if (tabContainer) {
            // 先克隆移除旧事件
            const newContainer = tabContainer.cloneNode(true);
            tabContainer.parentNode.replaceChild(newContainer, tabContainer);

            newContainer.addEventListener('click', function (e) {
                const button = e.target.closest('.nav-link');
                if (!button) return;

                e.preventDefault();
                e.stopPropagation();

                const targetId = button.getAttribute('data-bs-target');
                if (!targetId) return;

                console.log('Tab clicked:', targetId);

                // 切换 tab 按钮状态
                newContainer.querySelectorAll('.nav-link').forEach(function (btn) {
                    btn.classList.remove('active');
                });
                button.classList.add('active');

                // 切换 pane 显示
                document.querySelectorAll('#v-pills-tabContent .tab-pane').forEach(function (pane) {
                    pane.classList.remove('show', 'active');
                });

                const targetPane = document.querySelector(targetId);
                if (targetPane) {
                    targetPane.classList.add('show', 'active');
                    console.log('Activated pane:', targetId);
                    // 切换后同步高度
                    equalizeTabPanesHeight();
                } else {
                    console.error('Target pane not found:', targetId);
                }
            });
        }

        console.log('Settings tabs initialized');

        // 重新绑定保存按钮事件（innerHTML 替换后需要重新绑定）
        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        if (saveSettingsBtn) {
            saveSettingsBtn.onclick = null;
            saveSettingsBtn.addEventListener('click', function() {
                console.log('Save button clicked');
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.saveSettings) {
                    FileToolsSettings.saveSettings();
                } else if (typeof saveSettings === 'function') {
                    saveSettings();
                }
            });
        } else {
            console.error('saveSettingsBtn not found in DOM');
        }

        // 重新绑定测试连接按钮事件
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

        // 重新绑定恢复默认按钮事件
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

        // 重新绑定滑块事件（采样参数 + 惩罚参数）
        const sliderIds = ['tempRange', 'topPRange', 'topKRange', 'minPRange', 'repeatPenaltyRange', 'freqPenaltyRange', 'presencePenaltyRange'];
        sliderIds.forEach(function(sliderId) {
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

        // 重新绑定添加目录按钮
        const addDirectoryBtn = document.getElementById('addDirectoryBtn');
        if (addDirectoryBtn) {
            addDirectoryBtn.onclick = null;
            addDirectoryBtn.addEventListener('click', function() {
                if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.browseAndAddDirectory) {
                    FileToolsDirectory.browseAndAddDirectory();
                } else if (typeof FileToolsDirectory !== 'undefined' && FileToolsDirectory.addDirectory) {
                    FileToolsDirectory.addDirectory();
                }
            });
        }

        // 重新绑定接入模式切换事件
        const modeLocal = document.getElementById('modeLocal');
        const modeAPI = document.getElementById('modeAPI');
        const localSettings = document.getElementById('localSettings');
        const apiSettings = document.getElementById('apiSettings');

        if (modeLocal && modeAPI) {
            modeLocal.onchange = null;
            modeAPI.onchange = null;

            modeLocal.addEventListener('change', function() {
                if (this.checked) {
                    if (localSettings) localSettings.style.display = 'block';
                    if (apiSettings) apiSettings.style.display = 'none';
                }
            });

            modeAPI.addEventListener('change', function() {
                if (this.checked) {
                    if (localSettings) localSettings.style.display = 'none';
                    if (apiSettings) apiSettings.style.display = 'block';
                }
            });
        }

        // 重新绑定 API 提供商切换事件
        const apiProviderSelect = document.getElementById('apiProviderSelect');
        if (apiProviderSelect) {
            apiProviderSelect.onchange = null;
            apiProviderSelect.addEventListener('change', function() {
                if (typeof FileToolsSettings !== 'undefined' && FileToolsSettings.onProviderChange) {
                    FileToolsSettings.onProviderChange();
                } else if (typeof onProviderChange === 'function') {
                    onProviderChange();
                }
            });
        }

        // 重新绑定目录列表删除按钮事件委托
        document.querySelectorAll('.directory-list').forEach(function(list) {
            // 先移除旧的事件监听器（通过克隆替换）
            const newList = list.cloneNode(true);
            list.parentNode.replaceChild(newList, list);

            newList.addEventListener('click', function(e) {
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

        // 重新绑定密码显示切换按钮
        const toggleApiKeyBtn = document.getElementById('toggleApiKeyBtn');
        const apiKeyInput = document.getElementById('apiKeyInput');
        if (toggleApiKeyBtn && apiKeyInput) {
            toggleApiKeyBtn.onclick = null;
            toggleApiKeyBtn.addEventListener('click', function() {
                const type = apiKeyInput.type === 'password' ? 'text' : 'password';
                apiKeyInput.type = type;
                // 只切换图标，不显示中文文字
                const icon = this.querySelector('i');
                if (icon) {
                    icon.className = type === 'password' ? 'bi bi-eye' : 'bi bi-eye-slash';
                }
            });
        }

        console.log('Settings events rebound after innerHTML');
    }

    /**
     * 打开设置模态框
     */
    function openSettingsModal() {
        console.log('openSettingsModal called');
        const modalEl = document.getElementById('settingsModal');
        if (!modalEl) {
            console.error('Settings modal element not found!');
            return;
        }

        // 立即显示模态框，提供即时反馈
        FileToolsUtils.showModal(modalEl);

        // 先恢复内容（让用户可以立即看到界面）
        const modalBody = modalEl.querySelector('.modal-body');
        const originalContent = modalBody.innerHTML;

        // 如果之前有内容，先显示原始内容
        if (originalContent && originalContent.trim()) {
            modalBody.innerHTML = originalContent;
        }

        // 初始化 tabs 和事件（不等待数据加载）
        _tabsInitialized = false;
        initSettingsTabs();
        initAboutButtons();
        equalizeTabPanesHeight();
        loadCurrentVersion();

        // 后台加载设置
        loadSettings().then(function (config) {
            initialSettings = getCurrentSettings();
            console.log('Settings loaded successfully');
            if (typeof FileToolsDirectory !== 'undefined') {
                FileToolsDirectory.loadDirectories();
            }
        }).catch(function (err) {
            console.error('Failed to load settings:', err);
            // 即使加载失败也显示界面
            if (typeof FileToolsDirectory !== 'undefined') {
                FileToolsDirectory.loadDirectories();
            }
            // 只在真正失败时显示提示
            FileToolsUtils.showToast('设置加载失败', 'warning');
        });
    }

    /**
     * 恢复默认设置
     */
    let _resetInProgress = false;
    function resetSettings() {
        if (_resetInProgress) return;
        _resetInProgress = true;

        const resetModalEl = document.getElementById('resetConfirmModal');
        // 检查 modal 是否已经显示
        if (resetModalEl && resetModalEl.classList.contains('show')) {
            _resetInProgress = false;
            return;
        }

        FileToolsUtils.showModal(resetModalEl);

        // 500ms 后重置标志（防止快速重复点击）
        setTimeout(() => { _resetInProgress = false; }, 500);
    }

    /**
     * 安全设置元素值
     */
    function safeSetValue(id, value) {
        const el = document.getElementById(id);
        if (el) {
            el.value = value;
            return true;
        }
        return false;
    }

    /**
     * 安全设置元素文本
     */
    function safeSetText(id, text) {
        const el = document.getElementById(id);
        if (el) {
            el.innerText = text;
            return true;
        }
        return false;
    }

    /**
     * 确认重置
     */
    function confirmReset() {
        // 采样参数
        safeSetValue('tempRange', 0.7);
        safeSetText('tempValue', '0.7');
        safeSetValue('topPRange', 0.9);
        safeSetText('topPValue', '0.9');
        safeSetValue('topKRange', 40);
        safeSetText('topKValue', '40');
        safeSetValue('minPRange', 0.05);
        safeSetText('minPValue', '0.05');
        safeSetValue('maxTokensInput', 2048);
        safeSetValue('seedInput', -1);

        // 惩罚参数
        safeSetValue('repeatPenaltyRange', 1.1);
        safeSetText('repeatPenaltyValue', '1.1');
        safeSetValue('freqPenaltyRange', 0.0);
        safeSetText('freqPenaltyValue', '0.0');
        safeSetValue('presencePenaltyRange', 0.0);
        safeSetText('presencePenaltyValue', '0.0');

        // API 设置重置
        safeSetValue('apiProviderSelect', 'siliconflow');
        safeSetValue('apiUrlInput', 'https://api.siliconflow.cn/v1/chat/completions');
        safeSetValue('apiKeyInput', '');
        safeSetValue('modelNameInput', 'deepseek-ai/DeepSeek-V2.5');

        // 模式重置为本地
        const modeLocal = document.getElementById('modeLocal');
        const modeAPI = document.getElementById('modeAPI');
        const localSettings = document.getElementById('localSettings');
        const apiSettings = document.getElementById('apiSettings');
        if (modeLocal) modeLocal.checked = true;
        if (modeAPI) modeAPI.checked = false;
        if (localSettings) localSettings.style.display = 'block';
        if (apiSettings) apiSettings.style.display = 'none';

        // 本地 API URL 重置
        safeSetValue('localApiUrlInput', 'http://localhost:8000/v1/chat/completions');

        // RAG 设置重置 (元素可能不存在)
        safeSetValue('ragTopKInput', 5);
        safeSetValue('ragContextLengthInput', 2048);

        // 搜索设置重置 (元素可能不存在)
        safeSetValue('searchTextWeightInput', 0.6);
        safeSetValue('searchVectorWeightInput', 0.4);

        // 更新缓存的 provider keys
        cachedProviderKeys = { siliconflow: '', deepseek: '', custom: '' };

        // 更新 initialSettings 以反映重置后的状态
        initialSettings = getCurrentSettings();

        FileToolsUtils.hideModal(document.getElementById('resetConfirmModal'));
        FileToolsUtils.showToast('已恢复默认参数', 'success');
    }

    /**
     * 更新重建索引进度 UI
     * 注意：此函数可能在 DOM 元素不存在时被调用（如 innerHTML 替换后）
     * 因此所有 DOM 操作都需要空值检查
     */
    function updateRebuildUI(progress, statusText, fileCountText, iconState, barClass, statusClass) {
        try {
            const progressBar = document.getElementById('rebuildProgressBar');
            const percentText = document.getElementById('rebuildPercent');
            const statusEl = document.getElementById('rebuildStatus');
            const countEl = document.getElementById('rebuildFileCount');
            const spinner = document.getElementById('rebuildSpinner');
            const successIcon = document.getElementById('rebuildSuccessIcon');
            const cancelIcon = document.getElementById('rebuildCancelIcon');
            const errorIcon = document.getElementById('rebuildErrorIcon');

            if (progressBar) {
                progressBar.style.width = progress + '%';
                progressBar.className = 'rebuild-progress-bar ' + (barClass || '');
                progressBar.setAttribute('aria-valuenow', progress);
                progressBar.setAttribute('aria-valuemin', 0);
                progressBar.setAttribute('aria-valuemax', 100);
            }
            if (percentText) percentText.textContent = progress + '%';
            if (statusEl) {
                statusEl.textContent = statusText || '处理中...';
                statusEl.className = 'rebuild-status-text ' + (statusClass || '');
            }
            if (countEl) countEl.textContent = fileCountText || '';

            // 图标状态切换
            if (spinner) spinner.style.display = iconState === 'spinner' ? '' : 'none';
            if (successIcon) successIcon.classList.toggle('d-none', iconState !== 'success');
            if (cancelIcon) cancelIcon.classList.toggle('d-none', iconState !== 'cancel');
            if (errorIcon) errorIcon.classList.toggle('d-none', iconState !== 'error');
        } catch (e) {
            console.warn('updateRebuildUI: DOM更新失败（元素可能已被替换）:', e);
        }
    }

    /**
     * 显示重建索引确认弹窗
     */
    function showRebuildModal() {
        const rebuildModalEl = document.getElementById('rebuildIndexModal');
        const modalBody = document.getElementById('rebuildModalBody');
        const modalFooter = document.getElementById('rebuildModalFooter');
        const closeBtn = document.getElementById('rebuildCloseBtn');

        // 重置为初始状态（使用 HTML 中定义的静态内容）
        modalBody.innerHTML = `
            <p class="mb-0 small">确定要重建文件索引吗？<br>这可能需要一些时间。</p>
            <div class="alert alert-warning mt-3 mb-0 py-2 px-2 small text-start" style="font-size: 0.75rem;">
                <i class="bi bi-info-circle me-1"></i>
                重建期间请勿操作文件，如有文件监控冲突可暂时关闭监控。
            </div>
        `;
        modalFooter.style.display = '';
        modalFooter.innerHTML = `
            <button type="button" class="btn btn-sm btn-outline-secondary border-0" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-sm btn-primary px-3" id="rebuildConfirmBtn">确定</button>
        `;
        closeBtn.style.display = 'block';

        // 绑定确认按钮事件
        const confirmBtn = document.getElementById('rebuildConfirmBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                confirmRebuild();
            });
        }

        // 绑定取消按钮点击事件 - 关闭时也取消后端任务
        if (closeBtn) {
            closeBtn.onclick = null; // 清除之前的绑定
            closeBtn.addEventListener('click', function() {
                cancelRebuild();
            });
        }

        FileToolsUtils.showModal(rebuildModalEl);
    }

    /**
     * 取消重建索引
     */
    async function cancelRebuild() {
        try {
            const response = await fetchWithTimeout('/api/rebuild-index', {
                method: 'DELETE'
            }, 10000);
            const data = await response.json();

            if (response.ok) {
                FileToolsUtils.showToast('已取消重建索引', 'info');
            } else {
                throw new Error(data.detail || '取消失败');
            }
        } catch (error) {
            console.error('Cancel rebuild error:', error);
            FileToolsUtils.showToast('取消失败: ' + error.message, 'error');
        }

        // 隐藏模态框
        const modalEl = document.getElementById('rebuildIndexModal');
        if (modalEl) {
            FileToolsUtils.hideModal(modalEl);
        }
    }

    /**
     * 确认重建索引（使用SSE流式进度）
     */
    async function confirmRebuild() {
        const modalEl = document.getElementById('rebuildIndexModal');
        const modalBody = document.getElementById('rebuildModalBody');
        const modalFooter = document.getElementById('rebuildModalFooter');
        const closeBtn = document.getElementById('rebuildCloseBtn');

        // 显示取消按钮
        closeBtn.style.display = 'block';
        closeBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                stroke="currentColor" style="width: 20px; height: 20px;">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
        `;
        // 使用 addEventListener 而不是 onclick，避免重复绑定
        closeBtn.removeEventListener('click', cancelRebuild);
        closeBtn.addEventListener('click', cancelRebuild);
        modalFooter.style.display = 'none';

        let eventSource = null;
        let sseFinished = false;

        // 显示进度条UI - 现代化设计
        modalBody.innerHTML = `
            <div class="rebuild-progress-container">
                <div class="rebuild-icon-wrapper" id="rebuildIconWrapper">
                    <div id="rebuildSpinner" class="rebuild-spinner">
                        <svg viewBox="0 0 50 50" class="spinner-svg">
                            <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-dasharray="31.4 31.4" class="spinner-circle"/>
                        </svg>
                    </div>
                    <div id="rebuildSuccessIcon" class="rebuild-status-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 6L9 17l-5-5"/>
                        </svg>
                    </div>
                    <div id="rebuildCancelIcon" class="rebuild-status-icon rebuild-cancel-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </div>
                    <div id="rebuildErrorIcon" class="rebuild-status-icon rebuild-error-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 8v4M12 16h.01"/>
                        </svg>
                    </div>
                </div>
                <div class="rebuild-progress-info">
                    <div id="rebuildStatus" class="rebuild-status-text">正在准备重建索引...</div>
                    <div id="rebuildFileCount" class="rebuild-file-count"></div>
                </div>
                <div class="rebuild-progress-bar-wrapper">
                    <div id="rebuildProgressBar" class="rebuild-progress-bar" role="progressbar" style="width: 0%;">
                        <div class="rebuild-progress-fill"></div>
                    </div>
                    <div id="rebuildPercent" class="rebuild-percent-text">0%</div>
                </div>
            </div>
        `;

        // SSE 完成后清理函数
        function finishSSE() {
            if (sseFinished) return;
            sseFinished = true;
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            // 确保 spinner 被隐藏
            const spinner = document.getElementById('rebuildSpinner');
            if (spinner) spinner.style.display = 'none';
        }

        // 120秒超时：如果 SSE 没有收到完成消息，自动降级到轮询
        const sseTimeout = setTimeout(() => {
            if (!sseFinished) {
                console.warn('SSE 超时（120秒未收到完成消息），降级到轮询模式');
                finishSSE();
                performPollingRebuild(modalBody, modalFooter, closeBtn);
            }
        }, 120000);

        try {
            // 检查 EventSource 是否可用
            if (typeof EventSource === 'undefined') {
                throw new Error('EventSource not available');
            }

            console.log('SSE: 正在连接...');
            // 使用SSE流式接口
            eventSource = new EventSource('/api/rebuild-index/stream');
            console.log('SSE: EventSource 已创建, readyState:', eventSource.readyState);

            eventSource.onopen = function() {
                console.log('SSE: 连接已打开, readyState:', eventSource.readyState);
            };

            eventSource.onmessage = function(event) {
                console.log('[SSE RAW]', event.data, 'lastEventId:', event.lastEventId);
                console.log('SSE: 收到消息:', event.data);
                try {
                    const data = JSON.parse(event.data);

                    if (data.status === 'success') {
                        console.log('[SSE SUCCESS] 收到成功消息!', data);
                        clearTimeout(sseTimeout);
                        finishSSE();

                        // 直接隐藏 spinner（双重保险）
                        const spinner = document.getElementById('rebuildSpinner');
                        if (spinner) spinner.style.display = 'none';

                        // 使用辅助函数更新 UI
                        updateRebuildUI(
                            100,
                            '索引重建完成！',
                            `扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}`,
                            'success',
                            'fill-success',
                            'success'
                        );

                        // 立即显示完成状态
                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="text-success fw-bold me-auto">
                                <i class="bi bi-check-circle-fill"></i> 重建完成！
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;

                        // 1.5秒后自动关闭弹窗并提示
                        setTimeout(() => {
                            const modalEl = document.getElementById('rebuildIndexModal');
                            if (modalEl) {
                                FileToolsUtils.hideModal(modalEl);
                                FileToolsUtils.showToast('索引重建完成！', 'success');
                            }
                        }, 1500);

                    } else if (data.status === 'progress') {
                        // 更新进度条
                        const progress = data.progress || 0;
                        updateRebuildUI(
                            progress,
                            '正在重建索引...',
                            '',
                            'spinner',
                            '',
                            ''
                        );

                    } else if (data.status === 'keepalive') {
                        // 保持连接活跃，不做处理（只更新最后活跃时间）
                        // console.debug('SSE keepalive received');

                    } else if (data.status === 'error') {
                        clearTimeout(sseTimeout);
                        finishSSE();
                        updateRebuildUI(
                            100,
                            '索引重建失败',
                            data.error || '',
                            'error',
                            'fill-error',
                            'error'
                        );
                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="text-danger fw-bold me-auto">
                                <i class="bi bi-exclamation-circle-fill"></i> 失败
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;
                        throw new Error(data.error || '重建索引失败');

                    } else if (data.status === 'cancelled') {
                        clearTimeout(sseTimeout);
                        finishSSE();
                        updateRebuildUI(
                            100,
                            '索引重建已取消',
                            `扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}`,
                            'cancel',
                            'fill-warning',
                            'warning'
                        );
                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="text-warning fw-bold me-auto">
                                <i class="bi bi-x-circle-fill"></i> 已取消
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;
                        FileToolsUtils.showToast('索引重建已取消', 'warning');
                    }
                } catch (e) {
                    console.error('SSE解析错误:', e);
                    FileToolsUtils.showToast('重建失败: ' + e.message, 'error');
                }
            };

            eventSource.onerror = function(event) {
                console.warn('SSE: 连接错误, readyState:', event.target.readyState, ', sseFinished:', sseFinished);
                if (sseFinished) {
                    console.log('SSE: 已完成，忽略错误');
                    return;
                }
                // 根据错误状态决定延迟时间
                const isClosed = event.target.readyState === EventSource.CLOSED;
                const checkDelay = isClosed ? 1000 : 3000;
                const logMsg = isClosed ? 'SSE: 连接已关闭' : 'SSE连接错误';

                if (isClosed) {
                    console.log(logMsg + ', sseFinished:', sseFinished);
                } else {
                    console.warn(logMsg + '，3秒后检查是否需要降级到轮询模式...');
                }

                // 统一的降级检查逻辑
                setTimeout(async () => {
                    if (sseFinished) {
                        console.log('SSE: 任务已完成，无需降级');
                        return;
                    }
                    // 检查后端是否存活
                    try {
                        const healthRes = await fetchWithTimeout('/api/health', {}, 3000);
                        if (healthRes.ok) {
                            // 后端存活，降级到轮询继续跟踪进度
                            console.warn('SSE: 后端存活，降级到轮询模式');
                            clearTimeout(sseTimeout);
                            finishSSE();
                            performPollingRebuild(modalBody, modalFooter, closeBtn);
                        } else {
                            // 后端返回错误状态
                            console.error('SSE: 后端健康检查返回错误');
                            clearTimeout(sseTimeout);
                            finishSSE();
                            updateRebuildUI(100, '后端响应异常', '请检查后端日志', 'error', 'fill-error', 'error');
                            modalFooter.style.display = 'flex';
                            modalFooter.innerHTML = `
                                <div class="text-danger fw-bold me-auto">
                                    <i class="bi bi-exclamation-circle-fill"></i> 后端异常
                                </div>
                                <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                            `;
                        }
                    } catch (healthErr) {
                        // 后端不可达
                        console.error('SSE: 后端不可达:', healthErr);
                        clearTimeout(sseTimeout);
                        finishSSE();
                        updateRebuildUI(100, '后端连接失败', '请重启应用', 'error', 'fill-error', 'error');
                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="text-danger fw-bold me-auto">
                                <i class="bi bi-exclamation-circle-fill"></i> 连接失败
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;
                        FileToolsUtils.showToast('后端连接失败，请重启应用', 'error');
                    }
                }, checkDelay);
            };

        } catch (error) {
            console.error('SSE初始化失败:', error);
            clearTimeout(sseTimeout);
            finishSSE();
            performPollingRebuild(modalBody, modalFooter, closeBtn);
        }

        // 添加模态框关闭事件监听，以便在用户点击X或外部区域时取消重建
        const handleModalHidden = function() {
            clearTimeout(sseTimeout);
            finishSSE();
            closeBtn.removeEventListener('click', cancelRebuild);
            modalEl.removeEventListener('hidden.bs.modal', handleModalHidden);
        };
        modalEl.addEventListener('hidden.bs.modal', handleModalHidden);
    }

    /**
     * 降级方案：使用普通POST请求重建索引
     */
    async function performFallbackRebuild(modalBody, modalFooter, closeBtn) {
        modalBody.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <p class="mb-0 small text-muted">正在重建索引，请稍候...</p>
            </div>
        `;

        try {
            const response = await fetchWithTimeout('/api/rebuild-index', {
                method: 'POST'
            }, 60000);
            const data = await response.json();

            if (response.ok) {
                modalBody.innerHTML = `
                    <div class="text-center">
                        <i class="bi bi-check-circle-fill text-success display-4 mb-3"></i>
                        <p class="mb-0 small">索引重建完成</p>
                        <p class="small text-muted mt-1">扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}</p>
                    </div>
                `;
            } else {
                throw new Error(data.detail || '未知错误');
            }
        } catch (error) {
            console.error('Error rebuilding index:', error);
            const safeErrorMessage = FileToolsUtils.escapeHtml(error.message || '请求失败');
            modalBody.innerHTML = `
                <div class="text-center">
                    <i class="bi bi-x-circle-fill text-danger display-4 mb-3"></i>
                    <p class="mb-0 small">索引重建失败</p>
                    <p class="small text-muted mt-1">${safeErrorMessage}</p>
                </div>
            `;
        } finally {
            closeBtn.style.display = 'block';
            modalFooter.style.display = 'flex';
            modalFooter.innerHTML = `
                <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
            `;
        }
    }

    /**
     * 轮询方案：使用 POST 请求启动重建，然后轮询进度
     * 这是 SSE 不可用时的降级方案
     */
    async function performPollingRebuild(modalBody, modalFooter, closeBtn) {
        let pollingInterval = null;
        let isCompleted = false;
        let consecutiveFailures = 0;  // 连续失败计数
        const MAX_CONSECUTIVE_FAILURES = 5;  // 连续5次失败才判定后端崩溃

        const stopPolling = () => {
            isCompleted = true;
            if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
        };

        // 显示轮询模式 UI - 使用相同的现代化设计
        modalBody.innerHTML = `
            <div class="rebuild-progress-container">
                <div class="rebuild-icon-wrapper" id="rebuildIconWrapper">
                    <div id="rebuildSpinner" class="rebuild-spinner">
                        <svg viewBox="0 0 50 50" class="spinner-svg">
                            <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-dasharray="31.4 31.4" class="spinner-circle"/>
                        </svg>
                    </div>
                    <div id="rebuildSuccessIcon" class="rebuild-status-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 6L9 17l-5-5"/>
                        </svg>
                    </div>
                    <div id="rebuildCancelIcon" class="rebuild-status-icon rebuild-cancel-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </div>
                    <div id="rebuildErrorIcon" class="rebuild-status-icon rebuild-error-icon d-none">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 8v4M12 16h.01"/>
                        </svg>
                    </div>
                </div>
                <div class="rebuild-progress-info">
                    <div id="rebuildStatus" class="rebuild-status-text">正在启动重建任务...</div>
                    <div id="rebuildFileCount" class="rebuild-file-count"></div>
                </div>
                <div class="rebuild-progress-bar-wrapper">
                    <div id="rebuildProgressBar" class="rebuild-progress-bar" role="progressbar" style="width: 0%;">
                        <div class="rebuild-progress-fill"></div>
                    </div>
                    <div id="rebuildPercent" class="rebuild-percent-text">0%</div>
                </div>
            </div>
        `;

        try {
            // 1. 首先检查是否已有重建任务在进行（独立try-catch，超时不影响主流程）
            let existingProgress = null;
            try {
                const progressRes = await fetchWithTimeout('/api/rebuild-progress', {}, 3000);
                if (progressRes.ok) {
                    existingProgress = await progressRes.json();
                    if (existingProgress.in_progress) {
                        updateRebuildUI(
                            existingProgress.progress || 0,
                            '正在重建索引...',
                            `扫描: ${existingProgress.files_scanned || 0} | 索引: ${existingProgress.files_indexed || 0}`,
                            'spinner',
                            '',
                            ''
                        );
                    }
                }
            } catch (e) {
                // 忽略检查超时，继续正常流程
                console.debug('检查已有任务超时，继续启动新任务...');
            }

            // 2. 启动重建任务（如果当前没有进行中的任务）
            if (!isCompleted) {
                try {
                    await fetchWithTimeout('/api/rebuild-index', {
                        method: 'POST'
                    }, 5000); // 5秒超时，因为这是非阻塞的
                } catch (e) {
                    // 忽略启动超时，任务可能已经在后台运行
                    console.debug('启动重建任务（后台进行）...');
                }
            }

            // 3. 轮询进度
            pollingInterval = setInterval(async () => {
                if (isCompleted) return;

                try {
                    const resp = await fetchWithTimeout('/api/rebuild-progress', {}, 10000);
                    if (!resp.ok) {
                        console.warn('获取进度失败');
                        return;
                    }

                    const data = await resp.json();
                    consecutiveFailures = 0;  // 成功获取，重置失败计数

                    // 先检查是否被取消或出错
                    if (data.error || (!data.in_progress && data.files_indexed === 0 && data.files_scanned === 0)) {
                        const isCancelled = data.error && (data.error === '用户取消' || (typeof data.error === 'string' && data.error.includes('取消')));
                        stopPolling();

                        updateRebuildUI(
                            100,
                            isCancelled ? '索引重建已取消' : '索引重建失败',
                            data.error || '',
                            isCancelled ? 'cancel' : 'error',
                            isCancelled ? 'fill-warning' : 'fill-error',
                            isCancelled ? 'warning' : 'error'
                        );

                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="${isCancelled ? 'text-warning' : 'text-danger'} fw-bold me-auto">
                                <i class="bi ${isCancelled ? 'bi-x-circle-fill' : 'bi-exclamation-circle-fill'}"></i> ${isCancelled ? '已取消' : '失败'}
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;

                        FileToolsUtils.showToast(isCancelled ? '索引重建已取消' : '索引重建失败: ' + data.error, isCancelled ? 'warning' : 'error');
                        return;
                    }

                    // 检查是否完成（正常完成）
                    if (!data.in_progress) {
                        stopPolling();

                        updateRebuildUI(
                            100,
                            '索引重建完成！',
                            `扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}`,
                            'success',
                            'fill-success',
                            'success'
                        );

                        modalFooter.style.display = 'flex';
                        modalFooter.innerHTML = `
                            <div class="text-success fw-bold me-auto">
                                <i class="bi bi-check-circle-fill"></i> 重建完成！
                            </div>
                            <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                        `;

                        // 1.5秒后自动关闭弹窗并提示
                        setTimeout(() => {
                            const modalEl = document.getElementById('rebuildIndexModal');
                            if (modalEl) {
                                FileToolsUtils.hideModal(modalEl);
                                FileToolsUtils.showToast('索引重建完成！', 'success');
                            }
                        }, 1500);
                        return;
                    }

                    // 更新进度条
                    const progress = data.progress || 0;
                    updateRebuildUI(
                        progress,
                        '正在重建索引...',
                        `扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}`,
                        'spinner',
                        '',
                        ''
                    );
                } catch (e) {
                    // 检查是否是连接被拒绝的错误（后端可能崩溃了）
                    const isConnectionRefused = e.message && (
                        e.message.includes('ERR_CONNECTION_REFUSED') ||
                        e.message.includes('Failed to fetch') ||
                        e.message.includes('net::ERR')
                    );

                    if (isConnectionRefused) {
                        consecutiveFailures++;
                        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
                            // 连续多次失败，判定后端崩溃
                            console.error('后端连续不可达，停止轮询:', e.message);
                            stopPolling();
                            updateRebuildUI(
                                100,
                                '后端连接失败',
                                '请检查后端服务是否正常运行',
                                'error',
                                'fill-error',
                                'error'
                            );
                            modalFooter.style.display = 'flex';
                            modalFooter.innerHTML = `
                                <div class="text-danger fw-bold me-auto">
                                    <i class="bi bi-exclamation-circle-fill"></i> 连接失败
                                </div>
                                <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                            `;
                            FileToolsUtils.showToast('后端连接失败，请重启应用', 'error');
                            return;
                        }
                        // 未达阈值，继续轮询
                        console.warn(`后端暂时不可达 (${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES})，继续轮询...`);
                    } else {
                        // 其他错误，继续轮询
                        console.warn('获取进度失败，继续轮询:', e.message);
                    }
                }
            }, 1000);  // 每秒轮询一次
        } catch (error) {
            console.error('Error rebuilding index:', error);
            stopPolling();
            updateRebuildUI(
                100,
                '索引重建失败',
                error.message || '请求失败',
                'error',
                'fill-error',
                'error'
            );
            closeBtn.style.display = 'block';
            modalFooter.style.display = 'flex';
            modalFooter.innerHTML = `
                <div class="text-danger fw-bold me-auto">
                    <i class="bi bi-exclamation-circle-fill"></i> 失败
                </div>
                <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
            `;
        }
    }

    /**
     * 更新滑块值显示
     * @param {string} sliderId - 滑块 ID
     * @param {string} displayId - 显示元素 ID
     */
    function updateSliderValue(sliderId, displayId) {
        const slider = document.getElementById(sliderId);
        const display = document.getElementById(displayId);
        if (slider && display) {
            display.innerText = slider.value;
        }
    }

    /**
     * 加载当前版本（不检查更新）
     */
    async function loadCurrentVersion() {
        const versionSpan = document.getElementById('currentVersion');
        if (!versionSpan) return;
        try {
            const versionRes = await fetchWithTimeout('/api/version', {}, 5000);
            const versionData = await versionRes.json();
            const version = versionData?.version;
            versionSpan.textContent = version ? `v${version}` : 'v1.0.0';
        } catch (e) {
            console.warn('获取版本失败:', e);
            versionSpan.textContent = 'v1.0.0';
        }
    }

    /**
     * 检查更新
     */
    async function checkForUpdate() {
        const btn = document.getElementById('checkUpdateBtn');
        const resultDiv = document.getElementById('updateResult');

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-arrow-repeat me-2 spin"></i>检查中...';
        }

        // 清除之前的自动隐藏定时器
        if (resultDiv.hideTimer) {
            clearTimeout(resultDiv.hideTimer);
        }

        try {
            const response = await fetchWithTimeout('/api/check-update', {}, 10000);
            const data = await response.json();

            // 检查响应是否正常（check-update API 失败时返回 503）
            if (!response.ok || data.detail) {
                resultDiv.className = 'small text-center alert alert-warning mt-3 mx-auto';
                resultDiv.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i>检查更新失败，请稍后重试`;
                resultDiv.style.display = 'block';
                // 5秒后自动隐藏
                resultDiv.hideTimer = setTimeout(() => { resultDiv.style.display = 'none'; }, 3000);
                return;
            }

            const latestVer = data.latest_version || data.current_version || '1.0.0';
            // 使用 DOMPurify 消毒 release_notes 和 download_url 防止 XSS
            const sanitizedNotes = DOMPurify.sanitize(data.release_notes || '', { ALLOWED_TAGS: ['b', 'i', 'br', 'p', 'ul', 'li', 'a'] });
            const sanitizedUrl = DOMPurify.sanitize(data.download_url || '#', { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
            if (data.is_update_available) {
                resultDiv.className = 'small text-center alert alert-success mt-3 mx-auto';
                resultDiv.innerHTML = `
                    <div class="fw-bold mb-2"><i class="bi bi-check-circle me-1"></i>发现新版本: v${latestVer}</div>
                    <div class="mb-2">${sanitizedNotes}</div>
                    <a href="${sanitizedUrl}" target="_blank" class="btn btn-sm btn-success">
                        <i class="bi bi-download me-1"></i>前往下载
                    </a>
                `;
                resultDiv.style.display = 'block';
                // 新版本提示不自动隐藏，等待用户操作
            } else {
                resultDiv.className = 'small text-center alert alert-secondary mt-3 mx-auto';
                resultDiv.innerHTML = `<i class="bi bi-check-circle me-1"></i>当前已是最新版本 (v${latestVer})`;
                resultDiv.style.display = 'block';
                // 5秒后自动隐藏
                resultDiv.hideTimer = setTimeout(() => { resultDiv.style.display = 'none'; }, 3000);
            }
        } catch (error) {
            console.error('检查更新失败:', error);
            resultDiv.className = 'small text-center alert alert-warning mt-3 mx-auto';
            resultDiv.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i>检查更新失败，请稍后重试`;
            resultDiv.style.display = 'block';
            // 5秒后自动隐藏
            resultDiv.hideTimer = setTimeout(() => { resultDiv.style.display = 'none'; }, 3000);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-arrow-repeat me-2"></i>检查更新';
            }
        }
    }

    /**
     * 初始化关于 tab 按钮
     */
    function initAboutButtons() {
        console.log('[initAboutButtons] START');
        console.log('[initAboutButtons] document.readyState:', document.readyState);

        // 检查 DOM 中所有按钮
        const allButtons = document.querySelectorAll('#v-pills-about button');
        console.log('[initAboutButtons] All buttons in #v-pills-about:', allButtons.length, allButtons);

        // 检查更新按钮
        const btn = document.getElementById('checkUpdateBtn');
        console.log('[initAboutButtons] checkUpdateBtn:', !!btn, btn ? btn.id : 'null');

        // GitHub 按钮
        const githubBtn = document.getElementById('githubBtn');
        console.log('[initAboutButtons] githubBtn:', !!githubBtn, githubBtn ? githubBtn.id : 'null');

        // Issue 按钮
        const issueBtn = document.getElementById('issueBtn');
        console.log('[initAboutButtons] issueBtn:', !!issueBtn, issueBtn ? issueBtn.id : 'null');

        if (btn) {
            btn.onclick = null;
            btn.addEventListener('click', function() {
                console.log('[initAboutButtons] checkUpdateBtn clicked!');
                checkForUpdate();
            });
        }

        if (githubBtn) {
            githubBtn.onclick = null;
            githubBtn.addEventListener('click', function(event) {
                console.log('[initAboutButtons] githubBtn clicked!');
                event.preventDefault();
                window.TauriAPI.openExternal('https://github.com/Dry-U/File-tools')
                    .catch(err => {
                        console.warn('[initAboutButtons] openExternal failed:', err);
                        window.open('https://github.com/Dry-U/File-tools', '_blank');
                    });
            });
        }

        if (issueBtn) {
            issueBtn.onclick = null;
            issueBtn.addEventListener('click', function(event) {
                console.log('[initAboutButtons] issueBtn clicked!');
                event.preventDefault();
                window.TauriAPI.openExternal('https://github.com/Dry-U/File-tools/issues')
                    .catch(err => {
                        console.warn('[initAboutButtons] openExternal failed:', err);
                        window.open('https://github.com/Dry-U/File-tools/issues', '_blank');
                    });
            });
        }
        console.log('[initAboutButtons] END');
    }

    // 公共 API
    return {
        loadSettings,
        getCurrentSettings,
        saveSettings,
        onProviderChange,
        testAPIConnection,
        initSettingsTabs,
        openSettingsModal,
        resetSettings,
        confirmReset,
        showRebuildModal,
        confirmRebuild,
        updateSliderValue,
        hasUnsavedChanges,
        checkForUpdate,
        initAboutButtons
    };
})();

// 全局暴露函数（向后兼容）
const loadSettings = FileToolsSettings.loadSettings;
const getCurrentSettings = FileToolsSettings.getCurrentSettings;
const saveSettings = FileToolsSettings.saveSettings;
const onProviderChange = FileToolsSettings.onProviderChange;
const testAPIConnection = FileToolsSettings.testAPIConnection;
const initSettingsTabs = FileToolsSettings.initSettingsTabs;
const openSettingsModal = FileToolsSettings.openSettingsModal;
const resetSettings = FileToolsSettings.resetSettings;
const confirmReset = FileToolsSettings.confirmReset;
const showRebuildModal = FileToolsSettings.showRebuildModal;
const confirmRebuild = FileToolsSettings.confirmRebuild;
const hasUnsavedChanges = FileToolsSettings.hasUnsavedChanges;
const checkForUpdate = FileToolsSettings.checkForUpdate;
const initAboutButtons = FileToolsSettings.initAboutButtons;