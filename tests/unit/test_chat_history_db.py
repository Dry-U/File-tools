"""Chat History DB 单元测试"""
import pytest
import sys
import os
import tempfile
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.chat_history_db import ChatHistoryDB


class TestChatHistoryDB:
    """ChatHistoryDB 测试类"""

    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)
            yield db
            db.close()

    def test_init(self, temp_db):
        """测试初始化"""
        assert temp_db.db_path.exists()

    def test_init_default_path(self):
        """测试默认路径初始化"""
        db = ChatHistoryDB()
        assert db.db_path is not None
        db.close()

    def test_create_session(self, temp_db):
        """测试创建会话"""
        result = temp_db.create_session("test_session")
        assert result == True

    def test_create_session_with_title(self, temp_db):
        """测试带标题创建会话"""
        result = temp_db.create_session("test_session", "测试会话")
        assert result == True

    def test_create_session_invalid_id(self, temp_db):
        """测试无效会话ID"""
        result = temp_db.create_session("")
        assert result == False

    def test_create_session_invalid_characters(self, temp_db):
        """测试无效字符会话ID"""
        result = temp_db.create_session("test/session")  # 包含非法字符
        assert result == False

    def test_create_session_too_long(self, temp_db):
        """测试过长会话ID"""
        long_id = "a" * 300
        result = temp_db.create_session(long_id)
        assert result == False

    def test_add_message(self, temp_db):
        """测试添加消息"""
        temp_db.create_session("test_session")
        result = temp_db.add_message("test_session", "user", "Hello")
        assert result == True

    def test_add_message_auto_create_session(self, temp_db):
        """测试自动创建会话"""
        result = temp_db.add_message("new_session", "user", "Hello")
        assert result == True
        assert temp_db.session_exists("new_session")

    def test_add_message_invalid_session(self, temp_db):
        """测试无效会话ID添加消息"""
        result = temp_db.add_message("", "user", "Hello")
        assert result == False

    def test_add_message_invalid_role(self, temp_db):
        """测试无效角色"""
        temp_db.create_session("test_session")
        # 应该仍然可以添加，不验证角色
        result = temp_db.add_message("test_session", "invalid_role", "Hello")
        assert result == True

    def test_get_session_messages(self, temp_db):
        """测试获取会话消息"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "Hello")
        temp_db.add_message("test_session", "assistant", "Hi there")

        messages = temp_db.get_session_messages("test_session")
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"

    def test_get_session_messages_empty(self, temp_db):
        """测试获取空会话消息"""
        temp_db.create_session("test_session")
        messages = temp_db.get_session_messages("test_session")
        assert messages == []

    def test_get_session_messages_invalid_id(self, temp_db):
        """测试无效会话ID获取消息"""
        messages = temp_db.get_session_messages("")
        assert messages == []

    def test_get_session_messages_with_limit(self, temp_db):
        """测试限制消息数量"""
        temp_db.create_session("test_session")
        for i in range(10):
            temp_db.add_message("test_session", "user", f"Message {i}")

        messages = temp_db.get_session_messages("test_session", limit=5)
        assert len(messages) == 5

    def test_get_all_sessions(self, temp_db):
        """测试获取所有会话"""
        temp_db.create_session("session1", "会话1")
        temp_db.create_session("session2", "会话2")
        temp_db.add_message("session1", "user", "Hello")

        sessions = temp_db.get_all_sessions()
        assert len(sessions) == 2

    def test_get_all_sessions_empty(self, temp_db):
        """测试获取空会话列表"""
        sessions = temp_db.get_all_sessions()
        assert sessions == []

    def test_get_all_sessions_order(self, temp_db):
        """测试会话排序"""
        temp_db.create_session("session1")
        time.sleep(0.01)
        temp_db.create_session("session2")

        sessions = temp_db.get_all_sessions()
        # 应该按更新时间倒序
        assert sessions[0]["session_id"] == "session2"

    def test_delete_session(self, temp_db):
        """测试删除会话"""
        temp_db.create_session("test_session")
        result = temp_db.delete_session("test_session")
        assert result == True
        assert not temp_db.session_exists("test_session")

    def test_delete_session_with_messages(self, temp_db):
        """测试删除带消息的会话"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "Hello")
        temp_db.delete_session("test_session")

        messages = temp_db.get_session_messages("test_session")
        assert messages == []

    def test_delete_session_invalid_id(self, temp_db):
        """测试删除无效会话"""
        result = temp_db.delete_session("nonexistent")
        assert result == False

    def test_delete_session_empty_id(self, temp_db):
        """测试删除空会话ID"""
        result = temp_db.delete_session("")
        assert result == False

    def test_session_exists(self, temp_db):
        """测试会话存在性检查"""
        temp_db.create_session("test_session")
        assert temp_db.session_exists("test_session") == True
        assert temp_db.session_exists("nonexistent") == False

    def test_session_exists_invalid_id(self, temp_db):
        """测试无效ID存在性检查"""
        assert temp_db.session_exists("") == False

    def test_clear_session_messages(self, temp_db):
        """测试清空会话消息"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "Hello")
        result = temp_db.clear_session_messages("test_session")

        assert result == True
        messages = temp_db.get_session_messages("test_session")
        assert messages == []

    def test_clear_session_messages_keep_session(self, temp_db):
        """测试清空消息后保留会话"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "Hello")
        temp_db.clear_session_messages("test_session")

        assert temp_db.session_exists("test_session") == True

    def test_clear_session_messages_invalid_id(self, temp_db):
        """测试清空无效会话消息"""
        result = temp_db.clear_session_messages("")
        assert result == False

    def test_auto_update_title(self, temp_db):
        """测试自动更新标题"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "This is a very long message that should be truncated")

        sessions = temp_db.get_all_sessions()
        assert len(sessions[0]["title"]) <= 33  # 30 + "..."

    def test_message_count_increment(self, temp_db):
        """测试消息计数递增"""
        temp_db.create_session("test_session")
        temp_db.add_message("test_session", "user", "Hello")
        temp_db.add_message("test_session", "assistant", "Hi")

        sessions = temp_db.get_all_sessions()
        assert sessions[0]["message_count"] == 2

    def test_update_timestamp(self, temp_db):
        """测试更新时间戳"""
        temp_db.create_session("test_session")
        old_sessions = temp_db.get_all_sessions()
        old_time = old_sessions[0]["updated_at"]

        time.sleep(0.01)
        temp_db.add_message("test_session", "user", "Hello")

        new_sessions = temp_db.get_all_sessions()
        new_time = new_sessions[0]["updated_at"]
        assert new_time > old_time


class TestChatHistoryDBEdgeCases:
    """ChatHistoryDB 边界情况测试"""

    @pytest.fixture
    def temp_db(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)
            yield db
            db.close()
            import time
            time.sleep(0.1)  # Windows 下等待文件锁释放

    def test_concurrent_access(self, temp_db):
        """测试并发访问"""
        temp_db.create_session("test_session")

        def add_messages():
            for i in range(50):
                temp_db.add_message("test_session", "user", f"Message {i}")

        threads = [
            threading.Thread(target=add_messages),
            threading.Thread(target=add_messages)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        messages = temp_db.get_session_messages("test_session")
        assert len(messages) == 100

    def test_very_long_message(self, temp_db):
        """测试超长消息"""
        temp_db.create_session("test_session")
        long_content = "A" * 100000
        result = temp_db.add_message("test_session", "user", long_content)
        assert result == True

        messages = temp_db.get_session_messages("test_session")
        assert messages[0]["content"] == long_content

    def test_special_characters_in_message(self, temp_db):
        """测试消息中的特殊字符"""
        temp_db.create_session("test_session")
        special_content = "Hello! @#$%^&*() 你好世界 🌍 <script>alert('xss')</script>"
        temp_db.add_message("test_session", "user", special_content)

        messages = temp_db.get_session_messages("test_session")
        assert messages[0]["content"] == special_content

    def test_unicode_in_session_id(self, temp_db):
        """测试会话ID中的Unicode"""
        # 包含Unicode字符的ID应该被拒绝
        result = temp_db.create_session("会话123")
        assert result == False

    def test_sql_injection_attempt(self, temp_db):
        """测试SQL注入尝试"""
        temp_db.create_session("test_session")
        malicious_content = "'; DROP TABLE messages; --"
        result = temp_db.add_message("test_session", "user", malicious_content)
        assert result == True

        # 验证表仍然存在
        messages = temp_db.get_session_messages("test_session")
        assert len(messages) == 1

    def test_session_id_with_safe_special_chars(self, temp_db):
        """测试带安全特殊字符的会话ID"""
        # 只有字母、数字、下划线、连字符被允许
        result = temp_db.create_session("test-session_1")
        assert result == True

    def test_multiple_databases(self):
        """测试多个数据库实例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db1 = ChatHistoryDB(db_path)
            db2 = ChatHistoryDB(db_path)  # 相同路径

            db1.create_session("session1")
            db2.create_session("session2")

            sessions = db1.get_all_sessions()
            assert len(sessions) == 2

            db1.close()
            db2.close()

    def test_empty_message_content(self, temp_db):
        """测试空消息内容"""
        temp_db.create_session("test_session")
        result = temp_db.add_message("test_session", "user", "")
        assert result == True

        messages = temp_db.get_session_messages("test_session")
        assert messages[0]["content"] == ""

    def test_very_short_session_id(self, temp_db):
        """测试超短会话ID"""
        result = temp_db.create_session("a")
        assert result == True


