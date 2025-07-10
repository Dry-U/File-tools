# src/core/security_manager.py
import os
import json
import time
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader

logger = setup_logger()

class SecurityManager:
    """安全管理器：加密存储、RBAC、审计追踪（基于文档5.1）"""

    def __init__(self, config: ConfigLoader):
        self.config = config
        self.encryption_key = self._load_or_generate_key()
        self.cipher = Fernet(self.encryption_key)
        self.audit_log_path = config.get('system', 'data_dir') + '/logs/audit.log'
        self.roles: Dict[str, List[str]] = {  # 简单RBAC：角色权限
            'user': ['read', 'query'],
            'admin': ['read', 'query', 'scan', 'update']
        }
        self.current_user_role: str = 'user'  # 默认；实际可从登录获取

    def _load_or_generate_key(self) -> bytes:
        """加载或生成AES-256密钥"""
        key_path = self.config.get('system', 'data_dir') + '/encryption.key'
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                return f.read()
        key = Fernet.generate_key()
        with open(key_path, 'wb') as f:
            f.write(key)
        logger.info("生成新加密密钥")
        return key

    def encrypt_data(self, data: Dict[str, Any]) -> bytes:
        """加密数据（e.g., 元数据或索引）"""
        try:
            json_data = json.dumps(data).encode()
            return self.cipher.encrypt(json_data)
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise

    def decrypt_data(self, encrypted: bytes) -> Dict[str, Any]:
        """解密数据"""
        try:
            json_data = self.cipher.decrypt(encrypted).decode()
            return json.loads(json_data)
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise

    def check_permission(self, action: str, role: Optional[str] = None) -> bool:
        """RBAC权限检查"""
        role = role or self.current_user_role
        if action not in self.roles.get(role, []):
            logger.warning(f"权限拒绝: {role} 尝试 {action}")
            return False
        return True

    def log_audit(self, event: str, details: Dict[str, Any]):
        """审计追踪：追加不可变日志"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {event} - {json.dumps(details)}\n"
        with open(self.audit_log_path, 'a') as f:
            f.write(log_entry)
        logger.info(f"审计日志: {event}")

    # 示例：加密存储索引（集成到VectorEngine等）
    def save_encrypted_index(self, index_data: Dict[str, Any], file_path: str):
        encrypted = self.encrypt_data(index_data)
        with open(file_path, 'wb') as f:
            f.write(encrypted)
        self.log_audit("save_index", {"file": file_path})

    def load_encrypted_index(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, 'rb') as f:
            encrypted = f.read()
        data = self.decrypt_data(encrypted)
        self.log_audit("load_index", {"file": file_path})
        return data