# src/utils/logger.py
import logging
import logging.handlers
from pathlib import Path
import yaml

def setup_logger(config_path: str = 'config.yaml') -> logging.Logger:
    """设置企业级日志系统，支持文件轮转和级别配置"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    log_level = config['system'].get('log_level', 'INFO')
    log_dir = Path(config['system']['data_dir']) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger('doc-assistant')
    logger.setLevel(log_level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # 文件处理器（轮转日志，每日新文件）
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / 'app.log', when='midnight', interval=1, backupCount=7
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger