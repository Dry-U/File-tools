# src/core/file_scanner.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件扫描器模块 - 负责扫描文件系统并识别可索引文件"""
import os
import re
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Tuple
import logging
import fnmatch
import hashlib
import mimetypes
import tantivy
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import threading

from backend.utils.config_loader import ConfigLoader
from backend.core.index_manager import IndexManager
from backend.core.document_parser import DocumentParser

class FileScanner:
    """文件扫描器类，负责扫描文件系统并识别可索引文件（支持多线程并行处理）"""

    # 默认配置
    DEFAULT_MAX_WORKERS = 4  # 默认并行工作线程数
    DEFAULT_BATCH_SIZE = 50  # 默认批处理大小

    def __init__(self, config_loader, document_parser=None, index_manager=None):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)

        # 配置参数
        self.scan_paths: List[str] = self._get_scan_paths()
        self.exclude_patterns: List[str] = self._get_exclude_patterns()
        # 从配置获取并转换为整数，增加健壮性检查
        try:
            max_file_size_value = config_loader.get('file_scanner', 'max_file_size', 100)
            max_file_size_mb = int(max_file_size_value)
        except Exception as e:
            self.logger.error(f"获取最大文件大小配置失败: {str(e)}")
            max_file_size_mb = 100
        self.max_file_size: int = max_file_size_mb * 1024 * 1024  # MB to bytes

        self.target_extensions: Dict[str, List[str]] = self._get_target_extensions()
        self.all_extensions: List[str] = [ext for exts in self.target_extensions.values() for ext in exts]

        # 并行处理配置
        try:
            scan_threads = config_loader.getint('file_scanner', 'scan_threads', self.DEFAULT_MAX_WORKERS)
            self.max_workers = max(1, min(scan_threads, 16))  # 限制在1-16之间
        except Exception:
            self.max_workers = self.DEFAULT_MAX_WORKERS

        self.batch_size = self.DEFAULT_BATCH_SIZE

        # 依赖组件
        self.document_parser = document_parser or DocumentParser(config_loader)
        self.index_manager = index_manager

        # 进度回调
        self.progress_callback = None

        # 扫描控制标志
        self._stop_flag = False
        self._stop_lock = threading.Lock()

        # 扫描统计信息（线程安全）
        self._stats_lock = threading.Lock()
        self.scan_stats = {
            'total_files_scanned': 0,
            'total_files_indexed': 0,
            'total_files_skipped': 0,
            'total_size_scanned': 0,
            'scan_time': 0,
            'last_scan_time': None
        }

        # 文件哈希缓存（避免重复处理未变更文件）
        self._file_hash_cache: Dict[str, Tuple[str, float]] = {}
        self._cache_lock = threading.Lock()
        self._cache_max_size = 10000

        self.logger.info(f"文件扫描器初始化完成，配置: 扫描路径 {len(self.scan_paths)} 个, "
                        f"排除模式 {len(self.exclude_patterns)} 个, 并行线程: {self.max_workers}")
        
    def set_progress_callback(self, callback):
        """设置进度回调函数"""
        self.progress_callback = callback
        return self

    def _is_stop_requested(self) -> bool:
        """线程安全地检查是否请求停止"""
        with self._stop_lock:
            return self._stop_flag

    def _increment_stat(self, stat_name: str, value: int = 1):
        """线程安全地增加统计值"""
        with self._stats_lock:
            self.scan_stats[stat_name] += value

    def _get_file_hash(self, file_path: str) -> Optional[str]:
        """计算文件哈希（用于检测文件是否变更）"""
        try:
            # 使用文件大小和修改时间作为快速哈希
            stat = os.stat(file_path)
            hash_input = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(hash_input.encode()).hexdigest()
        except Exception:
            return None

    def _is_file_changed(self, file_path: str) -> bool:
        """检查文件是否自上次扫描以来已变更"""
        current_hash = self._get_file_hash(file_path)
        if not current_hash:
            return True  # 无法计算哈希，假设已变更

        with self._cache_lock:
            cached = self._file_hash_cache.get(file_path)
            if cached and cached[0] == current_hash:
                return False  # 文件未变更

            # 更新缓存
            self._file_hash_cache[file_path] = (current_hash, time.time())

            # 限制缓存大小
            if len(self._file_hash_cache) > self._cache_max_size:
                # 移除最旧的条目
                oldest = min(self._file_hash_cache.items(), key=lambda x: x[1][1])
                del self._file_hash_cache[oldest[0]]

            return True

    def _process_file_batch(self, file_paths: List[Path]) -> List[Dict]:
        """批量处理文件，返回成功索引的文档列表"""
        results = []
        for file_path in file_paths:
            if self._is_stop_requested():
                break
            try:
                result = self._process_file(file_path)
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.debug(f"批量处理文件失败 {file_path}: {e}")
        return results

    def _get_scan_paths(self) -> List[str]:
        """从配置中获取扫描路径"""
        scan_paths_value = ""
        try:
            scan_paths_value = self.config_loader.get('file_scanner', 'scan_paths', "")
            self.logger.info(f"配置的扫描路径原始值: {scan_paths_value} (类型: {type(scan_paths_value).__name__})")
        except Exception as e:
            self.logger.error(f"获取扫描路径配置失败: {str(e)}")
            scan_paths_value = ""

        # 处理scan_paths的列表和字符串类型
        if isinstance(scan_paths_value, list):
            scan_paths = scan_paths_value
        elif isinstance(scan_paths_value, str):
            scan_paths = scan_paths_value.split(';') if scan_paths_value else []
        else:
            scan_paths = [str(scan_paths_value)] if scan_paths_value else []
        # 过滤空路径和不存在的路径
        valid_paths = []
        for path in scan_paths:
            path = path.strip()
            if path:
                # 处理Windows路径
                expanded_path = Path(path).expanduser()
                self.logger.info(f"检查路径: {path} -> {expanded_path}")
                if expanded_path.exists() and expanded_path.is_dir():
                    valid_paths.append(str(expanded_path))
                    self.logger.info(f"✓ 有效路径: {expanded_path}")
                else:
                    self.logger.warning(f"✗ 扫描路径不存在或不是目录: {path}")
        
        # 如果没有有效路径，使用默认路径
        if not valid_paths:
            # 检查并尝试创建一个默认的扫描路径
            default_path = Path.home() / "Documents"
            if not default_path.exists():
                default_path = Path.home()

            # 如果路径不存在，尝试创建它
            if not default_path.exists():
                try:
                    default_path.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"创建默认扫描路径: {default_path}")
                except Exception as e:
                    self.logger.error(f"无法创建默认扫描路径: {default_path}, 错误: {e}")
                    # 如果无法创建路径，则使用用户主目录
                    default_path = Path.home()

            valid_paths.append(str(default_path))
            self.logger.warning(f"未配置有效的扫描路径，使用默认路径: {default_path}")
        
        self.logger.info(f"最终扫描路径列表: {valid_paths}")
        return valid_paths
    
    def _get_exclude_patterns(self) -> List[str]:
        """从配置中获取排除模式"""
        exclude_patterns_str = ""
        try:
            exclude_patterns_value = self.config_loader.get('file_scanner', 'exclude_patterns', "")
            exclude_patterns_str = str(exclude_patterns_value)
        except Exception as e:
            self.logger.error(f"获取排除模式配置失败: {str(e)}")
            exclude_patterns_str = ""
        
        # 确保exclude_patterns_str是字符串类型
        if not isinstance(exclude_patterns_str, str):
            exclude_patterns_str = str(exclude_patterns_str)
        
        exclude_patterns = exclude_patterns_str.split(';')
        # 过滤空模式
        return [pattern.strip() for pattern in exclude_patterns if pattern.strip()]
    
    def _get_target_extensions(self) -> Dict[str, List[str]]:
        """从配置中获取目标文件类型及其扩展名"""
        # 默认支持的文件类型
        default_extensions = {
            'document': ['.txt', '.md', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'],
            # 移除图片
            # 'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
            # 移除音视频
            # 'audio': ['.mp3', '.wav', '.flac', '.ogg'],
            # 'video': ['.mp4', '.avi', '.mov', '.mkv']
        }
        
        # 从配置中获取自定义文件类型
        try:
            config_extensions_value = self.config_loader.get('file_scanner', 'file_types', None)
            
            # 如果配置返回的是字典，直接使用
            if isinstance(config_extensions_value, dict):
                result = {}
                for type_name, ext_str in config_extensions_value.items():
                    # ext_str 可能是 '.txt,.md,.pdf' 格式
                    if isinstance(ext_str, str):
                        exts = [ext.strip() for ext in ext_str.split(',')]
                        result[type_name] = exts
                    elif isinstance(ext_str, list):
                        result[type_name] = ext_str
                self.logger.info(f"从配置加载文件类型: {result}")
                return result if result else default_extensions
            
            # 如果是字符串格式: document=.txt,.md,.pdf;image=.jpg,.png
            elif isinstance(config_extensions_value, str) and config_extensions_value:
                result = {}
                for type_entry in config_extensions_value.split(';'):
                    if '=' in type_entry:
                        type_name, ext_list = type_entry.split('=', 1)
                        type_name = type_name.strip()
                        exts = [ext.strip() for ext in ext_list.split(',')]
                        result[type_name] = exts
                
                # 强制移除图片、音频、视频类型，即使配置中有
                for forbidden in ['image', 'audio', 'video']:
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
        """扫描所有配置的路径并索引文件（使用并行处理优化性能）"""
        start_time = time.time()
        self.logger.info("开始扫描并索引文件")
        self.logger.info(f"扫描路径列表: {self.scan_paths}, 并行线程: {self.max_workers}")

        # 重置停止标志
        with self._stop_lock:
            self._stop_flag = False

        # 重置扫描统计信息
        with self._stats_lock:
            self.scan_stats = {
                'total_files_scanned': 0,
                'total_files_indexed': 0,
                'total_files_skipped': 0,
                'total_size_scanned': 0,
                'scan_time': 0,
                'last_scan_time': None
            }

        # 初始化进度
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

        # 收集所有待扫描文件
        all_files = self._collect_files()
        total_files = len(all_files)
        self.logger.info(f"共收集到 {total_files} 个待扫描文件")

        if total_files == 0:
            self.logger.warning("没有找到需要扫描的文件")
            return self.scan_stats

        # 使用线程池并行处理文件
        processed_count = 0
        last_progress_update = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有文件处理任务
            future_to_file = {
                executor.submit(self._process_file_worker, file_path): file_path
                for file_path in all_files
            }

            # 处理完成的任务
            for future in as_completed(future_to_file):
                if self._is_stop_requested():
                    executor.shutdown(wait=False)
                    self.logger.info("扫描已被停止")
                    break

                file_path = future_to_file[future]
                try:
                    future.result()
                    processed_count += 1

                    # 更新进度（每1%或每100个文件更新一次）
                    progress = int((processed_count / total_files) * 100)
                    if (progress > last_progress_update or
                        processed_count - last_progress_update >= 100):
                        if self.progress_callback:
                            try:
                                self.progress_callback(min(99, progress))
                            except Exception as e:
                                self.logger.debug(f"更新进度回调失败: {e}")
                        last_progress_update = processed_count

                except Exception as e:
                    self.logger.error(f"处理文件失败 {file_path}: {e}")

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
            self.scan_stats['scan_time'] = time.time() - start_time
            self.scan_stats['last_scan_time'] = time.time()
            stats = self.scan_stats.copy()

        self.logger.info(f"扫描完成，统计: 扫描文件 {stats['total_files_scanned']} 个, "
                        f"索引文件 {stats['total_files_indexed']} 个, "
                        f"跳过文件 {stats['total_files_skipped']} 个, "
                        f"耗时 {stats['scan_time']:.2f} 秒, "
                        f"平均速度: {stats['total_files_scanned'] / max(stats['scan_time'], 0.001):.1f} 文件/秒")

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

    def _collect_files_from_dir(self, dir_path: Path, files_list: List[Path]):
        """从目录收集文件（递归）"""
        if not dir_path.exists() or not dir_path.is_dir():
            return

        try:
            for root, dirs, files in os.walk(dir_path):
                if self._is_stop_requested():
                    break

                # 过滤排除的目录
                dirs[:] = [
                    d for d in dirs
                    if not any(pattern in d for pattern in self.exclude_patterns)
                ]

                for file_name in files:
                    if self._is_stop_requested():
                        break
                    file_path = Path(root) / file_name
                    if self._should_index(str(file_path)):
                        files_list.append(file_path)
        except PermissionError:
            self.logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            self.logger.error(f"收集文件失败 {dir_path}: {e}")

    def _process_file_worker(self, file_path: Path) -> bool:
        """工作线程：处理单个文件"""
        try:
            return self._process_file(file_path)
        except Exception as e:
            self.logger.debug(f"工作线程处理文件失败 {file_path}: {e}")
            return False

    def _scan_directory(self, dir_path: Path, total_estimate: int = 0) -> None:
        """递归扫描目录并索引符合条件的文件

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

            for root, dirs, files in os.walk(dir_path):
                if self._stop_flag:
                    self.logger.info(f"扫描被停止，已处理 {file_count} 个项目")
                    return

                for file_name in files:
                    if self._stop_flag:
                        self.logger.info(f"扫描被停止，已处理 {file_count} 个项目")
                        return

                    try:
                        file_path = Path(root) / file_name

                        # 检查文件是否为有效的普通文件
                        try:
                            stat_result = file_path.stat()
                            # 跳过特殊文件（如管道、设备文件等）
                            if not (stat_result.st_mode & 0o170000 == 0o100000):
                                continue
                        except OSError:
                            self.logger.warning(f"无法获取文件状态 {file_path}, 跳过")
                            continue

                        self.logger.debug(f"处理文件: {file_path}")
                        self._process_file(file_path)
                        file_count += 1

                        # 更新进度（如果启用）
                        if enable_progress and file_count % self._PROGRESS_FREQUENCY == 0:
                            progress = min(99, int((self.scan_stats['total_files_scanned'] / total_estimate) * 100))
                            try:
                                self.progress_callback(progress)
                            except Exception as e:
                                self.logger.warning(f"更新进度回调失败: {str(e)}")

                        # 记录日志
                        if file_count % log_frequency == 0:
                            self.logger.info(f"已处理 {file_count} 个文件...")

                    except Exception as e:
                        # 单个文件处理失败不应停止整个扫描
                        self.logger.error(f"处理文件失败 {file_name} in {root}: {str(e)}")
                        continue

            self.logger.info(f"目录扫描完成，共处理 {file_count} 个文件")

        except PermissionError:
            self.logger.error(f"无权限访问目录: {dir_path}", exc_info=True)
        except Exception as e:
            self.logger.error(f"扫描目录失败 {dir_path}: {str(e)}", exc_info=True)
    
    def _process_file(self, file_path: Path) -> bool:
        """处理单个文件，检查是否应索引并执行索引操作（线程安全）"""
        file_path_str = str(file_path)

        # 检查文件是否变更（使用缓存）
        if not self._is_file_changed(file_path_str):
            self._increment_stat('total_files_scanned')
            self.logger.debug(f"文件未变更，跳过: {file_path_str}")
            return False

        self._increment_stat('total_files_scanned')

        # 检查是否应索引该文件
        if self._should_index(file_path_str):
            try:
                # 记录文件大小
                file_stat = file_path.stat()
                file_size = file_stat.st_size
                self._increment_stat('total_size_scanned', file_size)

                # 执行索引操作
                success = self._index_file(file_path_str)
                if success:
                    self._increment_stat('total_files_indexed')
                    self.logger.debug(f"成功索引文件: {file_path_str}, 大小: {file_size} bytes")
                    return True
                else:
                    self._increment_stat('total_files_skipped')
                    self.logger.debug(f"跳过索引文件: {file_path_str} (索引失败)")
                    return False
            except PermissionError:
                self.logger.warning(f"无权限访问文件: {file_path_str}")
                self._increment_stat('total_files_skipped')
                return False
            except OSError as e:
                self.logger.warning(f"操作系统错误访问文件 {file_path_str}: {str(e)}")
                self._increment_stat('total_files_skipped')
                return False
            except Exception as e:
                self.logger.error(f"处理文件失败 {file_path_str}: {str(e)}", exc_info=True)
                self._increment_stat('total_files_skipped')
                return False
        else:
            self._increment_stat('total_files_skipped')
            self.logger.debug(f"跳过文件: {file_path_str} (不符合索引条件)")
            return False
    
    def _should_index(self, path: str) -> bool:
        """检查是否应索引文件：扩展名、排除模式、文件大小、系统文件"""
        file_path = Path(path)
        
        # 检查文件大小
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                self.logger.info(f"跳过过大文件: {path}, 大小: {file_size}, 限制: {self.max_file_size}")
                return False
            self.logger.info(f"文件大小检查通过: {path}, 大小: {file_size}")
        except Exception as e:
            self.logger.warning(f"获取文件大小失败 {path}: {str(e)}")
            return False
        
        # 检查文件扩展名
        file_ext = file_path.suffix.lower()
        
        # 强制拒绝图片和媒体扩展名
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg', '.webp', 
                       '.mp3', '.wav', '.flac', '.ogg', '.m4a',
                       '.mp4', '.avi', '.mov', '.mkv', '.wmv']:
             self.logger.info(f"强制跳过媒体文件: {path}")
             return False

        self.logger.info(f"检查文件扩展名: {path}, 扩展名: {file_ext}, 支持的扩展名: {self.all_extensions}")
        if not any(file_ext == ext for ext in self.all_extensions):
            self.logger.info(f"跳过不支持的文件类型: {path}")
            return False
        self.logger.info(f"文件扩展名检查通过: {path}")
        
        # 检查排除模式
        self.logger.info(f"检查排除模式: {path}, 排除模式: {self.exclude_patterns}")
        if any(re.search(pattern, path) for pattern in self.exclude_patterns):
            self.logger.info(f"跳过匹配排除模式的文件: {path}")
            return False
        self.logger.info(f"排除模式检查通过: {path}")
        
        # 检查是否为系统文件
        if self._is_system_file(path):
            self.logger.info(f"跳过系统文件: {path}")
            return False
        self.logger.info(f"系统文件检查通过: {path}")
        
        self.logger.info(f"文件应被索引: {path}")
        return True
    
    def _is_system_file(self, path: str) -> bool:
        """检测是否为系统文件"""
        # 首先检查扩展名，对已知的文档文件直接跳过可执行文件检查
        file_ext = Path(path).suffix.lower()
        document_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                              '.txt', '.md', '.csv', '.json', '.xml', '.rtf', '.html', '.htm', '.py',
                              '.js', '.java', '.cpp', '.c', '.h', '.cs', '.go', '.rs', '.php', '.rb', 
                              '.swift', '.zip', '.rar', '.7z', '.tar', '.gz'}
        
        if file_ext in document_extensions:
            # 对于已知文档类型，只检查路径模式，不检查可执行头
            if platform.system() == 'Windows':
                if re.search(r'\$[A-Za-z]', path):
                    return True
            # 检查隐藏文件
            if any(part.startswith('.') and part != '.' for part in Path(path).parts):
                return True
            return False
        
        # 对于其他文件类型，执行完整的检查
        if platform.system() == 'Windows':
            # 检查是否为临时文件或系统文件
            if re.search(r'\$[A-Za-z]', path):
                return True

        # 检查隐藏文件
        if any(part.startswith('.') and part != '.' for part in Path(path).parts):
            return True

        # 对非文档文件执行可执行文件头检查
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
                if header in [b'MZ\x90\x00', b'\x7fELF']:  # Windows和Linux可执行文件头
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
            file_type = 'unknown'
            for type_name, extensions in self.target_extensions.items():
                if file_ext in extensions:
                    file_type = type_name
                    break
            
            # 读取文件内容
            content = self._read_file_content(file_path, file_ext)
            
            # 构建文档字典
            document = {
                'path': str(file_path),
                'filename': file_path_obj.name,
                'content': content,
                'file_type': file_type,
                'size': file_size,
                'created': created_time,
                'modified': modified_time,
                'keywords': ''  # 可以后续扩展关键词提取
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
            if file_ext in ['.txt', '.md', '.json', '.xml', '.csv', '.log', '.py', '.js', '.java', '.cpp', '.c', '.h']:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except UnicodeDecodeError:
                    # 尝试其他编码
                    with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                        return f.read()
            
            # 对于其他类型，返回文件名作为内容(后续可以扩展支持PDF、Word等)
            return Path(file_path).name
        except Exception as e:
            self.logger.warning(f"读取文件内容失败 {file_path}: {str(e)}")
            return Path(file_path).name
    
    def stop_scan(self):
        """停止扫描操作"""
        self.logger.info("正在停止扫描...")
        self._stop_flag = True
    
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

    def get_scannable_files(self, directory: str = None) -> List[str]:
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
                self.scan_stats['total_files_indexed'] += 1
                self.logger.info(f"成功更新文件索引: {file_path}")
            else:
                self.scan_stats['total_files_skipped'] += 1
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
            count = 0
            for ext in extensions:
                # 这里只是统计配置中定义的类型，实际统计需要扫描文件
                pass
            stats[file_type] = count
        
        # 如果有索引管理器，可以从索引中获取实际统计
        if self.index_manager:
            try:
                # 获取索引中的文件类型统计
                searcher = self.index_manager.tantivy_index.searcher()
                collector = tantivy.Collector()
                
                # 这里需要根据实际的索引结构来统计
                # 由于我们没有直接访问tantivy的Collector，我们使用搜索来近似统计
                for file_type in stats.keys():
                    query = self.index_manager.tantivy_index.parse_query(file_type, ['file_type'])
                    top_docs = searcher.search(query, 0)  # 只需要计数，不需要结果
                    stats[file_type] = top_docs.total_count
            except Exception as e:
                self.logger.warning(f"获取索引中文件类型统计失败: {str(e)}")
        
        return stats

    def scan_with_filters(self, filters: Dict = None) -> Dict:
        """使用过滤器扫描文件"""
        if filters is None:
            filters = {}
        
        # 保存原始统计信息
        original_stats = self.scan_stats.copy()
        
        # 重置统计信息
        self.scan_stats = {
            'total_files_scanned': 0,
            'total_files_indexed': 0,
            'total_files_skipped': 0,
            'total_size_scanned': 0,
            'scan_time': 0,
            'last_scan_time': None
        }
        
        start_time = time.time()
        
        # 根据过滤器执行扫描
        scan_paths = filters.get('scan_paths', self.scan_paths)
        file_types = filters.get('file_types', None)
        
        for path in scan_paths:
            if self._stop_flag:
                break
            self._scan_directory(Path(path), 0)  # 这里简化处理，不计算预估总数
        
        self.scan_stats['scan_time'] = time.time() - start_time
        self.scan_stats['last_scan_time'] = time.time()
        
        return self.scan_stats

# 示例用法
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 这里仅作为示例，实际使用时需要传入真实的配置和依赖
    class MockConfig:
        def get(self, section, option, fallback=''):
            if section == 'file_scanner' and option == 'scan_paths':
                return './test_scan_dir'
            return fallback
            
        def getint(self, section, option, fallback=0):
            if section == 'file_scanner' and option == 'max_file_size':
                return 10
            return fallback
    
    # 配置日志用于示例
    logging.basicConfig(level=logging.INFO)
    _mock_logger = logging.getLogger(__name__)

    class MockIndexManager:
        def update_document(self, file_path):
            _mock_logger.info(f"更新文档索引: {file_path}")
    
    # 创建测试目录和文件
    test_dir = './test_scan_dir'
    os.makedirs(test_dir, exist_ok=True)
    
    test_file = os.path.join(test_dir, 'test_file.txt')
    with open(test_file, 'w') as f:
        f.write('This is a test file for file scanner.')
    
    try:
        # 初始化扫描器
        config = MockConfig()
        index_manager = MockIndexManager()
        scanner = FileScanner(config, index_manager=index_manager)
        
        # 执行扫描
        stats = scanner.scan_and_index()
        _mock_logger.info(f"扫描统计: {stats}")
        
    finally:
        # 清理测试文件和目录
        if os.path.exists(test_file):
            os.remove(test_file)
        if os.path.exists(test_dir):
            os.rmdir(test_dir)