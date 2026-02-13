"""Chat history database manager using SQLite."""

import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional


class ChatHistoryDB:
    """SQLite-based chat history storage."""

    def __init__(self, db_path: str = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to data/chat_history.db
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
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        """Initialize database tables."""
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
        """Validate session_id format.

        Args:
            session_id: Session identifier to validate

        Returns:
            True if valid
        """
        if not session_id or not isinstance(session_id, str):
            return False
        if len(session_id) > 256:
            return False
        # Allow alphanumeric, underscore, hyphen, and some safe characters
        import re
        return bool(re.match(r'^[\w\-.$@:]+$', session_id))

    def create_session(self, session_id: str, title: str = None) -> bool:
        """Create a new session.

        Args:
            session_id: Unique session identifier
            title: Session title (optional)

        Returns:
            True if created successfully
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
            print(f"Error creating session: {e}")
            return False

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """Add a message to a session.

        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content

        Returns:
            True if added successfully
        """
        if not self._validate_session_id(session_id):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        now = time.time()
        try:
            # Ensure session exists
            cursor.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, '新对话', now, now)
            )

            # Add message
            cursor.execute("""
                INSERT INTO messages (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, content, now))

            # Update session
            cursor.execute("""
                UPDATE sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE session_id = ?
            """, (now, session_id))

            # Update title if this is the first user message
            if role == 'user':
                cursor.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                    (session_id,)
                )
                user_count = cursor.fetchone()[0]
                if user_count == 1:  # First user message
                    title = content[:30] + '...' if len(content) > 30 else content
                    cursor.execute(
                        "UPDATE sessions SET title = ? WHERE session_id = ?",
                        (title, session_id)
                    )

            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding message: {e}")
            return False

    def get_session_messages(self, session_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get all messages for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
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
            print(f"Error getting session messages: {e}")
            return []

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions.

        Returns:
            List of session dictionaries
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
            print(f"Error getting all sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully
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
            print(f"Error deleting session: {e}")
            return False

    def clear_session_messages(self, session_id: str) -> bool:
        """Clear all messages from a session but keep the session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully
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
            print(f"Error clearing session messages: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Session identifier

        Returns:
            True if session exists
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
            print(f"Error checking session existence: {e}")
            return False

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
