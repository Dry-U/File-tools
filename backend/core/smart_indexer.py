# src/core/smart_indexer.py
import time
from collections import deque
from typing import Dict
from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader

# 临时定义缺失的类
class VectorEngine:
    def __init__(self, config_loader):
        self.config_loader = config_loader
    def add_documents(self, docs):
        pass
    def remove_by_path(self, path):
        pass

class HybridRetriever:
    def __init__(self, config_loader, vector_engine):
        self.config_loader = config_loader
        self.vector_engine = vector_engine

logger = setup_logger()

class SmartIndexer:
    """智能增量索引器：缓冲变化并批量处理（基于文档3.1.2，优化）"""

    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.change_buffer: deque[Dict[str, str]] = deque(maxlen=1000)  # { 'type': 'update/delete', 'path': str }
        self.last_index_time: float = time.time()
        self.vector_engine = VectorEngine(self.config_loader)
        self.retriever = HybridRetriever(self.config_loader, self.vector_engine)
        # 后续：self.parser = UniversalParser()
        # self.vector_engine = VectorEngine(config)

    def add_change(self, path: str, change_type: str):
        """添加文件变化到缓冲"""
        if change_type not in ['update', 'delete']:
            logger.warning(f"无效变化类型: {change_type}")
            return
        self.change_buffer.append({'type': change_type, 'path': path})
        self.process_changes()  # 检查是否触发批量

    def process_changes(self):
        """检查缓冲并触发批量索引"""
        if len(self.change_buffer) >= 500 or time.time() - self.last_index_time > 300:  # 5分钟
            self._bulk_index()
            self.last_index_time = time.time()

    def _bulk_index(self):
        """批量索引处理（事务式）"""
        if not self.change_buffer:
            return
        
        # 模拟DB事务（实际可使用SQLite）
        try:
            for action in list(self.change_buffer):  # 复制以避免修改中迭代
                if action['type'] == 'update':
                    self._update_index(action['path'])
                elif action['type'] == 'delete':
                    self._remove_from_index(action['path'])
            self.change_buffer.clear()
            logger.info(f"批量索引完成: 处理 {len(self.change_buffer)} 个变化")
        except Exception as e:
            logger.error(f"批量索引失败: {e}")

    def _update_index(self, path: str):
        """更新单个文件索引（解析+向量化）"""
        # 后续集成Part 3/4：
        # doc = self.parser.parse(path)
        # if doc:
        #     self.vector_engine.add_documents([doc])
        logger.info(f"更新索引: {path}")  # 占位

    def _remove_from_index(self, path: str):
        """从索引移除"""
        # 后续：self.vector_engine.remove_by_path(path)
        logger.info(f"移除索引: {path}")  # 占位