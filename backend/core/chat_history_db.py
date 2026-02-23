"""聊天历史数据库管理器 - 使用SQLite"""

import re
import sqlite3
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

# Pre-compile session ID validation regex
SESSION_ID_PATTERN = re.compile(r'^[\w\-.$@:]+$')  # 会话ID验证正则


class ChatHistoryDB:
    """基于SQLite的聊天历史存储"""

    def __init__(self, db_path: str = None):
        """初始化数据库连接

        Args:
            db_path: SQLite数据库文件路径，默认为 data/chat_history.db
        """
        if db_path is None:
            # Default location: data/chat_history.db
            base_dir = Path(__file__).parent.parent.parent
            db_path = base_dir / "data" / "chat_history.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-local storage for connections
        self._local = threading.local()

        # Initialize tables
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                created_at REAL,
                updated_at REAL,
                message_count INTEGER DEFAULT 0
            )
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)

        # Index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)
        """)

        conn.commit()

    def _validate_session_id(self, session_id: str) -> bool:
        """验证会话ID格式

        Args:
            session_id: 要验证的会话标识符

        Returns:
            有效返回True
        """
        if not session_id or not isinstance(session_id, str):
            return False
        if len(session_id) > 256:
            return False
        # Allow alphanumeric, underscore, hyphen, and some safe characters
        return bool(SESSION_ID_PATTERN.match(session_id))

    def create_session(self, session_id: str, title: str = None) -> bool:
        """创建新会话

        Args:
            session_id: 唯一会话标识符
            title: 会话标题（可选）

        Returns:
            创建成功返回True
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        now = time.time()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (session_id, title or '新对话', now, now))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return False

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """添加消息到会话

        Args:
            session_id: 会话标识符
            role: 'user' 或 'assistant'
            content: 消息内容

        Returns:
            添加成功返回True
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        now = time.time()
        try:
            # 确保会话存在
            cursor.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, '新对话', now, now)
            )

            # 添加消息
            cursor.execute("""
                INSERT INTO messages (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, content, now))

            # 更新会话
            cursor.execute("""
                UPDATE sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE session_id = ?
            """, (now, session_id))

            # 如果是第一条用户消息，更新标题
            if role == 'user':
                cursor.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                    (session_id,)
                )
                user_count = cursor.fetchone()[0]
                if user_count == 1:
                    title = content[:30] + '...' if len(content) > 30 else content
                    cursor.execute(
                        "UPDATE sessions SET title = ? WHERE session_id = ?",
                        (title, session_id)
                    )

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"添加消息失败: {e}")
            return False

    def get_session_messages(self, session_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """获取会话的所有消息

        Args:
            session_id: 会话标识符
            limit: 返回消息的最大数量

        Returns:
            消息字典列表
        """
        if not self._validate_session_id(session_id):
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if limit:
                cursor.execute("""
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp
                    LIMIT ?
                """, (session_id, limit))
            else:
                cursor.execute("""
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp
                """, (session_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取会话消息失败: {e}")
            return []

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话

        Returns:
            会话字典列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT session_id, title, created_at, updated_at, message_count
                FROM sessions
                ORDER BY updated_at DESC
            """)

            rows = cursor.fetchall()
            sessions = []
            for row in rows:
                session = dict(row)
                # Get last message preview
                cursor.execute("""
                    SELECT content FROM messages
                    WHERE session_id = ? AND role = 'assistant'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (session['session_id'],))
                last = cursor.fetchone()
                if last:
                    preview = last['content'][:50] + '...' if len(last['content']) > 50 else last['content']
                    session['last_message'] = preview
                else:
                    session['last_message'] = ''
                sessions.append(session)

            return sessions
        except Exception as e:
            logger.error(f"获取所有会话失败: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息

        Args:
            session_id: 会话标识符

        Returns:
            删除成功返回True
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False

    def clear_session_messages(self, session_id: str) -> bool:
        """清空会话的所有消息但保留会话

        Args:
            session_id: 会话标识符

        Returns:
            清空成功返回True
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute(
                "UPDATE sessions SET message_count = 0, updated_at = ? WHERE session_id = ?",
                (time.time(), session_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"清空会话消息失败: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """检查会话是否存在

        Args:
            session_id: 会话标识符

        Returns:
            会话存在返回True
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查会话存在性失败: {e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
