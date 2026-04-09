#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web API 端点测试
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api import dependencies

# 导入 app 和依赖注入函数
from backend.api.main import RateLimiter, app


# 创建 mock 配置实例
def mock_get(section, key=None, default=None):
    defaults = {
        ("system", "data_dir"): "./data",
        ("system", "log_level"): "INFO",
        ("system", "log_max_size"): "10485760",
        ("system", "log_backup_count"): "5",
        ("file_scanner", "scan_paths"): ["/test"],
        ("monitor", "directories"): [],
        ("monitor", "enabled"): False,
    }
    if key is None:
        # 返回整个 section
        sections = {
            "system": {
                "data_dir": "./data",
                "log_level": "INFO",
                "log_max_size": "10485760",
                "log_backup_count": "5",
            },
            "file_scanner": {"scan_paths": ["/test"]},
            "monitor": {"enabled": False, "directories": []},
        }
        return sections.get(section, default or {})
    return defaults.get((section, key), default)


mock_config_instance = Mock()
mock_config_instance.get.side_effect = mock_get
mock_config_instance.getboolean.return_value = False
mock_config_instance.getint.return_value = 100
mock_config_instance.getfloat.return_value = 0.5


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


@pytest.fixture
def dependency_override():
    """Fixture that provides dependency override and cleanup"""
    # 保存原始依赖覆盖
    original_overrides = app.dependency_overrides.copy()

    yield app.dependency_overrides

    # 清理：恢复原始依赖覆盖
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


class TestHealthEndpoint:
    """健康检查端点测试"""

    def test_health_check_healthy(self, client):
        """测试健康检查 - 健康状态"""
        app.state.initialized = True
        response = client.get("/api/health")
        assert response.status_code == 200, "健康检查应返回 HTTP 200"
        assert response.json()["status"] == "healthy", "初始化后状态应为 healthy"

    def test_health_check_starting(self, client):
        """测试健康检查 - 未初始化状态"""
        app.state.initialized = False
        response = client.get("/api/health")
        assert response.status_code == 200, "健康检查应返回 HTTP 200"
        assert response.json()["initialized"] is False, "initialized 应为 False"


