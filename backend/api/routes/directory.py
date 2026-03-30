"""
目录管理相关路由
"""

import os
import sys
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends

from backend.api.models import (
    DirectoryPath,
    DirectoryResponse,
    BrowseResponse,
    DirectoriesListResponse,
    DirectoryInfo,
)
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.api.dependencies import (
    get_config_loader,
    get_file_monitor,
    get_file_scanner,
    get_index_manager,
)

logger = get_logger(__name__)
router = APIRouter()


def _normalize_path_list(paths: list) -> list:
    """
    规范化路径列表，处理字符串配置和绝对路径转换

    Args:
        paths: 路径列表或分号分隔的字符串

    Returns:
        规范化后的绝对路径列表
    """
    if isinstance(paths, str):
        paths = [p.strip() for p in paths.split(";") if p.strip()]
    return [os.path.abspath(str(p)) for p in paths]


def _validate_directory_path(path: str) -> tuple[bool, str]:
    """
    验证目录路径是否安全

    Args:
        path: 要验证的路径

    Returns:
        (是否有效, 错误信息)
    """
    if not path:
        return False, "路径不能为空"

    # 检查路径遍历攻击
    normalized = os.path.abspath(os.path.expanduser(path))

    # 检查是否是有效的文件系统路径格式
    try:
        Path(normalized).resolve()
    except (OSError, ValueError):
        return False, f"无效的路径格式: {path}"

    # Windows 特殊检查
    if sys.platform == "win32":
        # 禁止UNC路径（网络共享）除非明确允许
        if normalized.startswith("\\\\"):
            return False, "不支持网络共享路径"
        # 检查驱动器格式
        if len(normalized) >= 2 and normalized[1] == ":":
            drive = normalized[0].upper()
            if not drive.isalpha():
                return False, f"无效的驱动器号: {drive}"

    return True, normalized


def _estimate_file_count(path: str, max_count: int = 9999) -> int:
    """估算目录中的文件数量"""
    try:
        path_obj = Path(path)
        if not path_obj.exists() or not path_obj.is_dir():
            return 0

        count = 0
        for item in path_obj.rglob("*"):
            if item.is_file():
                count += 1
                if count >= max_count:
                    return max_count
        return count
    except Exception:
        return 0


@router.get("/directories")
async def get_directories(
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor=Depends(get_file_monitor),
) -> DirectoriesListResponse:
    """获取当前管理的目录列表"""
    try:
        # 获取扫描路径和监控目录
        scan_paths = _normalize_path_list(
            config_loader.get("file_scanner", "scan_paths", [])
        )
        monitored_dirs = _normalize_path_list(
            file_monitor.get_monitored_directories() if file_monitor else []
        )

        # 合并所有目录（去重）
        all_paths = set(scan_paths + monitored_dirs)

        # 构建目录信息列表
        directories = []
        for path in sorted(all_paths):
            exists = os.path.exists(path) and os.path.isdir(path)
            is_scanning = path in scan_paths
            is_monitoring = path in monitored_dirs
            file_count = _estimate_file_count(path) if exists else 0

            directories.append(
                DirectoryInfo(
                    path=path,
                    exists=exists,
                    is_scanning=is_scanning,
                    is_monitoring=is_monitoring,
                    file_count=file_count,
                )
            )

        return DirectoriesListResponse(directories=directories)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取目录列表错误: {str(e)}")
        raise HTTPException(
            status_code=500, detail="获取目录列表失败，请稍后重试"
        ) from e


