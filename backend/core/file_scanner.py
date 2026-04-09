# src/core/file_scanner.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件扫描器模块 - 负责扫描文件系统并识别可索引文件（支持同步和异步操作）"""

import asyncio
import fnmatch
import logging
import os
import platform
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from backend.core.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_WORKERS,
    LOG_FREQUENCY,
    PROGRESS_FREQUENCY,
)
from backend.core.document_parser import DocumentParser
from backend.core.index_manager import IndexManager
from backend.utils.config_loader import ConfigLoader

# 异步支持（可选依赖）
try:
    import aiofiles

    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

# 可选的快速扫描支持（Rust-based scandir）
try:
    from scandir_rs import Scandir, Walk

    SCANDIR_RS_AVAILABLE = True
except ImportError:
    SCANDIR_RS_AVAILABLE = False
    Scandir = None
    Walk = None


class FileScanner:
    """文件扫描器类，负责扫描文件系统并识别可索引文件（支持多线程并行处理）"""

    # 默认配置（从 constants 模块导入）
    DEFAULT_MAX_WORKERS = DEFAULT_MAX_WORKERS  # type: ignore  # 默认并行工作线程数
    DEFAULT_BATCH_SIZE = DEFAULT_BATCH_SIZE  # type: ignore  # 默认批处理大小
    _LOG_FREQUENCY = LOG_FREQUENCY  # type: ignore
    _PROGRESS_FREQUENCY = PROGRESS_FREQUENCY  # type: ignore

    def __init__(
        self,
        config_loader: ConfigLoader,
        document_parser: Optional[DocumentParser] = None,
        index_manager: Optional[IndexManager] = None,
    ) -> None:
        self.config_loader: ConfigLoader = config_loader
        self.logger: logging.Logger = logging.getLogger(__name__)

        # 配置参数
        self.scan_paths: List[str] = self._get_scan_paths()
        self.exclude_patterns: List[str] = self._get_exclude_patterns()
        # 从配置获取并转换为整数，增加健壮性检查
        try:
            max_file_size_value = config_loader.get(
                "file_scanner", "max_file_size", 100
            )
            max_file_size_mb = int(max_file_size_value)
        except Exception as e:
            self.logger.error(f"获取最大文件大小配置失败: {str(e)}")
            max_file_size_mb = 100
        self.max_file_size: int = max_file_size_mb * 1024 * 1024  # MB to bytes

        self.target_extensions: Dict[str, List[str]] = self._get_target_extensions()
        # 使用 set 进行 O(1) 查找，提高性能
        self.all_extensions: set[str] = {
            ext for exts in self.target_extensions.values() for ext in exts
        }

        # 并行处理配置
        try:
            scan_threads = config_loader.getint(
                "file_scanner", "scan_threads", self.DEFAULT_MAX_WORKERS
            )
            self.max_workers = max(
                1, min(scan_threads, 32)
            )  # 限制在1-32之间，提升并行度
        except Exception:
            self.max_workers = self.DEFAULT_MAX_WORKERS

        self.batch_size = self.DEFAULT_BATCH_SIZE

        # 缓存配置
        try:
            self._cache_max_size = config_loader.getint(
                "file_scanner", "hash_cache_size", 10000
            )
            self._cache_max_size = max(
                1000, min(self._cache_max_size, 100000)
            )  # 限制在1k-100k之间
        except Exception:
            self._cache_max_size = 10000

        # 依赖组件
        self.document_parser: DocumentParser = document_parser or DocumentParser(
            config_loader
        )
        self.index_manager: Optional[IndexManager] = index_manager

        # 进度回调
        self.progress_callback: Optional[Callable[[int], None]] = None

        # 扫描控制标志
        self._stop_flag: bool = False
        self._stop_lock: threading.Lock = threading.Lock()

        # 扫描统计信息（线程安全）
        self._stats_lock: threading.Lock = threading.Lock()
        self.scan_stats: Dict[str, Any] = {
            "total_files_scanned": 0,
            "total_files_indexed": 0,
            "total_files_skipped": 0,
            "total_size_scanned": 0,
            "scan_time": 0,
            "last_scan_time": None,
        }

        # 文件哈希缓存（避免重复处理未变更文件）
        # value: (quick_key(size:mtime), md5_hash, last_access_time)
        self._file_hash_cache: Dict[str, Tuple[str, str, float]] = {}
        self._cache_lock: threading.Lock = threading.Lock()

        self.logger.info(
            f"文件扫描器初始化完成，配置: 扫描路径 {len(self.scan_paths)} 个, "
            f"排除模式 {len(self.exclude_patterns)} 个, 并行线程: {self.max_workers}, "
            f"哈希缓存大小: {self._cache_max_size}"
        )

    def set_progress_callback(self, callback: Callable[[int], None]) -> "FileScanner":
        """设置进度回调函数"""
        self.progress_callback = callback
        return self

    def _is_stop_requested(self) -> bool:
        """线程安全地检查是否请求停止"""
        with self._stop_lock:
            return self._stop_flag

    def _increment_stat(self, stat_name: str, value: int = 1) -> None:
        """线程安全地增加统计值"""
        with self._stats_lock:
            self.scan_stats[stat_name] += value

    def _get_file_hash(self, file_path: str, quick_key: str) -> str:
        """
        获取文件标识（用于检测文件是否变更）

        直接使用 quick_key（size:mtime）作为变更标识，避免不必要的 MD5 计算。
        文件大小和修改时间的组合足以检测文件变更。
        """
        return quick_key

    def _is_file_changed(self, file_path: str) -> bool:
        """检查文件是否自上次扫描以来已变更（线程安全，使用双检锁模式）"""
        try:
            stat = os.stat(file_path)
            quick_key = f"{stat.st_size}:{stat.st_mtime}"
        except Exception:
            return True  # 无法获取文件状态，假设已变更

        # 第一重检查：无锁快速路径
        with self._cache_lock:
            cached = self._file_hash_cache.get(file_path)
            if cached:
                cached_quick_key, cached_hash, _ = cached
                if cached_quick_key == quick_key:
                    return False  # 文件未变更

        # 计算哈希（在锁外部）
        current_hash = self._get_file_hash(file_path, quick_key)
        if not current_hash:
            return True  # 无法计算哈希，假设已变更

        # 第二重检查：加锁确认和更新
        with self._cache_lock:
            cached = self._file_hash_cache.get(file_path)
            if cached:
                cached_quick_key, cached_hash, _ = cached
                if cached_quick_key == quick_key and cached_hash == current_hash:
                    return False  # 文件未变更（另一个线程可能已更新）

            # 更新缓存
            self._file_hash_cache[file_path] = (quick_key, current_hash, time.time())

            # 限制缓存大小
            if len(self._file_hash_cache) > self._cache_max_size:
                # 移除最旧的20%条目（批量清理比逐个清理更高效）
                self._trim_cache()

            return True

    def _trim_cache(self):
        """修剪缓存，移除最旧的20%条目"""
        if not self._file_hash_cache:
            return

        # 按访问时间排序
        sorted_items = sorted(self._file_hash_cache.items(), key=lambda x: x[1][2])

        # 移除最旧的20%
        entries_to_remove = max(1, len(sorted_items) // 5)
        for i in range(entries_to_remove):
            del self._file_hash_cache[sorted_items[i][0]]

        cache_info = (
            f"移除了 {entries_to_remove} 个条目，当前大小: {len(self._file_hash_cache)}"
        )
        self.logger.debug(f"缓存修剪：{cache_info}")

    def _process_file_batch(self, file_paths: List[Path]) -> List[Dict]:
        """批量处理文件，返回成功处理的文档列表（文档格式，用于批量索引）"""
        results = []
        for file_path in file_paths:
            if self._is_stop_requested():
                break
            try:
                # 将文件转换为文档字典，而不是直接索引
                doc = self._process_file_to_doc(file_path)
                if doc:
                    results.append(doc)
            except Exception as e:
                self.logger.debug(f"批量处理文件失败 {file_path}: {e}")
        return results

    def _get_scan_paths(self) -> List[str]:
        """从配置中获取扫描路径"""
        scan_paths_value = ""
        try:
            scan_paths_value = self.config_loader.get("file_scanner", "scan_paths", "")
            # 避免在大规模扫描时刷屏 info 日志
            path_info = f"类型: {type(scan_paths_value).__name__}"
            self.logger.debug(f"配置的扫描路径原始值: {scan_paths_value} ({path_info})")
        except Exception as e:
            self.logger.error(f"获取扫描路径配置失败: {str(e)}")
            scan_paths_value = ""

        # 处理scan_paths的列表和字符串类型
        if isinstance(scan_paths_value, list):
            scan_paths = scan_paths_value
        elif isinstance(scan_paths_value, str):
            scan_paths = scan_paths_value.split(";") if scan_paths_value else []
        else:
            scan_paths = [str(scan_paths_value)] if scan_paths_value else []
        # 过滤空路径和不存在的路径
        valid_paths = []
        for path in scan_paths:
            path = path.strip()
            if path:
                # 处理Windows路径
                expanded_path = Path(path).expanduser()
                self.logger.debug(f"检查路径: {path} -> {expanded_path}")
                if expanded_path.exists() and expanded_path.is_dir():
                    valid_paths.append(str(expanded_path))
                    self.logger.debug(f"✓ 有效路径: {expanded_path}")
                else:
                    self.logger.warning(f"✗ 扫描路径不存在或不是目录: {path}")

        # 如果没有有效路径，记录警告但不自动回退到 Documents
        # 用户需要显式配置扫描路径，而不是自动使用某个默认值
        if not valid_paths:
            self.logger.info(
                "未配置有效的扫描路径，将使用空列表（用户需在设置中显式添加扫描目录）"
            )

        self.logger.info(f"最终扫描路径列表: {valid_paths}")
        return valid_paths

    @staticmethod
    def _match_exclude(pattern: str, text: str) -> bool:
        """排除规则匹配：同时兼容 regex 与 glob。"""
        if not pattern:
            return False
        try:
            # 含 glob 通配符时按 glob 匹配，否则按正则匹配
            if any(ch in pattern for ch in ("*", "?", "[")):
                return fnmatch.fnmatch(text, pattern)
            return re.search(pattern, text) is not None
        except re.error:
            # 正则非法时回退为子串包含
            return pattern in text

    def _get_exclude_patterns(self) -> List[str]:
        """从配置中获取排除模式"""
        # 始终排除的临时文件模式（硬编码，不可配置）
        always_exclude = [
            "~$*",  # Office临时文件 (Word/Excel等)
            "*.tmp",  # 临时文件
            "*.temp",  # 临时文件
            ".DS_Store",  # macOS元数据
            "Thumbs.db",  # Windows缩略图缓存
            "desktop.ini",  # Windows桌面配置
            "*.lnk",  # Windows快捷方式
            "*.doc",  # 旧版Word格式，解析经常超时失败
        ]

        exclude_patterns_str = ""
        try:
            exclude_patterns_value = self.config_loader.get(
                "file_scanner", "exclude_patterns", ""
            )
            exclude_patterns_str = str(exclude_patterns_value)
        except Exception as e:
            self.logger.error(f"获取排除模式配置失败: {str(e)}")
            exclude_patterns_str = ""

        # 确保exclude_patterns_str是字符串类型
        if not isinstance(exclude_patterns_str, str):
            exclude_patterns_str = str(exclude_patterns_str)

        exclude_patterns = exclude_patterns_str.split(";")
        # 合并始终排除的模式和用户配置的模式
        all_patterns = always_exclude + [
            pattern.strip() for pattern in exclude_patterns if pattern.strip()
        ]
        return all_patterns

    def _get_target_extensions(self) -> Dict[str, List[str]]:
        """从配置中获取目标文件类型及其扩展名"""
        # 默认支持的文件类型
        default_extensions = {
            "document": [
                ".txt",
                ".md",
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".xml",
                ".properties",
                ".java",
                ".py",
                ".js",
                ".cpp",
                ".c",
                ".h",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".ini",
                ".cfg",
                ".conf",
            ],
            # 移除图片
            # 'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
            # 移除音视频
            # 'audio': ['.mp3', '.wav', '.flac', '.ogg'],
            # 'video': ['.mp4', '.avi', '.mov', '.mkv']
        }

        # 从配置中获取自定义文件类型
        try:
            config_extensions_value = self.config_loader.get(
                "file_scanner", "file_types", None
            )

            # 如果配置返回的是字典，直接使用
            if isinstance(config_extensions_value, dict):
                result = {}
                for type_name, ext_str in config_extensions_value.items():
                    # ext_str 可能是 '.txt,.md,.pdf' 格式
                    if isinstance(ext_str, str):
                        exts = [ext.strip() for ext in ext_str.split(",")]
                        result[type_name] = exts
                    elif isinstance(ext_str, list):
                        result[type_name] = ext_str
                self.logger.info(f"从配置加载文件类型: {result}")
                return result if result else default_extensions

            # 如果是字符串格式: document=.txt,.md,.pdf;image=.jpg,.png
            elif isinstance(config_extensions_value, str) and config_extensions_value:
                result = {}
                for type_entry in config_extensions_value.split(";"):
                    if "=" in type_entry:
                        type_name, ext_list = type_entry.split("=", 1)
                        type_name = type_name.strip()
                        exts = [ext.strip() for ext in ext_list.split(",")]
                        result[type_name] = exts

                # 强制移除图片、音频、视频类型，即使配置中有
                for forbidden in ["image", "audio", "video"]:
                    if forbidden in result:
                        self.logger.warning(f"强制移除不支持的文件类型: {forbidden}")
                        del result[forbidden]

                self.logger.info(f"从配置加载文件类型: {result}")
                return result if result else default_extensions
        except Exception as e:
            self.logger.error(f"解析配置文件类型失败: {str(e)}")

        self.logger.info(f"使用默认文件类型: {default_extensions}")
        return default_extensions

    def scan_and_index(self) -> Dict:
        """扫描所有配置的路径并索引文件（流式并行处理优化性能）

        优化策略:
        1. 流式收集文件，边收集边处理，无需等待全部收集完成
        2. 使用os.scandir替代os.walk减少stat()调用
        3. 线程池并行处理文件，减少等待时间
        4. 实时进度报告（收集阶段0-5%，处理阶段5-95%）

        LlamaIndex benchmark: 异步并行处理比顺序执行快3.5x
        """
        start_time = time.time()
        self.logger.info("开始扫描并索引文件（流式模式）")
        self.logger.info(
            f"开始扫描: {len(self.scan_paths)} 个路径, 并行线程: {self.max_workers}"
        )

        # 重置停止标志
        with self._stop_lock:
            self._stop_flag = False

        # 重置扫描统计信息
        with self._stats_lock:
            self.scan_stats = {
                "total_files_scanned": 0,
                "total_files_indexed": 0,
                "total_files_skipped": 0,
                "total_size_scanned": 0,
                "scan_time": 0,
                "last_scan_time": None,
            }

        # 初始化进度 - 报告0%开始收集
        if self.progress_callback:
            try:
                self.progress_callback(0)
            except Exception as e:
                self.logger.warning(f"初始化进度回调失败: {str(e)}")

        # 启动索引批量模式
        if self.index_manager:
            try:
                self.index_manager.start_batch_mode()
                self.logger.info("启动索引批量模式")
            except Exception as e:
                self.logger.warning(f"启动批量模式失败: {e}")

        # 流式处理：边收集边处理
        batch_size = self.batch_size * self.max_workers  # 动态计算批次大小
        file_buffer = []
        processed_count = 0
        total_collected = 0
        last_progress_update = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 流式收集文件并处理
            for file_path in self._collect_files_streaming():
                if self._is_stop_requested():
                    break

                total_collected += 1
                file_buffer.append(file_path)

                # 收集阶段进度报告（0-5%）
                # 每收集10个文件报告一次进度（而非1000个）
                if total_collected % 10 == 0 and self.progress_callback:
                    try:
                        # 收集阶段进度范围: 0-5%
                        self.progress_callback(min(5, total_collected // 2))
                    except Exception as e:
                        self.logger.debug(f"收集阶段进度回调失败: {e}")

                # 当缓冲区满时，处理当前批次
                if len(file_buffer) >= batch_size:
                    # 提交批次处理任务，返回文档而非直接索引
                    futures = {
                        executor.submit(self._process_file_to_doc_worker, fp): fp
                        for fp in file_buffer
                    }

                    # 收集文档并批量索引
                    documents_batch = []
                    for future in as_completed(futures):
                        if self._is_stop_requested():
                            executor.shutdown(wait=False)
                            break
                        try:
                            doc = future.result()
                            processed_count += 1
                            if doc:
                                documents_batch.append(doc)

                            # 批量索引：当收集到足够文档时
                            if len(documents_batch) >= 100 and self.index_manager:
                                try:
                                    self.index_manager.batch_add_documents(
                                        documents_batch
                                    )
                                    documents_batch.clear()
                                except Exception as e:
                                    self.logger.error(f"批量索引失败: {e}")

                            # 处理阶段进度报告（5-95%）
                            estimated_total = max(total_collected, processed_count)
                            progress = 5 + int((processed_count / estimated_total) * 90)
                            if progress > last_progress_update:
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(min(95, progress))
                                    except Exception as e:
                                        self.logger.debug(f"更新进度回调失败: {e}")
                                last_progress_update = progress

                        except Exception as e:
                            self.logger.error(f"处理文件失败: {e}")

                    # 处理剩余未索引的文档
                    if documents_batch and self.index_manager:
                        try:
                            self.index_manager.batch_add_documents(documents_batch)
                        except Exception as e:
                            self.logger.error(f"批量索引失败: {e}")

                    # 清空缓冲区
                    file_buffer.clear()

            # 处理剩余文件
            if file_buffer and not self._is_stop_requested():
                futures = {
                    executor.submit(self._process_file_to_doc_worker, fp): fp
                    for fp in file_buffer
                }

                documents_batch = []
                for future in as_completed(futures):
                    if self._is_stop_requested():
                        break
                    try:
                        doc = future.result()
                        processed_count += 1
                        if doc:
                            documents_batch.append(doc)

                        # 批量索引
                        if len(documents_batch) >= 100 and self.index_manager:
                            try:
                                self.index_manager.batch_add_documents(documents_batch)
                                documents_batch.clear()
                            except Exception as e:
                                self.logger.error(f"批量索引失败: {e}")

                        # 处理阶段进度报告（5-95%）
                        estimated_total = max(total_collected, processed_count)
                        progress = 5 + int((processed_count / estimated_total) * 90)
                        if progress > last_progress_update:
                            if self.progress_callback:
                                try:
                                    self.progress_callback(min(95, progress))
                                except Exception as e:
                                    self.logger.debug(f"剩余文件进度回调失败: {e}")
                            last_progress_update = progress
                    except Exception as e:
                        self.logger.error(f"处理文件失败: {e}")

                # 处理剩余文档
                if documents_batch and self.index_manager:
                    try:
                        self.index_manager.batch_add_documents(documents_batch)
                    except Exception as e:
                        self.logger.error(f"批量索引失败: {e}")

        # 结束索引批量模式（提交所有剩余文档）
        if self.index_manager:
            try:
                self.index_manager.end_batch_mode(commit=True)
                self.logger.info("批量模式结束，索引已提交")
            except Exception as e:
                self.logger.error(f"结束批量模式失败: {e}")

        # 设置完成进度
        if self.progress_callback:
            try:
                self.progress_callback(100)
            except Exception as e:
                self.logger.warning(f"完成进度回调失败: {str(e)}")

        # 计算扫描时间
        with self._stats_lock:
            self.scan_stats["scan_time"] = time.time() - start_time
            self.scan_stats["last_scan_time"] = time.time()
            stats = self.scan_stats.copy()

        avg_speed = stats["total_files_scanned"] / max(stats["scan_time"], 0.001)
        scan_info = (
            f"扫描完成，统计: 扫描文件 {stats['total_files_scanned']} 个, "
            f"索引文件 {stats['total_files_indexed']} 个, "
            f"跳过文件 {stats['total_files_skipped']} 个, "
            f"耗时 {stats['scan_time']:.2f} 秒, "
            f"平均速度: {avg_speed:.1f} 文件/秒"
        )
        self.logger.info(scan_info)

        return stats

    def _collect_files(self) -> List[Path]:
        """收集所有需要扫描的文件路径"""
        all_files = []
        for path in self.scan_paths:
            if self._is_stop_requested():
                break
            try:
                self._collect_files_from_dir(Path(path), all_files)
            except Exception as e:
                self.logger.error(f"收集文件失败 {path}: {e}")
        return all_files

    def _collect_files_from_dir(
        self, dir_path: Path, files_list: List[Path], progress_info: dict = None
    ):
        """从目录收集文件（递归）- 使用os.scandir优化性能"""
        if not dir_path.exists() or not dir_path.is_dir():
            return

        try:
            self._scan_dir_recursive(dir_path, files_list, progress_info)
        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.error(f"收集文件失败 {dir_path}: {e}")

    def _collect_files_streaming(self) -> Generator[Path, None, None]:
        """流式收集文件路径 - 生成器模式，边收集边yield

        使用os.scandir进行高效目录遍历，配合排除模式过滤。
        文件被找到时立即yield，而非等待全部收集完成。
        """
        for path in self.scan_paths:
            if self._is_stop_requested():
                break
            yield from self._collect_files_from_dir_streaming(Path(path))

    def _collect_files_from_dir_streaming(
        self, dir_path: Path
    ) -> Generator[Path, None, None]:
        """从目录流式收集文件（递归）- 使用os.scandir优化性能"""
        if not dir_path.exists() or not dir_path.is_dir():
            return

        try:
            yield from self._scan_dir_recursive_streaming(dir_path)
        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.error(f"收集文件失败 {dir_path}: {e}")

    def _scan_dir_recursive_streaming(
        self, dir_path: Path
    ) -> Generator[Path, None, None]:
        """使用os.scandir递归扫描目录（生成器模式），比os.walk更快"""
        # 每处理 N 个条目检查一次停止标志
        _CHECK_STOP_INTERVAL = 100
        entry_count = 0

        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if self._is_stop_requested():
                        self.logger.info(f"扫描已停止: {dir_path}")
                        return

                    entry_count += 1
                    if (
                        entry_count % _CHECK_STOP_INTERVAL == 0
                        and self._is_stop_requested()
                    ):
                        return

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not any(
                                self._match_exclude(pattern, entry.name)
                                for pattern in self.exclude_patterns
                            ):
                                # 递归扫描子目录
                                yield from self._scan_dir_recursive_streaming(
                                    Path(entry.path)
                                )
                        elif entry.is_file(follow_symlinks=False):
                            try:
                                stat_result = entry.stat()
                                if stat_result.st_mode & 0o170000 != 0o100000:
                                    continue
                            except OSError:
                                continue
                            file_ext = Path(entry.name).suffix.lower()
                            if file_ext in self.all_extensions:
                                yield Path(entry.path)
                    except (PermissionError, OSError):
                        continue
        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.debug(f"扫描目录失败 {dir_path}: {e}")

    def _scan_dir_recursive(
        self, dir_path: Path, files_list: List[Path], progress_info: dict = None
    ):
        """使用os.scandir递归扫描目录，比os.walk更快"""
        # 每处理 N 个条目检查一次停止标志，避免过于频繁的锁竞争
        _CHECK_STOP_INTERVAL = 100
        entry_count = 0
        # 每 N 个文件报告一次进度
        _PROGRESS_INTERVAL = 500

        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    # 频繁检查停止请求，提高取消响应速度
                    if self._is_stop_requested():
                        self.logger.info(f"扫描已停止，当前目录: {dir_path}")
                        return

                    entry_count += 1
                    if entry_count % _CHECK_STOP_INTERVAL == 0:
                        # 每 N 个条目检查一次（平衡响应速度与性能）
                        if self._is_stop_requested():
                            self.logger.info(
                                f"扫描已停止（周期性检查），当前目录: {dir_path}"
                            )
                            return

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            # 过滤排除的目录
                            if not any(
                                self._match_exclude(pattern, entry.name)
                                for pattern in self.exclude_patterns
                            ):
                                # 递归扫描子目录
                                self._scan_dir_recursive(
                                    Path(entry.path), files_list, progress_info
                                )
                                # 子目录返回后再次检查停止标志
                                if self._is_stop_requested():
                                    return
                        elif entry.is_file(follow_symlinks=False):
                            # 检查是否为普通文件（不是管道、设备等特殊文件）
                            try:
                                stat_result = entry.stat()
                                if stat_result.st_mode & 0o170000 != 0o100000:
                                    continue  # 跳过特殊文件
                            except OSError:
                                continue
                            # 快速扩展名检查（不调用stat）
                            file_ext = Path(entry.name).suffix.lower()
                            if file_ext in self.all_extensions:
                                files_list.append(Path(entry.path))
                                # 定期报告收集进度
                                if (
                                    progress_info
                                    and len(files_list) % _PROGRESS_INTERVAL == 0
                                ):
                                    if self.progress_callback:
                                        try:
                                            # 收集阶段进度：0-5%
                                            progress = min(
                                                4, int(len(files_list) / 1000)
                                            )
                                            self.progress_callback(progress)
                                        except Exception:
                                            pass
                    except (PermissionError, OSError):
                        continue
        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.debug(f"扫描目录失败 {dir_path}: {e}")

    def _collect_files_fast(self, progress_info: dict = None) -> List[Path]:
        """快速收集所有需要扫描的文件路径

        使用os.scandir进行高效目录遍历，配合排除模式过滤。
        scandir-rs虽然快，但由于其内部队列机制与我们的目录排除逻辑不兼容，暂不使用。
        """
        all_files = []

        for path in self.scan_paths:
            if self._is_stop_requested():
                break
            try:
                self._collect_files_from_dir(Path(path), all_files, progress_info)
            except Exception as e:
                self.logger.error(f"收集文件失败 {path}: {e}")

        return all_files

    def _collect_with_scandir_rs(self, dir_path: Path, files_list: List[Path]):
        """使用scandir-rs收集文件（Rust并行遍历)

        scandir-rs使用Rayon进行并行目录遍历，比os.walk快4x以上。
        Walk返回(root, subdirs, files)元组，类似os.walk。

        注意：scandir-rs返回相对路径，需要从dir_path目录运行才能正确解析路径。
        """
        if not dir_path.exists() or not dir_path.is_dir():
            return

        original_cwd = os.getcwd()
        try:
            # scandir-rs需要从目标目录运行以返回正确的相对路径
            os.chdir(dir_path)

            walk = Walk(".", skip_hidden=False)

            for root, subdirs, files in walk:
                if self._is_stop_requested():
                    walk.stop()
                    break

                # 过滤排除的子目录（使用我们的_match_exclude函数）
                subdirs[:] = [
                    d
                    for d in subdirs
                    if not any(
                        self._match_exclude(pattern, d)
                        for pattern in self.exclude_patterns
                    )
                ]

                for file_name in files:
                    if self._is_stop_requested():
                        break
                    file_path = Path(root) / file_name
                    # 检查是否为普通文件（不是管道、设备等特殊文件）
                    try:
                        stat_result = file_path.stat()
                        if stat_result.st_mode & 0o170000 != 0o100000:
                            continue  # 跳过特殊文件
                    except OSError:
                        continue
                    # 快速扩展名检查
                    file_ext = file_path.suffix.lower()
                    if file_ext in self.all_extensions:
                        files_list.append(file_path)

        except Exception as e:
            self.logger.error(f"scandir-rs遍历失败 {dir_path}: {e}")
        finally:
            os.chdir(original_cwd)

    def _process_file_worker(self, file_path: Path) -> bool:
        """工作线程：处理单个文件"""
        try:
            return self._process_file(file_path)
        except Exception as e:
            self.logger.debug(f"工作线程处理文件失败 {file_path}: {e}")
            return False

    def _process_file_to_doc_worker(self, file_path: Path) -> Optional[Dict]:
        """工作线程：将文件处理为文档字典（用于批量索引）

        Returns:
            文档字典，如果处理失败或不应索引则返回 None
        """
        try:
            return self._process_file_to_doc(file_path)
        except Exception as e:
            self.logger.debug(f"工作线程处理文件失败 {file_path}: {e}")
            return None

    def _scan_directory(self, dir_path: Path, total_estimate: int = 0) -> None:
        """递归扫描目录并索引符合条件的文件（使用os.scandir优化）

        Args:
            dir_path: 要扫描的目录路径
            total_estimate: 预估的总文件数，用于进度计算。为0时不更新进度
        """
        self.logger.info(f"扫描目录: {dir_path}")

        # 检查目录是否存在且可访问
        if not dir_path.exists():
            self.logger.warning(f"扫描目录不存在: {dir_path}")
            return
        if not dir_path.is_dir():
            self.logger.warning(f"扫描路径不是目录: {dir_path}")
            return

        enable_progress = total_estimate > 0 and self.progress_callback is not None
        log_frequency = 50 if not enable_progress else self._LOG_FREQUENCY

        try:
            self.logger.info(f"开始遍历目录: {dir_path}")
            file_count = 0

            # 使用os.scandir递归扫描
            def scan_recursive(current_dir: Path):
                nonlocal file_count
                try:
                    with os.scandir(current_dir) as entries:
                        for entry in entries:
                            if self._is_stop_requested():
                                return
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    # 过滤排除的目录
                                    if not any(
                                        self._match_exclude(pattern, entry.name)
                                        for pattern in self.exclude_patterns
                                    ):
                                        scan_recursive(Path(entry.path))
                                elif entry.is_file(follow_symlinks=False):
                                    # 检查文件是否为有效的普通文件
                                    try:
                                        stat_result = entry.stat()
                                        if stat_result.st_mode & 0o170000 != 0o100000:
                                            continue
                                    except OSError:
                                        continue

                                    self._process_file(Path(entry.path))
                                    file_count += 1

                                    # 更新进度（如果启用）
                                    if (
                                        enable_progress
                                        and file_count % self._PROGRESS_FREQUENCY == 0
                                    ):
                                        progress = min(
                                            99,
                                            int(
                                                (
                                                    self.scan_stats[
                                                        "total_files_scanned"
                                                    ]
                                                    / total_estimate
                                                )
                                                * 100
                                            ),
                                        )
                                        try:
                                            if self.progress_callback:
                                                self.progress_callback(progress)
                                        except Exception as e:
                                            self.logger.warning(
                                                f"更新进度回调失败: {str(e)}"
                                            )

                                    # 记录日志
                                    if file_count % log_frequency == 0:
                                        self.logger.info(
                                            f"已处理 {file_count} 个文件..."
                                        )

                            except (PermissionError, OSError):
                                continue
                            except Exception as e:
                                self.logger.debug(f"处理条目失败 {entry.path}: {e}")
                                continue
                except PermissionError:
                    self.logger.warning(f"无权限访问目录: {current_dir}")
                except Exception as e:
                    self.logger.error(f"扫描目录失败 {current_dir}: {str(e)}")

            scan_recursive(dir_path)
            self.logger.info(f"目录扫描完成，共处理 {file_count} 个文件")

        except PermissionError:
            self.logger.error(f"无权限访问目录: {dir_path}", exc_info=True)
        except Exception as e:
            self.logger.error(f"扫描目录失败 {dir_path}: {str(e)}", exc_info=True)

    def _process_file_to_doc(self, file_path: Path) -> Optional[Dict]:
        """将文件处理为文档字典（用于批量索引）

        与 _process_file 不同，此方法不直接索引文件，而是返回文档字典，
        以便调用者可以使用 batch_add_documents 进行批量索引。

        Returns:
            文档字典，如果不应索引则返回 None
        """
        file_path_str = str(file_path)

        # 获取文件stat信息（用于缓存检查和后续使用）
        try:
            file_stat = os.stat(file_path_str)
        except Exception:
            self.logger.debug(f"无法获取文件状态 {file_path_str}")
            return None

        quick_key = f"{file_stat.st_size}:{file_stat.st_mtime}"

        # 检查文件是否变更（使用缓存）
        with self._cache_lock:
            cached = self._file_hash_cache.get(file_path_str)
            if cached:
                cached_quick_key, cached_hash, _ = cached
                if cached_quick_key == quick_key:
                    self._increment_stat("total_files_scanned")
                    self.logger.debug(f"文件未变更，跳过: {file_path_str}")
                    return None

        self._increment_stat("total_files_scanned")

        # 检查是否应索引该文件（传入stat_result避免重复调用stat）
        if not self._should_index(file_path_str, file_stat):
            self._increment_stat("total_files_skipped")
            self.logger.debug(f"跳过文件: {file_path_str} (不符合索引条件)")
            return None

        try:
            # 记录文件大小
            file_size = file_stat.st_size
            self._increment_stat("total_size_scanned", file_size)

            # 构建文档字典（不索引）
            doc = self._build_document(file_path_str, file_stat)
            if doc:
                self._increment_stat("total_files_indexed")
                # 更新缓存
                current_hash = self._get_file_hash(file_path_str, quick_key)
                with self._cache_lock:
                    self._file_hash_cache[file_path_str] = (
                        quick_key,
                        current_hash,
                        time.time(),
                    )
                    if len(self._file_hash_cache) > self._cache_max_size:
                        self._trim_cache()
                self.logger.debug(
                    f"成功构建文档: {file_path_str}, 大小: {file_size} bytes"
                )
                return doc
            else:
                self._increment_stat("total_files_skipped")
                return None

        except PermissionError:
            self.logger.warning(f"无权限访问文件: {file_path_str}")
            self._increment_stat("total_files_skipped")
            return None
        except OSError as e:
            self.logger.warning(f"操作系统错误访问文件 {file_path_str}: {str(e)}")
            self._increment_stat("total_files_skipped")
            return None
        except Exception as e:
            self.logger.error(f"处理文件失败 {file_path_str}: {str(e)}", exc_info=True)
            self._increment_stat("total_files_skipped")
            return None

    def _build_document(
        self, file_path: str, stat_info: os.stat_result
    ) -> Optional[Dict]:
        """构建文档字典（用于批量索引）"""
        try:
            file_path_obj = Path(file_path)

            # 使用已获取的stat信息
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)

            # 获取文件类型
            file_ext = file_path_obj.suffix.lower()
            file_type = "unknown"
            for type_name, extensions in self.target_extensions.items():
                if file_ext in extensions:
                    file_type = type_name
                    break

            # 读取文件内容
            content = self._read_file_content(file_path, file_ext)

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

            return document
        except Exception as e:
            self.logger.error(f"构建文档失败 {file_path}: {str(e)}")
            return None

    def _process_file(self, file_path: Path) -> bool:
        """处理单个文件，检查是否应索引并执行索引操作（线程安全）"""
        file_path_str = str(file_path)

        # 获取文件stat信息（用于缓存检查和后续使用）
        try:
            file_stat = os.stat(file_path_str)
        except Exception:
            self.logger.debug(f"无法获取文件状态 {file_path_str}")
            return False

        quick_key = f"{file_stat.st_size}:{file_stat.st_mtime}"

        # 检查文件是否变更（使用缓存）
        with self._cache_lock:
            cached = self._file_hash_cache.get(file_path_str)
            if cached:
                cached_quick_key, cached_hash, _ = cached
                if cached_quick_key == quick_key:
                    self._increment_stat("total_files_scanned")
                    self.logger.debug(f"文件未变更，跳过: {file_path_str}")
                    return False

        self._increment_stat("total_files_scanned")

        # 检查是否应索引该文件（传入stat_result避免重复调用stat）
        if not self._should_index(file_path_str, file_stat):
            self._increment_stat("total_files_skipped")
            self.logger.debug(f"跳过文件: {file_path_str} (不符合索引条件)")
            return False

        try:
            # 记录文件大小
            file_size = file_stat.st_size
            self._increment_stat("total_size_scanned", file_size)

            # 执行索引操作
            success = self._index_file_with_stat(file_path_str, file_stat)
            if success:
                self._increment_stat("total_files_indexed")
                # 更新缓存
                current_hash = self._get_file_hash(file_path_str, quick_key)
                with self._cache_lock:
                    self._file_hash_cache[file_path_str] = (
                        quick_key,
                        current_hash,
                        time.time(),
                    )
                    if len(self._file_hash_cache) > self._cache_max_size:
                        self._trim_cache()
                self.logger.debug(
                    f"成功索引文件: {file_path_str}, 大小: {file_size} bytes"
                )
                return True
            else:
                self._increment_stat("total_files_skipped")
                self.logger.debug(f"跳过索引文件: {file_path_str} (索引失败)")
                return False
        except PermissionError:
            self.logger.warning(f"无权限访问文件: {file_path_str}")
            self._increment_stat("total_files_skipped")
            return False
        except OSError as e:
            self.logger.warning(f"操作系统错误访问文件 {file_path_str}: {str(e)}")
            self._increment_stat("total_files_skipped")
            return False
        except Exception as e:
            self.logger.error(f"处理文件失败 {file_path_str}: {str(e)}", exc_info=True)
            self._increment_stat("total_files_skipped")
            return False

    # 媒体文件扩展名集合（用于快速查找）
    _MEDIA_EXTENSIONS = frozenset(
        [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".tiff",
            ".svg",
            ".webp",
            ".mp3",
            ".wav",
            ".flac",
            ".ogg",
            ".m4a",
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".wmv",
        ]
    )

    def _should_index(
        self, path: str, stat_result: Optional[os.stat_result] = None
    ) -> bool:
        """检查是否应索引文件：扩展名、排除模式、文件大小、系统文件

        Args:
            path: 文件路径
            stat_result: 可选的预获取stat结果，避免重复调用stat
        """
        file_path = Path(path)
        file_ext = file_path.suffix.lower()

        # 强制拒绝媒体扩展名
        if file_ext in self._MEDIA_EXTENSIONS:
            return False

        # 快速扩展名检查（使用 set 的 O(1) 查找）
        if file_ext not in self.all_extensions:
            return False

        # 获取文件大小（如果未提供stat_result）
        if stat_result is None:
            try:
                stat_result = file_path.stat()
            except Exception as e:
                self.logger.debug(f"获取文件大小失败 {path}: {e}")
                return False

        # 检查文件大小
        if stat_result.st_size > self.max_file_size:
            size_mb = stat_result.st_size / 1024 / 1024
            self.logger.debug(
                f"跳过过大文件: {os.path.basename(path)}, 大小: {size_mb:.1f}MB"
            )
            return False

        # 检查排除模式
        if any(self._match_exclude(pattern, path) for pattern in self.exclude_patterns):
            return False

        # 检查是否为系统文件（只对可能可执行的扩展名进行检查）
        if file_ext in self._EXECUTABLE_EXTENSIONS:
            if self._is_system_file(path, stat_result):
                return False

        return True

    # 可能包含可执行文件的扩展名集合（需要检查文件头）
    _EXECUTABLE_EXTENSIONS = frozenset(
        [
            ".exe",
            ".dll",
            ".sys",
            ".bat",
            ".cmd",
            ".ps1",
            ".vbs",
            ".js",
            ".jar",
            ".bin",
            ".sh",
            ".bash",
            ".out",
            ".ko",
            ".so",
            ".dylib",
            ".scr",
        ]
    )

    def _is_system_file(self, path: str) -> bool:
        """检测是否为系统文件"""
        # 首先检查扩展名，对已知的文档文件直接跳过可执行文件检查
        file_ext = Path(path).suffix.lower()
        document_extensions = {
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".rtf",
            ".html",
            ".htm",
            ".py",
            ".js",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".cs",
            ".go",
            ".rs",
            ".php",
            ".rb",
            ".swift",
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
        }

        if file_ext in document_extensions:
            # 对于已知文档类型，只检查路径模式，不检查可执行头
            if platform.system() == "Windows":
                if re.search(r"\$[A-Za-z]", path):
                    return True
            # 检查隐藏文件
            if any(part.startswith(".") and part != "." for part in Path(path).parts):
                return True
            return False

        # 对于其他文件类型，执行完整的检查
        if platform.system() == "Windows":
            # 检查是否为临时文件或系统文件
            if re.search(r"\$[A-Za-z]", path):
                return True

        # 检查隐藏文件
        if any(part.startswith(".") and part != "." for part in Path(path).parts):
            return True

        # 只有当文件扩展名可能是可执行文件时才检查文件头
        if file_ext not in self._EXECUTABLE_EXTENSIONS:
            return False

        # 对可疑文件执行可执行文件头检查
        try:
            with open(path, "rb") as f:
                header = f.read(4)
                if header in [b"MZ\x90\x00", b"\x7fELF"]:  # Windows和Linux可执行文件头
                    return True
        except Exception:
            pass  # 无法读取，假设非系统文件

        return False

    def index_file(self, file_path: str) -> bool:
        """索引单个文件 (公开方法，供FileMonitor调用)"""
        return self._index_file(file_path)

    def _index_file(self, file_path: str) -> bool:
        """索引单个文件"""
        if not self.index_manager:
            self.logger.error("索引管理器未初始化")
            return False

        try:
            # 构建文档对象
            file_path_obj = Path(file_path)

            # 获取文件基本信息
            stat_info = file_path_obj.stat()
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)

            # 获取文件类型
            file_ext = file_path_obj.suffix.lower()
            file_type = "unknown"
            for type_name, extensions in self.target_extensions.items():
                if file_ext in extensions:
                    file_type = type_name
                    break

            # 读取文件内容
            content = self._read_file_content(file_path, file_ext)

            # 构建文档字典
            document = {
                "path": str(file_path),
                "filename": file_path_obj.name,
                "content": content,
                "file_type": file_type,
                "size": file_size,
                "created": created_time,
                "modified": modified_time,
                "keywords": "",  # 可以后续扩展关键词提取
            }

            # 调用索引管理器更新文档
            self.index_manager.update_document(document)
            self.logger.debug(f"已索引文件: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"索引文件失败 {file_path}: {str(e)}")
            import traceback

            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return False

    def _index_file_with_stat(self, file_path: str, stat_info: os.stat_result) -> bool:
        """索引单个文件（使用预获取的stat信息避免重复调用stat）"""
        if not self.index_manager:
            self.logger.error("索引管理器未初始化")
            return False

        try:
            file_path_obj = Path(file_path)

            # 使用已获取的stat信息
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)

            # 获取文件类型
            file_ext = file_path_obj.suffix.lower()
            file_type = "unknown"
            for type_name, extensions in self.target_extensions.items():
                if file_ext in extensions:
                    file_type = type_name
                    break

            # 读取文件内容
            content = self._read_file_content(file_path, file_ext)

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

            # 调用索引管理器更新文档
            self.index_manager.update_document(document)
            self.logger.debug(f"已索引文件: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"索引文件失败 {file_path}: {str(e)}")
            import traceback

            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return False

    def _read_file_content(self, file_path: str, file_ext: str) -> str:
        """读取文件内容"""
        try:
            if self.document_parser:
                try:
                    parsed = self.document_parser.extract_text(file_path)
                    if isinstance(parsed, str) and parsed.strip():
                        return parsed
                except Exception:
                    pass
            # 对于文本类文件，直接读取
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
                ".yaml",
                ".yml",
                ".toml",
                ".ini",
                ".cfg",
                ".conf",
                ".properties",
                ".gradle",
                ".sh",
                ".bat",
                ".ps1",
                ".sql",
                ".html",
                ".css",
            ]:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()
                except UnicodeDecodeError:
                    # 尝试其他编码
                    with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                        return f.read()

            # 对于其他类型，返回文件名作为内容(后续可以扩展支持PDF、Word等)
            return Path(file_path).name
        except Exception as e:
            self.logger.warning(f"读取文件内容失败 {file_path}: {str(e)}")
            return Path(file_path).name

    def stop_scan(self):
        """停止扫描操作"""
        self.logger.info("正在停止扫描...")
        with self._stop_lock:
            self._stop_flag = True

    def close(self):
        """关闭文件扫描器，释放资源"""
        self.logger.info("正在关闭文件扫描器...")

        # 停止扫描操作
        with self._stop_lock:
            self._stop_flag = True

        # 清空文件哈希缓存
        with self._cache_lock:
            cache_size = len(self._file_hash_cache)
            self._file_hash_cache.clear()
            self.logger.info(f"已清空文件哈希缓存（{cache_size} 条目）")

        # 关闭文档解析器
        if self.document_parser is not None:
            try:
                if hasattr(self.document_parser, "close"):
                    self.document_parser.close()
                    self.logger.info("文档解析器已关闭")
            except Exception as e:
                self.logger.warning(f"关闭文档解析器时出错：{e}")
            self.document_parser = None

        self.logger.info("文件扫描器已关闭")

    def get_supported_file_types(self) -> Dict[str, List[str]]:
        """获取支持的文件类型及其扩展名"""
        return self.target_extensions.copy()

    def get_scan_stats(self) -> Dict:
        """获取最近一次扫描的统计信息"""
        return self.scan_stats.copy()

    def get_scan_paths(self) -> List[str]:
        """获取当前配置的扫描路径"""
        return self.scan_paths.copy()

    def add_scan_path(self, path: str) -> bool:
        """添加新的扫描路径"""
        expanded_path = Path(path).expanduser()
        if not expanded_path.exists() or not expanded_path.is_dir():
            self.logger.error(f"添加扫描路径失败: {path} 不存在或不是目录")
            return False

        path_str = str(expanded_path)
        if path_str in self.scan_paths:
            self.logger.warning(f"扫描路径已存在: {path_str}")
            return True

        self.scan_paths.append(path_str)
        self.logger.info(f"已添加扫描路径: {path_str}")
        return True

    def remove_scan_path(self, path: str) -> bool:
        """移除扫描路径"""
        expanded_path = str(Path(path).expanduser())
        if expanded_path not in self.scan_paths:
            self.logger.warning(f"扫描路径不存在: {expanded_path}")
            return True

        self.scan_paths.remove(expanded_path)
        self.logger.info(f"已移除扫描路径: {expanded_path}")
        return True

    def set_max_file_size(self, size_mb: int) -> None:
        """设置最大文件大小限制（MB）"""
        if size_mb <= 0:
            self.logger.warning("最大文件大小必须为正数")
            return

        self.max_file_size = size_mb * 1024 * 1024
        self.logger.info(f"已设置最大文件大小: {size_mb} MB")

    def get_scannable_files(self, directory: Optional[str] = None) -> List[str]:
        """获取可扫描的文件列表"""
        scan_dirs = [directory] if directory else self.scan_paths
        scannable_files = []

        for scan_dir in scan_dirs:
            if not os.path.exists(scan_dir):
                self.logger.warning(f"扫描目录不存在: {scan_dir}")
                continue

            try:
                for root, dirs, files in os.walk(scan_dir):
                    if self._stop_flag:
                        break

                    for file_name in files:
                        file_path = os.path.join(root, file_name)

                        # 检查是否应该索引此文件
                        if self._should_index(file_path):
                            scannable_files.append(file_path)

            except PermissionError:
                self.logger.error(f"无权限访问目录: {scan_dir}")
            except Exception as e:
                self.logger.error(f"扫描目录时出错 {scan_dir}: {str(e)}")

        return scannable_files

    def update_single_file(self, file_path: str) -> bool:
        """更新单个文件的索引"""
        try:
            if not os.path.exists(file_path):
                self.logger.warning(f"文件不存在: {file_path}")
                return False

            if not self._should_index(file_path):
                self.logger.info(f"文件不符合索引条件: {file_path}")
                return False

            # 索引文件
            success = self._index_file(file_path)
            if success:
                self._increment_stat("total_files_indexed")
                self.logger.info(f"成功更新文件索引: {file_path}")
            else:
                self._increment_stat("total_files_skipped")
                self.logger.warning(f"更新文件索引失败: {file_path}")

            return success
        except Exception as e:
            self.logger.error(f"更新单个文件时出错 {file_path}: {str(e)}")
            return False

    def remove_file_from_index(self, file_path: str) -> bool:
        """从索引中移除文件"""
        try:
            if self.index_manager:
                success = self.index_manager.delete_document(file_path)
                if success:
                    self.logger.info(f"成功从索引中移除文件: {file_path}")
                else:
                    self.logger.warning(f"从索引中移除文件失败: {file_path}")
                return success
            else:
                self.logger.error("索引管理器未初始化")
                return False
        except Exception as e:
            self.logger.error(f"从索引中移除文件时出错 {file_path}: {str(e)}")
            return False

    def get_file_type_stats(self) -> Dict[str, int]:
        """获取文件类型统计信息"""
        stats = {}
        for file_type, extensions in self.target_extensions.items():
            stats[file_type] = 0

        # 如果有索引管理器，可以从索引中获取实际统计
        if self.index_manager and self.index_manager.tantivy_index:
            try:
                # 获取索引中的文件类型统计
                searcher = self.index_manager.tantivy_index.searcher()

                for file_type in stats.keys():
                    query = self.index_manager.tantivy_index.parse_query(
                        file_type, ["file_type"]
                    )
                    top_docs = searcher.search(query, 0)  # 只需要计数，不需要结果
                    stats[file_type] = getattr(
                        top_docs,
                        "total_count",
                        len(top_docs.hits) if hasattr(top_docs, "hits") else 0,
                    )
            except Exception as e:
                self.logger.warning(f"获取索引中文件类型统计失败: {str(e)}")

        return stats

    def scan_with_filters(self, filters: Optional[Dict] = None) -> Dict:
        """使用过滤器扫描文件"""
        if filters is None:
            filters = {}

        # 重置统计信息
        self.scan_stats = {
            "total_files_scanned": 0,
            "total_files_indexed": 0,
            "total_files_skipped": 0,
            "total_size_scanned": 0,
            "scan_time": 0,
            "last_scan_time": None,
        }

        start_time = time.time()

        # 根据过滤器执行扫描
        scan_paths = filters.get("scan_paths", self.scan_paths)

        for path in scan_paths:
            if self._is_stop_requested():
                break
            self._scan_directory(Path(path), 0)  # 这里简化处理，不计算预估总数

        self.scan_stats["scan_time"] = time.time() - start_time
        self.scan_stats["last_scan_time"] = time.time()

        return self.scan_stats

    # ==================== 异步扫描支持 ====================

    async def scan_and_index_async(
        self, progress_callback: Optional[Callable[[int], None]] = None
    ) -> Dict:
        """
        异步扫描并索引文件

        使用 asyncio 和 aiofiles 进行异步文件 I/O，提高 I/O 密集型任务的性能。

        Args:
            progress_callback: 进度回调函数，接收 0-100 的进度值

        Returns:
            扫描统计信息字典
        """
        if not AIOFILES_AVAILABLE:
            self.logger.warning("aiofiles 未安装，回退到同步扫描模式")
            if progress_callback:
                self.set_progress_callback(progress_callback)
            return self.scan_and_index()

        start_time = time.time()
        self.logger.info("开始异步扫描并索引文件")

        # 重置停止标志和统计信息
        with self._stop_lock:
            self._stop_flag = False

        with self._stats_lock:
            self.scan_stats = {
                "total_files_scanned": 0,
                "total_files_indexed": 0,
                "total_files_skipped": 0,
                "total_size_scanned": 0,
                "scan_time": 0,
                "last_scan_time": None,
            }

        # 初始化进度
        if progress_callback:
            try:
                progress_callback(0)
            except Exception as e:
                self.logger.warning(f"初始化进度回调失败: {str(e)}")

        # 启动索引批量模式
        if self.index_manager:
            try:
                self.index_manager.start_batch_mode()
                self.logger.info("启动索引批量模式")
            except Exception as e:
                self.logger.warning(f"启动批量模式失败: {e}")

        try:
            # 异步收集所有待扫描文件
            all_files = await self._collect_files_async()
            total_files = len(all_files)
            self.logger.info(f"共收集到 {total_files} 个待扫描文件")

            if total_files == 0:
                self.logger.warning("没有找到需要扫描的文件")
                return self.scan_stats

            # 使用信号量限制并发数
            semaphore = asyncio.Semaphore(self.max_workers)
            processed_count = 0
            last_progress_update = 0

            async def process_with_semaphore(file_path: Path):
                async with semaphore:
                    return await self._process_file_async(file_path)

            # 分批处理文件
            batch_size = self.batch_size * self.max_workers
            for batch_start in range(0, total_files, batch_size):
                if self._is_stop_requested():
                    self.logger.info("扫描已被停止")
                    break

                batch_end = min(batch_start + batch_size, total_files)
                current_batch = all_files[batch_start:batch_end]

                # 并发处理当前批次
                tasks = [process_with_semaphore(fp) for fp in current_batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 处理结果
                for result in results:
                    processed_count += 1
                    if isinstance(result, Exception):
                        self.logger.debug(f"处理文件失败: {result}")

                    # 更新进度
                    progress = int((processed_count / total_files) * 100)
                    if (
                        progress > last_progress_update
                        or processed_count - last_progress_update >= 100
                    ):
                        if progress_callback:
                            try:
                                progress_callback(min(99, progress))
                            except Exception as e:
                                self.logger.debug(f"更新进度回调失败: {e}")
                        last_progress_update = processed_count

                self.logger.debug(f"批次完成: {batch_start}-{batch_end}")

            # 设置完成进度
            if progress_callback:
                try:
                    progress_callback(100)
                except Exception as e:
                    self.logger.warning(f"完成进度回调失败: {str(e)}")

        finally:
            # 结束索引批量模式
            if self.index_manager:
                try:
                    self.index_manager.end_batch_mode(commit=True)
                    self.logger.info("批量模式结束，索引已提交")
                except Exception as e:
                    self.logger.error(f"结束批量模式失败: {e}")

        # 计算扫描时间
        with self._stats_lock:
            self.scan_stats["scan_time"] = time.time() - start_time
            self.scan_stats["last_scan_time"] = time.time()
            stats = self.scan_stats.copy()

        self.logger.info(
            f"异步扫描完成，统计: 扫描文件 {stats['total_files_scanned']} 个, "
            f"索引文件 {stats['total_files_indexed']} 个, "
            f"跳过文件 {stats['total_files_skipped']} 个, "
            f"耗时 {stats['scan_time']:.2f} 秒"
        )

        return stats

    async def _collect_files_async(self) -> List[Path]:
        """异步收集所有需要扫描的文件路径"""
        all_files = []
        for path in self.scan_paths:
            if self._is_stop_requested():
                break
            try:
                await self._collect_files_from_dir_async(Path(path), all_files)
            except Exception as e:
                self.logger.error(f"异步收集文件失败 {path}: {e}")
        return all_files

    async def _collect_files_from_dir_async(
        self, dir_path: Path, files_list: List[Path]
    ):
        """异步从目录收集文件（递归）"""
        if not dir_path.exists() or not dir_path.is_dir():
            return

        loop = asyncio.get_event_loop()

        try:
            # 使用线程池执行 os.walk（因为 os.walk 没有异步版本）
            def walk_directory():
                result = []
                for root, dirs, files in os.walk(dir_path):
                    if self._is_stop_requested():
                        break

                    # 过滤排除的目录
                    dirs[:] = [
                        d
                        for d in dirs
                        if not any(
                            self._match_exclude(pattern, d)
                            for pattern in self.exclude_patterns
                        )
                    ]

                    for file_name in files:
                        if self._is_stop_requested():
                            break
                        file_path = Path(root) / file_name
                        if self._should_index(str(file_path)):
                            result.append(file_path)
                return result

            # 在线程池中执行同步的 os.walk
            files = await loop.run_in_executor(None, walk_directory)
            files_list.extend(files)

        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.error(f"异步收集文件失败 {dir_path}: {e}")

    async def _process_file_async(self, file_path: Path) -> bool:
        """异步处理单个文件"""
        file_path_str = str(file_path)

        # 检查文件是否变更（同步操作，使用锁保护）
        if not self._is_file_changed(file_path_str):
            self._increment_stat("total_files_scanned")
            return False

        self._increment_stat("total_files_scanned")

        # 检查是否应索引该文件
        if self._should_index(file_path_str):
            try:
                # 使用 aiofiles 异步读取文件
                success = await self._index_file_async(file_path_str)
                if success:
                    self._increment_stat("total_files_indexed")
                    return True
                else:
                    self._increment_stat("total_files_skipped")
                    return False
            except Exception as e:
                self.logger.debug(f"异步处理文件失败 {file_path}: {e}")
                self._increment_stat("total_files_skipped")
                return False
        else:
            self._increment_stat("total_files_skipped")
            return False

    async def _index_file_async(self, file_path: str) -> bool:
        """异步索引单个文件"""
        if not self.index_manager:
            self.logger.error("索引管理器未初始化")
            return False

        try:
            file_path_obj = Path(file_path)

            # 获取文件基本信息（同步操作）
            stat_info = file_path_obj.stat()
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)

            # 获取文件类型
            file_ext = file_path_obj.suffix.lower()
            file_type = "unknown"
            for type_name, extensions in self.target_extensions.items():
                if file_ext in extensions:
                    file_type = type_name
                    break

            # 异步读取文件内容
            content = await self._read_file_content_async(file_path, file_ext)

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

            # 调用索引管理器更新文档（同步操作，在线程池中执行）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self.index_manager.update_document, document
            )

            self.logger.debug(f"已异步索引文件: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"异步索引文件失败 {file_path}: {str(e)}")
            return False

    async def _read_file_content_async(self, file_path: str, file_ext: str) -> str:
        """异步读取文件内容"""
        try:
            # 优先使用文档解析器
            if self.document_parser:
                try:
                    # 文档解析器通常是同步的，在线程池中执行
                    loop = asyncio.get_event_loop()
                    parsed = await loop.run_in_executor(
                        None, self.document_parser.extract_text, file_path
                    )
                    if isinstance(parsed, str) and parsed.strip():
                        return parsed
                except Exception:
                    pass

            # 对于文本类文件，使用 aiofiles 异步读取
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
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        return await f.read()
                except UnicodeDecodeError:
                    # 尝试其他编码
                    async with aiofiles.open(
                        file_path, "r", encoding="gbk", errors="ignore"
                    ) as f:
                        return await f.read()

            # 对于其他类型，返回文件名作为内容
            return Path(file_path).name

        except Exception as e:
            self.logger.warning(f"异步读取文件内容失败 {file_path}: {str(e)}")
            return Path(file_path).name


# 示例用法
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 这里仅作为示例，实际使用时需要传入真实的配置和依赖
    class MockConfig:
        def get(self, section, option, fallback=""):
            if section == "file_scanner" and option == "scan_paths":
                return "./test_scan_dir"
            return fallback

        def getint(self, section, option, fallback=0):
            if section == "file_scanner" and option == "max_file_size":
                return 10
            return fallback

    # 配置日志用于示例
    logging.basicConfig(level=logging.INFO)
    _mock_logger = logging.getLogger(__name__)

    class MockIndexManager:
        def update_document(self, file_path):
            _mock_logger.info(f"更新文档索引: {file_path}")

    # 创建测试目录和文件
    test_dir = "./test_scan_dir"
    os.makedirs(test_dir, exist_ok=True)

    test_file = os.path.join(test_dir, "test_file.txt")
    with open(test_file, "w") as f:
        f.write("This is a test file for file scanner.")

    try:
        # 初始化扫描器
        config = MockConfig()  # type: ignore[arg-type]
        index_manager = MockIndexManager()  # type: ignore[arg-type]
        scanner = FileScanner(config, index_manager=index_manager)  # type: ignore[arg-type]

        # 执行扫描
        stats = scanner.scan_and_index()
        _mock_logger.info(f"扫描统计: {stats}")

    finally:
        # 清理测试文件和目录
        if os.path.exists(test_file):
            os.remove(test_file)
        if os.path.exists(test_dir):
            os.rmdir(test_dir)
