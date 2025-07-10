# src/core/privacy_filter.py
import re
from typing import List, Dict
import spacy
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader

logger = setup_logger()

class PrivacyFilter:
    """隐私数据脱敏过滤器：正则+NER（基于文档5.1）"""

    def __init__(self, config: ConfigLoader):
        self.sensitive_patterns: Dict[str, str] = {
            'id_card': r'\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b',
            'phone': r'\b1[3-9]\d{9}\b',
            'bank_card': r'\b[1-9]\d{9,17}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        }
        # 可从config扩展模式
        custom_patterns = config.get('privacy', 'custom_patterns', {})
        self.sensitive_patterns.update(custom_patterns)
        
        try:
            self.ner_model = spacy.load('zh_core_web_sm')  # 中文NER模型，支持PERSON/ORG/LOC
        except Exception as e:
            logger.warning(f"Spacy模型加载失败: {e}, fallback to en_core_web_sm")
            self.ner_model = spacy.load('en_core_web_sm')

    def sanitize(self, text: str) -> str:
        """脱敏文本：正则替换 + NER实体识别"""
        # 正则替换
        for key, pattern in self.sensitive_patterns.items():
            text = re.sub(pattern, f'[{key.upper()}_REDACTED]', text)
        
        # NER实体替换
        doc = self.ner_model(text)
        entities = [(ent.text, ent.label_) for ent in doc.ents if ent.label_ in ['PERSON', 'ORG', 'GPE', 'LOC']]
        for word, entity in entities:
            text = text.replace(word, f"[{entity}_REDACTED]")
        
        logger.debug(f"脱敏后文本: {text[:100]}...")  # 仅记录前100字符
        return text