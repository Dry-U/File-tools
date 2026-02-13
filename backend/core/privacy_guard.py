"""
隐私保护模块 - 敏感信息检测与脱敏
始终启用，无需开关
"""
import re
import hashlib
from typing import Dict, Tuple, List, Optional
from backend.utils.logger import setup_logger

logger = setup_logger()

# 敏感信息检测规则
SENSITIVE_PATTERNS = {
    'phone': (r'\b1[3-9]\d{9}\b', '***手机号***'),
    'id_card': (r'\b\d{17}[\dXx]\b', '***身份证***'),
    'email': (r'\b[\w.-]+@[\w.-]+\.\w+\b', '***邮箱***'),
}


class PrivacyGuard:
    """隐私保护守卫 - 始终启用"""

    def __init__(self, max_map_size: int = 1000):
        self.patterns = SENSITIVE_PATTERNS
        self._mask_map: Dict[str, str] = {}  # 哈希 -> 占位符映射
        self._max_map_size = max_map_size
        self._access_order: List[str] = []  # 用于LRU清理

    def detect_sensitive(self, text: str) -> List[Tuple[str, str, str]]:
        """
        检测文本中的敏感信息

        Returns:
            List of (类型, 原文, 位置) 元组
        """
        findings = []
        for ptype, (pattern, _) in self.patterns.items():
            for match in re.finditer(pattern, text):
                findings.append((ptype, match.group(), match.span()))
        return findings

    def _cleanup_old_mappings(self):
        """LRU清理：当映射表过大时清理最旧的条目"""
        while len(self._mask_map) > self._max_map_size:
            oldest_key = self._access_order.pop(0)
            self._mask_map.pop(oldest_key, None)

    def redact(self, text: str) -> str:
        """
        脱敏处理 - 将敏感信息替换为占位符

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        if not text:
            return text

        # 检查是否需要清理
        if len(self._mask_map) > self._max_map_size:
            self._cleanup_old_mappings()

        result = text
        for ptype, (pattern, placeholder) in self.patterns.items():
            def replace_func(match):
                original = match.group()
                # 使用哈希记录映射关系，便于后续还原（如需要）
                key = hashlib.md5(original.encode()).hexdigest()[:8]
                self._mask_map[key] = original
                # 更新访问顺序
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return f"[{placeholder}:{key}]"

            result = re.sub(pattern, replace_func, result)

        return result

    def restore(self, text: str) -> str:
        """
        还原脱敏内容（用于响应展示时提示用户）

        Args:
            text: 包含脱敏标记的文本

        Returns:
            还原后的文本
        """
        if not text:
            return text

        result = text
        for ptype, (pattern, placeholder) in self.patterns.items():
            # 匹配 [***XXX***:hash] 格式
            marker_pattern = rf'\[{re.escape(placeholder)}:([a-f0-9]{{8}})\]'

            def restore_func(match):
                key = match.group(1)
                original = self._mask_map.get(key)
                if original:
                    return original
                return match.group(0)  # 无法还原则保留原样

            result = re.sub(marker_pattern, restore_func, result)

        return result

    def clear_map(self):
        """清除映射表（每次请求后调用）"""
        self._mask_map.clear()

    def has_sensitive(self, text: str) -> bool:
        """检查是否包含敏感信息"""
        return len(self.detect_sensitive(text)) > 0


# 全局实例
_privacy_guard = PrivacyGuard()


def get_privacy_guard() -> PrivacyGuard:
    """获取隐私保护实例"""
    return _privacy_guard


def redact_text(text: str) -> str:
    """便捷函数：脱敏文本"""
    return _privacy_guard.redact(text)


def has_sensitive_info(text: str) -> bool:
    """便捷函数：检查是否包含敏感信息"""
    return _privacy_guard.has_sensitive(text)
