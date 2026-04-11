#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件监控器模块 - 监控文件系统变化（高性能版本）"""

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from backend.core.index_manager import IndexManager


class FileMonitor:
    """文件监控器类，负责监控指定目录的文件变化（支持并行事件处理）"""

    # 默认配置
    DEFAULT_MAX_WORKERS = 2  # 默认并行处理线程数
    DEFAULT_BUFFER_TIMEOUT = 0.1  # 事件缓冲超时时间（秒），降低延迟

    def __init__(self, config_loader, index_manager=None, file_scanner=None):
        self.config_loader = config_loader
        self.index_manager: Optional["IndexManager"] = index_manager
        self.file_scanner = file_scanner
        self.logger = logging.getLogger(__name__)

        # 监控配置 - 使用ConfigLoader获取配置
        self.monitored_dirs = self._get_monitored_directories()
        self.ignored_patterns = self._get_ignored_patterns()
        monitor_config = config_loader.get("monitor")
        if monitor_config is None:
            monitor_config = {}
        self.refresh_interval = int(monitor_config.get("refresh_interval", 1))

        # 并行处理配置
        try:
            self.max_workers = max(
                1,
                min(
                    int(monitor_config.get("max_workers", self.DEFAULT_MAX_WORKERS)), 4
                ),
            )
        except Exception:
            self.max_workers = self.DEFAULT_MAX_WORKERS

        # 读取防抖时间配置
        try:
            debounce_time = float(
                monitor_config.get("debounce_time", self.DEFAULT_BUFFER_TIMEOUT)
            )
            self._buffer_timeout = max(
                0.05, min(debounce_time, 1.0)
            )  # 限制在0.05-1.0秒
        except Exception:
            self._buffer_timeout = self.DEFAULT_BUFFER_TIMEOUT

        # 读取最大递归深度配置
        try:
            self._max_depth = int(monitor_config.get("max_depth", 3))
            self._max_depth = max(1, min(self._max_depth, 10))  # 限制在1-10层
        except Exception:
            self._max_depth = 3

        # 读取自动排除阈值配置（文件数超过此值自动排除）
        try:
            self._auto_exclude_threshold = int(
                monitor_config.get("auto_exclude_threshold", 5000)
            )
            self._auto_exclude_threshold = max(
                100, min(self._auto_exclude_threshold, 50000)
            )
        except Exception:
            self._auto_exclude_threshold = 5000

        # 读取最大监控文件数
        try:
            self._max_files = int(monitor_config.get("max_files", 10000))
            self._max_files = max(1000, min(self._max_files, 100000))
        except Exception:
            self._max_files = 10000

        # 初始化监控器
        self.observer = None
        self.handler = None
        self.is_running = False

        # 用于去重和防抖（线程安全）
        self._event_buffer = {}
        self._buffer_lock = (
            threading.Lock()
        )  # 保护 _event_buffer 和 _last_process_time 的锁
        self._last_process_time = time.time()

        # 并行处理线程池
        self._executor: Optional[ThreadPoolExecutor] = None

        # 处理统计
        self._processed_count = 0
        self._dropped_count = 0

        # 过滤并验证监控目录
        self.monitored_dirs = self._filter_monitored_directories(self.monitored_dirs)

        if self.monitored_dirs:
            dirs_str = ", ".join(self.monitored_dirs)
            init_msg = (
                f"文件监控器初始化完成，监控目录: {dirs_str}, "
                f"并行线程: {self.max_workers}, 缓冲超时: {self._buffer_timeout}s, "
                f"最大深度: {self._max_depth}, "
                f"自动排除阈值: {self._auto_exclude_threshold}文件"
            )
            self.logger.info(init_msg)
        else:
            self.logger.info("文件监控器初始化完成，未启用监控（无配置目录）")

    def _get_monitored_directories(self):
        """从配置中获取需要监控的目录"""
        monitored_dirs = []

        # 从配置中获取监控目录 - 使用ConfigLoader
        try:
            # 使用ConfigLoader获取monitor配置
            monitor_config = self.config_loader.get("monitor")
            if monitor_config is None:
                monitor_config = {}
            config_dirs = monitor_config.get("directories", "")
        except Exception as e:
            self.logger.error(f"获取监控目录配置失败: {str(e)}")
            config_dirs = ""

        if config_dirs:
            # Handle both list and string types for config_dirs
            if isinstance(config_dirs, list):
                dir_list = config_dirs
            else:
                # 分割配置中的目录列表
                dir_list = config_dirs.split(";")

            for dir_path in dir_list:
                dir_path = str(dir_path).strip()
                if dir_path and os.path.exists(dir_path):
                    monitored_dirs.append(os.path.abspath(dir_path))

        # 如果没有配置监控目录，默认关闭监控
        # 用户需要显式配置监控目录以启用此功能
        if not monitored_dirs:
            self.logger.info(
                "未配置监控目录，文件监控功能已禁用。请在配置中显式指定监控目录以启用。"
            )

        return monitored_dirs

    def _filter_monitored_directories(self, monitored_dirs):
        """过滤监控目录，排除超过深度和文件数限制的目录"""
        filtered_dirs = []

        for dir_path in monitored_dirs:
            # 检查目录深度
            try:
                depth = self._get_directory_depth(dir_path, self._max_depth)
                if depth > self._max_depth:
                    warn_msg = (
                        f"目录 {dir_path} 深度({depth})超过最大限制"
                        f"({self._max_depth})，将限制监控深度"
                    )
                    self.logger.warning(warn_msg)
            except Exception as e:
                self.logger.debug(f"检查目录深度失败 {dir_path}: {e}")

            # 检查文件数量
            try:
                file_count = self._count_files_in_directory(
                    dir_path, max_count=self._auto_exclude_threshold
                )
                if file_count >= self._auto_exclude_threshold:
                    warn_msg = (
                        f"目录 {dir_path} 文件数量({file_count})超过阈值"
                        f"({self._auto_exclude_threshold})，跳过监控此目录以避免性能问题"
                    )
                    self.logger.warning(warn_msg)
                    continue  # 跳过此目录
            except Exception as e:
                self.logger.debug(f"统计目录文件数失败 {dir_path}: {e}")

            filtered_dirs.append(dir_path)

        return filtered_dirs

    def _get_directory_depth(self, dir_path, max_check_depth=10):
        """获取目录的实际深度"""
        max_depth = 0
        try:
            for root, dirs, files in os.walk(dir_path):
                # 计算当前深度
                current_depth = root.count(os.sep) - dir_path.count(os.sep)
                max_depth = max(max_depth, current_depth)
                if max_depth >= max_check_depth:
                    return max_depth  # 提前返回，避免遍历太深
                # 限制遍历的子目录数量
                if len(dirs) > 100:
                    dirs[:] = dirs[:100]  # 只遍历前100个子目录
        except Exception:
            pass
        return max_depth

    def _count_files_in_directory(self, dir_path, max_count=5000):
        """统计目录中的文件数量（带上限，避免长时间遍历）"""
        count = 0
        try:
            for root, dirs, files in os.walk(dir_path):
                count += len(files)
                if count >= max_count:
                    return count  # 提前返回
                # 限制遍历的子目录数量
                if len(dirs) > 100:
                    dirs[:] = dirs[:100]
        except Exception:
            pass
        return count

    def _get_ignored_patterns(self):
        """从配置中获取需要忽略的文件模式"""
        ignored_patterns = set()

        # 从配置中获取忽略模式 - 使用ConfigLoader
        monitor_config = self.config_loader.get("monitor")
        if monitor_config is None:
            monitor_config = {}
        config_patterns = monitor_config.get("ignored_patterns", "")
        if config_patterns:
            for pattern in config_patterns.split(";"):
                pattern = pattern.strip()
                if pattern:
                    ignored_patterns.add(pattern)

        # 添加默认的忽略模式
        default_ignored = {
            ".git",
            ".svn",
            ".hg",
            "__pycache__",
            ".idea",
            ".vscode",
            "node_modules",
            "venv",
            "env",
            ".DS_Store",
            "Thumbs.db",
            ".cache",
            ".log",
            ".tmp",
            ".temp",
            ".bak",
            "~$",
            # 用户目录下的常见大文件夹/应用数据
            "Rainmeter",
            "Tencent Files",
            "nt_qq",
            "WeChat Files",
            "OneDrive",
            "Dropbox",
            ".nuget",
            ".gradle",
            ".m2",
            ".npm",
            ".yarn",
            "AppData",
            "ProgramData",
            "System Volume Information",
            "$Recycle.Bin",
            # 游戏平台
            "Steam",
            "Epic Games",
            "Origin",
            "Battle.net",
            # 开发工具缓存
            ".angular",
            ".next",
            "dist",
            "build",
            "target",
            "out",
            ".nuxt",
            ".output",
        }
        ignored_patterns.update(default_ignored)

        return ignored_patterns

    def start_monitoring(self):
        """开始监控文件系统变化（使用线程池优化）"""
        if self.is_running:
            self.logger.warning("监控器已经在运行中")
            return

        try:
            # 确保之前的线程池已正确关闭（防止重复创建）
            if self._executor is not None:
                try:
                    self._executor.shutdown(wait=True)
                except Exception as e:
                    self.logger.warning(f"关闭旧线程池时出错: {e}")
                self._executor = None

            # 初始化线程池
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._processed_count = 0
            self._dropped_count = 0

            # 初始化事件处理器
            self.handler = FileChangeHandler(self, self.ignored_patterns)

            # 初始化监控器
            self.observer = Observer()

            # 添加需要监控的目录
            for dir_path in self.monitored_dirs:
                self.observer.schedule(self.handler, dir_path, recursive=True)

            # 启动监控器
            self.observer.start()
            self.is_running = True

            self.logger.info(
                f"文件监控已启动，监控 {len(self.monitored_dirs)} 个目录，"
                f"并行线程: {self.max_workers}"
            )
        except Exception as e:
            self.logger.error(f"启动文件监控失败: {str(e)}")
            self.is_running = False
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None
            if self.observer:
                try:
                    self.observer.stop()
                    self.observer.join()
                except (OSError, RuntimeError):
                    pass

    def stop_monitoring(self):
        """停止监控文件系统变化"""
        if not self.is_running:
            self.logger.warning("监控器尚未启动")
            return

        try:
            # 停止监控器
            if self.observer:
                self.observer.stop()
                self.observer.join()

            # 关闭线程池
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None

            self.is_running = False
            self.logger.info(
                f"文件监控已停止，处理了 {self._processed_count} 个事件，"
                f"丢弃了 {self._dropped_count} 个重复事件"
            )
        except Exception as e:
            self.logger.error(f"停止文件监控失败: {str(e)}")

    def process_event(self, event):
        """处理文件系统事件"""
        # 检查是否需要忽略此事件
        if self._should_ignore(event):
            return

        # 获取事件路径
        event_path = event.src_path
        event_type = event.event_type

        # 记录事件
        self.logger.debug(f"接收到文件系统事件: {event_type} - {event_path}")

        # 将事件添加到缓冲区（线程安全）
        events_to_process = []
        with self._buffer_lock:
            # 列表存储，同一路径的所有事件都不丢失
            event_info = {
                "type": event_type,
                "path": event_path,
                "timestamp": time.time(),
            }
            self._event_buffer.setdefault(event_path, []).append(event_info)

            # 缓冲区大小限制，防止内存溢出（最多 5000 条事件）
            total_events = sum(len(events) for events in self._event_buffer.values())
            if total_events > 5000:
                # 清空最旧的事件（按时间戳排序，保留最新的 3000 条）
                all_events = []
                for path, path_events in self._event_buffer.items():
                    all_events.extend(path_events)
                all_events.sort(key=lambda x: x["timestamp"])
                kept_events = all_events[-3000:]
                self._event_buffer.clear()
                for event in kept_events:
                    self._event_buffer.setdefault(event["path"], []).append(event)
                self.logger.warning(f"缓冲区超限，已清理至 5000 条事件")

            # 定期处理缓冲区中的事件（防抖）
            current_time = time.time()
            if current_time - self._last_process_time >= self._buffer_timeout:
                self._last_process_time = current_time
                # 复制需要处理的事件（展平列表）
                for path, path_events in list(self._event_buffer.items()):
                    for event_info in path_events:
                        if (
                            current_time - event_info["timestamp"]
                            >= self._buffer_timeout
                        ):
                            events_to_process.append(event_info)
                # 清空缓冲区
                self._event_buffer.clear()

        # 处理事件（不在锁内）
        if events_to_process:
            self._process_buffered_events(events_to_process)

    def _should_ignore(self, event):
        """检查是否应该忽略某个事件"""
        # 获取事件路径
        event_path = event.src_path

        # 检查路径深度
        try:
            # 找到对应的监控目录
            for monitored_dir in self.monitored_dirs:
                if event_path.startswith(monitored_dir):
                    # 计算相对深度
                    rel_path = os.path.relpath(event_path, monitored_dir)
                    depth = rel_path.count(os.sep) + (1 if event.is_directory else 0)
                    if depth > self._max_depth:
                        debug_msg = (
                            f"路径深度({depth})超过限制({self._max_depth})，"
                            f"忽略: {event_path}"
                        )
                        self.logger.debug(debug_msg)
                        return True
                    break
        except Exception:
            pass

        # 检查是否为目录
        if event.is_directory:
            # 检查目录是否在忽略列表中
            for pattern in self.ignored_patterns:
                if pattern in os.path.basename(event_path):
                    return True

        # 检查文件是否在忽略列表中
        for pattern in self.ignored_patterns:
            if event_path.endswith(pattern) or pattern in os.path.basename(event_path):
                return True

        return False

    def _process_buffered_events(self, events_to_process: List[Dict]):
        """处理已缓冲的事件（使用线程池并行处理）"""
        if not events_to_process:
            return

        # 使用线程池并行处理事件
        if events_to_process:
            if self._executor:
                try:
                    # 提交所有事件到线程池
                    futures = [
                        self._executor.submit(self._handle_event, event_info)
                        for event_info in events_to_process
                    ]
                    # 等待所有任务完成
                    for future in futures:
                        try:
                            future.result(timeout=5.0)
                        except Exception as e:
                            self.logger.debug(f"事件处理失败: {e}")
                except RuntimeError as e:
                    # 线程池已关闭，忽略此批次的事件
                    self.logger.debug(
                        f"线程池已关闭，跳过 {len(events_to_process)} 个事件: {e}"
                    )
                    self._dropped_count += len(events_to_process)
            else:
                # 线程池未初始化，串行处理
                for event_info in events_to_process:
                    self._handle_event(event_info)

            self._processed_count += len(events_to_process)
            self.logger.debug(f"处理了 {len(events_to_process)} 个文件系统事件")

    def _handle_event(self, event_info):
        """处理单个文件系统事件"""
        event_type = event_info["type"]
        event_path = event_info["path"]

        try:
            # 添加文件存在性检查延迟，防止文件操作未完成
            import time

            max_retries = 3
            retry_delay = 0.1

            # 对于新建和修改事件，等待文件操作完成
            if event_type in ("created", "modified"):
                for attempt in range(max_retries):
                    if os.path.exists(event_path) and os.path.isfile(event_path):
                        try:
                            # 对于刚创建/修改的文件，等待一下确保写入完成
                            time.sleep(retry_delay)
                            break
                        except OSError:
                            if attempt == max_retries - 1:
                                self.logger.warning(
                                    f"无法访问文件，跳过处理 {event_path}"
                                )
                                return
                            time.sleep(retry_delay)
                    else:
                        if attempt == max_retries - 1:
                            # 降低日志级别为debug，减少启动时的警告
                            self.logger.debug(
                                f"文件不存在或不是常规文件，跳过处理 {event_path}"
                            )
                            return
                        time.sleep(retry_delay)

            # 根据事件类型执行相应操作
            if event_type in ("created", "modified"):
                # 确保文件存在
                if os.path.exists(event_path) and os.path.isfile(event_path):
                    # 更新索引
                    self._update_index_for_file(event_path)
            elif event_type == "deleted":
                # 从索引中删除
                self._remove_from_index(event_path)
            elif event_type == "moved":
                # 注意：这里简化处理，实际上应该处理移动源路径和目标路径
                # 为简化，我们假设这是一个重命名操作，先删除旧路径，再添加新路径
                if "dest_path" in event_info:
                    dest_path = event_info["dest_path"]
                    if os.path.exists(dest_path) and os.path.isfile(dest_path):
                        self._remove_from_index(event_path)
                        self._update_index_for_file(dest_path)
        except Exception as e:
            self.logger.error(
                f"处理文件系统事件失败 {event_type} - {event_path}: {str(e)}"
            )
            import traceback

            self.logger.error(f"详细错误信息: {traceback.format_exc()}")

    def _update_index_for_file(self, file_path):
        """更新文件在索引中的信息"""
        if self.file_scanner:
            try:
                self.file_scanner.index_file(file_path)
                self.logger.debug(f"已通过FileScanner更新文件索引: {file_path}")
                return
            except Exception as e:
                self.logger.error(f"FileScanner更新索引失败 {file_path}: {str(e)}")

        if self.index_manager is None:
            self.logger.warning(f"索引管理器未初始化，跳过文件索引更新: {file_path}")
            return

        try:
            # 构建文档对象（模拟FileScanner中的逻辑）
            from datetime import datetime
            from pathlib import Path

            file_path_obj = Path(file_path)

            # 获取文件基本信息
            stat_info = file_path_obj.stat()
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)

            # 获取文件扩展名
            file_ext = file_path_obj.suffix.lower()

            # 简单的文件类型分类
            if file_ext in [
                ".txt",
                ".md",
                ".json",
                ".xml",
                ".csv",
                ".log",
                ".py",
                ".js",
                ".java",
                ".cpp",
                ".c",
                ".h",
            ]:
                file_type = "document"
            elif file_ext in [".zip", ".rar", ".7z", ".tar", ".gz"]:
                file_type = "archive"
            else:
                file_type = "unknown"

            # 读取文件内容（简化处理）
            content = file_path_obj.name  # 默认使用文件名作为内容
            try:
                # 对于文本类文件，尝试读取内容
                if file_ext in [
                    ".txt",
                    ".md",
                    ".json",
                    ".xml",
                    ".csv",
                    ".log",
                    ".py",
                    ".js",
                    ".java",
                    ".cpp",
                    ".c",
                    ".h",
                ]:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(1000)  # 限制读取内容大小
            except Exception:
                pass  # 保持默认内容

            # 构建文档字典
            document = {
                "path": str(file_path),
                "filename": file_path_obj.name,
                "content": content,
                "file_type": file_type,
                "size": file_size,
                "created": created_time,
                "modified": modified_time,
                "keywords": "",
            }

            # 调用索引管理器更新文件索引
            self.index_manager.update_document(document)
            self.logger.debug(f"已更新文件索引: {file_path}")
        except Exception as e:
            self.logger.error(f"更新文件索引失败 {file_path}: {str(e)}")

    def _remove_from_index(self, file_path):
        """从索引中删除文件"""
        if self.index_manager is None:
            self.logger.warning(f"索引管理器未初始化，跳过文件索引删除: {file_path}")
            return

        try:
            # 调用索引管理器删除文件索引
            self.index_manager.delete_document(file_path)
            self.logger.debug(f"已从索引中删除文件: {file_path}")
        except Exception as e:
            self.logger.error(f"从索引中删除文件失败 {file_path}: {str(e)}")

    def is_monitoring(self):
        """检查监控器是否正在运行"""
        return self.is_running

    def get_monitored_directories(self):
        """获取正在监控的目录列表"""
        return self.monitored_dirs.copy()

    def add_monitored_directory(self, dir_path):
        """添加一个新的监控目录"""
        if not os.path.isdir(dir_path):
            self.logger.error(f"添加监控目录失败: {dir_path} 不是有效的目录")
            return False

        dir_path = os.path.abspath(dir_path)

        # 检查目录是否已经在监控列表中
        if dir_path in self.monitored_dirs:
            self.logger.warning(f"目录已经在监控列表中: {dir_path}")
            return True

        try:
            # 添加到监控列表
            self.monitored_dirs.append(dir_path)

            # 如果监控器正在运行，更新监控器
            if self.is_running and self.observer and self.handler:
                self.observer.schedule(self.handler, dir_path, recursive=True)

            self.logger.info(f"已添加监控目录: {dir_path}")
            return True
        except Exception as e:
            self.logger.error(f"添加监控目录失败 {dir_path}: {str(e)}")
            # 如果添加失败，从列表中移除
            if dir_path in self.monitored_dirs:
                self.monitored_dirs.remove(dir_path)
            return False

    def remove_monitored_directory(self, dir_path):
        """移除一个监控目录"""
        dir_path = os.path.abspath(dir_path)

        # 检查目录是否在监控列表中（Windows 下大小写不敏感）
        found = False
        if sys.platform == "win32":
            dir_path_lower = dir_path.lower()
            for i, existing in enumerate(self.monitored_dirs):
                if existing.lower() == dir_path_lower:
                    self.monitored_dirs.pop(i)
                    found = True
                    break
        else:
            if dir_path in self.monitored_dirs:
                self.monitored_dirs.remove(dir_path)
                found = True

        if not found:
            self.logger.warning(f"目录不在监控列表中: {dir_path}")
            return True

        try:
            # 如果监控器正在运行，更新监控器
            if self.is_running and self.observer and self.handler:
                # 注意：这里简化处理，实际上需要重新安排所有监控目录
                # 为了简化，我们停止并重新启动监控器
                self.stop_monitoring()
                self.start_monitoring()

            self.logger.info(f"已移除监控目录: {dir_path}")
            return True
        except Exception as e:
            self.logger.error(f"移除监控目录失败 {dir_path}: {str(e)}")
            # 如果移除失败，重新添加到列表（使用大小写安全检查）
            if sys.platform == "win32":
                dir_path_lower = dir_path.lower()
                if not any(p.lower() == dir_path_lower for p in self.monitored_dirs):
                    self.monitored_dirs.append(dir_path)
            else:
                if dir_path not in self.monitored_dirs:
                    self.monitored_dirs.append(dir_path)
            return False


