#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web API 端点测试
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 在导入 app 之前先 mock 相关组件
with patch('backend.utils.config_loader.ConfigLoader') as mock_config:
    with patch('backend.core.index_manager.IndexManager'):
        with patch('backend.core.search_engine.SearchEngine'):
            with patch('backend.core.file_scanner.FileScanner'):
                with patch('backend.core.file_monitor.FileMonitor'):
                    from backend.api.api import app, get_rate_limiter, RateLimiter


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_rate_limiter():
    """创建模拟限流器"""
    limiter = RateLimiter()
    limiter._requests = {}
    return limiter


class TestHealthEndpoint:
    """健康检查端点测试"""

    def test_health_check_healthy(self, client):
        """测试健康检查 - 健康状态"""
        app.state.initialized = True
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_check_starting(self, client):
        """测试健康检查 - 启动中"""
        app.state.initialized = False
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "starting"


class TestRateLimiter:
    """限流器测试"""

    def test_rate_limiter_init(self):
        """测试限流器初始化"""
        limiter = RateLimiter(max_entries=100)
        assert limiter._max_entries == 100
        assert limiter._requests == {}

    def test_rate_limiter_allow_first_request(self):
        """测试首次请求允许"""
        limiter = RateLimiter()
        assert limiter.is_allowed("test_key", max_requests=10, window=60) == True

    def test_rate_limiter_block_excess(self):
        """测试超出限制阻止"""
        limiter = RateLimiter()
        # 发送超过限制的请求
        for i in range(5):
            limiter.is_allowed("test_key", max_requests=3, window=60)
        # 第4个请求应该被阻止
        assert limiter.is_allowed("test_key", max_requests=3, window=60) == False

    def test_rate_limiter_different_keys(self):
        """测试不同key独立计数"""
        limiter = RateLimiter()
        limiter.is_allowed("key1", max_requests=1, window=60)
        assert limiter.is_allowed("key2", max_requests=1, window=60) == True

    def test_rate_limiter_cleanup_expired(self):
        """测试过期清理"""
        limiter = RateLimiter()
        limiter._requests["old_key"] = [0]  # 很久以前的时间戳
        limiter._last_cleanup = 0
        limiter.is_allowed("new_key", max_requests=10, window=1)
        # old_key 应该被清理
        assert "old_key" not in limiter._requests

    def test_rate_limiter_emergency_cleanup(self):
        """测试紧急清理"""
        limiter = RateLimiter(max_entries=4)
        # 填满条目
        for i in range(4):
            limiter.is_allowed(f"key{i}", max_requests=10, window=60)
        # 触发紧急清理
        limiter.is_allowed("new_key", max_requests=10, window=60)
        # 应该只剩下一半
        assert len(limiter._requests) <= 3


class TestSearchEndpoint:
    """搜索端点测试"""

    @pytest.fixture
    def mock_search_engine(self):
        """创建模拟搜索引擎"""
        engine = Mock()
        engine.search.return_value = [
            {
                "path": "/test/doc1.txt",
                "filename": "doc1.txt",
                "score": 0.9,
                "snippet": "Test content"
            }
        ]
        return engine

    def test_search_success(self, client, mock_search_engine):
        """测试成功搜索"""
        with patch('backend.api.api.get_search_engine', return_value=mock_search_engine):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                response = client.post("/api/search", json={"query": "test", "filters": {}})
                assert response.status_code == 200
                results = response.json()
                assert len(results) > 0
                assert results[0]["file_name"] == "doc1.txt"

    def test_search_empty_query(self, client, mock_search_engine):
        """测试空查询"""
        with patch('backend.api.api.get_search_engine', return_value=mock_search_engine):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                response = client.post("/api/search", json={"query": "", "filters": {}})
                assert response.status_code == 400
                assert "不能为空" in response.json()["detail"]

    def test_search_no_query_field(self, client):
        """测试缺少query字段"""
        with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
            response = client.post("/api/search", json={"filters": {}})
            assert response.status_code == 200  # 会获取None作为query

    def test_search_rate_limited(self, client, mock_search_engine):
        """测试搜索限流"""
        limiter = Mock()
        limiter.is_allowed.return_value = False
        with patch('backend.api.api.get_search_engine', return_value=mock_search_engine):
            with patch('backend.api.api.get_rate_limiter', return_value=limiter):
                with patch('backend.api.api.get_config_loader') as mock_config:
                    mock_config.return_value.getboolean.return_value = True
                    response = client.post("/api/search", json={"query": "test"})
                    assert response.status_code == 429


