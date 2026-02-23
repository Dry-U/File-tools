# src/utils/logger.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日志工具模块 - 提供结构化日志记录功能"""
import logging
import os
import sys
from pathlib import Path
import datetime
import json
import traceback
import atexit
from queue import Queue
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler, QueueHandler, QueueListener
from typing import Optional, Dict, Any, Union, Literal
import threading
import time
from functools import wraps
from dataclasses import dataclass, asdict
from enum import Enum

class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

@dataclass
class LogContext:
    """日志上下文数据类"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    module: Optional[str] = None
    component: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

class LoggerConfig:
    """日志配置类"""

    def __init__(self, config):
        from backend.utils.config_loader import ConfigLoader
        if isinstance(config, ConfigLoader):
            self.log_level = config.get('system', 'log_level', 'INFO')
            self.log_dir = config.get('system', 'data_dir', './data') + '/logs'
            self.log_max_size = config.get('system', 'log_max_size', 10)
            self.log_backup_count = config.get('system', 'log_backup_count', 5)
            self.log_rotation = config.get('system', 'log_rotation', 'midnight')
            self.log_format = config.get('system', 'log_format', 'structured')
            self.log_json = config.get('system', 'log_json', False)
            self.log_sensitive_data = config.get('system', 'log_sensitive_data', False)
        else:
            system_config = config.get('system', {}) if hasattr(config, 'get') else {}
            self.log_level = system_config.get('log_level', 'INFO')
            self.log_dir = system_config.get('data_dir', './data') + '/logs'
            self.log_max_size = system_config.get('log_max_size', 10)
            self.log_backup_count = system_config.get('log_backup_count', 5)
            self.log_rotation = system_config.get('log_rotation', 'midnight')
            self.log_format = system_config.get('log_format', 'structured')
            self.log_json = system_config.get('log_json', False)
            self.log_sensitive_data = system_config.get('log_sensitive_data', False)

    def get_log_level(self) -> int:
        """获取日志级别"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'WARN': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
            'FATAL': logging.CRITICAL
        }
        return level_map.get(self.log_level.upper(), logging.INFO)

class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器
    
    支持标准格式和JSON格式输出
    包含丰富的上下文信息
    """

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, log_json: bool = False, style: Literal['%', '{', '$'] = '%'):
        super().__init__(fmt or '%(message)s', datefmt, style)
        self.log_json = log_json
        self.log_format = fmt

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        record.timestamp = datetime.datetime.fromtimestamp(record.created).isoformat()
        record.thread_name = threading.current_thread().name
        record.process_id = os.getpid()

        if self.log_json:
            log_data = {
                "timestamp": record.timestamp,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "thread": record.thread,
                "thread_name": record.thread_name,
                "process": record.process,
                "process_id": record.process_id,
            }

            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
                log_data["traceback"] = traceback.format_exception(*record.exc_info)

            if hasattr(record, 'context'):
                log_data["context"] = record.context
            if hasattr(record, 'custom_fields'):
                log_data["custom_fields"] = record.custom_fields

            return json.dumps(log_data, ensure_ascii=False, default=str)
        else:
            return super().format(record)

class CustomFormatter(logging.Formatter):
    """自定义日志格式化器"""

    COLORS = {
        logging.DEBUG: '\033[94m',
        logging.INFO: '\033[92m',
        logging.WARNING: '\033[93m',
        logging.ERROR: '\033[91m',
        logging.CRITICAL: '\033[95m'
    }
    RESET = '\033[0m'

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, use_color: bool = True):
        super().__init__(fmt or '%(message)s', datefmt)
        self.use_color = use_color and hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        original_fmt = self._style._fmt

        if self.use_color and record.levelno in self.COLORS:
            self._style._fmt = f"{self.COLORS[record.levelno]}{original_fmt}{self.RESET}"

        formatted = super().format(record)
        self._style._fmt = original_fmt

        return formatted

class EnterpriseLogger:
    """日志记录器类
    
    提供高级日志功能，包括上下文记录、性能监控、结构化日志等
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(EnterpriseLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.logger_dict = {}
            self.listeners = {}
            self.contexts = threading.local()
            self.initialized = True
            atexit.register(self.shutdown)

    def shutdown(self):
        """关闭所有日志监听器"""
        for listener in self.listeners.values():
            try:
                listener.stop()
            except Exception:
                pass

    def get_logger(self, name: str = 'file-tools', config = None) -> logging.Logger:
        """获取配置好的日志记录器"""
        if name not in self.logger_dict:
            # 创建新的logger实例
            logger = self._create_logger(name, config)
            self.logger_dict[name] = logger
        return self.logger_dict[name]

    def _create_logger(self, name: str, config) -> logging.Logger:
        """创建并配置日志记录器"""
        # 创建logger
        logger = logging.getLogger(name)
        
        # 避免重复添加处理器
        if logger.handlers:
            logger.handlers.clear()
        
        if config is None:
            from backend.utils.config_loader import ConfigLoader
            config = ConfigLoader()
        
        # 设置日志级别
        logger_config = LoggerConfig(config)
        log_level = logger_config.get_log_level()
        logger.setLevel(log_level)
        
        # 根据配置决定使用哪种格式化器
        if logger_config.log_json:
            formatter = StructuredFormatter(log_json=True)
        elif logger_config.log_format == 'structured':
            formatter = StructuredFormatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                log_json=False
            )
        else:
            formatter = CustomFormatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

        # 收集实际的处理器
        handlers = []

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

        # 创建文件处理器
        log_dir = Path(logger_config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f'{name}.log'
        
        # 根据配置选择轮转方式
        if logger_config.log_rotation == 'size':
            max_bytes = logger_config.log_max_size * 1024 * 1024  # 转换为字节
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=logger_config.log_backup_count,
                encoding='utf-8'
            )
        else:
            file_handler = TimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=logger_config.log_backup_count,
                encoding='utf-8'
            )
            file_handler.suffix = '%Y-%m-%d.log'

        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

        # 创建异步日志队列和监听器
        log_queue = Queue(-1)  # 无限大小的队列
        queue_handler = QueueHandler(log_queue)
        listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
        
        # 启动监听器并保存引用
        listener.start()
        self.listeners[name] = listener
        
        # 只添加QueueHandler到logger
        logger.addHandler(queue_handler)
        
        # 防止日志向上传播
        logger.propagate = False
        
        return logger

    def set_context(self, context: LogContext):
        """设置当前线程的日志上下文"""
        self.contexts.context = context

    def clear_context(self):
        """清除当前线程的日志上下文"""
        if hasattr(self.contexts, 'context'):
            delattr(self.contexts, 'context')

    def get_context(self) -> Optional[LogContext]:
        """获取当前线程的日志上下文"""
        return getattr(self.contexts, 'context', None)

    def log_with_context(self, logger: logging.Logger, level: LogLevel, message: str, 
                        custom_fields: Optional[Dict[str, Any]] = None, **kwargs):
        """记录带有上下文信息的日志"""
        context = self.get_context()
        extra = {}
        
        if context:
            extra['context'] = {
                'user_id': context.user_id,
                'session_id': context.session_id,
                'request_id': context.request_id,
                'module': context.module,
                'component': context.component
            }
        
        if custom_fields or (context and context.custom_fields):
            final_custom_fields = {}
            if context and context.custom_fields:
                final_custom_fields.update(context.custom_fields)
            if custom_fields:
                final_custom_fields.update(custom_fields)
            extra['custom_fields'] = final_custom_fields
        
        # 添加其他参数到日志中
        extra.update(kwargs)
        
        logger.log(level.value, message, extra=extra)