class TestRateLimiter:
    """限流器测试"""

    def test_rate_limiter_init(self):
        """测试限流器初始化"""
        limiter = RateLimiter(max_entries=100)
        assert limiter._max_entries == 100, "max_entries 应该设置为 100"
        assert limiter._requests == {}, "初始化时请求记录应为空"

    def test_rate_limiter_allow_first_request(self):
        """测试首次请求允许"""
        limiter = RateLimiter()
        is_allowed = limiter.is_allowed("test_key", max_requests=10, window=60)
        assert is_allowed is True, "首次请求应该被允许"

    def test_rate_limiter_block_excess(self):
        """测试超出限制阻止"""
        limiter = RateLimiter()
        for i in range(5):
            limiter.is_allowed("test_key", max_requests=3, window=60)
        is_allowed = limiter.is_allowed("test_key", max_requests=3, window=60)
        assert is_allowed is False, "超出限制的请求应该被阻止"

    def test_rate_limiter_different_keys(self):
        """测试不同key独立计数"""
        limiter = RateLimiter()
        limiter.is_allowed("key1", max_requests=1, window=60)
        is_allowed_key2 = limiter.is_allowed("key2", max_requests=1, window=60)
        assert is_allowed_key2 is True, "不同 key 应该独立计数"

    def test_rate_limiter_cleanup_expired(self):
        """测试过期清理"""
        limiter = RateLimiter()
        limiter._requests["old_key"] = [0]
        limiter._last_cleanup = 0
        limiter.is_allowed("new_key", max_requests=10, window=1)
        assert "old_key" not in limiter._requests, "过期的 key 应该被清理"

    def test_rate_limiter_emergency_cleanup(self):
        """测试紧急清理"""
        limiter = RateLimiter(max_entries=4)
        for i in range(4):
            limiter.is_allowed(f"key{i}", max_requests=10, window=60)
        limiter.is_allowed("new_key", max_requests=10, window=60)
        assert len(limiter._requests) <= 3, "紧急清理后应只剩一半条目"


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
                "snippet": "Test content",
            }
        ]
        return engine

    def test_search_success(self, client, mock_search_engine, dependency_override):
        """测试成功搜索"""
        # 创建专门用于搜索测试的 mock config，使用系统临时目录（跨平台）
        import tempfile

        from tests.factories import MockConfigFactory

        temp_dir = tempfile.gettempdir()
        search_config = MockConfigFactory.create_config(
            {"file_scanner": {"scan_paths": [temp_dir]}}
        )

        # 配置 mock 返回临时目录下的路径（通过 is_path_allowed 检查）
        import os

        tmp_file = os.path.join(temp_dir, "doc1.txt")
        mock_search_engine.search.return_value = [
            {
                "path": tmp_file,
                "filename": "doc1.txt",
                "content": "Test content",
                "score": 0.9,
                "file_type": "txt",
                "highlights": ["Test"],
            }
        ]

        dependency_override[dependencies.get_search_engine] = lambda: mock_search_engine
        dependency_override[dependencies.get_config_loader] = lambda: search_config
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post("/api/search", json={"query": "test", "filters": {}})
        assert response.status_code == 200, "搜索成功应返回 HTTP 200"
        results = response.json()
        assert len(results) > 0, "搜索结果不应为空"
        assert results[0]["file_name"] == "doc1.txt", "第一个结果文件名应为 doc1.txt"

    def test_search_empty_query(self, client, mock_search_engine, dependency_override):
        """测试空查询"""
        dependency_override[dependencies.get_search_engine] = lambda: mock_search_engine
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post("/api/search", json={"query": "", "filters": {}})
        assert response.status_code == 400, "空查询应返回 HTTP 400"
        assert "不能为空" in response.json()["detail"], "错误消息应包含'不能为空'"

    def test_search_no_query_field(self, client, dependency_override):
        """测试缺少query字段 - FastAPI会返回422验证错误"""
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post("/api/search", json={"filters": {}})
        # FastAPI validation error for missing required field
        assert response.status_code == 422, "缺少 query 字段应返回 HTTP 422"

    def test_search_rate_limited(self, client, mock_search_engine, dependency_override):
        """测试搜索限流"""
        limiter = Mock()
        limiter.is_allowed.return_value = False

        mock_config = Mock()
        mock_config.getboolean.return_value = True

        dependency_override[dependencies.get_search_engine] = lambda: mock_search_engine
        dependency_override[dependencies.get_rate_limiter] = lambda: limiter
        dependency_override[dependencies.get_config_loader] = lambda: mock_config

        response = client.post("/api/search", json={"query": "test"})
        assert response.status_code == 429, "限流时应返回 HTTP 429"


