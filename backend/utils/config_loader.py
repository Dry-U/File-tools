# src/utils/config_loader.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置加载器模块 - 负责加载、验证和管理配置"""

import base64
import datetime
import hashlib
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# 尝试导入加密库，如果不存在则使用简单的 base64 混淆
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTO_AVAILABLE = True
    # 保持向后兼容的别名
    PBKDF2 = PBKDF2HMAC
except ImportError:
    CRYPTO_AVAILABLE = False
    Fernet = None
    PBKDF2 = None
    PBKDF2HMAC = None
    hashes = None

# 延迟检查：只在实际需要时检查并显示警告
_CRYPTO_CHECKED = False


def _ensure_crypto_check():
    """确保已检查 cryptography 可用性，并在首次检查时记录日志"""
    global _CRYPTO_CHECKED
    if not _CRYPTO_CHECKED:
        _CRYPTO_CHECKED = True
        if not CRYPTO_AVAILABLE:
            logger.warning("cryptography 库未安装，敏感信息将使用简单混淆存储")
    return CRYPTO_AVAILABLE


logger = logging.getLogger(__name__)

# 敏感字段列表 - 这些字段会被加密存储
SENSITIVE_FIELDS: List[Tuple[str, str]] = [
    ("ai_model", "api_key"),
    ("ai_model", "api_secret"),
]