class TestChatEndpoint:
    """聊天端点测试"""

    @pytest.fixture
    def mock_rag_pipeline(self):
        """创建模拟RAG管道"""
        pipeline = Mock()
        pipeline.query.return_value = {"answer": "Test answer", "sources": ["/test/doc.txt"]}
        return pipeline

    def test_chat_success(self, client, mock_rag_pipeline):
        """测试成功聊天"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                response = client.post("/api/chat", json={"query": "Hello", "session_id": "test123"})
                assert response.status_code == 200
                result = response.json()
                assert result["answer"] == "Test answer"

    def test_chat_empty_query(self, client, mock_rag_pipeline):
        """测试空查询"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                response = client.post("/api/chat", json={"query": ""})
                assert response.status_code == 400

    def test_chat_disabled(self, client):
        """测试AI功能未启用"""
        with patch('backend.api.api.get_rag_pipeline', return_value=None):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                with patch('backend.api.api.get_config_loader') as mock_config:
                    mock_config.return_value.getboolean.return_value = False
                    response = client.post("/api/chat", json={"query": "Hello"})
                    assert response.status_code == 200
                    assert "未启用" in response.json()["answer"]

    def test_chat_no_session_id(self, client, mock_rag_pipeline):
        """测试无session_id"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                response = client.post("/api/chat", json={"query": "Hello"})
                assert response.status_code == 200


class TestSessionsEndpoint:
    """会话端点测试"""

    @pytest.fixture
    def mock_rag_pipeline(self):
        """创建模拟RAG管道"""
        pipeline = Mock()
        pipeline.get_all_sessions.return_value = [
            {"session_id": "sess1", "title": "Session 1"},
            {"session_id": "sess2", "title": "Session 2"}
        ]
        pipeline.clear_session.return_value = True
        pipeline.chat_db.get_session_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        return pipeline

    def test_get_sessions_success(self, client, mock_rag_pipeline):
        """测试获取会话列表"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            response = client.get("/api/sessions")
            assert response.status_code == 200
            sessions = response.json()["sessions"]
            assert len(sessions) == 2

    def test_get_sessions_no_rag(self, client):
        """测试无RAG时获取会话"""
        with patch('backend.api.api.get_rag_pipeline', return_value=None):
            response = client.get("/api/sessions")
            assert response.status_code == 200
            assert response.json()["sessions"] == []

    def test_delete_session_success(self, client, mock_rag_pipeline):
        """测试删除会话"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            response = client.delete("/api/sessions/test_session")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

    def test_delete_session_not_found(self, client, mock_rag_pipeline):
        """测试删除不存在的会话"""
        mock_rag_pipeline.clear_session.return_value = False
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            response = client.delete("/api/sessions/nonexistent")
            assert response.status_code == 404

    def test_delete_session_no_rag(self, client):
        """测试无RAG时删除会话"""
        with patch('backend.api.api.get_rag_pipeline', return_value=None):
            response = client.delete("/api/sessions/test")
            assert response.status_code == 500

    def test_get_session_messages_success(self, client, mock_rag_pipeline):
        """测试获取会话消息"""
        with patch('backend.api.api.get_rag_pipeline', return_value=mock_rag_pipeline):
            response = client.get("/api/sessions/test_session/messages")
            assert response.status_code == 200
            messages = response.json()["messages"]
            assert len(messages) == 2

    def test_get_session_messages_no_rag(self, client):
        """测试无RAG时获取消息"""
        with patch('backend.api.api.get_rag_pipeline', return_value=None):
            response = client.get("/api/sessions/test/messages")
            assert response.status_code == 500


class TestConfigEndpoint:
    """配置端点测试"""

    @pytest.fixture
    def mock_config_loader(self):
        """创建模拟配置加载器"""
        config = Mock()
        config.getboolean.side_effect = lambda section, key, default=False: {
            ("ai_model", "enabled"): True,
            ("ai_model", "security.verify_ssl"): True,
        }.get((section, key), default)
        config.get.side_effect = lambda section, key, default=None: {
            ("ai_model", "mode"): "api",
            ("ai_model", "api.provider"): "siliconflow",
            ("ai_model", "api.api_url"): "https://api.example.com",
            ("ai_model", "api.model_name"): "test-model",
            ("ai_model", "system_prompt"): "Test prompt",
            ("ai_model", "local.api_url"): "http://localhost:8000",
        }.get((section, key), default)
        config.getint.side_effect = lambda section, key, default=0: {
            ("ai_model", "local.max_context"): 4096,
            ("ai_model", "local.max_tokens"): 512,
            ("ai_model", "api.max_context"): 8192,
            ("ai_model", "api.max_tokens"): 2048,
            ("ai_model", "security.timeout"): 120,
            ("ai_model", "security.retry_count"): 2,
            ("rag", "max_history_turns"): 3,
            ("rag", "max_history_chars"): 1000,
        }.get((section, key), default)
        config.getfloat.side_effect = lambda section, key, default=0.0: {
            ("ai_model", "sampling.temperature"): 0.7,
            ("ai_model", "sampling.top_p"): 0.9,
            ("ai_model", "sampling.min_p"): 0.05,
        }.get((section, key), default)
        return config

    def test_get_config_success(self, client, mock_config_loader):
        """测试获取配置"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            response = client.get("/api/config")
            assert response.status_code == 200
            config = response.json()
            assert "ai_model" in config
            assert config["ai_model"]["enabled"] == True

    def test_update_config_success(self, client, mock_config_loader):
        """测试更新配置"""
        mock_config_loader.save.return_value = True
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            response = client.post("/api/config", json={
                "ai_model": {
                    "enabled": True
                }
            })
            assert response.status_code == 200
            assert response.json()["status"] == "success"

    def test_update_config_invalid_data(self, client, mock_config_loader):
        """测试无效配置数据"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            response = client.post("/api/config", json="not a dict")
            assert response.status_code == 400

    def test_update_config_empty_sections(self, client, mock_config_loader):
        """测试空配置节"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            response = client.post("/api/config", json={"unknown_section": {}})
            assert response.status_code == 200
            assert response.json()["status"] == "warning"