@router.post("/directories")
async def add_directory(
    request: DirectoryPath,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor=Depends(get_file_monitor),
    file_scanner=Depends(get_file_scanner),
) -> DirectoryResponse:
    """添加新目录（同时添加为扫描路径和监控目录）"""
    try:
        path = request.path.strip('"').strip("'")

        # 验证路径安全性
        is_valid, result = _validate_directory_path(path)
        if not is_valid:
            raise HTTPException(status_code=400, detail=result)
        expanded_path = result

        # 验证路径存在性和类型
        if not os.path.exists(expanded_path):
            raise HTTPException(status_code=400, detail=f"路径不存在: {expanded_path}")
        if not os.path.isdir(expanded_path):
            raise HTTPException(
                status_code=400, detail=f"路径不是目录: {expanded_path}"
            )

        # 检查是否已存在
        scan_paths = _normalize_path_list(
            config_loader.get("file_scanner", "scan_paths", [])
        )
        existing_paths = scan_paths
        if expanded_path in existing_paths:
            return DirectoryResponse(
                status="success",
                message="目录已在列表中",
                path=expanded_path,
                needs_rebuild=False,
            )

        # 添加到扫描路径
        config_loader.add_scan_path(expanded_path)

        # 更新 file_scanner 的扫描路径
        if file_scanner:
            if hasattr(file_scanner, "scan_paths"):
                if expanded_path not in file_scanner.scan_paths:
                    file_scanner.scan_paths.append(expanded_path)

        # 添加到监控目录
        if file_monitor:
            file_monitor.add_monitored_directory(expanded_path)

        # 更新配置中的监控目录
        monitor_dirs = _normalize_path_list(
            config_loader.get("monitor", "directories", [])
        )

        if expanded_path not in monitor_dirs:
            monitor_dirs.append(expanded_path)
            config_loader.set("monitor", "directories", monitor_dirs)

        # 保存配置
        config_loader.save()

        return DirectoryResponse(
            status="success",
            message="目录已添加",
            path=expanded_path,
            needs_rebuild=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加目录错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加目录失败: {str(e)}")


@router.delete("/directories")
async def remove_directory(
    request: DirectoryPath,
    config_loader: ConfigLoader = Depends(get_config_loader),
    file_monitor=Depends(get_file_monitor),
    index_manager=Depends(get_index_manager),
) -> DirectoryResponse:
    """删除目录（同时从扫描路径和监控目录中移除，并清理索引）"""
    try:
        path = request.path.strip('"').strip("'")

        # 验证路径安全性
        is_valid, result = _validate_directory_path(path)
        if not is_valid:
            raise HTTPException(status_code=400, detail=result)
        expanded_path = result

        # 从扫描路径中移除
        config_loader.remove_scan_path(expanded_path)

        # 从监控目录中移除
        if file_monitor:
            file_monitor.remove_monitored_directory(expanded_path)

        # 更新配置中的监控目录
        monitor_dirs = _normalize_path_list(
            config_loader.get("monitor", "directories", [])
        )
        monitor_dirs = [d for d in monitor_dirs if d != expanded_path]
        config_loader.set("monitor", "directories", monitor_dirs)

        # 保存配置
        config_loader.save()

        # 清理该目录在索引中的文档
        if index_manager:
            try:
                index_manager.delete_documents_by_directory(expanded_path)
                logger.info(f"已从索引中删除目录 {expanded_path} 下的文档")
            except Exception as e:
                logger.warning(f"清理索引失败: {str(e)}")

        return DirectoryResponse(
            status="success",
            message="目录已删除",
            path=expanded_path,
            needs_rebuild=False,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除目录错误: {str(e)}")
        raise HTTPException(status_code=500, detail="删除目录失败，请稍后重试") from e


def _show_directory_dialog() -> str | None:
    """
    在线程中显示目录选择对话框

    Returns:
        选中的路径或 None（如果取消）
    """
    import tkinter as tk
    from tkinter import filedialog

    # 创建隐藏的Tk窗口
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        # 打开目录选择对话框
        selected_path = filedialog.askdirectory(parent=root, title="选择要添加的目录")
        return selected_path if selected_path else None
    finally:
        # 确保销毁Tk窗口
        root.destroy()


@router.post("/directories/browse")
async def browse_directory() -> BrowseResponse:
    """打开系统文件对话框选择目录"""
    try:
        # 在线程池中运行阻塞的Tkinter操作
        loop = asyncio.get_event_loop()
        selected_path = await loop.run_in_executor(None, _show_directory_dialog)

        if selected_path:
            return BrowseResponse(
                status="success", path=os.path.abspath(selected_path), canceled=False
            )
        else:
            return BrowseResponse(status="success", canceled=True)
    except Exception as e:
        logger.error(f"打开目录选择对话框错误: {str(e)}")
        raise HTTPException(
            status_code=500, detail="打开目录选择对话框失败，请稍后重试"
        ) from e