class ConfigLoader:
    """配置加载器类，负责加载、验证和管理配置文件"""

    _instance = None
    _lock = threading.Lock()
    _file_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式确保全局只有一个ConfigLoader实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        重置单例实例（主要用于测试）

        警告：此方法会清除当前实例，仅在测试环境中使用
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance = None
        logger.debug("ConfigLoader 单例已重置")

    def __init__(self, config_path: Optional[str] = None):
        # 避免重复初始化 - 使用实例字典检查而非hasattr（因为_initialized是类属性）
        if "_initialized" in self.__dict__:
            return
        self._initialized = True

        # 初始化路径管理器
        from backend.utils.app_paths import get_app_paths

        self.app_paths = get_app_paths()
        self.app_paths.init_user_data()

        # 设置配置路径
        if config_path is not None:
            self.config_path = Path(config_path).resolve()
        else:
            # 使用用户数据目录的配置
            self.config_path = self.app_paths.config_path

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

        # 解密敏感字段
        self._decrypt_sensitive_fields()

    def _get_or_create_salt(self) -> bytes:
        """获取或创建盐值（存储在用户数据目录中）"""
        from backend.utils.app_paths import get_app_paths

        app_paths = get_app_paths()
        salt_path = app_paths.user_data_dir / ".salt"

        if salt_path.exists():
            try:
                with open(salt_path, "rb") as f:
                    return f.read()
            except Exception:
                pass

        # 生成新盐值
        import secrets

        salt = secrets.token_bytes(32)
        try:
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            with open(salt_path, "wb") as f:
                f.write(salt)
            # 设置权限（仅 POSIX 系统：Linux/macOS）
            if os.name == "posix":
                os.chmod(salt_path, 0o600)
        except Exception as e:
            logger.warning(f"保存盐值失败: {e}")
        return salt

    def _get_machine_fingerprint(self) -> List[str]:
        """
        收集机器指纹信息用于密钥派生

        Returns:
            机器标识信息列表
        """
        machine_info = [
            os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERDOMAIN", ""),
            os.environ.get("USERNAME", ""),
            str(Path.home()),
        ]

        # 添加平台信息
        try:
            import platform

            machine_info.extend(
                [
                    platform.node() or "",  # 机器名
                    platform.machine() or "",  # 架构 (x86_64, AMD64等)
                    platform.processor() or "",  # 处理器信息
                    platform.release() or "",  # 系统版本
                ]
            )
        except Exception:
            pass

        # 添加MAC地址
        try:
            import uuid

            node = uuid.getnode()
            if node:
                machine_info.append(str(node))
                # 添加MAC地址的十六进制表示
                mac = uuid.UUID(int=node).hex[-12:]
                machine_info.append(mac)
        except Exception:
            pass

        # Windows特有的机器标识
        if os.name == "nt":
            try:
                import winreg

                # 尝试读取系统UUID
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
                ) as key:
                    machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    if machine_guid:
                        machine_info.append(machine_guid)
            except Exception:
                pass

            # 尝试获取主板序列号
            try:
                import subprocess

                result = subprocess.run(
                    ["wmic", "baseboard", "get", "SerialNumber"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    lines = [
                        line.strip()
                        for line in result.stdout.strip().split("\n")
                        if line.strip()
                    ]
                    if len(lines) > 1 and lines[1] != "None":
                        machine_info.append(lines[1])
            except Exception:
                pass

        # Linux特有的机器标识
        elif os.name == "posix":
            try:
                # 尝试读取机器ID
                for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
                    if os.path.exists(path):
                        with open(path, "r") as f:
                            machine_id = f.read().strip()
                            if machine_id:
                                machine_info.append(machine_id)
                                break
            except Exception:
                pass

        # 过滤空值并返回
        return [info for info in machine_info if info]

    def _get_encryption_key(self) -> bytes:
        """
        生成基于机器标识的加密密钥

        使用机器特定的信息（如机器名、用户名等）派生密钥，
        结合随机盐值，提高安全性。
        """
        # 缓存密钥，避免每次都执行昂贵的 PBKDF2 运算
        if hasattr(self, "_cached_encryption_key"):
            return self._cached_encryption_key

        # 收集机器特定信息
        machine_info = self._get_machine_fingerprint()

        # 如果没有获取到任何机器信息，使用默认值（降级方案）
        if not machine_info:
            logger.warning("无法获取机器指纹信息，使用降级方案")
            machine_info = ["default", "fallback"]

        # 创建稳定的密钥派生输入
        key_material = "|".join(machine_info).encode("utf-8")

        # 获取盐值（随机生成或从文件读取）
        salt = self._get_or_create_salt()

        if _ensure_crypto_check() and PBKDF2 and hashes:
            # 使用 PBKDF2 派生密钥，符合 OWASP 2023 推荐
            kdf = PBKDF2(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,  # 使用随机盐值
                iterations=480000,  # OWASP 2023 推荐
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_material))
            self._cached_encryption_key = key
            return key
        else:
            # 降级方案：使用简单的哈希，但结合盐值
            h = hashlib.sha256()
            h.update(salt)
            h.update(key_material)
            key = base64.urlsafe_b64encode(h.digest())
            self._cached_encryption_key = key
            return key

    def _encrypt_value(self, value: str) -> str:
        """加密单个值"""
        if not value or not isinstance(value, str):
            return value

        # 检查是否已经加密（避免双重加密）
        if value.startswith("enc:"):
            return value

        try:
            key = self._get_encryption_key()

            if _ensure_crypto_check() and Fernet:
                f = Fernet(key)
                encrypted = f.encrypt(value.encode("utf-8"))
                return f"enc:{encrypted.decode('utf-8')}"
            else:
                # 拒绝使用不安全的 base64 降级方案存储新值
                # 这是一个安全硬性要求：cryptography 库必须安装才能存储敏感信息
                logger.error(
                    "CRITICAL SECURITY ERROR: cryptography 库未安装，"
                    "无法安全存储敏感信息（API密钥等）。"
                    "请安装 cryptography 库：uv add cryptography"
                )
                # 返回特殊标记，调用方应忽略此字段而不是使用不安全的 base64
                return "enc:REQUIRE_CRYPTOGRAPHY"
        except Exception as e:
            logger.error(f"加密失败: {e}")
            return None

    def _decrypt_value(self, value: str) -> str:
        """解密单个值"""
        if not value or not isinstance(value, str):
            return value

        # 检查是否是加密格式
        if not value.startswith("enc:"):
            return value

        try:
            key = self._get_encryption_key()
            encrypted_data = value[4:]  # 移除 'enc:' 前缀

            if encrypted_data.startswith("b64:"):
                # 降级方案：base64 解码
                obfuscated = encrypted_data[4:]
                return base64.b64decode(obfuscated).decode("utf-8")

            if _ensure_crypto_check() and Fernet:
                f = Fernet(key)
                decrypted = f.decrypt(encrypted_data.encode("utf-8"))
                return decrypted.decode("utf-8")
            else:
                # 无法解密 Fernet 格式
                logger.warning("无法解密 Fernet 格式的值，cryptography 库可能未安装")
                return value
        except Exception as e:
            logger.warning(f"解密失败: {e}")
            if encrypted_data.startswith("b64:") and not _ensure_crypto_check():
                logger.warning(
                    "SECURITY WARNING: 使用 Base64 解码。"
                    "请安装 cryptography 库以获得真正的加密保护。"
                )
            return value  # 返回原值，避免丢失配置

    def _encrypt_sensitive_fields(self) -> None:
        """加密所有敏感字段"""
        for section, key in SENSITIVE_FIELDS:
            if section in self.config and key in self.config[section]:
                value = self.config[section][key]
                if value and isinstance(value, str) and not value.startswith("enc:"):
                    encrypted = self._encrypt_value(value)
                    if encrypted == "enc:REQUIRE_CRYPTOGRAPHY":
                        # cryptography 未安装，跳过存储此敏感字段
                        logger.warning(
                            f"跳过存储敏感字段 {section}.{key}：cryptography 库未安装"
                        )
                        continue
                    self.config[section][key] = encrypted
                    logger.debug(f"已加密字段: {section}.{key}")

    def _decrypt_sensitive_fields(self) -> None:
        """解密所有敏感字段"""
        for section, key in SENSITIVE_FIELDS:
            if section in self.config and key in self.config[section]:
                value = self.config[section][key]
                if value and isinstance(value, str) and value.startswith("enc:"):
                    self.config[section][key] = self._decrypt_value(value)
                    logger.debug(f"已解密字段: {section}.{key}")

    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置 (线程安全)"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件未找到: {self.config_path}")

        with self._file_lock:
            with open(self.config_path, "r", encoding="utf-8") as f:
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

        # 使用路径管理器获取数据目录路径
        data_dir = self.app_paths.data_dir
        cache_dir = self.app_paths.cache_dir
        log_dir = self.app_paths.log_dir

        # 转换为相对路径（基于用户数据目录）
        def to_rel(path: Path) -> str:
            try:
                return str(path.relative_to(self.app_paths.user_data_dir))
            except ValueError:
                return str(path)

        # 默认配置
        default_config = {
            "system": {
                "app_name": "智能文件检索与问答系统",
                "version": "1.0.0",
                "data_dir": to_rel(data_dir),
                "log_level": "INFO",
                "log_dir": to_rel(log_dir),
                "cache_dir": to_rel(cache_dir),
                "temp_dir": "data/temp",
                "log_backup_count": 5,
                "log_max_size": 10,
                "log_rotation": "midnight",
                "log_format": "structured",
                "log_json": False,
                "log_sensitive_data": False,
            },
            "file_scanner": {
                "scan_paths": str(Path.home() / "Documents"),
                "exclude_patterns": (
                    ".git;.svn;.hg;__pycache__;.idea;.vscode;"
                    "node_modules;venv;env;.DS_Store;Thumbs.db"
                ),
                "max_file_size": 100,  # MB
                "file_types": {
                    "document": (
                        ".txt,.md,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.csv,.json,.xml"
                    ),
                    "code": ".py,.js,.java,.cpp,.c,.h,.cs,.go,.rs,.php,.rb,.swift",
                    "archive": ".zip,.rar,.7z,.tar,.gz",
                },
                "scan_threads": 4,
                "recursive": True,
            },
            "search": {
                "text_weight": 0.6,
                "vector_weight": 0.4,
                "max_results": 50,
                "highlight": True,
                "cache_ttl": 3600,  # 秒
                "min_score": 0.3,
                "bm25_k1": 1.5,
                "bm25_b": 0.75,
                "result_boost": True,
                "filename_boost": 1.5,
                "keyword_boost": 1.2,
                "hybrid_boost": 1.1,
                "semantic_score_high_threshold": 60.0,
                "semantic_score_low_threshold": 30.0,
            },
            "monitor": {
                "directories": str(Path.home() / "Documents"),
                "ignored_patterns": (
                    ".git;.svn;.hg;__pycache__;.idea;.vscode;"
                    "node_modules;venv;env;.DS_Store;Thumbs.db"
                ),
                "refresh_interval": 1,
                "debounce_time": 0.5,
                "enabled": True,
            },
            "embedding": {
                "enabled": True,
                "provider": "modelscope",
                "model_name": "iic/nlp_gte_sentence-embedding_chinese-base",
                "cache_dir": "./data/models",
                "similarity_threshold": 0.7,
                "batch_size": 8,
            },
            "ai_model": {
                "enabled": True,
                "interface_type": "wsl",  # 可选值: wsl, api
                "api_format": "openai_chat",
                "api_url": "http://127.0.0.1:8080/v1/chat/completions",
                "api_model": "wsl",
                "api_key": "",
                "system_prompt": (
                    "你是一名专业的中文文档助理。"
                    "请根据下方的【文档集合】回答用户的【问题】。\n"
                    "规则：\n"
                    "1. 严格基于文档内容回答，不要编造。\n"
                    "2. 如果用户询问某人、某事出现在哪里，或者询问来源，"
                    "请务必列出对应的文件名。\n"
                    "3. 如果答案仅出现在文件名中（例如文件名包含查询词），"
                    "请明确指出该文件。\n"
                    "4. 如果文档中没有相关信息，请直接说明未找到。"
                ),
                "max_tokens": 4096,
                "temperature": 0.6,
                "request_timeout": 600,
                "use_gpu": True,
            },
            "rag": {
                "max_docs": 3,
                "max_context_chars": 4000,
                "max_context_chars_total": 8000,
                "max_history_turns": 3,
                "max_history_chars": 1000,
                "max_output_tokens": 2048,
                "temperature": 0.5,
                "top_p": 0.9,
                "frequency_penalty": 0.2,
                "presence_penalty": 0.2,
                "repetition_penalty": 1.1,
                "prompt_template": (
                    "你是一名专业的中文文档分析助理。"
                    "请基于【文档集合】中的内容，对用户的【问题】"
                    "提供一个连贯、流畅、总结性的回答。\n\n"
                    "核心要求：\n"
                    "1. 严格基于文档内容回答，不得编造任何信息。\n"
                    "2. 将相关信息整合成一个连贯的段落，而非分点列表。\n"
                    "3. 突出关键信息和核心内容，提供综合性的总结。\n"
                    "4. 对于人物、研究、技术等主题，"
                    "提供背景、方法、成果等的完整概述。\n"
                    "5. 如需引用来源，请在回答中自然提及文档名称，"
                    "而非单独列出。\n"
                    "6. 重点提取技术细节、研究方法、实现方案、"
                    "实验结果等知识性内容。\n"
                    "7. 对于多个文档的信息，进行有机整合，形成统一的叙述。\n"
                    "8. 避免机械重复文档原文，而是进行概括和总结。\n"
                    "9. 确保回答逻辑清晰、语句通顺，"
                    "形成完整的信息实体描述。\n\n"
                    "【文档集合】:\n{context}\n\n"
                    "【问题】: {question}\n\n"
                    "请提供一个连贯、总结性的回答："
                ),
                "context_exhausted_response": (
                    "对话过长，为避免超出上下文，请说'重置'或简要概括后再继续。"
                ),
                "reset_response": "已清空上下文，可以重新开始提问。",
                "fallback_response": (
                    '我在本地索引中暂时没有找到与" {query} "'
                    "直接对应的正文内容。\n"
                    "你可以：\n"
                    "1. 再提供更具体的描述（如文件名、章节、作者、时间等）；\n"
                    '2. 指明文件类型或格式，例如"PDF 报告""Word 文档"；\n'
                    "3. 如果需要的是操作指南或检索策略，"
                    "也欢迎直接告诉我，我会给出建议。\n"
                    "告诉我更详细的线索后，"
                    "我会立即在全部已扫描文件中再次检索。"
                ),
                "greeting_response": (
                    "你好呀，我是 FileTools Copilot，本地文件的智能助手。\n"
                    "我可以帮你搜索 PDF、Word、PPT 甚至代码，"
                    "把结果整理成摘要或问答。\n"
                    "需要查资料、找报告要点、生成概览或者验证内容"
                    "都可以直接告诉我。\n"
                    "只要说出关键词或问题，"
                    "我就能立刻从本地库里找到相关内容。"
                ),
                "greeting_keywords": [
                    "你好",
                    "您好",
                    "hi",
                    "hello",
                    "嗨",
                    "嘿",
                    "在吗",
                    "在不",
                ],
                "reset_commands": ["重置", "清空上下文", "reset", "restart"],
            },
            "interface": {
                "theme": "light",
                "font_size": 12,
                "max_preview_size": 5242880,  # 5MB
                "auto_save_settings": True,
                "language": "zh_CN",
                "result_columns": ["文件名", "路径", "匹配度", "修改时间"],
                "splitter_pos": 300,
            },
            "advanced": {
                "auto_optimize_index": True,
                "index_refresh_interval": 3600,
                "max_cached_results": 1000,
                "optimize_interval": 86400,
                "whoosh_mem_limit": 512,
            },
            "index": {
                "tantivy_path": "./data/tantivy_index",
                "hnsw_path": "./data/hnsw_index",
                "metadata_path": "./data/metadata",
            },
        }

        # 保存默认配置到文件
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    default_config, f, allow_unicode=True, default_flow_style=False
                )

            # 确保配置文件有正确的权限
            if os.name == "posix":  # Unix-like systems
                os.chmod(self.config_path, 0o600)  # 只有所有者可读写

            logger.info(f"已创建默认配置文件: {self.config_path}")
        except Exception as e:
            logger.error(f"创建默认配置文件失败: {str(e)}")

        return default_config

    def _validate_config(self) -> None:
        """验证配置的有效性"""
        from backend.utils.app_paths import get_app_paths

        # 确保必要的配置部分存在
        required_sections = [
            "system",
            "file_scanner",
            "search",
            "monitor",
            "embedding",
            "ai_model",
            "rag",
            "interface",
            "advanced",
            "index",
        ]

        for section in required_sections:
            if section not in self.config:
                self.config[section] = {}

        # 获取 AppPaths 用于绝对路径
        app_paths = get_app_paths()

        # 确保数据目录存在（使用绝对路径）
        data_dir_str = self.get("system", "data_dir", "./data")
        if data_dir_str.startswith("./") or data_dir_str.startswith("."):
            data_dir = app_paths.user_data_dir / "data"
        else:
            data_dir = Path(data_dir_str)
        data_dir.mkdir(parents=True, exist_ok=True)
        # 更新配置为绝对路径
        self.set("system", "data_dir", str(data_dir))

        # 确保缓存目录存在
        cache_dir_str = self.get("system", "cache_dir", "./data/cache")
        if cache_dir_str.startswith("./") or cache_dir_str.startswith("."):
            cache_dir = app_paths.user_data_dir / "cache"
        else:
            cache_dir = Path(cache_dir_str)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.set("system", "cache_dir", str(cache_dir))

        # 确保临时目录存在
        temp_dir = app_paths.user_data_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.set("system", "temp_dir", str(temp_dir))

        # 确保索引目录存在
        index_dir = app_paths.user_data_dir / "index"
        index_dir.mkdir(parents=True, exist_ok=True)
        self.set("system", "index_dir", str(index_dir))

        # 确保日志目录存在
        log_dir = app_paths.user_data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.set("system", "log_dir", str(log_dir))

        # 验证并修正扫描路径
        scan_paths = self.get(
            "file_scanner", "scan_paths", str(Path.home() / "Documents")
        )
        if isinstance(scan_paths, str):
            # 如果是字符串，转换为列表
            paths = [p.strip() for p in scan_paths.split(";") if p.strip()]
            validated_paths = []
            for path in paths:
                expanded_path = Path(path).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_paths.append(str(expanded_path))
                else:
                    logger.warning(f"扫描路径不存在: {path}")
            if not validated_paths:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / "Documents"
                if not default_path.exists():
                    default_path = Path.home()
                validated_paths = [str(default_path)]
            self.set("file_scanner", "scan_paths", validated_paths)
        elif isinstance(scan_paths, list):
            # 如果已经是列表，验证每个路径
            # 如果是空列表（用户明确配置），保持为空，不填充默认值
            if len(scan_paths) == 0:
                logger.info("扫描路径配置为空，将在首次添加时设置")
                # 不修改配置，保持为空列表
            else:
                validated_paths = []
                for path in scan_paths:
                    expanded_path = Path(str(path)).expanduser()
                    if expanded_path.exists() and expanded_path.is_dir():
                        validated_paths.append(str(expanded_path))
                    else:
                        logger.warning(f"扫描路径不存在: {path}")
                if not validated_paths:
                    # 如果没有有效路径，使用默认路径
                    default_path = Path.home() / "Documents"
                    if not default_path.exists():
                        default_path = Path.home()
                    validated_paths = [str(default_path)]
                self.set("file_scanner", "scan_paths", validated_paths)

        # 验证监控目录
        monitor_dirs = self.get(
            "monitor", "directories", str(Path.home() / "Documents")
        )
        if isinstance(monitor_dirs, str):
            # 如果是字符串，转换为列表
            dirs = [d.strip() for d in monitor_dirs.split(";") if d.strip()]
            validated_dirs = []
            for dir_path in dirs:
                expanded_path = Path(dir_path).expanduser()
                if expanded_path.exists() and expanded_path.is_dir():
                    validated_dirs.append(str(expanded_path))
                else:
                    logger.warning(f"监控目录不存在: {dir_path}")
            if not validated_dirs:
                # 如果没有有效路径，使用默认路径
                default_path = Path.home() / "Documents"
                if not default_path.exists():
                    default_path = Path.home()
                validated_dirs = [str(default_path)]
            self.set("monitor", "directories", validated_dirs)
        elif isinstance(monitor_dirs, list):
            # 如果已经是列表，验证每个路径
            # 如果是空列表（用户明确配置），保持为空，不填充默认值
            if len(monitor_dirs) == 0:
                logger.info("监控目录配置为空，将在首次添加时设置")
                # 不修改配置，保持为空列表
            else:
                validated_dirs = []
                for dir_path in monitor_dirs:
                    expanded_path = Path(str(dir_path)).expanduser()
                    if expanded_path.exists() and expanded_path.is_dir():
                        validated_dirs.append(str(expanded_path))
                    else:
                        logger.warning(f"监控目录不存在: {dir_path}")
                if not validated_dirs:
                    # 如果没有有效路径，使用默认路径
                    default_path = Path.home() / "Documents"
                    if not default_path.exists():
                        default_path = Path.home()
                    validated_dirs = [str(default_path)]
                self.set("monitor", "directories", validated_dirs)

        # 验证数值配置
        self._validate_numeric_configs()

    def _validate_numeric_configs(self):
        """验证数值类型的配置"""
        numeric_configs = [
            ("file_scanner", "max_file_size", 100, 1, 1000),  # MB, 1-1000
            ("search", "max_results", 50, 1, 1000),
            ("search", "text_weight", 0.6, 0.0, 1.0),
            ("search", "vector_weight", 0.4, 0.0, 1.0),
            ("search", "min_score", 0.3, 0.0, 1.0),
            ("search", "bm25_k1", 1.5, 0.1, 10.0),
            ("search", "bm25_b", 0.75, 0.0, 1.0),
            ("search", "filename_boost", 1.5, 0.1, 10.0),
            ("search", "keyword_boost", 1.2, 0.1, 10.0),
            ("search", "hybrid_boost", 1.1, 0.1, 5.0),
            ("search", "semantic_score_high_threshold", 60.0, 0.0, 100.0),
            ("search", "semantic_score_low_threshold", 30.0, 0.0, 100.0),
            ("search", "cache_ttl", 3600, 60, 86400),  # 1分钟到1天
            ("monitor", "refresh_interval", 1, 0.1, 60),  # 0.1秒到60秒
            ("monitor", "debounce_time", 0.5, 0.1, 5.0),  # 0.1秒到5秒
            ("file_scanner", "scan_threads", 4, 1, 16),
            ("rag", "max_docs", 3, 1, 10),
            ("rag", "max_context_chars", 4000, 100, 10000),
            ("rag", "max_context_chars_total", 8000, 100, 20000),
            ("rag", "max_history_turns", 3, 1, 20),
            ("rag", "max_history_chars", 1000, 100, 5000),
            ("rag", "max_output_tokens", 2048, 100, 8192),
            ("rag", "temperature", 0.5, 0.0, 2.0),
            ("rag", "top_p", 0.9, 0.0, 1.0),
            ("rag", "frequency_penalty", 0.2, -2.0, 2.0),
            ("rag", "presence_penalty", 0.2, -2.0, 2.0),
            ("rag", "repetition_penalty", 1.1, 0.1, 2.0),
            ("ai_model", "max_tokens", 4096, 100, 8192),
            ("ai_model", "temperature", 0.6, 0.0, 2.0),
            ("ai_model", "request_timeout", 600, 10, 3600),
            ("interface", "font_size", 12, 8, 24),
            (
                "interface",
                "max_preview_size",
                5242880,
                1024,
                50 * 1024 * 1024,
            ),  # 1KB到50MB
            ("interface", "splitter_pos", 300, 100, 1000),
            ("system", "log_max_size", 10, 1, 100),  # MB
            ("system", "log_backup_count", 5, 1, 20),
            ("advanced", "index_refresh_interval", 3600, 60, 86400),
            ("advanced", "max_cached_results", 1000, 100, 10000),
            ("advanced", "optimize_interval", 86400, 3600, 604800),  # 1小时到7天
            ("advanced", "whoosh_mem_limit", 512, 64, 2048),  # MB
        ]

        for section, key, default_val, min_val, max_val in numeric_configs:
            try:
                val = self.get(section, key, default_val)
                if isinstance(val, (int, float)):
                    if val < min_val or val > max_val:
                        logger.warning(
                            f"配置项 {section}.{key} 的值 {val} "
                            f"超出范围 [{min_val}, {max_val}]，"
                            f"使用默认值 {default_val}"
                        )
                        self.set(section, key, default_val)
                else:
                    logger.warning(
                        f"配置项 {section}.{key} 的值 {val} "
                        f"不是数值类型，使用默认值 {default_val}"
                    )
                    self.set(section, key, default_val)
            except Exception as e:
                logger.error(f"验证配置项 {section}.{key} 时出错: {e}")
                self.set(section, key, default_val)

        # 验证字符串配置
        self._validate_string_configs()

    def _validate_string_configs(self):
        """验证字符串类型的配置"""
        import re

        # 验证 URL 格式
        url_configs = [
            ("ai_model", "api_url", "http://127.0.0.1:8080/v1/chat/completions"),
        ]

        url_pattern = re.compile(
            r"^(https?://)?"  # 协议
            r"(([\w.-]+)"  # 域名
            r"|(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}))"  # IP 地址
            r"(:\d{1,5})?"  # 端口号
            r"(/[\w./-]*)?$"  # 路径
        )

        for section, key, default_val in url_configs:
            try:
                val = self.get(section, key, default_val)
                if val and isinstance(val, str):
                    # 允许 localhost 和 127.0.0.1
                    if not url_pattern.match(val) and "localhost" not in val:
                        logger.warning(
                            f"配置项 {section}.{key} 的 URL 格式无效: {val}，使用默认值"
                        )
                        self.set(section, key, default_val)
            except Exception as e:
                logger.error(f"验证 URL 配置项 {section}.{key} 时出错: {e}")
                self.set(section, key, default_val)

        # 验证路径格式（不能包含非法字符）
        path_configs = [
            ("system", "data_dir"),
            ("system", "index_dir"),
            ("system", "cache_dir"),
            ("system", "temp_dir"),
        ]

        # Windows 非法字符排除驱动器字母格式 (如 C:\, D:/)
        # 允许：反斜杠、斜杠、冒号（在驱动器字母后）、普通字母数字
        invalid_chars = '<>"|?*'

        import re

        # Windows 驱动器路径正则: C:\, D:/ 等
        windows_drive_pattern = re.compile(r"^[A-Za-z]:[\\/]")

        for section, key in path_configs:
            try:
                val = self.get(section, key, "")
                if val and isinstance(val, str):
                    # 如果是 Windows 绝对路径（包含驱动器字母和冒号），直接跳过验证
                    # 这是合法的 Windows 路径格式
                    if ":" in val and windows_drive_pattern.match(val):
                        # Windows 绝对路径，如 C:\Users\... 或 D:/Documents/...
                        # 这是合法路径，跳过所有非法字符检查
                        pass
                    elif any(c in val for c in invalid_chars):
                        logger.warning(
                            f"配置项 {section}.{key} 包含非法字符: {val}，使用默认值"
                        )
                        self.set(section, key, "./data")
            except Exception as e:
                logger.error(f"验证路径配置项 {section}.{key} 时出错: {e}")

        # 验证枚举值
        enum_configs = [
            (
                "system",
                "log_level",
                ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                "INFO",
            ),
            (
                "system",
                "log_rotation",
                ["midnight", "daily", "weekly", "monthly"],
                "midnight",
            ),
            (
                "system",
                "log_format",
                ["structured", "simple", "detailed"],
                "structured",
            ),
            (
                "embedding",
                "provider",
                ["fastembed", "sentence_transformers", "modelscope"],
                "fastembed",
            ),
        ]

        for section, key, allowed_values, default_val in enum_configs:
            try:
                val = self.get(section, key, default_val)
                if val and isinstance(val, str):
                    if val.upper() not in [v.upper() for v in allowed_values]:
                        logger.warning(
                            f"配置项 {section}.{key} 的值 {val} "
                            f"不在允许的范围 {allowed_values} 内，"
                            f"使用默认值 {default_val}"
                        )
                        self.set(section, key, default_val)
            except Exception as e:
                logger.error(f"验证枚举配置项 {section}.{key} 时出错: {e}")
                self.set(section, key, default_val)

    def get(self, section, key: Optional[str] = None, default: Any = None) -> Any:
        """获取配置值"""
        # 添加类型检查，防止section为dict等不可哈希类型
        if not isinstance(section, (str, int)):
            logger.warning(f"配置section必须是可哈希类型，收到类型: {type(section)}")
            return default

        if section not in self.config:
            # 尝试从配置中获取默认值
            if section == "embedding":
                return (
                    {
                        "enabled": False,
                        "provider": "fastembed",
                        "model_name": "BAAI/bge-small-zh-v1.5",
                        "cache_dir": "./data/models",
                        "similarity_threshold": 0.7,
                        "batch_size": 8,
                    }
                    if key is None
                    else default
                )
            elif section == "ai_model":
                return (
                    {
                        "enabled": False,
                        "interface_type": "wsl",
                        "api_format": "openai_chat",
                        "api_url": "http://127.0.0.1:8080/v1/chat/completions",
                        "api_model": "wsl",
                        "api_key": "",
                        "system_prompt": "你是一名专业的中文文档助理...",
                        "max_tokens": 4096,
                        "temperature": 0.6,
                        "request_timeout": 600,
                        "use_gpu": True,
                    }
                    if key is None
                    else default
                )
            elif section == "rag":
                return (
                    {
                        "max_docs": 3,
                        "max_context_chars": 4000,
                        "max_context_chars_total": 8000,
                        "max_history_turns": 3,
                        "max_history_chars": 1000,
                        "max_output_tokens": 2048,
                        "temperature": 0.5,
                        "top_p": 0.9,
                        "frequency_penalty": 0.2,
                        "presence_penalty": 0.2,
                        "repetition_penalty": 1.1,
                        "prompt_template": "你是一名专业的中文文档分析助理...",
                        "context_exhausted_response": (
                            "对话过长，为避免超出上下文，请说'重置'或简要概括后再继续。"
                        ),
                        "reset_response": "已清空上下文，可以重新开始提问。",
                        "fallback_response": "我在本地索引中暂时没有找到...",
                        "greeting_response": "你好呀，我是 FileTools Copilot...",
                        "greeting_keywords": [
                            "你好",
                            "您好",
                            "hi",
                            "hello",
                            "嗨",
                            "嘿",
                            "在吗",
                            "在不",
                        ],
                        "reset_commands": ["重置", "清空上下文", "reset", "restart"],
                    }
                    if key is None
                    else default
                )
            else:
                return default

        if key is None:
            return self.config[section]

        # 支持点分隔符访问嵌套配置
        # (如 "local.api_url" → config[section]["local"]["api_url"])
        if "." in key:
            keys = key.split(".")
            value = self.config[section]
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value

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
            return value.lower() in ("true", "yes", "1", "y", "t")
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return default

    def getlist(
        self,
        section: str,
        key: str,
        default: Optional[list] = None,
        delimiter: str = ";",
    ) -> list:
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
        """设置配置值，支持点分隔符访问嵌套配置 (如 "local.api_url")"""
        if section not in self.config:
            self.config[section] = {}

        # 支持点分隔符访问嵌套配置
        # (如 "local.api_url" → config[section]["local"]["api_url"])
        if "." in key:
            keys = key.split(".")
            current = self.config[section]
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                elif not isinstance(current[k], dict):
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
        else:
            self.config[section][key] = value

    def _backup_config(self) -> None:
        """备份当前配置文件 (线程安全)"""
        if not self.config_path.exists():
            return

        # 创建备份文件名，添加时间戳
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = (
            self.config_path.parent
            / f"{self.config_path.stem}_{timestamp}.{self.config_path.suffix}"
        )

        try:
            # 复制当前配置文件到备份文件
            import shutil

            with self._file_lock:
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
                if (
                    file.is_file()
                    and file.name.startswith(f"{stem}_")
                    and file.name.endswith(suffix)
                ):
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
        """保存配置到文件 (线程安全，使用原子写入防止配置损坏)"""
        try:
            # 在保存前加密敏感字段
            self._encrypt_sensitive_fields()

            # 确保配置目录存在
            config_dir = self.config_path.parent
            config_dir.mkdir(parents=True, exist_ok=True)

            # 创建临时文件路径
            temp_path = config_dir / f"{self.config_path.stem}.tmp"
            backup_path = config_dir / f"{self.config_path.stem}.bak"

            with self._file_lock:
                # 步骤1: 写入临时文件
                with open(temp_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        self.config, f, allow_unicode=True, default_flow_style=False
                    )
                    f.flush()
                    os.fsync(f.fileno())  # 确保数据写入磁盘

                # 步骤2: 如果原配置存在，创建备份
                if self.config_path.exists():
                    try:
                        backup_path.unlink(missing_ok=True)
                        os.replace(self.config_path, backup_path)
                    except Exception as e:
                        logger.warning(f"创建配置备份失败: {e}")

                # 步骤3: 原子重命名临时文件到目标文件
                os.replace(temp_path, self.config_path)

                # 步骤4: 确保配置文件有正确的权限
                if os.name == "posix":  # Unix-like systems
                    os.chmod(self.config_path, 0o600)  # 只有所有者可读写

                # 步骤5: 成功写入后删除备份
                if backup_path.exists():
                    try:
                        backup_path.unlink()
                    except Exception:
                        pass

            logger.debug(f"配置已保存: {self.config_path}")

            # 保存后解密敏感字段，以便内存中保持明文
            self._decrypt_sensitive_fields()

            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            # 保存失败时也尝试解密，避免配置被锁在加密状态
            self._decrypt_sensitive_fields()

            # 尝试恢复备份
            try:
                if backup_path and backup_path.exists() and temp_path.exists():
                    os.replace(backup_path, self.config_path)
                    logger.info("已从备份恢复配置文件")
            except Exception as restore_error:
                logger.error(f"恢复配置备份失败: {restore_error}")

            return False

    def get_path(self, section: str, key: str, default: str = "") -> Path:
        """获取路径形式的配置"""
        path_str = self.get(section, key, default)
        if not path_str:
            return Path()

        # 处理用户主目录符号
        if isinstance(path_str, str) and path_str.startswith("~"):
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

            scan_paths = self.get("file_scanner", "scan_paths", [])
            if isinstance(scan_paths, str):
                scan_paths = [p.strip() for p in scan_paths.split(";") if p.strip()]

            path_str = str(expanded_path)
            if path_str not in scan_paths:
                scan_paths.append(path_str)
                self.set("file_scanner", "scan_paths", scan_paths)

            return True
        except Exception as e:
            logger.error(f"添加扫描路径失败: {str(e)}")
            return False

    def remove_scan_path(self, path: str) -> bool:
        """移除扫描路径"""
        try:
            scan_paths = self.get("file_scanner", "scan_paths", [])
            if isinstance(scan_paths, str):
                scan_paths = [p.strip() for p in scan_paths.split(";") if p.strip()]

            expanded_path = os.path.abspath(os.path.expanduser(path))

            # Windows 下使用大小写不敏感比较
            if sys.platform == "win32":
                scan_paths_lower = [p.lower() for p in scan_paths]
                expanded_path_lower = expanded_path.lower()
                if expanded_path_lower in scan_paths_lower:
                    idx = scan_paths_lower.index(expanded_path_lower)
                    scan_paths.pop(idx)
            else:
                if expanded_path in scan_paths:
                    scan_paths.remove(expanded_path)

            self.set("file_scanner", "scan_paths", scan_paths)
            return True
        except Exception as e:
            logger.error(f"移除扫描路径失败: {str(e)}")
            return False

    def enable_ai_model(self) -> bool:
        """启用AI模型"""
        try:
            self.set("ai_model", "enabled", True)
            return True
        except Exception as e:
            logger.error(f"启用AI模型失败: {str(e)}")
            return False

    def disable_ai_model(self) -> bool:
        """禁用AI模型"""
        try:
            self.set("ai_model", "enabled", False)
            return True
        except Exception as e:
            logger.error(f"禁用AI模型失败: {str(e)}")
            return False
