"""测试数据工厂 - 用于生成测试数据"""
from typing import Dict, Any, List, Optional
import random
import string
from datetime import datetime, timedelta


class DocumentFactory:
    """文档数据工厂"""

    @staticmethod
    def create(
        path: Optional[str] = None,
        filename: Optional[str] = None,
        content: Optional[str] = None,
        file_type: Optional[str] = None,
        size: Optional[int] = None,
        modified: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建单个文档数据

        Args:
            path: 文件路径
            filename: 文件名
            content: 文件内容
            file_type: 文件类型
            size: 文件大小
            modified: 修改时间戳
            **kwargs: 额外字段

        Returns:
            文档数据字典
        """
        if filename is None:
            filename = f"doc_{random.randint(1000, 9999)}.txt"

        if path is None:
            path = f"/test/{filename}"

        if content is None:
            content = DocumentFactory._generate_content()

        if file_type is None:
            file_type = filename.split('.')[-1] if '.' in filename else 'txt'

        if size is None:
            size = len(content.encode('utf-8'))

        if modified is None:
            modified = datetime.now().timestamp()

        doc = {
            "path": path,
            "filename": filename,
            "content": content,
            "file_type": file_type,
            "size": size,
            "modified": modified,
        }
        doc.update(kwargs)
        return doc

    @staticmethod
    def create_batch(
        count: int,
        file_types: Optional[List[str]] = None,
        base_path: str = "/test"
    ) -> List[Dict[str, Any]]:
        """
        批量创建文档数据

        Args:
            count: 数量
            file_types: 文件类型列表
            base_path: 基础路径

        Returns:
            文档数据列表
        """
        if file_types is None:
            file_types = ['txt', 'pdf', 'doc', 'docx', 'md']

        documents = []
        for i in range(count):
            file_type = random.choice(file_types)
            filename = f"doc_{i}.{file_type}"
            doc = DocumentFactory.create(
                path=f"{base_path}/{filename}",
                filename=filename,
                file_type=file_type
            )
            documents.append(doc)

        return documents

    @staticmethod
    def _generate_content(min_words: int = 10, max_words: int = 100) -> str:
        """生成随机内容"""
        word_count = random.randint(min_words, max_words)
        words = [
            "Python", "programming", "code", "development", "software",
            "data", "analysis", "machine", "learning", "artificial",
            "intelligence", "neural", "network", "algorithm", "function",
            "class", "object", "method", "variable", "constant",
            "test", "example", "sample", "document", "file",
            "search", "index", "query", "result", "database"
        ]
        return " ".join(random.choices(words, k=word_count))


class SessionFactory:
    """会话数据工厂"""

    @staticmethod
    def create(
        session_id: Optional[str] = None,
        name: Optional[str] = None,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
        message_count: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建会话数据

        Args:
            session_id: 会话ID
            name: 会话名称
            created_at: 创建时间
            updated_at: 更新时间
            message_count: 消息数量
            **kwargs: 额外字段

        Returns:
            会话数据字典
        """
        if session_id is None:
            session_id = f"sess_{random.randint(10000, 99999)}"

        if name is None:
            name = f"Session {random.randint(1, 100)}"

        now = datetime.now()
        if created_at is None:
            created_at = now.timestamp()

        if updated_at is None:
            updated_at = (now + timedelta(minutes=random.randint(1, 60))).timestamp()

        session = {
            "session_id": session_id,
            "name": name,
            "created_at": created_at,
            "updated_at": updated_at,
            "message_count": message_count,
        }
        session.update(kwargs)
        return session

    @staticmethod
    def create_batch(count: int) -> List[Dict[str, Any]]:
        """批量创建会话数据"""
        return [SessionFactory.create(message_count=random.randint(0, 50)) for _ in range(count)]


class MessageFactory:
    """消息数据工厂"""

    @staticmethod
    def create(
        role: str = "user",
        content: Optional[str] = None,
        timestamp: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建消息数据

        Args:
            role: 角色 (user/assistant)
            content: 消息内容
            timestamp: 时间戳
            **kwargs: 额外字段

        Returns:
            消息数据字典
        """
        if content is None:
            content = MessageFactory._generate_content(role)

        if timestamp is None:
            timestamp = datetime.now().timestamp()

        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }
        message.update(kwargs)
        return message

    @staticmethod
    def create_conversation(
        turns: int = 3,
        include_sources: bool = False
    ) -> List[Dict[str, Any]]:
        """
        创建完整对话

        Args:
            turns: 对话轮数
            include_sources: 是否包含来源信息

        Returns:
            消息列表
        """
        messages = []
        for i in range(turns):
            # User message
            user_msg = MessageFactory.create(role="user", content=f"Question {i+1}?")
            messages.append(user_msg)

            # Assistant message
            assistant_content = f"Answer {i+1} to your question."
            if include_sources:
                assistant_content += "\n\nSources: /test/doc1.txt"

            assistant_msg = MessageFactory.create(role="assistant", content=assistant_content)
            messages.append(assistant_msg)

        return messages

    @staticmethod
    def _generate_content(role: str) -> str:
        """生成随机消息内容"""
        if role == "user":
            questions = [
                "What is Python?",
                "How do I search for files?",
                "Tell me about machine learning.",
                "What documents do I have?",
                "Search for code examples.",
                "Find my notes about AI.",
            ]
            return random.choice(questions)
        else:
            answers = [
                "Python is a programming language.",
                "You can search using the search bar.",
                "Machine learning is a subset of AI.",
                "Here are your documents...",
                "I found these code examples...",
                "Here are your AI notes...",
            ]
            return random.choice(answers)


class SearchResultFactory:
    """搜索结果数据工厂"""

    @staticmethod
    def create(
        path: Optional[str] = None,
        filename: Optional[str] = None,
        content: Optional[str] = None,
        score: Optional[float] = None,
        file_type: Optional[str] = None,
        highlights: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建搜索结果数据

        Args:
            path: 文件路径
            filename: 文件名
            content: 匹配内容
            score: 匹配分数
            file_type: 文件类型
            highlights: 高亮片段
            **kwargs: 额外字段

        Returns:
            搜索结果字典
        """
        if filename is None:
            filename = f"result_{random.randint(1000, 9999)}.txt"

        if path is None:
            path = f"/test/{filename}"

        if content is None:
            content = f"This is search result content with some matching text."

        if score is None:
            score = round(random.uniform(0.5, 1.0), 2)

        if file_type is None:
            file_type = filename.split('.')[-1] if '.' in filename else 'txt'

        if highlights is None:
            highlights = ["matching text"]

        result = {
            "path": path,
            "filename": filename,
            "content": content,
            "score": score,
            "file_type": file_type,
            "highlights": highlights,
        }
        result.update(kwargs)
        return result

    @staticmethod
    def create_batch(
        count: int,
        min_score: float = 0.5,
        max_score: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        批量创建搜索结果

        Args:
            count: 数量
            min_score: 最小分数
            max_score: 最大分数

        Returns:
            搜索结果列表
        """
        results = []
        for i in range(count):
            score = round(random.uniform(min_score, max_score), 2)
            result = SearchResultFactory.create(
                filename=f"result_{i}.txt",
                score=score
            )
            results.append(result)

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results


class ConfigFactory:
    """配置数据工厂"""

    @staticmethod
    def create_minimal() -> Dict[str, Any]:
        """创建最小配置"""
        return {
            "system": {"data_dir": "./data"},
            "search": {"max_results": 10},
            "embedding": {"enabled": False},
        }

    @staticmethod
    def create_full() -> Dict[str, Any]:
        """创建完整配置"""
        return {
            "system": {
                "data_dir": "./data",
                "log_level": "INFO"
            },
            "search": {
                "text_weight": 0.6,
                "vector_weight": 0.4,
                "max_results": 20,
                "min_score": 0.3
            },
            "embedding": {
                "enabled": True,
                "provider": "fastembed",
                "model": "bge-small-zh"
            },
            "ai_model": {
                "enabled": True,
                "interface_type": "api",
                "api_url": "http://localhost:8080/v1/chat/completions",
                "context_size": 4096
            },
            "file_scanner": {
                "scan_paths": ["./documents"],
                "batch_size": 100
            },
            "monitor": {
                "enabled": True
            }
        }
