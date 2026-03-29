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
     * 优先使用 pywebview 原生对话框，降级到后端 Tkinter 方案
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
                    if (result.canceled) return;
                    if (result.success && result.path) {
                        selectedPath = result.path;
                    } else {
                        FileToolsUtils.showToast(result.message || '未选择目录', 'warning');
                        return;
                    }
                } catch (e) {
                    console.warn('pywebview 原生对话框失败，降级到后端方案:', e);
                    selectedPath = null;
                }
            }

            // 降级：通过后端 API 打开 Tkinter 对话框
            if (!selectedPath) {
                const browseResult = await fetch('/api/directories/browse', { method: 'POST' });
                const data = await browseResult.json();
                if (data.canceled) return;
                if (!data.path) {
                    FileToolsUtils.showToast('未选择目录', 'warning');
                    return;
                }
                selectedPath = data.path;
            }

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
            console.error('Browse and add directory error:', error);
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
                FileToolsUtils.showToast('目录已删除', 'success');
                await loadDirectories();
            } else {
                throw new Error(result.detail || '删除失败');
            }
        } catch (error) {
            console.error('Remove directory error:', error);
            FileToolsUtils.showToast('删除目录失败: ' + error.message, 'error');
        }
    }

    // 公共 API
    return {
        loadDirectories,
        renderDirectories,
        browseAndAddDirectory,
        removeDirectory
    };
})();

// 全局暴露函数（向后兼容）
const loadDirectories = FileToolsDirectory.loadDirectories;
const renderDirectories = FileToolsDirectory.renderDirectories;
const browseAndAddDirectory = FileToolsDirectory.browseAndAddDirectory;
const removeDirectory = FileToolsDirectory.removeDirectory;