class TestChatEndpoint:
    """聊天端点测试"""

    @pytest.fixture
    def mock_rag_pipeline(self):
        """创建模拟RAG管道"""
        pipeline = Mock()
        pipeline.query.return_value = {
            "answer": "Test answer",
            "sources": [{"path": "/test/doc.txt", "content": "Test content"}],
        }
        return pipeline

    def test_chat_success(self, client, mock_rag_pipeline, dependency_override):
        """测试成功聊天"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post(
            "/api/chat", json={"query": "Hello", "session_id": "test123"}
        )
        assert response.status_code == 200, "聊天成功应返回 HTTP 200"
        result = response.json()
        assert result["answer"] == "Test answer", "回答内容应与 mock 一致"

    def test_chat_empty_query(self, client, mock_rag_pipeline, dependency_override):
        """测试空查询"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post("/api/chat", json={"query": ""})
        assert response.status_code == 400, "空查询应返回 HTTP 400"

    def test_chat_disabled(self, client, dependency_override):
        """测试AI功能未启用"""
        mock_config = Mock()
        mock_config.getboolean.return_value = False

        dependency_override[dependencies.get_rag_pipeline] = lambda: None
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()
        dependency_override[dependencies.get_config_loader] = lambda: mock_config

        response = client.post("/api/chat", json={"query": "Hello"})
        assert response.status_code == 200, "AI 未启用时应优雅降级"
        assert "未启用" in response.json()["answer"], "应提示功能未启用"

    def test_chat_no_session_id(self, client, mock_rag_pipeline, dependency_override):
        """测试无session_id"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()

        response = client.post("/api/chat", json={"query": "Hello"})
        assert response.status_code == 200, "无 session_id 应自动创建新会话"


class TestSessionsEndpoint:
    """会话端点测试"""

    @pytest.fixture
    def mock_rag_pipeline(self):
        """创建模拟RAG管道"""
        pipeline = Mock()
        pipeline.get_all_sessions.return_value = [
            {"session_id": "sess1", "title": "Session 1"},
            {"session_id": "sess2", "title": "Session 2"},
        ]
        pipeline.clear_session.return_value = True
        pipeline.chat_db.get_session_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        return pipeline

    def test_get_sessions_success(self, client, mock_rag_pipeline, dependency_override):
        """测试获取会话列表"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline

        response = client.get("/api/sessions")
        assert response.status_code == 200, "获取会话列表应返回 HTTP 200"
        sessions = response.json()["sessions"]
        assert len(sessions) == 2, "应返回 2 个会话"

    def test_get_sessions_no_rag(self, client, dependency_override):
        """测试无RAG时获取会话"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: None

        response = client.get("/api/sessions")
        assert response.status_code == 200, "无 RAG 时应返回空列表"
        assert response.json()["sessions"] == [], "sessions 应为空列表"

    def test_delete_session_success(
        self, client, mock_rag_pipeline, dependency_override
    ):
        """测试删除会话"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline

        response = client.delete("/api/sessions/test_session")
        assert response.status_code == 200, "删除会话应返回 HTTP 200"
        assert response.json()["status"] == "success", "删除状态应为 success"

    def test_delete_session_not_found(
        self, client, mock_rag_pipeline, dependency_override
    ):
        """测试删除不存在的会话"""
        mock_rag_pipeline.clear_session.return_value = False
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline

        response = client.delete("/api/sessions/nonexistent")
        assert response.status_code == 404, "删除不存在的会话应返回 HTTP 404"

    def test_delete_session_no_rag(self, client, dependency_override):
        """测试无RAG时删除会话"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: None

        response = client.delete("/api/sessions/test")
        assert response.status_code == 500, "无 RAG 时删除应返回 HTTP 500"

    def test_get_session_messages_success(
        self, client, mock_rag_pipeline, dependency_override
    ):
        """测试获取会话消息"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: mock_rag_pipeline

        response = client.get("/api/sessions/test_session/messages")
        assert response.status_code == 200, "获取消息应返回 HTTP 200"
        messages = response.json()["messages"]
        assert len(messages) == 2, "应返回 2 条消息"

    def test_get_session_messages_no_rag(self, client, dependency_override):
        """测试无RAG时获取消息"""
        dependency_override[dependencies.get_rag_pipeline] = lambda: None

        response = client.get("/api/sessions/test/messages")
        assert response.status_code == 500, "无 RAG 时获取消息应返回 HTTP 500"


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

    def test_get_config_success(self, client, mock_config_loader, dependency_override):
        """测试获取配置"""
        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader

        response = client.get("/api/config")
        assert response.status_code == 200, "获取配置应返回 HTTP 200"
        config = response.json()
        assert "ai_model" in config, "配置应包含 ai_model 节"
        assert config["ai_model"]["enabled"], "ai_model.enabled 应为 true"

    def test_update_config_success(
        self, client, mock_config_loader, dependency_override
    ):
        """测试更新配置"""
        mock_config_loader.save.return_value = True
        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader

        response = client.post("/api/config", json={"ai_model": {"enabled": True}})
        assert response.status_code == 200, "更新配置应返回 HTTP 200"
        assert response.json()["status"] == "success", "更新状态应为 success"

    def test_update_config_invalid_data(
        self, client, mock_config_loader, dependency_override
    ):
        """测试无效配置数据"""
        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader

        response = client.post("/api/config", json="not a dict")
        assert response.status_code == 400, "无效配置数据应返回 HTTP 400"

    def test_update_config_empty_sections(
        self, client, mock_config_loader, dependency_override
    ):
        """测试空配置节"""
        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader

        response = client.post("/api/config", json={"unknown_section": {}})
        assert response.status_code == 200, "空配置节应被接受"
        assert response.json()["status"] == "warning", "未知节应返回警告状态"


