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
from typing import List, Dict, Set, Optional
import logging
from backend.core.document_parser import DocumentParser

class FileScanner:
    """文件扫描器类，负责扫描文件系统并识别可索引文件"""
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
        
        # 依赖组件
        self.document_parser = document_parser or DocumentParser(config_loader)
        self.index_manager = index_manager
        
        # 进度回调
        self.progress_callback = None
        
        # 扫描控制标志
        self._stop_flag = False
        
        # 扫描统计信息
        self.scan_stats = {
            'total_files_scanned': 0,
            'total_files_indexed': 0,
            'total_files_skipped': 0,
            'total_size_scanned': 0,
            'scan_time': 0,
            'last_scan_time': None
        }
        
        self.logger.info(f"文件扫描器初始化完成，配置: 扫描路径 {len(self.scan_paths)} 个, 排除模式 {len(self.exclude_patterns)} 个")
        
    def set_progress_callback(self, callback):
        """设置进度回调函数"""
        self.progress_callback = callback
        return self
    
    def _get_scan_paths(self) -> List[str]:
        """从配置中获取扫描路径"""
        scan_paths_str = ""
        try:
            scan_paths_value = self.config_loader.get('file_scanner', 'scan_paths', "")
            scan_paths_str = str(scan_paths_value)
            self.logger.info(f"配置的扫描路径字符串: {scan_paths_str}")
        except Exception as e:
            self.logger.error(f"获取扫描路径配置失败: {str(e)}")
            scan_paths_str = ""
        
        # 确保scan_paths_str是字符串类型
        if not isinstance(scan_paths_str, str):
            scan_paths_str = str(scan_paths_str)
        
        scan_paths = scan_paths_str.split(';')
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
        """扫描所有配置的路径并索引文件"""
        start_time = time.time()
        self.logger.info("开始扫描并索引文件")
        self.logger.info(f"扫描路径列表: {self.scan_paths}")

        # 重置停止标志
        self._stop_flag = False

        # 重置扫描统计信息
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

        # 预估总文件数用于进度计算
        total_files_estimate = 0
        for path in self.scan_paths:
            try:
                # 简单估算文件数量，避免长时间计算
                for root, dirs, files in os.walk(path):
                    if self._stop_flag:
                        break
                    total_files_estimate += len(files)
                    # 限制估算以避免长时间阻塞
                    if total_files_estimate > 10000:  # 限制估算数量
                        break
                if total_files_estimate > 10000:
                    break
            except Exception:
                continue

        scanned_count = 0
        # 扫描每个配置的路径
        self.logger.info(f"开始扫描 {len(self.scan_paths)} 个路径，预估文件数: {total_files_estimate}")
        for i, path in enumerate(self.scan_paths):
            self.logger.info(f"扫描路径[{i}]: {path}")
            if self._stop_flag:
                self.logger.info("扫描已被停止")
                break
            self._scan_directory_with_progress(Path(path), total_files_estimate)

        # 设置完成进度
        if self.progress_callback:
            try:
                self.progress_callback(100)
            except Exception as e:
                self.logger.warning(f"完成进度回调失败: {str(e)}")

        # 计算扫描时间
        self.scan_stats['scan_time'] = time.time() - start_time
        self.scan_stats['last_scan_time'] = time.time()

        self.logger.info(f"扫描完成，统计: 扫描文件 {self.scan_stats['total_files_scanned']} 个, 索引文件 {self.scan_stats['total_files_indexed']} 个, 跳过文件 {self.scan_stats['total_files_skipped']} 个, 耗时 {self.scan_stats['scan_time']:.2f} 秒")

        return self.scan_stats

    def _scan_directory_with_progress(self, dir_path: Path, total_estimate: int) -> None:
        """带进度更新的目录扫描"""
        self.logger.info(f"扫描目录: {dir_path}")

        # Log if directory exists and is accessible
        if not dir_path.exists():
            self.logger.warning(f"扫描目录不存在: {dir_path}")
            return
        if not dir_path.is_dir():
            self.logger.warning(f"扫描路径不是目录: {dir_path}")
            return

        try:
            self.logger.info(f"开始遍历目录: {dir_path}")

            # 避免将整个目录树加载到内存中，使用迭代器方式
            try:
                # 使用walk方法替代rglob，对大目录更友好
                import os
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
                                if not (stat_result.st_mode & 0o170000 == 0o100000):  # 普通文件检查
                                    continue
                            except OSError:
                                self.logger.warning(f"无法获取文件状态 {file_path}, 跳过")
                                continue

                            self.logger.debug(f"处理文件: {file_path}")
                            self._process_file(file_path)
                            file_count += 1

                            # 更新进度（如果预估总数大于0）
                            if total_estimate > 0:
                                progress = min(99, int((self.scan_stats['total_files_scanned'] / total_estimate) * 100))
                                if self.progress_callback and file_count % 10 == 0:  # 每10个文件更新一次进度
                                    try:
                                        self.progress_callback(progress)
                                    except Exception as e:
                                        self.logger.warning(f"更新进度回调失败: {str(e)}")

                            if file_count % 100 == 0:  # 每处理100个文件记录一次日志
                                self.logger.info(f"已处理 {file_count} 个文件...")
                        except Exception as e:
                            # 单个文件处理失败不应停止整个扫描
                            self.logger.error(f"处理文件失败 {file_name} in {root}: {str(e)}")
                            continue

                self.logger.info(f"目录扫描完成，共处理 {file_count} 个文件")
            except Exception as e:
                self.logger.error(f"遍历目录失败 {dir_path}: {str(e)}")
                import traceback
                self.logger.error(f"详细错误信息: {traceback.format_exc()}")
                return

        except PermissionError:
            self.logger.error(f"无权限访问目录: {dir_path}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
        except Exception as e:
            self.logger.error(f"扫描目录失败 {dir_path}: {str(e)}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")

    def _scan_directory(self, dir_path: Path) -> None:
        """递归扫描目录并索引符合条件的文件"""
        self.logger.info(f"扫描目录: {dir_path}")

        # Log if directory exists and is accessible
        if not dir_path.exists():
            self.logger.warning(f"扫描目录不存在: {dir_path}")
            return
        if not dir_path.is_dir():
            self.logger.warning(f"扫描路径不是目录: {dir_path}")
            return

        try:
            self.logger.info(f"开始遍历目录: {dir_path}")

            # 避免将整个目录树加载到内存中，使用迭代器方式
            try:
                # 使用walk方法替代rglob，对大目录更友好
                import os
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
                                if not (stat_result.st_mode & 0o170000 == 0o100000):  # 普通文件检查
                                    continue
                            except OSError:
                                self.logger.warning(f"无法获取文件状态 {file_path}, 跳过")
                                continue

                            self.logger.debug(f"处理文件: {file_path}")
                            self._process_file(file_path)
                            file_count += 1
                            if file_count % 50 == 0:  # 每处理50个文件记录一次日志
                                self.logger.info(f"已处理 {file_count} 个文件...")
                        except Exception as e:
                            # 单个文件处理失败不应停止整个扫描
                            self.logger.error(f"处理文件失败 {file_name} in {root}: {str(e)}")
                            continue

                self.logger.info(f"目录扫描完成，共处理 {file_count} 个文件")
            except Exception as e:
                self.logger.error(f"遍历目录失败 {dir_path}: {str(e)}")
                import traceback
                self.logger.error(f"详细错误信息: {traceback.format_exc()}")
                return

        except PermissionError:
            self.logger.error(f"无权限访问目录: {dir_path}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
        except Exception as e:
            self.logger.error(f"扫描目录失败 {dir_path}: {str(e)}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
    
    def _process_file(self, file_path: Path) -> bool:
        """处理单个文件，检查是否应索引并执行索引操作"""
        file_path_str = str(file_path)
        self.scan_stats['total_files_scanned'] += 1
        
        # 每处理10个文件就更新一次进度
        if self.progress_callback and self.scan_stats['total_files_scanned'] % 10 == 0:
            try:
                # 计算进度百分比 (简单估算,每100个文件增加1%)
                progress = min(99, self.scan_stats['total_files_scanned'] // 100)
                self.progress_callback(progress)
            except Exception as e:
                self.logger.warning(f"更新进度回调失败: {str(e)}")
        
        # 检查是否应索引该文件
        if self._should_index(file_path_str):
            try:
                # 记录文件大小
                file_size = file_path.stat().st_size
                self.scan_stats['total_size_scanned'] += file_size
                
                # 执行索引操作
                success = self._index_file(file_path_str)
                if success:
                    self.scan_stats['total_files_indexed'] += 1
                    return True
                else:
                    self.scan_stats['total_files_skipped'] += 1
                    return False
            except Exception as e:
                self.logger.error(f"处理文件失败 {file_path_str}: {str(e)}")
                self.scan_stats['total_files_skipped'] += 1
                return False
        else:
            self.scan_stats['total_files_skipped'] += 1
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
    
    class MockIndexManager:
        def update_document(self, file_path):
            print(f"更新文档索引: {file_path}")
    
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
        print(f"扫描统计: {stats}")
        
    finally:
        # 清理测试文件和目录
        if os.path.exists(test_file):
            os.remove(test_file)
        if os.path.exists(test_dir):
            os.rmdir(test_dir)