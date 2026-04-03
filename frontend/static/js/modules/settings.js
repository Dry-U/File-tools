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
                    top_k: getInt('topKInput', 40),
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
     * 保存设置
     */
    async function saveSettings() {
        // 先检查是否有未保存的更改
        if (!hasUnsavedChanges()) {
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

        const settings = getCurrentSettings();

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                FileToolsUtils.hideModal(document.getElementById('settingsModal'));
                setTimeout(function() {
                    FileToolsUtils.showToast('设置已保存', 'success');
                }, 300);
                initialSettings = getCurrentSettings();
                // 重新缓存 provider keys
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
    let _tabsInitialized = false;
    function initSettingsTabs() {
        if (_tabsInitialized) {
            // 已初始化过，仅重置到第一个 tab
            const firstTab = document.querySelector('#v-pills-tab .nav-link');
            if (firstTab && !firstTab.classList.contains('active')) {
                firstTab.click();
            }
            return;
        }
        _tabsInitialized = true;
        console.log('Initializing settings tabs...');

        document.querySelectorAll('#v-pills-tab .nav-link').forEach(function (button) {
            button.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                const targetId = this.getAttribute('data-bs-target');
                if (!targetId) return;

                console.log('Tab clicked:', targetId);

                // 使用实时 DOM 查询，确保操作的是当前 DOM 中的节点
                document.querySelectorAll('#v-pills-tab .nav-link').forEach(function (btn) {
                    btn.classList.remove('active');
                });
                document.querySelectorAll('#v-pills-tabContent .tab-pane').forEach(function (pane) {
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

        console.log('Settings tabs initialized');
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

        // API 设置重置
        document.getElementById('apiProviderSelect').value = 'siliconflow';
        document.getElementById('apiUrlInput').value = 'https://api.siliconflow.cn/v1/chat/completions';
        document.getElementById('apiKeyInput').value = '';
        document.getElementById('modelNameInput').value = 'deepseek-ai/DeepSeek-V2.5';

        // 模式重置为本地
        document.getElementById('modeLocal').checked = true;
        document.getElementById('modeAPI').checked = false;
        document.getElementById('localSettings').style.display = 'block';
        document.getElementById('apiSettings').style.display = 'none';

        // 本地 API URL 重置
        document.getElementById('localApiUrlInput').value = 'http://localhost:8000/v1/chat/completions';

        // RAG 设置重置
        document.getElementById('ragTopKInput').value = 5;
        document.getElementById('ragContextLengthInput').value = 2048;

        // 搜索设置重置
        document.getElementById('searchTextWeightInput').value = 0.6;
        document.getElementById('searchVectorWeightInput').value = 0.4;

        // 更新缓存的 provider keys
        cachedProviderKeys = { siliconflow: '', deepseek: '', custom: '' };

        // 更新 initialSettings 以反映重置后的状态
        initialSettings = getCurrentSettings();

        FileToolsUtils.hideModal(document.getElementById('resetConfirmModal'));
        FileToolsUtils.showToast('已恢复默认参数', 'success');
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

        FileToolsUtils.showModal(rebuildModalEl);
    }

    /**
     * 取消重建索引
     */
    async function cancelRebuild() {
        try {
            const response = await fetch('/api/rebuild-index', {
                method: 'DELETE'
            });
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
        closeBtn.onclick = cancelRebuild;
        modalFooter.style.display = 'none';

        let eventSource = null;

        // 显示进度条UI
        modalBody.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <div class="progress mb-2" style="height: 20px;">
                    <div id="rebuildProgressBar" class="progress-bar progress-bar-striped progress-bar-animated"
                         role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                </div>
                <p id="rebuildStatus" class="mb-0 small text-muted">正在准备重建索引...</p>
                <p id="rebuildFileCount" class="small text-muted mt-1"></p>
            </div>
        `;

        try {
            // 使用SSE流式接口
            eventSource = new EventSource('/api/rebuild-index/stream');

            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);

                    if (data.status === 'success') {
                        // 重建完成
                        const progressBar = document.getElementById('rebuildProgressBar');
                        progressBar.style.width = '100%';
                        progressBar.textContent = '100%';
                        progressBar.className = 'progress-bar bg-success';

                        document.getElementById('rebuildStatus').textContent = '索引重建完成！';
                        document.getElementById('rebuildFileCount').textContent =
                            `扫描: ${data.files_scanned || 0} | 索引: ${data.files_indexed || 0}`;

                        eventSource.close();

                        // 3秒后自动关闭
                        setTimeout(() => {
                            closeBtn.style.display = 'block';
                            closeBtn.onclick = null;
                            modalFooter.style.display = 'flex';
                            modalFooter.innerHTML = `
                                <button type="button" class="btn btn-sm btn-primary px-3" data-bs-dismiss="modal">关闭</button>
                            `;
                        }, 2000);

                    } else if (data.status === 'progress') {
                        // 更新进度条
                        const progress = data.progress || 0;
                        const progressBar = document.getElementById('rebuildProgressBar');
                        if (progressBar) {
                            progressBar.style.width = progress + '%';
                            progressBar.textContent = progress + '%';
                        }
                        document.getElementById('rebuildStatus').textContent = '正在重建索引... ' + progress + '%';

                    } else if (data.status === 'error') {
                        throw new Error(data.error || '重建索引失败');
                    } else if (data.status === 'heartbeat') {
                        // 心跳包，不需要处理
                    }
                } catch (e) {
                    console.error('SSE解析错误:', e);
                }
            };

            eventSource.onerror = function(event) {
                console.error('SSE连接错误:', event);
                // 如果是完成后的错误（已完成时会关闭连接），不显示错误
                if (event.target.readyState === EventSource.CLOSED) {
                    return;
                }

                // 降级到普通请求
                eventSource.close();
                performFallbackRebuild(modalBody, modalFooter, closeBtn);
            };

        } catch (error) {
            console.error('Error rebuilding index:', error);
            // 降级到普通请求
            performFallbackRebuild(modalBody, modalFooter, closeBtn);
        }

        // 添加模态框关闭事件监听，以便在用户点击X或外部区域时取消重建
        const handleModalHidden = function() {
            if (eventSource) {
                eventSource.close();
            }
            // 如果重建正在进行中，发送取消请求
            if (closeBtn.onclick === cancelRebuild) {
                cancelRebuild();
            }
            closeBtn.onclick = null;
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
            const response = await fetch('/api/rebuild-index', {
                method: 'POST'
            });
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