class TestPreviewEndpoint:
    """文件预览端点测试"""

    @pytest.fixture
    def mock_index_manager(self):
        """创建模拟索引管理器"""
        manager = Mock()
        manager.get_document_content.return_value = "Test document content"
        return manager

    def test_preview_success(self, client, dependency_override):
        """测试成功预览"""
        # Create mock index manager that returns content for get_document_content
        mock_index_manager = Mock()
        mock_index_manager.get_document_content.return_value = "Test document content"

        mock_config = Mock()
        mock_config.get.return_value = "/test"
        mock_config.getboolean.return_value = False
        mock_config.getint.return_value = 5242880  # 5MB

        # Create a mock Path class that returns chainable mock objects
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = False
        mock_path_instance.is_symlink.return_value = False
        mock_path_instance.stat.return_value.st_size = 100
        mock_path_instance.resolve.return_value = mock_path_instance  # chainable
        mock_path_instance.name = "file.txt"

        def mock_resolve_path(path_str, config):
            return mock_path_instance

        # Override all dependencies
        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager
        dependency_override[dependencies.get_config_loader] = lambda: mock_config
        dependency_override[dependencies.get_is_path_allowed] = lambda: (
            lambda path, config: True
        )
        dependency_override[dependencies.get_resolve_path_if_allowed] = lambda: (
            mock_resolve_path
        )

        # Patch Path in the search module and safe_read_file
        with (
            patch(
                "backend.api.routes.search.safe_read_file",
                return_value="Test document content",
            ),
        ):
            response = client.post("/api/preview", json={"path": "/test/file.txt"})
            assert response.status_code == 200, "预览成功应返回 HTTP 200"
            assert "content" in response.json(), "响应应包含 content 字段"

    def test_preview_empty_path(self, client):
        """测试空路径"""
        response = client.post("/api/preview", json={"path": ""})
        assert response.status_code == 400, "空路径应返回 HTTP 400"
        assert "error" in response.json()["detail"], "空路径应返回错误信息"

    def test_preview_path_not_allowed(
        self, client, mock_index_manager, dependency_override
    ):
        """测试不允许的路径"""
        mock_config = Mock()
        mock_config.get.return_value = "/test/path"
        mock_config.getboolean.return_value = False

        def mock_resolve_path_none(path_str, config):
            return None

        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager
        dependency_override[dependencies.get_config_loader] = lambda: mock_config
        dependency_override[dependencies.get_is_path_allowed] = lambda: (
            lambda path, config: False
        )
        dependency_override[dependencies.get_resolve_path_if_allowed] = lambda: (
            mock_resolve_path_none
        )

        response = client.post("/api/preview", json={"path": "/etc/passwd"})
        assert response.status_code == 403, "不允许的路径应返回 HTTP 403"

    def test_preview_file_not_found(
        self, client, mock_index_manager, dependency_override
    ):
        """测试文件不存在"""
        mock_config = Mock()
        mock_config.get.return_value = "/test/path"

        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_instance.is_dir.return_value = False

        def mock_resolve_path(path_str, config):
            return mock_path_instance

        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager
        dependency_override[dependencies.get_config_loader] = lambda: mock_config
        dependency_override[dependencies.get_is_path_allowed] = lambda: (
            lambda path, config: True
        )
        dependency_override[dependencies.get_resolve_path_if_allowed] = lambda: (
            mock_resolve_path
        )

        response = client.post("/api/preview", json={"path": "/test/nonexistent.txt"})
        assert response.status_code == 404, "文件不存在应返回 HTTP 404"