def setup_logger(
    name: str = 'file-tools',
    log_level: Optional[int] = None,
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    config = None,
    console: bool = True,
    file: bool = True,
    rotating: bool = True,
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    date_format: str = '%Y-%m-%d %H:%M:%S'
) -> logging.Logger:
    """设置日志记录器（兼容旧接口）"""
    enterprise_logger = EnterpriseLogger()
    return enterprise_logger.get_logger(name, config)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取已配置的日志记录器（兼容旧接口）"""
    if name is None:
        name = 'file-tools'
    enterprise_logger = EnterpriseLogger()
    return enterprise_logger.get_logger(name)


def set_context(context: LogContext):
    """设置日志上下文"""
    enterprise_logger = EnterpriseLogger()
    enterprise_logger.set_context(context)


def clear_context():
    """清除日志上下文"""
    enterprise_logger = EnterpriseLogger()
    enterprise_logger.clear_context()


def log_execution_time(func):
    """装饰器：记录函数执行时间"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        logger.info(f"开始执行函数: {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"函数 {func.__name__} 执行完成，耗时: {execution_time:.4f}秒")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"函数 {func.__name__} 执行失败，耗时: {execution_time:.4f}秒，错误: {str(e)}")
            raise
    return wrapper


def log_error_with_context(context: Optional[LogContext] = None):
    """装饰器：记录函数错误并包含上下文信息"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            
            if context:
                set_context(context)
                
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"函数 {func.__name__} 执行出错: {str(e)}",
                    exc_info=True
                )
                raise
            finally:
                if context:
                    clear_context()
        return wrapper
    return decorator


def performance_monitor(metric_name: str, description: str = ""):
    """装饰器：监控函数性能指标"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start_time = time.time()
            start_memory = 0  # 简化实现，实际应用中可使用psutil
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.info(
                    f"性能指标: {metric_name}",
                    extra={
                        'metric_name': metric_name,
                        'description': description,
                        'execution_time': execution_time,
                        'status': 'success'
                    }
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"性能指标: {metric_name} 执行失败",
                    extra={
                        'metric_name': metric_name,
                        'description': description,
                        'execution_time': execution_time,
                        'status': 'error',
                        'error': str(e)
                    }
                )
                raise
        return wrapper
    return decorator


# 便捷的日志记录函数（兼容旧接口）
def debug(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录调试级别日志"""
    logger = get_logger()
    logger.debug(message, *args, **kwargs)

def info(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录信息级别日志"""
    logger = get_logger()
    logger.info(message, *args, **kwargs)

def warning(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录警告级别日志"""
    logger = get_logger()
    logger.warning(message, *args, **kwargs)

def error(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录错误级别日志"""
    logger = get_logger()
    logger.error(message, *args, **kwargs)

def critical(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录严重错误级别日志"""
    logger = get_logger()
    logger.critical(message, *args, **kwargs)

def exception(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录异常日志"""
    logger = get_logger()
    logger.exception(message, *args, **kwargs)