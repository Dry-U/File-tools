#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件监控器模块 - 监控文件系统变化"""
import os
import time
import logging
from typing import TYPE_CHECKING, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from datetime import datetime

if TYPE_CHECKING:
    from backend.core.index_manager import IndexManager

class FileMonitor:
    """文件监控器类，负责监控指定目录的文件变化"""
    def __init__(self, config_loader, index_manager=None, file_scanner=None):
        self.config_loader = config_loader
        self.index_manager: Optional['IndexManager'] = index_manager
        self.file_scanner = file_scanner
        self.logger = logging.getLogger(__name__)
        
        # 监控配置 - 使用ConfigLoader获取配置
        self.monitored_dirs = self._get_monitored_directories()
        self.ignored_patterns = self._get_ignored_patterns()
        monitor_config = config_loader.get('monitor')
        if monitor_config is None:
            monitor_config = {}
        self.refresh_interval = int(monitor_config.get('refresh_interval', 1))
        
        # 初始化监控器
        self.observer = None
        self.handler = None
        self.is_running = False
        
        # 用于去重和防抖
        self._event_buffer = {}
        self._last_process_time = time.time()
        self._buffer_timeout = 0.5  # 事件缓冲超时时间（秒）
        
        self.logger.info(f"文件监控器初始化完成，监控目录: {', '.join(self.monitored_dirs)}")
    
    def _get_monitored_directories(self):
        """从配置中获取需要监控的目录"""
        monitored_dirs = []
        
        # 从配置中获取监控目录 - 使用ConfigLoader
        try:
            # 使用ConfigLoader获取monitor配置
            monitor_config = self.config_loader.get('monitor')
            if monitor_config is None:
                monitor_config = {}
            config_dirs = monitor_config.get('directories', '')
        except Exception as e:
            self.logger.error(f"获取监控目录配置失败: {str(e)}")
            config_dirs = ''
        
        if config_dirs:
            # 分割配置中的目录列表
            for dir_path in config_dirs.split(';'):
                dir_path = dir_path.strip()
                if dir_path and os.path.exists(dir_path):
                    monitored_dirs.append(os.path.abspath(dir_path))
        
        # 如果没有配置监控目录,在Windows系统下监控所有磁盘驱动器
        if not monitored_dirs:
            if os.name == 'nt':  # Windows系统
                # 使用ctypes获取所有磁盘驱动器(标准库方案)
                drives = []
                try:
                    import ctypes
                    # 遍历可能的驱动器字母 A-Z
                    for drive_letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        drive_path = f"{drive_letter}:\\"
                        # 使用GetDriveType函数检查是否为有效的驱动器
                        # 类型: 2=可移动磁盘 3=固定磁盘 4=网络驱动器 5=光驱 6=RAM磁盘
                        if ctypes.windll.kernel32.GetDriveTypeW(drive_path) in [2, 3, 4, 5, 6]:
                            if os.path.exists(drive_path):
                                drives.append(drive_path)
                except Exception as e:
                    self.logger.error(f"使用ctypes获取驱动器信息失败: {str(e)}")
                    # 最终备选方案：尝试使用win32api
                    try:
                        import win32api  # type: ignore
                        drives_str = win32api.GetLogicalDriveStrings()
                        drives = drives_str.split('\\000')[:-1]
                    except (ImportError, Exception) as e:
                        self.logger.warning(f"win32api备选方案也失败: {str(e)}")
                        drives = []
                        
                # 添加检测到的驱动器
                if drives:
                    for drive in drives:
                        drive_path = os.path.abspath(drive)
                        if os.path.exists(drive_path) and os.path.isdir(drive_path):
                            monitored_dirs.append(drive_path)
                    self.logger.info(f"未配置监控目录，默认监控所有磁盘驱动器: {', '.join(monitored_dirs)}")
                else:
                    # 无法获取驱动器信息时使用用户主目录作为备选
                    default_dir = os.path.expanduser('~')
                    if os.path.exists(default_dir):
                        monitored_dirs.append(default_dir)
                        self.logger.warning(f"未配置监控目录，无法自动检测所有磁盘驱动器，默认监控用户主目录: {default_dir}")
            else:
                # 非Windows系统，保持使用用户主目录
                default_dir = os.path.expanduser('~')
                if os.path.exists(default_dir):
                    monitored_dirs.append(default_dir)
                    self.logger.warning(f"未配置监控目录，默认监控用户主目录: {default_dir}")
                else:
                    self.logger.error("未配置监控目录，且默认用户主目录不存在")
        
        return monitored_dirs
    
    def _get_ignored_patterns(self):
        """从配置中获取需要忽略的文件模式"""
        ignored_patterns = set()
        
        # 从配置中获取忽略模式 - 使用ConfigLoader
        monitor_config = self.config_loader.get('monitor')
        if monitor_config is None:
            monitor_config = {}
        config_patterns = monitor_config.get('ignored_patterns', '')
        if config_patterns:
            for pattern in config_patterns.split(';'):
                pattern = pattern.strip()
                if pattern:
                    ignored_patterns.add(pattern)
        
        # 添加默认的忽略模式
        default_ignored = {
            '.git', '.svn', '.hg', '__pycache__', '.idea', '.vscode',
            'node_modules', 'venv', 'env', '.DS_Store', 'Thumbs.db',
            '.cache', '.log', '.tmp', '.temp', '.bak', '~$'
        }
        ignored_patterns.update(default_ignored)
        
        return ignored_patterns
    
    def start_monitoring(self):
        """开始监控文件系统变化"""
        if self.is_running:
            self.logger.warning("监控器已经在运行中")
            return
        
        try:
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
            
            self.logger.info(f"文件监控已启动，监控 {len(self.monitored_dirs)} 个目录")
        except Exception as e:
            self.logger.error(f"启动文件监控失败: {str(e)}")
            self.is_running = False
            if self.observer:
                try:
                    self.observer.stop()
                    self.observer.join()
                except:
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
            
            self.is_running = False
            self.logger.info("文件监控已停止")
        except Exception as e:
            self.logger.error(f"停止文件监控失败: {str(e)}")
    
    def process_event(self, event):
        """处理文件系统事件"""
        # 检查是否需要忽略此事件
        if self._should_ignore(event):
            return
        
        # 获取事件路径
        event_path = event.src_path if event.is_directory else event.src_path
        event_type = event.event_type
        
        # 记录事件
        self.logger.debug(f"接收到文件系统事件: {event_type} - {event_path}")
        
        # 将事件添加到缓冲区
        self._event_buffer[event_path] = {
            'type': event_type,
            'path': event_path,
            'timestamp': time.time()
        }
        
        # 定期处理缓冲区中的事件（防抖）
        current_time = time.time()
        if current_time - self._last_process_time >= self._buffer_timeout:
            self._process_buffer()
            self._last_process_time = current_time
    
    def _should_ignore(self, event):
        """检查是否应该忽略某个事件"""
        # 获取事件路径
        event_path = event.src_path
        
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
    
    def _process_buffer(self):
        """处理事件缓冲区"""
        if not self._event_buffer:
            return
        
        current_time = time.time()
        processed_count = 0
        
        # 处理超时的事件
        paths_to_remove = []
        
        for path, event_info in self._event_buffer.items():
            if current_time - event_info['timestamp'] >= self._buffer_timeout:
                self._handle_event(event_info)
                paths_to_remove.append(path)
                processed_count += 1
        
        # 从缓冲区中移除已处理的事件
        for path in paths_to_remove:
            del self._event_buffer[path]
        
        if processed_count > 0:
            self.logger.debug(f"处理了 {processed_count} 个文件系统事件")
    
    def _handle_event(self, event_info):
        """处理单个文件系统事件"""
        event_type = event_info['type']
        event_path = event_info['path']
        
        try:
            # 根据事件类型执行相应操作
            if event_type in ('created', 'modified'):
                # 确保文件存在
                if os.path.exists(event_path):
                    # 更新索引
                    self._update_index_for_file(event_path)
            elif event_type == 'deleted':
                # 从索引中删除
                self._remove_from_index(event_path)
            elif event_type == 'moved':
                # 注意：这里简化处理，实际上应该处理移动源路径和目标路径
                # 为简化，我们假设这是一个重命名操作，先删除旧路径，再添加新路径
                if 'dest_path' in event_info:
                    dest_path = event_info['dest_path']
                    if os.path.exists(dest_path):
                        self._remove_from_index(event_path)
                        self._update_index_for_file(dest_path)
        except Exception as e:
            self.logger.error(f"处理文件系统事件失败 {event_type} - {event_path}: {str(e)}")
    
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
            from pathlib import Path
            from datetime import datetime
            import os
            
            file_path_obj = Path(file_path)
            
            # 获取文件基本信息
            stat_info = file_path_obj.stat()
            file_size = stat_info.st_size
            created_time = datetime.fromtimestamp(stat_info.st_ctime)
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)
            
            # 获取文件扩展名
            file_ext = file_path_obj.suffix.lower()
            
            # 简单的文件类型分类
            if file_ext in ['.txt', '.md', '.json', '.xml', '.csv', '.log', '.py', '.js', '.java', '.cpp', '.c', '.h']:
                file_type = 'document'
            elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg']:
                file_type = 'image'
            elif file_ext in ['.mp3', '.wav', '.flac', '.ogg', '.m4a']:
                file_type = 'audio'
            elif file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv']:
                file_type = 'video'
            elif file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
                file_type = 'archive'
            else:
                file_type = 'unknown'
            
            # 读取文件内容（简化处理）
            content = file_path_obj.name  # 默认使用文件名作为内容
            try:
                # 对于文本类文件，尝试读取内容
                if file_ext in ['.txt', '.md', '.json', '.xml', '.csv', '.log', '.py', '.js', '.java', '.cpp', '.c', '.h']:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(1000)  # 限制读取内容大小
            except Exception:
                pass  # 保持默认内容
            
            # 构建文档字典
            document = {
                'path': str(file_path),
                'filename': file_path_obj.name,
                'content': content,
                'file_type': file_type,
                'size': file_size,
                'created': created_time,
                'modified': modified_time,
                'keywords': ''
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
        
        # 检查目录是否在监控列表中
        if dir_path not in self.monitored_dirs:
            self.logger.warning(f"目录不在监控列表中: {dir_path}")
            return True
        
        try:
            # 从监控列表中移除
            self.monitored_dirs.remove(dir_path)
            
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
            # 如果移除失败，重新添加到列表
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 这里仅作为示例，实际使用时需要传入真实的索引管理器和配置
    class MockIndexManager:
        def update_document(self, file_path):
            print(f"更新文档索引: {file_path}")
            
        def delete_document(self, file_path):
            print(f"删除文档索引: {file_path}")
    
    class MockConfig:
        def get(self, section, option, fallback=None):
            if section == 'monitor' and option == 'directories':
                return './test_dir'
            return fallback
            
        def getint(self, section, option, fallback=0):
            return fallback
    
    # 创建测试目录
    test_dir = './test_dir'
    os.makedirs(test_dir, exist_ok=True)
    
    try:
        # 初始化监控器
        index_manager = MockIndexManager()
        config = MockConfig()
        monitor = FileMonitor(index_manager, config)
        
        # 启动监控
        monitor.start_monitoring()
        
        # 创建测试文件
        test_file = os.path.join(test_dir, 'test_file.txt')
        with open(test_file, 'w') as f:
            f.write('This is a test file.')
        
        # 修改测试文件
        time.sleep(1)
        with open(test_file, 'a') as f:
            f.write('\nModified content.')
        
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

