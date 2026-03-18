/**
 * FileTools - 设置管理模块
 * 提供设置加载、保存、重置、API 测试等功能
 */

const FileToolsSettings = (function() {
    'use strict';

    let initialSettings = null;

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
            const response = await fetch('/api/config');
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
            setValue('topKInput', sampling.top_k ?? 40);
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

        // 安全设置
        if (config.ai_model && config.ai_model.security) {
            const verifySslCheck = document.getElementById('verifySslCheck');
            if (verifySslCheck) {
                verifySslCheck.checked = config.ai_model.security.verify_ssl ?? true;
            }
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
        
        return {
            ai_mode: document.getElementById('modeAPI')?.checked ? 'api' : 'local',
            ai_model: {
                mode: document.getElementById('modeAPI')?.checked ? 'api' : 'local',
                api: {
                    provider: provider,
                    api_url: getValue('apiUrlInput', ''),
                    model_name: getValue('modelNameInput', ''),
                    api_key: apiKey,
                    // 同时保存到 keys.{provider} 确保兼容
                    keys: {
                        siliconflow: provider === 'siliconflow' ? apiKey : '',
                        deepseek: provider === 'deepseek' ? apiKey : '',
                        custom: provider === 'custom' ? apiKey : ''
                    }
                },
                sampling: {
                    temperature: getFloat('tempRange', 0.7),
                    top_p: getFloat('topPRange', 0.9),
                    top_k: getInt('topKInput', 40),
                    min_p: getFloat('minPRange', 0.05),
                    max_tokens: getInt('maxTokensInput', 2048),
                    seed: getInt('seedInput', -1)
                },
                penalties: {
                    repeat_penalty: getFloat('repeatPenaltyRange', 1.1),
                    frequency_penalty: getFloat('freqPenaltyRange', 0.0),
                    presence_penalty: getFloat('presencePenaltyRange', 0.0)
                },
                security: {
                    verify_ssl: getChecked('verifySslCheck', true)
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
     * 保存设置
     */
    async function saveSettings() {
        const settings = getCurrentSettings();

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            if (response.ok) {
                FileToolsUtils.showToast('设置已保存', 'success');
                initialSettings = settings;
                FileToolsUtils.hideModal(document.getElementById('settingsModal'));
            } else {
                const error = await response.json();
                throw new Error(error.detail || '保存失败');
            }
        } catch (error) {
            console.error('保存设置失败:', error);
            FileToolsUtils.showToast('保存设置失败: ' + error.message, 'error');
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

        if (API_PROVIDER_DEFAULTS[provider]) {
            urlInput.value = API_PROVIDER_DEFAULTS[provider].url;
            modelInput.value = API_PROVIDER_DEFAULTS[provider].model;
        }
    }

    /**
     * 测试 API 连接 - 智能保存逻辑
     * - 配置有变化：测试成功后自动保存
     * - 配置无变化：直接测试
     */
    async function testAPIConnection() {
        const btn = document.getElementById('testConnectionBtn') || document.querySelector('[onclick="testAPIConnection()"]');
        const originalText = btn ? btn.innerHTML : '';
        
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
                const saveResponse = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentSettings)
                });

                if (!saveResponse.ok) {
                    throw new Error('保存配置失败');
                }
                
                // 更新 initialSettings
                initialSettings = currentSettings;
            }

            // 测试连接
            const response = await fetch('/api/model/test');
            const result = await response.json();

            if (result.status === 'ok') {
                const message = hasChanges 
                    ? `配置已保存<br>模式: ${result.mode}<br>模型: ${result.model}`
                    : `模式: ${result.mode}<br>模型: ${result.model}`;
                FileToolsUtils.showTestResultModal('连接成功', message, true);
            } else {
                FileToolsUtils.showTestResultModal('连接失败', result.error || '未知错误', false);
            }
        } catch (error) {
            FileToolsUtils.showTestResultModal('测试出错', error.message, false);
        } finally {
            if (btn) {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }
    }

    /**
     * 初始化设置面板 Tab 切换
     */
    function initSettingsTabs() {
        console.log('Initializing settings tabs...');
        const tabButtons = document.querySelectorAll('#v-pills-tab .nav-link');
        const tabPanes = document.querySelectorAll('#v-pills-tabContent .tab-pane');

        tabButtons.forEach(function (button) {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);

            newButton.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                const targetId = this.getAttribute('data-bs-target');
                if (!targetId) return;

                console.log('Tab clicked:', targetId);

                tabButtons.forEach(function (btn) {
                    btn.classList.remove('active');
                });
                tabPanes.forEach(function (pane) {
                    pane.classList.remove('show', 'active');
                });

                this.classList.add('active');

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

    /**
     * 打开设置模态框
     */
    function openSettingsModal() {
        console.log('openSettingsModal called');
        const modalEl = document.getElementById('settingsModal');
        if (modalEl) {
            console.log('Settings modal element found, loading settings...');
            loadSettings().then(function () {
                initialSettings = getCurrentSettings();
                console.log('Settings loaded, showing modal...');
                if (typeof FileToolsDirectory !== 'undefined') {
                    FileToolsDirectory.loadDirectories();
                }
                initSettingsTabs();
                FileToolsUtils.showModal(modalEl);
            }).catch(function (err) {
                console.error('Failed to load settings:', err);
                if (typeof FileToolsDirectory !== 'undefined') {
                    FileToolsDirectory.loadDirectories();
                }
                initSettingsTabs();
                FileToolsUtils.showModal(modalEl);
            });
        } else {
            console.error('Settings modal element not found!');
        }
    }

    /**
     * 恢复默认设置
     */
    function resetSettings() {
        const resetModalEl = document.getElementById('resetConfirmModal');
        FileToolsUtils.showModal(resetModalEl);
    }

    /**
     * 确认重置
     */
    function confirmReset() {
        // 采样参数
        document.getElementById('tempRange').value = 0.7;
        document.getElementById('tempValue').innerText = '0.7';
        document.getElementById('topPRange').value = 0.9;
        document.getElementById('topPValue').innerText = '0.9';
        document.getElementById('topKInput').value = 40;
        document.getElementById('minPRange').value = 0.05;
        document.getElementById('minPValue').innerText = '0.05';
        document.getElementById('maxTokensInput').value = 2048;
        document.getElementById('seedInput').value = -1;

        // 惩罚参数
        document.getElementById('repeatPenaltyRange').value = 1.1;
        document.getElementById('repeatPenaltyValue').innerText = '1.1';
        document.getElementById('freqPenaltyRange').value = 0.0;
        document.getElementById('freqPenaltyValue').innerText = '0.0';
        document.getElementById('presencePenaltyRange').value = 0.0;
        document.getElementById('presencePenaltyValue').innerText = '0.0';

        FileToolsUtils.hideModal(document.getElementById('resetConfirmModal'));
        FileToolsUtils.showToast('已恢复默认参数', 'success');
    }

    /**
     * 显示重建索引确认弹窗
     */
    function showRebuildModal() {
        const rebuildModalEl = document.getElementById('rebuildIndexModal');

        document.getElementById('rebuildModalBody').innerHTML = `
            <p class="mb-0 small">确定要重建文件索引吗？<br>这可能需要一些时间。</p>
        `;
        document.getElementById('rebuildModalFooter').innerHTML = `
            <button type="button" class="btn btn-sm btn-outline-secondary border-0" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-sm btn-primary px-3" id="rebuildConfirmBtn">确定</button>
        `;
        document.getElementById('rebuildCloseBtn').style.display = 'block';

        // 绑定确认按钮事件
        const confirmBtn = document.getElementById('rebuildConfirmBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                confirmRebuild();
            });
        }

        FileToolsUtils.showModal(rebuildModalEl);
    }

    /**
     * 确认重建索引
     */
    async function confirmRebuild() {
        const modalBody = document.getElementById('rebuildModalBody');
        const modalFooter = document.getElementById('rebuildModalFooter');
        const closeBtn = document.getElementById('rebuildCloseBtn');

        closeBtn.style.display = 'none';
        modalFooter.style.display = 'none';

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
            const safeErrorMessage = FileToolsUtils.escapeHtml(error.message || '请求失败');
            modalBody.innerHTML = `
                <i class="bi bi-x-circle-fill text-danger display-4 mb-3"></i>
                <p class="mb-0 small">索引重建失败</p>
                <p class="small text-muted mt-1">${safeErrorMessage}</p>
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
        hasUnsavedChanges
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