"""聊天历史数据库管理器 - 使用 SQLite"""

import re
import sqlite3
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

# Pre-compile session ID validation regex
# 只允许字母数字、下划线、连字符，长度限制在 1-64 字符
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # 会话 ID 验证正则


class ChatHistoryDB:
    """基于 SQLite 的聊天历史存储"""

    def __init__(self, db_path: Optional[str] = None):
        """初始化数据库连接

        Args:
            db_path: SQLite 数据库文件路径，默认为 data/chat_history.db
        """
        if db_path is None:
            # Default location: data/chat_history.db
            base_dir = Path(__file__).parent.parent.parent
            db_path = str(base_dir / "data" / "chat_history.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-local storage for connections
        self._local = threading.local()

        # 跟踪所有线程的连接
        self._all_connections = []
        self._connections_lock = threading.Lock()

        # Initialize tables
        self._init_db()

    @contextmanager
    def get_cursor(self):
        """获取数据库游标的上下文管理器

        自动处理事务提交/回滚和游标关闭

        Yields:
            sqlite3.Cursor: 数据库游标

        Example:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM sessions")
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            logger.error(f"数据库操作失败：{e}")
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cursor.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地数据库连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            # 记录连接以便后续统一关闭
            with self._connections_lock:
                self._all_connections.append(self._local.conn)
        return self._local.conn

    def close(self) -> None:
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
                # 从跟踪列表中移除
                with self._connections_lock:
                    if self._local.conn in self._all_connections:
                        self._all_connections.remove(self._local.conn)
                self._local.conn = None
            except Exception as e:
                logger.warning(f"关闭数据库连接失败：{e}")

    def close_all(self) -> None:
        """关闭所有线程的数据库连接"""
        with self._connections_lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"关闭数据库连接失败：{e}")
            self._all_connections.clear()

        # 同时关闭当前线程的连接
        self.close()

    def __del__(self):
        """析构时确保连接被关闭"""
        try:
            self.close_all()
        except Exception:
            pass  # 静默忽略析构时的异常

    def _init_db(self):
        """初始化数据库表"""
        with self.get_cursor() as cursor:
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

    def _validate_session_id(self, session_id: str) -> bool:
        """验证会话 ID 格式

        Args:
            session_id: 要验证的会话标识符

        Returns:
            有效返回 True
        """
        if not session_id or not isinstance(session_id, str):
            return False
        if len(session_id) > 64:
            return False
        # Allow alphanumeric, underscore, hyphen, and some safe characters
        return bool(SESSION_ID_PATTERN.match(session_id))

    def create_session(self, session_id: str, title: Optional[str] = None) -> bool:
        """创建新会话

        Args:
            session_id: 唯一会话标识符
            title: 会话标题（可选）

        Returns:
            创建成功返回 True
        """
        if not self._validate_session_id(session_id):
            return False

        with self.get_cursor() as cursor:
            now = time.time()
            cursor.execute(
                """
                INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, title or "新对话", now, now),
            )
            return cursor.rowcount > 0

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """添加消息到会话

        Args:
            session_id: 会话标识符
            role: 'user' 或 'assistant'
            content: 消息内容

        Returns:
            添加成功返回 True
        """
        if not self._validate_session_id(session_id):
            return False

        with self.get_cursor() as cursor:
            now = time.time()

            # 优化：使用 INSERT OR IGNORE 自动创建会话（如果不存在）
            # 这样可以避免先查询再创建的两次数据库操作
            cursor.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at, message_count) VALUES (?, ?, ?, ?, 0)",
                (session_id, "新对话", now, now),
            )

            # 添加消息
            cursor.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, role, content, now),
            )

            # 更新会话
            cursor.execute(
                """
                UPDATE sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE session_id = ?
            """,
                (now, session_id),
            )

            # 如果是第一条用户消息，更新标题
            if role == "user":
                cursor.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                    (session_id,),
                )
                user_count = cursor.fetchone()[0]
                if user_count == 1:
                    title = content[:30] + "..." if len(content) > 30 else content
                    cursor.execute(
                        "UPDATE sessions SET title = ? WHERE session_id = ?",
                        (title, session_id),
                    )

            return True

    def get_session_messages(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取会话的所有消息

        Args:
            session_id: 会话标识符
            limit: 返回消息的最大数量

        Returns:
            消息字典列表
        """
        if not self._validate_session_id(session_id):
            return []

        with self.get_cursor() as cursor:
            if limit:
                cursor.execute(
                    """
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp
                    LIMIT ?
                """,
                    (session_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp
                """,
                    (session_id,),
                )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话

        Returns:
            会话字典列表
        """
        with self.get_cursor() as cursor:
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
                cursor.execute(
                    """
                    SELECT content FROM messages
                    WHERE session_id = ? AND role = 'assistant'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    (session["session_id"],),
                )
                last = cursor.fetchone()
                if last:
                    preview = (
                        last["content"][:50] + "..."
                        if len(last["content"]) > 50
                        else last["content"]
                    )
                    session["last_message"] = preview
                else:
                    session["last_message"] = ""
                sessions.append(session)

            return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息

        Args:
            session_id: 会话标识符

        Returns:
            删除成功返回 True
        """
        if not self._validate_session_id(session_id):
            return False

        with self.get_cursor() as cursor:
            # 先删除关联的消息
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            # 再删除会话
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.rowcount > 0

    def clear_session_messages(self, session_id: str) -> bool:
        """清空会话的所有消息但保留会话

        Args:
            session_id: 会话标识符

        Returns:
            清空成功返回 True
        """
        if not self._validate_session_id(session_id):
            return False

        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute(
                "UPDATE sessions SET message_count = 0, updated_at = ? WHERE session_id = ?",
                (time.time(), session_id),
            )
            return True

    def session_exists(self, session_id: str) -> bool:
        """检查会话是否存在

        Args:
            session_id: 会话标识符

        Returns:
            会话存在返回 True
        """
        if not self._validate_session_id(session_id):
            return False

        with self.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.fetchone() is not None

    def cleanup_old_sessions(
        self, max_age_days: int = 30, max_sessions: int = 1000
    ) -> int:
        """
        清理旧会话，防止数据库无限增长

        Args:
            max_age_days: 会话最大保留天数
            max_sessions: 最大保留会话数

        Returns:
            删除的会话数
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        deleted_count = 0
        try:
            # 显式事务确保多步操作的原子性
            cursor.execute("BEGIN TRANSACTION")
            try:
                # 1. 删除超过 max_age_days 天的旧会话
                cutoff_time = time.time() - (max_age_days * 24 * 3600)
                cursor.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff_time,))
                deleted_count += cursor.rowcount

                # 2. 如果会话数仍然超过 max_sessions，删除最旧的
                cursor.execute("SELECT COUNT(*) FROM sessions")
                count = cursor.fetchone()[0]

                if count > max_sessions:
                    # 删除最旧的会话，保留 max_sessions 个
                    cursor.execute(
                        """
                        DELETE FROM sessions
                        WHERE session_id IN (
                            SELECT session_id FROM sessions
                            ORDER BY updated_at DESC
                            LIMIT -1 OFFSET ?
                        )
                        """,
                        (max_sessions,),
                    )
                    deleted_count += cursor.rowcount

                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                raise

            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧会话")
            return deleted_count
        finally:
            cursor.close()