class TestRebuildIndexEndpoint:
    """重建索引端点测试"""

    @pytest.fixture
    def mock_file_scanner(self):
        """创建模拟文件扫描器"""
        scanner = Mock()
        scanner.scan_and_index.return_value = {
            "total_files_scanned": 100,
            "total_files_indexed": 50,
        }
        scanner.scan_paths = ["/test/path"]
        return scanner

    @pytest.fixture
    def mock_index_manager(self):
        """创建模拟索引管理器"""
        manager = Mock()
        manager.rebuild_index.return_value = True
        return manager

    def test_rebuild_index_success(
        self, client, mock_file_scanner, mock_index_manager, dependency_override
    ):
        """测试成功重建索引"""
        mock_config = Mock()
        mock_config.getboolean.return_value = False

        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner
        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager
        dependency_override[dependencies.get_rate_limiter] = lambda: RateLimiter()
        dependency_override[dependencies.get_config_loader] = lambda: mock_config

        response = client.post("/api/rebuild-index")
        assert response.status_code == 200, "重建索引成功应返回 HTTP 200"
        result = response.json()
        assert result["status"] == "success", "状态应为 success"
        assert result["files_scanned"] == 100, "应扫描 100 个文件"

    def test_rebuild_index_rate_limited(
        self, client, mock_file_scanner, mock_index_manager, dependency_override
    ):
        """测试重建索引限流"""
        limiter = Mock()
        limiter.is_allowed.return_value = False

        mock_config = Mock()
        mock_config.getboolean.return_value = True

        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner
        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager
        dependency_override[dependencies.get_rate_limiter] = lambda: limiter
        dependency_override[dependencies.get_config_loader] = lambda: mock_config

        response = client.post("/api/rebuild-index")
        assert response.status_code == 429, "限流时应返回 HTTP 429"