class FileChangeHandler(FileSystemEventHandler):
    """文件系统事件处理器"""

    def __init__(self, file_monitor, ignored_patterns):
        self.file_monitor = file_monitor
        self.ignored_patterns = ignored_patterns

    def on_created(self, event):
        """处理文件创建事件"""
        self.file_monitor.process_event(event)

    def on_deleted(self, event):
        """处理文件删除事件"""
        self.file_monitor.process_event(event)

    def on_modified(self, event):
        """处理文件修改事件"""
        # 对于频繁修改的文件，可能需要额外的防抖处理
        self.file_monitor.process_event(event)

    def on_moved(self, event):
        """处理文件移动事件"""
        # 这里可以添加额外的移动事件处理逻辑
        # 为简化，我们复用已有的事件处理逻辑
        self.file_monitor.process_event(event)


# 示例用法
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 这里仅作为示例，实际使用时需要传入真实的索引管理器和配置
    logging.basicConfig(level=logging.INFO)
    _mock_logger = logging.getLogger(__name__)

    class MockIndexManager:
        def update_document(self, file_path):
            _mock_logger.info(f"更新文档索引: {file_path}")

        def delete_document(self, file_path):
            _mock_logger.info(f"删除文档索引: {file_path}")

    class MockConfig:
        def get(self, section, option, fallback=None):
            if section == "monitor" and option == "directories":
                return "./test_dir"
            return fallback

        def getint(self, section, option, fallback=0):
            return fallback

    # 创建测试目录
    test_dir = "./test_dir"
    os.makedirs(test_dir, exist_ok=True)

    try:
        # 初始化监控器
        index_manager = MockIndexManager()
        config = MockConfig()
        monitor = FileMonitor(index_manager, config)

        # 启动监控
        monitor.start_monitoring()

        # 创建测试文件
        test_file = os.path.join(test_dir, "test_file.txt")
        with open(test_file, "w") as f:
            f.write("This is a test file.")

        # 修改测试文件
        time.sleep(1)
        with open(test_file, "a") as f:
            f.write("\nModified content.")

        # 删除测试文件
        time.sleep(1)
        os.remove(test_file)

        # 等待一段时间让监控器处理事件
        time.sleep(2)

        # 停止监控
        monitor.stop_monitoring()

    finally:
        # 清理测试目录
        if os.path.exists(test_dir):
            os.rmdir(test_dir)