class TestPreviewEndpoint:
    """文件预览端点测试"""

    @pytest.fixture
    def mock_index_manager(self):
        """创建模拟索引管理器"""
        manager = Mock()
        manager.get_document_content.return_value = "Test document content"
        return manager

    @pytest.fixture
    def mock_config_loader(self):
        """创建模拟配置加载器"""
        config = Mock()
        config.get.return_value = "/test/path"
        return config

    def test_preview_success(self, client, mock_index_manager, mock_config_loader):
        """测试成功预览"""
        with patch('backend.api.api.get_index_manager', return_value=mock_index_manager):
            with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
                with patch('os.path.exists', return_value=True):
                    with patch('os.path.isdir', return_value=True):
                        with patch('os.path.abspath', return_value="/test"):
                            with patch('os.path.getsize', return_value=1000):
                                response = client.post("/api/preview", json={"path": "/test/file.txt"})
                                assert response.status_code == 200
                                assert "content" in response.json()

    def test_preview_empty_path(self, client):
        """测试空路径"""
        response = client.post("/api/preview", json={"path": ""})
        assert response.status_code == 200
        assert "错误" in response.json()["content"]

    def test_preview_path_not_allowed(self, client, mock_config_loader):
        """测试不允许的路径"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.is_path_allowed', return_value=False):
                response = client.post("/api/preview", json={"path": "/etc/passwd"})
                assert response.status_code == 200
                assert "超出允许范围" in response.json()["content"]

    def test_preview_file_not_found(self, client, mock_index_manager, mock_config_loader):
        """测试文件不存在"""
        with patch('backend.api.api.get_index_manager', return_value=mock_index_manager):
            with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
                with patch('os.path.exists', return_value=False):
                    with patch('backend.api.api.is_path_allowed', return_value=True):
                        response = client.post("/api/preview", json={"path": "/test/nonexistent.txt"})
                        assert response.status_code == 200
                        assert "不存在" in response.json()["content"]


class TestRebuildIndexEndpoint:
    """重建索引端点测试"""

    @pytest.fixture
    def mock_file_scanner(self):
        """创建模拟文件扫描器"""
        scanner = Mock()
        scanner.scan_and_index.return_value = {
            "total_files_scanned": 100,
            "total_files_indexed": 50
        }
        scanner.scan_paths = ["/test/path"]
        return scanner

    @pytest.fixture
    def mock_index_manager(self):
        """创建模拟索引管理器"""
        manager = Mock()
        manager.rebuild_index.return_value = True
        return manager

    def test_rebuild_index_success(self, client, mock_file_scanner, mock_index_manager):
        """测试成功重建索引"""
        with patch('backend.api.api.get_file_scanner', return_value=mock_file_scanner):
            with patch('backend.api.api.get_index_manager', return_value=mock_index_manager):
                with patch('backend.api.api.get_rate_limiter', return_value=RateLimiter()):
                    with patch('backend.api.api.get_config_loader') as mock_config:
                        mock_config.return_value.getboolean.return_value = False  # 禁用限流
                        response = client.post("/api/rebuild-index")
                        assert response.status_code == 200
                        result = response.json()
                        assert result["status"] == "success"
                        assert result["files_scanned"] == 100

    def test_rebuild_index_rate_limited(self, client, mock_file_scanner, mock_index_manager):
        """测试重建索引限流"""
        limiter = Mock()
        limiter.is_allowed.return_value = False
        with patch('backend.api.api.get_file_scanner', return_value=mock_file_scanner):
            with patch('backend.api.api.get_index_manager', return_value=mock_index_manager):
                with patch('backend.api.api.get_rate_limiter', return_value=limiter):
                    with patch('backend.api.api.get_config_loader') as mock_config:
                        mock_config.return_value.getboolean.return_value = True
                        response = client.post("/api/rebuild-index")
                        assert response.status_code == 429


class TestDirectoryEndpoints:
    """目录管理端点测试"""

    @pytest.fixture
    def mock_config_loader(self):
        """创建模拟配置加载器"""
        config = Mock()
        config.get.return_value = ["/test/path1", "/test/path2"]
        config.getboolean.return_value = True
        return config

    @pytest.fixture
    def mock_file_monitor(self):
        """创建模拟文件监控器"""
        monitor = Mock()
        monitor.get_monitored_directories.return_value = ["/test/path1"]
        return monitor

    def test_get_directories_success(self, client, mock_config_loader, mock_file_monitor):
        """测试获取目录列表"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.get_file_monitor', return_value=mock_file_monitor):
                with patch('os.path.exists', return_value=True):
                    with patch('os.path.isdir', return_value=True):
                        response = client.get("/api/directories")
                        assert response.status_code == 200
                        directories = response.json()["directories"]
                        assert len(directories) >= 1

    def test_add_directory_success(self, client, mock_config_loader, mock_file_monitor):
        """测试添加目录"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.get_file_monitor', return_value=mock_file_monitor):
                with patch('backend.api.api.get_file_scanner', return_value=Mock()):
                    with patch('os.path.exists', return_value=True):
                        with patch('os.path.isdir', return_value=True):
                            with patch('os.path.abspath', return_value="/new/path"):
                                response = client.post("/api/directories", json={"path": "/new/path"})
                                assert response.status_code == 200
                                assert response.json()["status"] == "success"

    def test_add_directory_not_exist(self, client, mock_config_loader, mock_file_monitor):
        """测试添加不存在的目录"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.get_file_monitor', return_value=mock_file_monitor):
                with patch('os.path.exists', return_value=False):
                    response = client.post("/api/directories", json={"path": "/nonexistent"})
                    assert response.status_code == 400

    def test_add_directory_not_directory(self, client, mock_config_loader, mock_file_monitor):
        """测试添加非目录路径"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.get_file_monitor', return_value=mock_file_monitor):
                with patch('os.path.exists', return_value=True):
                    with patch('os.path.isdir', return_value=False):
                        response = client.post("/api/directories", json={"path": "/test/file.txt"})
                        assert response.status_code == 400

    def test_remove_directory_success(self, client, mock_config_loader, mock_file_monitor):
        """测试删除目录"""
        with patch('backend.api.api.get_config_loader', return_value=mock_config_loader):
            with patch('backend.api.api.get_file_monitor', return_value=mock_file_monitor):
                with patch('os.path.abspath', return_value="/test/path"):
                    response = client.request("DELETE", "/api/directories", json={"path": "/test/path"})
                    assert response.status_code == 200
                    assert response.json()["status"] == "success"


class TestPathSecurity:
    """路径安全测试"""

    def test_is_path_allowed_valid(self):
        """测试有效路径"""
        from backend.api.api import is_path_allowed
        config = Mock()
        config.get.return_value = "/allowed/path"
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.abspath', side_effect=lambda x: x):
                result = is_path_allowed("/allowed/path/file.txt", config)
                assert result == True

    def test_is_path_allowed_traversal(self):
        """测试路径遍历攻击"""
        from backend.api.api import is_path_allowed
        config = Mock()
        result = is_path_allowed("../../../etc/passwd", config)
        assert result == False

    def test_is_path_allowed_empty(self):
        """测试空路径"""
        from backend.api.api import is_path_allowed
        config = Mock()
        result = is_path_allowed("", config)
        assert result == False

    def test_is_path_allowed_double_slash(self):
        """测试双斜杠路径"""
        from backend.api.api import is_path_allowed
        config = Mock()
        result = is_path_allowed("//etc/passwd", config)
        assert result == False


class TestRootEndpoint:
    """根端点测试"""

    def test_root_success(self, client):
        """测试根端点"""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.read_text', return_value="<html>Test</html>"):
                response = client.get("/")
                assert response.status_code == 200
                assert "<html>" in response.text

    def test_root_no_frontend(self, client):
        """测试无前端文件"""
        with patch('pathlib.Path.exists', return_value=False):
            response = client.get("/")
            assert response.status_code == 200
            assert "message" in response.json()


class TestFaviconEndpoint:
    """Favicon端点测试"""

    def test_favicon_exists(self, client):
        """测试favicon存在"""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.read_bytes', return_value=b"fake_icon_data"):
                response = client.get("/favicon.ico")
                assert response.status_code == 200

    def test_favicon_not_exists(self, client):
        """测试favicon不存在"""
        with patch('pathlib.Path.exists', return_value=False):
            response = client.get("/favicon.ico")
            assert response.status_code == 204


class TestModelTestEndpoint:
    """模型测试端点测试"""

    def test_test_model_connection_success(self, client):
        """测试模型连接成功"""
        with patch('backend.core.model_manager.ModelManager') as mock_mm:
            mock_instance = Mock()
            mock_instance.test_connection.return_value = {"status": "ok"}
            mock_mm.return_value = mock_instance
            with patch('backend.api.api.get_config_loader', return_value=Mock()):
                response = client.get("/api/model/test")
                assert response.status_code == 200

    def test_test_model_connection_error(self, client):
        """测试模型连接失败"""
        with patch('backend.core.model_manager.ModelManager') as mock_mm:
            mock_mm.side_effect = Exception("Connection failed")
            with patch('backend.api.api.get_config_loader', return_value=Mock()):
                response = client.get("/api/model/test")
                assert response.status_code == 200
                assert response.json()["status"] == "error"


# 保留原有的导入测试
if __name__ == "__main__":
    print("测试Web API初始化...")

    try:
        from backend.utils.config_loader import ConfigLoader
        print("[OK] ConfigLoader导入成功")

        from backend.utils.logger import get_logger
        logger = get_logger(__name__)
        print("[OK] Logger导入和初始化成功")

        import backend.api.api
        print("[OK] Web API模块导入成功")

        from backend.api.api import app
        print("[OK] App导入成功")

        print("\n所有组件加载成功!")
        print("运行命令: python -m uvicorn backend.api.api:app --host 127.0.0.1 --port 8000")

    except ImportError as e:
        print(f"[错误] 导入错误: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"[错误] 其他错误: {e}")
        import traceback
        traceback.print_exc()
