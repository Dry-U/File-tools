# src/utils/config_loader.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置加载器模块 - 负责加载、验证和管理配置"""
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import os
import datetime
import logging

logger = logging.getLogger(__name__)

class ConfigLoader:
    """配置加载器类，负责加载、验证和管理配置文件"""
    def __init__(self, config_path: Optional[str] = None):
        # 默认配置路径，如果未指定则使用当前目录下的config.yaml
        default_path = Path('config.yaml')
        self.config_path = Path(config_path).resolve() if config_path is not None else default_path.resolve()
        self.config: Dict[str, Any] = {}  # 初始化空配置
        
        # 尝试加载配置文件，如果不存在则创建默认配置
        try:
            self.config = self._load_config()
        except FileNotFoundError:
            self.config = self._create_default_config()
        except Exception as e:
            logger.error(f"配置加载失败: {str(e)}")
            self.config = self._create_default_config()
        
        # 验证配置
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件未找到: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 确保配置是字典类型
        if not isinstance(config, dict):
            config = {}
        
        return config
    
    def _create_default_config(self) -> Dict[str, Any]:
        """创建默认配置文件"""
        # 确保配置目录存在
        config_dir = self.config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        # 默认配置
        default_config = {
            'system': {
                'app_name': '智能文件检索与问答系统',
                'version': '1.0.0',
                'data_dir': './data',
                'log_level': 'INFO',
                'index_dir': './data/index',
                'cache_dir': './data/cache',
                'temp_dir': './data/temp',
                'log_backup_count': 5,
                'log_max_size': 10,
                'log_rotation': 'midnight',
                'log_format': 'structured',
                'log_json': False,
                'log_sensitive_data': False
            },
            'file_scanner': {
                'scan_paths': str(Path.home() / 'Documents'),
                'exclude_patterns': '.git;.svn;.hg;__pycache__;.idea;.vscode;node_modules;venv;env;.DS_Store;Thumbs.db',
                'max_file_size': 100,  # MB
                'file_types': {
                    'document': '.txt,.md,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.csv,.json,.xml',
                    'code': '.py,.js,.java,.cpp,.c,.h,.cs,.go,.rs,.php,.rb,.swift',
                    'archive': '.zip,.rar,.7z,.tar,.gz'
                },
                'scan_threads': 4,
                'recursive': True
            },
            'search': {
                'text_weight': 0.6,
                'vector_weight': 0.4,
                'max_results': 50,
                'highlight': True,
                'cache_ttl': 3600,  # 秒
                'min_score': 0.3,
                'bm25_k1': 1.5,
                'bm25_b': 0.75,
                'result_boost': True,
                'filename_boost': 1.5,
                'keyword_boost': 1.2,
                'hybrid_boost': 1.1,
                'semantic_score_high_threshold': 60.0,
                'semantic_score_low_threshold': 30.0
            },
            'monitor': {
                'directories': str(Path.home() / 'Documents'),
                'ignored_patterns': '.git;.svn;.hg;__pycache__;.idea;.vscode;node_modules;venv;env;.DS_Store;Thumbs.db',
                'refresh_interval': 1,
                'debounce_time': 0.5,
                'enabled': True
            },
            'embedding': {
                'enabled': True,
                'provider': 'modelscope',
                'model_name': 'iic/nlp_gte_sentence-embedding_chinese-base',
                'cache_dir': './data/models',
                'similarity_threshold': 0.7,
                'batch_size': 8
            },
            'ai_model': {
                'enabled': True,
                'interface_type': 'wsl',  # 可选值: wsl, api
                'api_format': 'openai_chat',
                'api_url': 'http://127.0.0.1:8080/v1/chat/completions',
                'api_model': 'wsl',
                'api_key': '',
                'system_prompt': '你是一名专业的中文文档助理。请根据下方的【文档集合】回答用户的【问题】。\n规则：\n1. 严格基于文档内容回答，不要编造。\n2. 如果用户询问某人、某事出现在哪里，或者询问来源，请务必列出对应的文件名。\n3. 如果答案仅出现在文件名中（例如文件名包含查询词），请明确指出该文件。\n4. 如果文档中没有相关信息，请直接说明未找到。',
                'max_tokens': 4096,
                'temperature': 0.6,
                'request_timeout': 600,
                'use_gpu': True
            },
            'rag': {
                'max_docs': 3,
                'max_context_chars': 4000,
                'max_context_chars_total': 8000,
                'max_history_turns': 3,
                'max_history_chars': 1000,
                'max_output_tokens': 2048,
                'temperature': 0.5,
                'top_p': 0.9,
                'frequency_penalty': 0.2,
                'presence_penalty': 0.2,
                'repetition_penalty': 1.1,
                'prompt_template': '你是一名专业的中文文档分析助理。请基于【文档集合】中的内容，对用户的【问题】提供一个连贯、流畅、总结性的回答。\n\n核心要求：\n1. 严格基于文档内容回答，不得编造任何信息。\n2. 将相关信息整合成一个连贯的段落，而非分点列表。\n3. 突出关键信息和核心内容，提供综合性的总结。\n4. 对于人物、研究、技术等主题，提供背景、方法、成果等的完整概述。\n5. 如需引用来源，请在回答中自然提及文档名称，而非单独列出。\n6. 重点提取技术细节、研究方法、实现方案、实验结果等知识性内容。\n7. 对于多个文档的信息，进行有机整合，形成统一的叙述。\n8. 避免机械重复文档原文，而是进行概括和总结。\n9. 确保回答逻辑清晰、语句通顺，形成完整的信息实体描述。\n\n【文档集合】:\n{context}\n\n【问题】: {question}\n\n请提供一个连贯、总结性的回答：',
                'context_exhausted_response': '对话过长，为避免超出上下文，请说\'重置\'或简要概括后再继续。',
                'reset_response': '已清空上下文，可以重新开始提问。',
                'fallback_response': '我在本地索引中暂时没有找到与" {query} "直接对应的正文内容。\n你可以：\n1. 再提供更具体的描述（如文件名、章节、作者、时间等）；\n2. 指明文件类型或格式，例如"PDF 报告""Word 文档"；\n3. 如果需要的是操作指南或检索策略，也欢迎直接告诉我，我会给出建议。\n告诉我更详细的线索后，我会立即在全部已扫描文件中再次检索。',
                'greeting_response': '你好呀，我是 FileTools Copilot，本地文件的智能助手。\n我可以帮你搜索 PDF、Word、PPT 甚至代码，把结果整理成摘要或问答。\n需要查资料、找报告要点、生成概览或者验证内容都可以直接告诉我。\n只要说出关键词或问题，我就能立刻从本地库里找到相关内容。',
                'greeting_keywords': ['你好', '您好', 'hi', 'hello', '嗨', '嘿', '在吗', '在不'],
                'reset_commands': ['重置', '清空上下文', 'reset', 'restart']
            },
            'interface': {
                'theme': 'light',
                'font_size': 12,
                'max_preview_size': 5242880,  # 5MB
                'auto_save_settings': True,
                'language': 'zh_CN',
                'result_columns': ['文件名', '路径', '匹配度', '修改时间'],
                'splitter_pos': 300
            },
            'advanced': {
                'auto_optimize_index': True,
                'index_refresh_interval': 3600,
                'max_cached_results': 1000,
                'optimize_interval': 86400,
                'whoosh_mem_limit': 512
            },
            'index': {
                'tantivy_path': './data/tantivy_index',
                'hnsw_path': './data/hnsw_index',
                'metadata_path': './data/metadata'
            }
        }

        # 保存默认配置到文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)

            # 确保配置文件有正确的权限
            if os.name == 'posix':  # Unix-like systems
                os.chmod(self.config_path, 0o600)  # 只有所有者可读写

            logger.info(f"已创建默认配置文件: {self.config_path}")
        except Exception as e:
            logger.error(f"创建默认配置文件失败: {str(e)}")

        return default_config
    
    def _validate_config(self) -> None:
        """验证配置的有效性"""
        # 确保必要的配置部分存在
        required_sections = ['system', 'file_scanner', 'search', 'monitor', 'embedding', 'ai_model', 'rag', 'interface', 'advanced', 'index']

        for section in required_sections:
            if section not in self.config:
                self.config[section] = {}

        # 确保数据目录存在
        data_dir = Path(self.get('system', 'data_dir', './data'))
        data_dir.mkdir(parents=True, exist_ok=True)

        # 确保缓存目录存在
        cache_dir = Path(self.get('system', 'cache_dir', './data/cache'))
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 确保临时目录存在
        temp_dir = Path(self.get('system', 'temp_dir', './data/temp'))
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 确保索引目录存在
        index_dir = Path(self.get('system', 'index_dir', './data/index'))
        index_dir.mkdir(parents=True, exist_ok=True)

        # 确保日志目录存在
        log_dir = Path(self.get('system', 'data_dir', './data') + '/logs')
        log_dir.mkdir(parents=True, exist_ok=True)

        # 验证并修正扫描路径
        scan_paths = self.get('file_scanner', 'scan_paths', str(Path.home() / 'Documents'))
        if isinstance(scan_paths, str):
            # 如果是字符串，转换为列表
            paths = [p.strip() for p in scan_paths.split(';') if p.strip()]
            validated_paths = []
            for path in paths:
                expanded_path = Path(path).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_paths.append(str(expanded_path))
                else:
                    logger.warning(f"扫描路径不存在: {path}")
            if not validated_paths:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / 'Documents'
                if not default_path.exists():
                    default_path = Path.home()
                validated_paths = [str(default_path)]
            self.set('file_scanner', 'scan_paths', validated_paths)
        elif isinstance(scan_paths, list):
            # 如果已经是列表，验证每个路径
            validated_paths = []
            for path in scan_paths:
                expanded_path = Path(str(path)).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_paths.append(str(expanded_path))
                else:
                    logger.warning(f"扫描路径不存在: {path}")
            if not validated_paths:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / 'Documents'
                if not default_path.exists():
                    default_path = Path.home()
                validated_paths = [str(default_path)]
            self.set('file_scanner', 'scan_paths', validated_paths)

        # 验证监控目录
        monitor_dirs = self.get('monitor', 'directories', str(Path.home() / 'Documents'))
        if isinstance(monitor_dirs, str):
            # 如果是字符串，转换为列表
            dirs = [d.strip() for d in monitor_dirs.split(';') if d.strip()]
            validated_dirs = []
            for dir_path in dirs:
                expanded_path = Path(dir_path).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_dirs.append(str(expanded_path))
                else:
                    logger.warning(f"监控目录不存在: {dir_path}")
            if not validated_dirs:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / 'Documents'
                if not default_path.exists():
                    default_path = Path.home()
                validated_dirs = [str(default_path)]
            self.set('monitor', 'directories', validated_dirs)
        elif isinstance(monitor_dirs, list):
            # 如果已经是列表，验证每个路径
            validated_dirs = []
            for dir_path in monitor_dirs:
                expanded_path = Path(str(dir_path)).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_dirs.append(str(expanded_path))
                else:
                    logger.warning(f"监控目录不存在: {dir_path}")
            if not validated_dirs:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / 'Documents'
                if not default_path.exists():
                    default_path = Path.home()
                validated_dirs = [str(default_path)]
            self.set('monitor', 'directories', validated_dirs)

        # 验证数值配置
        self._validate_numeric_configs()

    def _validate_numeric_configs(self):
        """验证数值类型的配置"""
        numeric_configs = [
            ('file_scanner', 'max_file_size', 100, 1, 1000),  # MB, 1-1000
            ('search', 'max_results', 50, 1, 1000),
            ('search', 'text_weight', 0.6, 0.0, 1.0),
            ('search', 'vector_weight', 0.4, 0.0, 1.0),
            ('search', 'min_score', 0.3, 0.0, 1.0),
            ('search', 'bm25_k1', 1.5, 0.1, 10.0),
            ('search', 'bm25_b', 0.75, 0.0, 1.0),
            ('search', 'filename_boost', 1.5, 0.1, 10.0),
            ('search', 'keyword_boost', 1.2, 0.1, 10.0),
            ('search', 'hybrid_boost', 1.1, 0.1, 5.0),
            ('search', 'semantic_score_high_threshold', 60.0, 0.0, 100.0),
            ('search', 'semantic_score_low_threshold', 30.0, 0.0, 100.0),
            ('search', 'cache_ttl', 3600, 60, 86400),  # 1分钟到1天
            ('monitor', 'refresh_interval', 1, 0.1, 60),  # 0.1秒到60秒
            ('monitor', 'debounce_time', 0.5, 0.1, 5.0),  # 0.1秒到5秒
            ('file_scanner', 'scan_threads', 4, 1, 16),
            ('rag', 'max_docs', 3, 1, 10),
            ('rag', 'max_context_chars', 4000, 100, 10000),
            ('rag', 'max_context_chars_total', 8000, 100, 20000),
            ('rag', 'max_history_turns', 3, 1, 20),
            ('rag', 'max_history_chars', 1000, 100, 5000),
            ('rag', 'max_output_tokens', 2048, 100, 8192),
            ('rag', 'temperature', 0.5, 0.0, 2.0),
            ('rag', 'top_p', 0.9, 0.0, 1.0),
            ('rag', 'frequency_penalty', 0.2, -2.0, 2.0),
            ('rag', 'presence_penalty', 0.2, -2.0, 2.0),
            ('rag', 'repetition_penalty', 1.1, 0.1, 2.0),
            ('ai_model', 'max_tokens', 4096, 100, 8192),
            ('ai_model', 'temperature', 0.6, 0.0, 2.0),
            ('ai_model', 'request_timeout', 600, 10, 3600),
            ('interface', 'font_size', 12, 8, 24),
            ('interface', 'max_preview_size', 5242880, 1024, 50*1024*1024),  # 1KB到50MB
            ('interface', 'splitter_pos', 300, 100, 1000),
            ('system', 'log_max_size', 10, 1, 100),  # MB
            ('system', 'log_backup_count', 5, 1, 20),
            ('advanced', 'index_refresh_interval', 3600, 60, 86400),
            ('advanced', 'max_cached_results', 1000, 100, 10000),
            ('advanced', 'optimize_interval', 86400, 3600, 604800),  # 1小时到7天
            ('advanced', 'whoosh_mem_limit', 512, 64, 2048)  # MB
        ]

        for section, key, default_val, min_val, max_val in numeric_configs:
            try:
                val = self.get(section, key, default_val)
                if isinstance(val, (int, float)):
                    if val < min_val or val > max_val:
                        logger.warning(f"配置项 {section}.{key} 的值 {val} 超出范围 [{min_val}, {max_val}]，使用默认值 {default_val}")
                        self.set(section, key, default_val)
                else:
                    logger.warning(f"配置项 {section}.{key} 的值 {val} 不是数值类型，使用默认值 {default_val}")
                    self.set(section, key, default_val)
            except Exception as e:
                logger.error(f"验证配置项 {section}.{key} 时出错: {e}")
                self.set(section, key, default_val)
    
    def get(self, section, key: Optional[str] = None, default: Any = None) -> Any:
        """获取配置值"""
        # 添加类型检查，防止section为dict等不可哈希类型
        if not isinstance(section, (str, int)):
            logger.warning(f"配置section必须是可哈希类型，收到类型: {type(section)}")
            return default

        if section not in self.config:
            # 尝试从配置中获取默认值
            if section == 'embedding':
                return {
                    'enabled': False,
                    'provider': 'fastembed',
                    'model_name': 'BAAI/bge-small-zh-v1.5',
                    'cache_dir': './data/models',
                    'similarity_threshold': 0.7,
                    'batch_size': 8
                } if key is None else default
            elif section == 'ai_model':
                return {
                    'enabled': False,
                    'interface_type': 'wsl',
                    'api_format': 'openai_chat',
                    'api_url': 'http://127.0.0.1:8080/v1/chat/completions',
                    'api_model': 'wsl',
                    'api_key': '',
                    'system_prompt': '你是一名专业的中文文档助理...',
                    'max_tokens': 4096,
                    'temperature': 0.6,
                    'request_timeout': 600,
                    'use_gpu': True
                } if key is None else default
            elif section == 'rag':
                return {
                    'max_docs': 3,
                    'max_context_chars': 4000,
                    'max_context_chars_total': 8000,
                    'max_history_turns': 3,
                    'max_history_chars': 1000,
                    'max_output_tokens': 2048,
                    'temperature': 0.5,
                    'top_p': 0.9,
                    'frequency_penalty': 0.2,
                    'presence_penalty': 0.2,
                    'repetition_penalty': 1.1,
                    'prompt_template': '你是一名专业的中文文档分析助理...',
                    'context_exhausted_response': '对话过长，为避免超出上下文，请说\'重置\'或简要概括后再继续。',
                    'reset_response': '已清空上下文，可以重新开始提问。',
                    'fallback_response': '我在本地索引中暂时没有找到...',
                    'greeting_response': '你好呀，我是 FileTools Copilot...',
                    'greeting_keywords': ['你好', '您好', 'hi', 'hello', '嗨', '嘿', '在吗', '在不'],
                    'reset_commands': ['重置', '清空上下文', 'reset', 'restart']
                } if key is None else default
            else:
                return default

        if key is None:
            return self.config[section]

        return self.config[section].get(key, default)
    
    def getint(self, section: str, key: str, default: int = 0) -> int:
        """获取整数值的配置"""
        value = self.get(section, key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def getfloat(self, section: str, key: str, default: float = 0.0) -> float:
        """获取浮点数值的配置"""
        value = self.get(section, key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def getboolean(self, section: str, key: str, default: bool = False) -> bool:
        """获取布尔值的配置"""
        value = self.get(section, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'y', 't')
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return default
    
    def getlist(self, section: str, key: str, default: Optional[list] = None, delimiter: str = ';') -> list:
        """获取列表形式的配置"""
        if default is None:
            default = []
        
        value = self.get(section, key, default)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(delimiter) if item.strip()]
        return default
    
    def set(self, section: str, key: str, value: Any) -> None:
        """设置配置值"""
        if section not in self.config:
            self.config[section] = {}
        
        self.config[section][key] = value
    
    def _backup_config(self) -> None:
        """备份当前配置文件"""
        if not self.config_path.exists():
            return
        
        # 创建备份文件名，添加时间戳
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.config_path.parent / f"{self.config_path.stem}_{timestamp}.{self.config_path.suffix}"
        
        try:
            # 复制当前配置文件到备份文件
            import shutil
            shutil.copy2(self.config_path, backup_path)
            logger.info(f"已创建配置备份: {backup_path}")

            # 清理旧备份，保留最近5个
            self._cleanup_old_backups()
        except Exception as e:
            logger.error(f"创建配置备份失败: {str(e)}")
    
    def _cleanup_old_backups(self) -> None:
        """清理旧的配置备份文件，保留最近5个"""
        try:
            config_dir = self.config_path.parent
            stem = self.config_path.stem
            suffix = self.config_path.suffix
            
            # 查找所有备份文件
            backups = []
            for file in config_dir.iterdir():
                if file.is_file() and file.name.startswith(f"{stem}_") and file.name.endswith(suffix):
                    backups.append((file.stat().st_mtime, file))
            
            # 按修改时间排序（最新的在前）
            backups.sort(reverse=True)
            
            # 删除超过5个的旧备份
            for _, file in backups[5:]:
                try:
                    file.unlink()
                    logger.info(f"已删除旧备份: {file}")
                except Exception as e:
                    logger.warning(f"删除旧备份失败: {str(e)}")
        except Exception as e:
            logger.error(f"清理旧备份失败: {str(e)}")
    
    def save(self) -> bool:
        """保存配置到文件，自动创建备份"""
        try:
            # 先创建备份
            self._backup_config()
            
            # 确保配置目录存在
            config_dir = self.config_path.parent
            config_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            
            # 确保配置文件有正确的权限
            if os.name == 'posix':  # Unix-like systems
                os.chmod(self.config_path, 0o600)  # 只有所有者可读写
            
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            return False
    
    def get_path(self, section: str, key: str, default: str = '') -> Path:
        """获取路径形式的配置"""
        path_str = self.get(section, key, default)
        if not path_str:
            return Path()
        
        # 处理用户主目录符号
        if isinstance(path_str, str) and path_str.startswith('~'):
            path_str = os.path.expanduser(path_str)
        
        return Path(path_str).resolve()
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config.copy()

    def reload(self) -> bool:
        """重新加载配置文件"""
        try:
            self.config = self._load_config()
            self._validate_config()
            return True
        except Exception as e:
            logger.error(f"重新加载配置文件失败: {str(e)}")
            return False

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """更新配置"""
        try:
            for section, values in updates.items():
                if isinstance(values, dict):
                    if section not in self.config:
                        self.config[section] = {}
                    for key, value in values.items():
                        self.config[section][key] = value
                else:
                    # 如果不是字典，假定是直接的section=value形式
                    self.config[section] = values
            
            self._validate_config()
            return True
        except Exception as e:
            logger.error(f"更新配置失败: {str(e)}")
            return False

    def update_section(self, section: str, values: Dict[str, Any]) -> bool:
        """更新特定配置节"""
        try:
            if section not in self.config:
                self.config[section] = {}
            
            for key, value in values.items():
                self.config[section][key] = value
            
            self._validate_config()
            return True
        except Exception as e:
            logger.error(f"更新配置节 {section} 失败: {str(e)}")
            return False

    def add_scan_path(self, path: str) -> bool:
        """添加扫描路径"""
        try:
            expanded_path = Path(path).expanduser()
            if not expanded_path.exists() or not expanded_path.is_dir():
                logger.warning(f"路径不存在或不是目录: {path}")
                return False

            scan_paths = self.get('file_scanner', 'scan_paths', [])
            if isinstance(scan_paths, str):
                scan_paths = [p.strip() for p in scan_paths.split(';') if p.strip()]
            
            path_str = str(expanded_path)
            if path_str not in scan_paths:
                scan_paths.append(path_str)
                self.set('file_scanner', 'scan_paths', scan_paths)
            
            return True
        except Exception as e:
            logger.error(f"添加扫描路径失败: {str(e)}")
            return False

    def remove_scan_path(self, path: str) -> bool:
        """移除扫描路径"""
        try:
            scan_paths = self.get('file_scanner', 'scan_paths', [])
            if isinstance(scan_paths, str):
                scan_paths = [p.strip() for p in scan_paths.split(';') if p.strip()]
            
            expanded_path = str(Path(path).expanduser())
            if expanded_path in scan_paths:
                scan_paths.remove(expanded_path)
                self.set('file_scanner', 'scan_paths', scan_paths)
            
            return True
        except Exception as e:
            logger.error(f"移除扫描路径失败: {str(e)}")
            return False

    def enable_ai_model(self) -> bool:
        """启用AI模型"""
        try:
            self.set('ai_model', 'enabled', True)
            return True
        except Exception as e:
            logger.error(f"启用AI模型失败: {str(e)}")
            return False

    def disable_ai_model(self) -> bool:
        """禁用AI模型"""
        try:
            self.set('ai_model', 'enabled', False)
            return True
        except Exception as e:
            logger.error(f"禁用AI模型失败: {str(e)}")
            return False