class TestDirectoryEndpoints:
    """目录管理端点测试"""

    @pytest.fixture
    def mock_config_loader(self):
        """创建模拟配置加载器 - 使用工厂创建以支持
        set/add_scan_path/remove_scan_path 方法"""
        from tests.factories import MockConfigFactory

        return MockConfigFactory.create_config(
            {
                "file_scanner": {"scan_paths": ["/test/path1", "/test/path2"]},
                "monitor": {"directories": ["/test/path1", "/test/path2"]},
            }
        )

    @pytest.fixture
    def mock_file_monitor(self):
        """创建模拟文件监控器"""
        monitor = Mock()
        monitor.get_monitored_directories.return_value = ["/test/path1"]
        return monitor

    def test_get_directories_success(
        self, client, mock_config_loader, mock_file_monitor, dependency_override
    ):
        """测试获取目录列表"""
        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader
        dependency_override[dependencies.get_file_monitor] = lambda: mock_file_monitor

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=True),
        ):
            response = client.get("/api/directories")
            assert response.status_code == 200, "获取目录列表应返回 HTTP 200"
            directories = response.json()["directories"]
            assert len(directories) >= 1, "应至少返回 1 个目录"

    def test_add_directory_success(
        self, client, mock_config_loader, mock_file_monitor, dependency_override
    ):
        """测试添加目录"""
        mock_file_scanner = Mock()

        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader
        dependency_override[dependencies.get_file_monitor] = lambda: mock_file_monitor
        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=True),
            patch("os.path.abspath", return_value="/new/path"),
        ):
            response = client.post("/api/directories", json={"path": "/new/path"})
            assert response.status_code == 200, "添加目录应返回 HTTP 200"
            assert response.json()["status"] == "success", "状态应为 success"

    def test_add_directory_not_exist(
        self, client, mock_config_loader, mock_file_monitor, dependency_override
    ):
        """测试添加不存在的目录"""
        mock_file_scanner = Mock()

        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader
        dependency_override[dependencies.get_file_monitor] = lambda: mock_file_monitor
        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner

        with patch("os.path.exists", return_value=False):
            response = client.post("/api/directories", json={"path": "/nonexistent"})
            assert response.status_code == 400, "添加不存在目录应返回 HTTP 400"

    def test_add_directory_not_directory(
        self, client, mock_config_loader, mock_file_monitor, dependency_override
    ):
        """测试添加非目录路径"""
        mock_file_scanner = Mock()

        dependency_override[dependencies.get_config_loader] = lambda: mock_config_loader
        dependency_override[dependencies.get_file_monitor] = lambda: mock_file_monitor
        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=False),
        ):
            response = client.post("/api/directories", json={"path": "/test/file.txt"})
            assert response.status_code == 400, "添加非目录路径应返回 HTTP 400"

    def test_remove_directory_success(self, client, dependency_override):
        """测试删除目录"""
        mock_file_scanner = Mock()
        mock_file_scanner.scan_paths = ["/test/path"]  # 设置 scan_paths 属性
        mock_index_manager = Mock()
        mock_file_monitor = Mock()
        mock_file_monitor.get_monitored_directories.return_value = ["/test/path"]

        # 创建包含 /test/path 路径的配置
        from tests.factories import MockConfigFactory

        test_config = MockConfigFactory.create_config(
            {
                "file_scanner": {"scan_paths": ["/test/path"]},
                "monitor": {"directories": ["/test/path"]},
            }
        )

        dependency_override[dependencies.get_config_loader] = lambda: test_config
        dependency_override[dependencies.get_file_monitor] = lambda: mock_file_monitor
        dependency_override[dependencies.get_file_scanner] = lambda: mock_file_scanner
        dependency_override[dependencies.get_index_manager] = lambda: mock_index_manager

        with patch("os.path.abspath", return_value="/test/path"):
            response = client.request(
                "DELETE", "/api/directories", json={"path": "/test/path"}
            )
            assert response.status_code == 200, "删除目录应返回 HTTP 200"
            assert response.json()["status"] == "success", "状态应为 success"


class TestPathSecurity:
    """路径安全测试"""

    def test_is_path_allowed_valid(self):
        """测试有效路径"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        config.get.return_value = "/allowed/path"

        with patch.object(Path, "resolve", return_value=Path("/allowed/path/file.txt")):
            with patch.object(Path, "is_symlink", return_value=False):
                with patch.object(Path, "exists", return_value=True):
                    with patch.object(Path, "is_dir", return_value=True):
                        result = is_path_allowed("/allowed/path/file.txt", config)
                        assert result is True, "有效路径应该被允许"

    def test_is_path_allowed_traversal(self):
        """测试路径遍历攻击"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("../../../etc/passwd", config)
        assert result is False, "路径遍历攻击应被阻止"

    def test_is_path_allowed_empty(self):
        """测试空路径"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("", config)
        assert result is False, "空路径应被拒绝"

    def test_is_path_allowed_double_slash(self):
        """测试双斜杠路径"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("//etc/passwd", config)
        assert result is False, "双斜杠路径应被阻止"

    def test_is_path_allowed_null_byte(self):
        """测试空字节注入攻击"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("/allowed/path/file\x00.txt", config)
        assert result is False, "空字节注入应被阻止"

    def test_is_path_allowed_url_encoded_traversal(self):
        """测试URL编码的路径遍历攻击"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("/allowed/path/%2e%2e/%2e%2e/etc/passwd", config)
        assert result is False, "URL编码的路径遍历应被阻止"

    def test_is_path_allowed_double_url_encoded(self):
        """测试双重URL编码的路径遍历攻击"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("/allowed/path/%252e%252e/etc/passwd", config)
        assert result is False, "双重URL编码的路径遍历应被阻止"

    def test_is_path_allowed_dotdot_in_middle(self):
        """测试路径中间的 .. 遍历"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed("/allowed/path/../secret/file.txt", config)
        assert result is False, "路径中间的 .. 遍历应被阻止"

    def test_is_path_allowed_none_path(self):
        """测试None路径"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed(None, config)  # type: ignore[arg-type]
        assert result is False, "None 路径应被拒绝"

    def test_is_path_allowed_non_string_path(self):
        """测试非字符串路径"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        result = is_path_allowed(12345, config)  # type: ignore[arg-type]
        assert result is False, "非字符串路径应被拒绝"

    def test_is_path_allowed_no_scan_paths_configured(self):
        """测试未配置扫描路径时拒绝所有访问"""
        from backend.api.dependencies import is_path_allowed

        config = Mock()
        config.get.return_value = ""
        result = is_path_allowed("/some/path/file.txt", config)
        assert result is False, "未配置扫描路径时应拒绝所有访问"


