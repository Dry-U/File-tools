# src/core/file_scanner.py
import re
import platform
import time
from pathlib import Path
from typing import List, Dict
from collections import deque
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.core.smart_indexer import SmartIndexer  # 前向引用；实际导入

logger = setup_logger()

class FileChangeHandler(FileSystemEventHandler):
    """Watchdog事件处理器：捕获文件变化"""
    def __init__(self, indexer: 'SmartIndexer'):
        self.indexer = indexer

    def on_modified(self, event):
        if not event.is_directory:
            self.indexer.add_change(event.src_path, 'update')

    def on_created(self, event):
        if not event.is_directory:
            self.indexer.add_change(event.src_path, 'update')

    def on_deleted(self, event):
        if not event.is_directory:
            self.indexer.add_change(event.src_path, 'delete')

class FileScanner:
    """智能文件扫描器：识别、扫描和监控（基于文档3.1.1，增强）"""

    def __init__(self, config: ConfigLoader):
        self.config = config
        self.scan_paths: List[str] = config.get('file_scanner', 'scan_paths', [])
        self.exclude_patterns: List[str] = config.get('file_scanner', 'exclude_patterns', [])
        self.max_file_size: int = config.get('file_scanner', 'max_file_size', 100) * 1024 * 1024  # MB to bytes
        self.target_extensions: Dict[str, List[str]] = config.get('file_scanner', 'file_types', {})
        self.all_extensions = [ext for exts in self.target_extensions.values() for ext in exts]
        self.indexer = SmartIndexer(config)  # 注入索引器
        self.observer = Observer()  # Watchdog观察者

    def scan_and_index(self):
        """初始扫描并索引所有路径"""
        for path in self.scan_paths:
            self._scan_directory(Path(path).expanduser())
        self.indexer.process_changes()  # 触发批量索引
        self._start_monitoring()  # 启动实时监控

    def _scan_directory(self, dir_path: Path):
        """递归扫描目录，过滤并添加变化"""
        try:
            for file_path in dir_path.rglob('*'):
                if file_path.is_file() and self._should_index(str(file_path)):
                    self.indexer.add_change(str(file_path), 'update')
        except Exception as e:
            logger.error(f"扫描目录失败 {dir_path}: {e}")

    def _should_index(self, path: str) -> bool:
        """检查是否应索引：扩展、排除、大小、系统文件"""
        p = Path(path)
        if p.stat().st_size > self.max_file_size:
            return False
        
        if not any(p.suffix.lower() in self.all_extensions):
            return False
        
        if any(re.search(pattern, path) for pattern in self.exclude_patterns):
            return False
        
        return not self._is_system_file(path)

    def _is_system_file(self, path: str) -> bool:
        """高级系统文件检测（基于文档代码）"""
        if platform.system() == 'Windows':
            if re.search(r'\$[A-Za-z]', path):
                return True
        
        if any(part.startswith('.') and part != '.' for part in Path(path).parts):
            return True
        
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
                if header in [b'MZ\x90\x00', b'\x7fELF']:  # 可执行文件头
                    return True
        except Exception:
            pass  # 无法读取，假设非系统
        
        return False

    def _start_monitoring(self):
        """启动实时文件监控（使用watchdog模拟inotify/USN）"""
        event_handler = FileChangeHandler(self.indexer)
        for path in self.scan_paths:
            self.observer.schedule(event_handler, str(Path(path).expanduser()), recursive=True)
        self.observer.start()
        logger.info("文件监控启动")