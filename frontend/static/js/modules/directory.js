/**
 * FileTools - 目录管理模块
 * 提供目录的加载、渲染、添加、删除等功能
 */

const FileToolsDirectory = (function() {
    'use strict';

    // 目录数据
    let directoriesData = { directories: [] };
    // 防止重复打开对话框
    let isBrowsing = false;
    // 待删除目录路径（用于模态框确认）
    let pendingDeletePath = null;

    /**
     * 加载目录列表
     */
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

    /**
     * 渲染目录列表
     */
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

        container.innerHTML = directoriesData.directories.map(function (item) {
            const existsClass = item.exists ? '' : 'exists-false';
            const iconClass = item.exists ? 'bi-folder-fill' : 'bi-folder-x';
            const fileCountText = item.exists ? `约 ${item.file_count} 个文件` : '路径不存在';
            const pathAttr = FileToolsUtils.escapeHtml(item.path).replace(/"/g, '&quot;');

            return `
                <div class="directory-item ${existsClass}" data-path="${pathAttr}">
                    <i class="bi ${iconClass} directory-icon"></i>
                    <div class="directory-info">
                        <div class="directory-path" title="${pathAttr}">${FileToolsUtils.escapeHtml(item.path)}</div>
                        <div class="directory-meta">${FileToolsUtils.escapeHtml(fileCountText)}</div>
                    </div>
                    <button class="directory-delete" data-path="${pathAttr}" title="删除目录">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
        }).join('');
    }

    /**
     * 浏览并添加目录
     * 优先使用 pywebview 原生对话框，降级到 Bootstrap 模态框
     */
    async function browseAndAddDirectory() {
        if (isBrowsing) return;
        isBrowsing = true;
        try {
            let selectedPath = null;

            // 优先使用 pywebview 原生文件对话框
            if (window.pywebview && window.pywebview.api && window.pywebview.api.select_directory) {
                try {
                    const result = await window.pywebview.api.select_directory();
                    if (result.canceled) {
                        isBrowsing = false;
                        return;
                    }
                    if (result.success && result.path) {
                        selectedPath = result.path;
                    } else {
                        FileToolsUtils.showToast(result.message || '未选择目录', 'warning');
                        isBrowsing = false;
                        return;
                    }
                } catch (e) {
                    console.warn('pywebview 原生对话框失败，降级到模态框:', e);
                }
            }

            // 降级：显示 Bootstrap 模态框让用户输入路径
            if (!selectedPath) {
                await showAddDirectoryModal();
                isBrowsing = false;
                return;
            }

            await addDirectoryByPath(selectedPath);
        } catch (error) {
            console.error('Browse and add directory error:', error);
            FileToolsUtils.showToast('添加目录失败: ' + error.message, 'error');
            isBrowsing = false;
        }
    }

    /**
     * 显示添加目录模态框
     */
    async function showAddDirectoryModal() {
        return new Promise((resolve) => {
            const modalEl = document.getElementById('addDirectoryModal');
            const inputEl = document.getElementById('addDirectoryPathInput');
            const confirmBtn = document.getElementById('confirmAddDirectoryBtn');
            const browseBtn = document.getElementById('browseDirectoryBtn');

            if (!modalEl || !inputEl) {
                console.error('Add directory modal not found');
                resolve();
                return;
            }

            // 清空输入框
            inputEl.value = '';

            // 显示模态框
            FileToolsUtils.showModal(modalEl);

            let confirmed = false;

            // 确认添加按钮点击事件
            const handleConfirm = async function() {
                const path = inputEl.value.trim();
                if (!path) {
                    FileToolsUtils.showToast('请输入目录路径', 'warning');
                    return;
                }
                confirmed = true;
                cleanup();
                FileToolsUtils.hideModal(modalEl);
                await addDirectoryByPath(path);
                resolve();
            };

            // 浏览按钮点击事件（尝试调用 pywebview 原生对话框）
            const handleBrowse = async function() {
                // 尝试使用 pywebview 原生对话框
                if (window.pywebview && window.pywebview.api && window.pywebview.api.select_directory) {
                    try {
                        const result = await window.pywebview.api.select_directory();
                        if (!result.canceled && result.success && result.path) {
                            inputEl.value = result.path;
                        }
                    } catch (e) {
                        console.warn('pywebview browse failed:', e);
                    }
                }
            };

            // 模态框关闭后清理
            const handleHidden = function() {
                cleanup();
                if (!confirmed) {
                    isBrowsing = false;
                    resolve();
                }
            };

            const cleanup = function() {
                confirmBtn.removeEventListener('click', handleConfirm);
                browseBtn.removeEventListener('click', handleBrowse);
                modalEl.removeEventListener('hidden.bs.modal', handleHidden);
            };

            modalEl.addEventListener('hidden.bs.modal', handleHidden);
            confirmBtn.addEventListener('click', handleConfirm);
            browseBtn.addEventListener('click', handleBrowse);

            // 自动聚焦输入框
            setTimeout(() => inputEl.focus(), 100);
        });
    }

    /**
     * 通过路径添加目录
     */
    async function addDirectoryByPath(selectedPath) {
        try {
            const response = await fetch('/api/directories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: selectedPath })
            });

            const resultData = await response.json();

            if (response.ok && resultData.status === 'success') {
                FileToolsUtils.showToast('目录已添加', 'success');

                if (resultData.needs_rebuild) {
                    if (confirm('目录已添加，是否立即重建索引？\n这将扫描新添加目录中的文件。')) {
                        if (typeof FileToolsSettings !== 'undefined') {
                            FileToolsSettings.showRebuildModal();
                        }
                    }
                }

                await loadDirectories();
            } else {
                throw new Error(resultData.detail || '添加失败');
            }
        } catch (error) {
            console.error('Add directory error:', error);
            FileToolsUtils.showToast('添加目录失败: ' + error.message, 'error');
        } finally {
            isBrowsing = false;
        }
    }

    /**
     * 删除目录
     * @param {string} path - 目录路径
     */
    async function removeDirectory(path) {
        if (!path) return;

        // 使用 Bootstrap 模态框确认删除
        pendingDeletePath = path;
        const modalEl = document.getElementById('deleteDirectoryModal');
        if (modalEl) {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        } else {
            // 降级：使用原生确认框
            if (!confirm('确定要删除这个目录吗？\n该目录将不再被扫描和监控。')) {
                return;
            }
            doDeleteDirectory(path);
        }
    }

    /**
     * 执行删除目录（由模态框按钮调用）
     */
    async function doDeleteDirectory(path) {
        try {
            const modalEl = document.getElementById('deleteDirectoryModal');

            const response = await fetch('/api/directories', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                FileToolsUtils.showToast('目录已删除', 'success');
                // 隐藏模态框
                if (modalEl) {
                    FileToolsUtils.hideModal(modalEl);
                }
                await loadDirectories();
            } else {
                throw new Error(result.detail || '删除失败');
            }
        } catch (error) {
            console.error('Remove directory error:', error);
            FileToolsUtils.showToast('删除目录失败: ' + error.message, 'error');
        }
    }

    /**
     * 初始化目录相关模态框事件
     */
    function initDeleteModalEvents() {
        const modalEl = document.getElementById('deleteDirectoryModal');
        if (modalEl) {
            // 模态框关闭后清除 pendingDeletePath
            modalEl.addEventListener('hidden.bs.modal', function() {
                pendingDeletePath = null;
            });
        }
    }

    // 公共 API
    return {
        loadDirectories,
        renderDirectories,
        browseAndAddDirectory,
        removeDirectory,
        doDeleteDirectory,
        initDeleteModalEvents,
        // 暴露 pendingDeletePath 的存取器
        get pendingDeletePath() { return pendingDeletePath; },
        set pendingDeletePath(v) { pendingDeletePath = v; }
    };
})();

// 全局暴露函数（向后兼容）
const loadDirectories = FileToolsDirectory.loadDirectories;
const renderDirectories = FileToolsDirectory.renderDirectories;
const browseAndAddDirectory = FileToolsDirectory.browseAndAddDirectory;
const removeDirectory = FileToolsDirectory.removeDirectory;
const doDeleteDirectory = FileToolsDirectory.doDeleteDirectory;