class TestRootEndpoint:
    """根端点测试"""

    def test_root_success(self, client):
        """测试根端点"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="<html>Test</html>"):
                response = client.get("/")
                assert response.status_code == 200, "根端点应返回 HTTP 200"
                assert "<html>" in response.text, "响应应包含 HTML 内容"

    def test_root_no_frontend(self, client):
        """测试无前端文件"""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/")
            assert response.status_code == 200, "无前端时应优雅降级"
            assert "message" in response.json(), "响应应包含 message 字段"


class TestFaviconEndpoint:
    """Favicon端点测试"""

    def test_favicon_exists(self, client):
        """测试favicon存在"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_bytes", return_value=b"fake_icon_data"):
                response = client.get("/favicon.ico")
                assert response.status_code == 200, "favicon 存在时应返回 HTTP 200"

    def test_favicon_not_exists(self, client):
        """测试favicon不存在"""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/favicon.ico")
            assert response.status_code == 204, "favicon 不存在时应返回 HTTP 204"


class TestModelTestEndpoint:
    """模型测试端点测试"""

    def test_test_model_connection_success(self, client):
        """测试模型连接成功"""
        with patch("backend.core.model_manager.ModelManager") as mock_mm:
            mock_instance = Mock()
            mock_instance.test_connection.return_value = {"status": "ok"}
            mock_mm.return_value = mock_instance
            with patch(
                "backend.api.dependencies.get_config_loader", return_value=Mock()
            ):
                response = client.get("/api/model/test")
                assert response.status_code == 200, "模型连接成功应返回 HTTP 200"

    def test_test_model_connection_error(self, client):
        """测试模型连接失败"""
        with patch("backend.core.model_manager.ModelManager") as mock_mm:
            mock_mm.side_effect = Exception("Connection failed")
            with patch(
                "backend.api.dependencies.get_config_loader", return_value=Mock()
            ):
                response = client.get("/api/model/test")
                assert response.status_code == 200, "连接失败时应优雅降级"
                assert response.json()["status"] == "error", "应返回 error 状态"


if __name__ == "__main__":
    print("测试Web API初始化...")

    try:
        import importlib.util

        if importlib.util.find_spec("backend.utils.config_loader"):
            print("[OK] ConfigLoader导入成功")
        else:
            print("[FAIL] ConfigLoader模块未找到")

        from backend.utils.logger import get_logger

        logger = get_logger(__name__)
        print("[OK] Logger导入和初始化成功")

        if importlib.util.find_spec("backend.api"):
            print("[OK] Web API模块导入成功")
        else:
            print("[FAIL] Web API模块未找到")

        from backend.api.main import app

        print("[OK] App导入成功")

        print("\n所有组件加载成功!")
        print(
            "运行命令: python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000"
        )

    except ImportError as e:
        print(f"[错误] 导入错误: {e}")
        import traceback

        traceback.print_exc()
    except Exception as e:
        print(f"[错误] 其他错误: {e}")
        import traceback

        traceback.print_exc()
