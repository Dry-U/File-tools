# src/utils/logger.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日志工具模块 - 提供日志记录功能"""
import logging
import os
import sys
from pathlib import Path
import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional, Dict, Any, Union

class LoggerConfig:
    """日志配置类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.log_level = config.get('system', {}).get('log_level', 'INFO')
        self.log_dir = config.get('system', {}).get('data_dir', './data') + '/logs'
        self.log_max_size = config.get('system', {}).get('log_max_size', 10)  # MB
        self.log_backup_count = config.get('system', {}).get('log_backup_count', 5)
        self.log_rotation = config.get('system', {}).get('log_rotation', 'midnight')  # 或 'size'
    
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

class CustomFormatter(logging.Formatter):
    """自定义日志格式化器"""
    
    # 日志级别对应的颜色代码
    COLORS = {
        logging.DEBUG: '\033[94m',  # 蓝色
        logging.INFO: '\033[92m',  # 绿色
        logging.WARNING: '\033[93m',  # 黄色
        logging.ERROR: '\033[91m',  # 红色
        logging.CRITICAL: '\033[95m'  # 紫色
    }
    RESET = '\033[0m'
    
    def __init__(self, fmt: str = None, datefmt: str = None, use_color: bool = True):
        super().__init__(fmt, datefmt)
        self.use_color = use_color and hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        original_fmt = self._style._fmt
        
        # 如果支持颜色且启用了颜色，则为不同级别的日志添加颜色
        if self.use_color and record.levelno in self.COLORS:
            self._style._fmt = f"{self.COLORS[record.levelno]}{original_fmt}{self.RESET}"
        
        # 格式化日志
        formatted = super().format(record)
        
        # 恢复原始格式
        self._style._fmt = original_fmt
        
        return formatted

def setup_logger(
    name: str = 'file-tools',
    log_level: Optional[int] = None,
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    console: bool = True,
    file: bool = True,
    rotating: bool = True,
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    date_format: str = '%Y-%m-%d %H:%M:%S'
) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别
        log_file: 日志文件路径
        log_dir: 日志目录
        config: 配置字典，可从中获取日志配置
        console: 是否输出到控制台
        file: 是否输出到文件
        rotating: 是否使用轮转日志
        log_format: 日志格式
        date_format: 日期格式
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 创建logger
    logger = logging.getLogger(name)
    
    # 如果logger已经配置，先清空处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 设置日志级别
    if log_level is None:
        if config:
            logger_config = LoggerConfig(config)
            log_level = logger_config.get_log_level()
        else:
            log_level = logging.INFO
    
    logger.setLevel(log_level)
    
    # 创建格式化器
    formatter = CustomFormatter(log_format, date_format)
    
    # 创建控制台处理器
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 创建文件处理器（如果指定了日志文件或目录）
    if file and (log_file or log_dir):
        # 确保日志目录存在
        if not log_file and log_dir:
            log_dir_path = Path(log_dir)
            log_dir_path.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir_path / f'{name}.log')
        elif log_file and not log_dir:
            log_dir_path = Path(log_file).parent
            log_dir_path.mkdir(parents=True, exist_ok=True)
        
        # 创建文件处理器
        if rotating and config:
            logger_config = LoggerConfig(config)
            if logger_config.log_rotation == 'size':
                # 基于大小的轮转日志
                max_bytes = logger_config.log_max_size * 1024 * 1024  # 转换为字节
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=logger_config.log_backup_count,
                    encoding='utf-8'
                )
            else:
                # 基于时间的轮转日志
                file_handler = TimedRotatingFileHandler(
                    log_file,
                    when='midnight',
                    interval=1,
                    backupCount=logger_config.log_backup_count,
                    encoding='utf-8'
                )
                file_handler.suffix = '%Y-%m-%d.log'
        else:
            # 普通文件日志
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def get_logger(name: str = None) -> logging.Logger:
    """获取已配置的日志记录器
    
    Args:
        name: 日志记录器名称，如果为None则获取根日志记录器
    
    Returns:
        logging.Logger: 日志记录器
    """
    return logging.getLogger(name)

def debug(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录调试级别日志"""
    get_logger().debug(message, *args, **kwargs)

def info(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录信息级别日志"""
    get_logger().info(message, *args, **kwargs)

def warning(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录警告级别日志"""
    get_logger().warning(message, *args, **kwargs)

def error(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录错误级别日志"""
    get_logger().error(message, *args, **kwargs)

def critical(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录严重错误级别日志"""
    get_logger().critical(message, *args, **kwargs)

def exception(message: Union[str, Exception], *args, **kwargs) -> None:
    """记录异常日志"""
    get_logger().exception(message, *args, **kwargs)