class TestChatHistoryDBSessionValidation:
    """ChatHistoryDB 会话ID验证测试"""

    @pytest.fixture
    def temp_db(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)
            yield db
            db.close()
            import time
            time.sleep(0.1)

    @pytest.mark.parametrize("valid_id", [
        "session123",
        "test_session",
        "test-session",
        "SESSION_123",
        "123session",
        "a",
        "A" * 64,
    ])
    def test_valid_session_ids(self, temp_db, valid_id):
        """测试有效会话ID"""
        result = temp_db.create_session(valid_id)
        assert result == True

    @pytest.mark.parametrize("invalid_id", [
        "",
        "test/session",  # 斜杠
        "test\\session",  # 反斜杠
        "test session",  # 空格
        "test\tsession",  # 制表符
        "test\nsession",  # 换行
        "a" * 257,  # 过长
    ])
    def test_invalid_session_ids(self, temp_db, invalid_id):
        """测试无效会话ID"""
        result = temp_db.create_session(invalid_id)
        assert result == False


class TestChatHistoryDBConnectionManagement:
    """ChatHistoryDB 连接管理测试"""

    def test_close_all(self):
        """测试 close_all 关闭所有线程的连接"""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)

            # 在当前线程创建连接
            db.create_session("test_session")

            # 模拟多线程连接
            def create_connection():
                db.add_message("test_session", "user", "hello")

            threads = [threading.Thread(target=create_connection) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # 验证有多个连接被跟踪
            assert len(db._all_connections) >= 1

            # 关闭所有连接
            db.close_all()

            # 验证所有连接被清除
            assert len(db._all_connections) == 0

            # 验证关闭后仍可重新连接（惰性重连）
            db.create_session("test_session_2")
            assert db.session_exists("test_session_2")
            db.close()

    def test_close_removes_from_tracking(self):
        """测试 close() 从跟踪列表中移除连接"""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)
            db.create_session("test_session")

            assert len(db._all_connections) >= 1
            db.close()
            assert len(db._all_connections) == 0

    def test_del_closes_all_connections(self):
        """测试 __del__ 关闭所有连接"""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)
            db.create_session("test_session")
            initial_count = len(db._all_connections)
            assert initial_count >= 1

            # 调用 __del__（显式调用，因为Python可能不立即回收）
            db.__del__()
            assert len(db._all_connections) == 0

    def test_concurrent_close_all(self):
        """测试并发操作不会导致连接泄漏"""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_chat.db")
            db = ChatHistoryDB(db_path)

            # 多线程并发创建连接和操作
            def worker(worker_id):
                try:
                    sid = f"session_{worker_id}"
                    db.create_session(sid)
                    for i in range(10):
                        db.add_message(sid, "user", f"msg {worker_id}-{i}")
                except Exception:
                    pass  # SQLite 并发写入可能失败，这是预期的

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # 安全关闭所有连接
            db.close_all()

            # 验证所有连接被清除
            assert len(db._all_connections) == 0
            db.close()
