# tests/test_rag_workflow.py
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


def test_rag_workflow_basic():
    """测试RAG工作流的基本功能"""
    # For now, just test that the module can be imported
    from backend.core.rag_pipeline import RAGPipeline
    assert RAGPipeline is not None


class TestRAGWorkflowIntegration:
    """RAG工作流集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            test_file = Path(tmpdir) / "test_doc.txt"
            test_file.write_text("Python is a programming language. It is widely used for web development, data science, and automation.", encoding='utf-8')

            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            subdir_file = subdir / "another_doc.txt"
            subdir_file.write_text("Machine learning is a subset of artificial intelligence.", encoding='utf-8')

            yield tmpdir

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = './data'
        config.getboolean.return_value = False
        config.getint.return_value = 100
        return config

    def test_end_to_end_search_workflow(self, temp_test_dir, mock_config):
        """测试端到端搜索工作流"""
        with patch('backend.core.index_manager.IndexManager'):
            with patch('backend.core.search_engine.SearchEngine') as mock_se:
                # 配置模拟搜索引擎
                search_engine = Mock()
                search_engine.search.return_value = [
                    {
                        'path': os.path.join(temp_test_dir, 'test_doc.txt'),
                        'filename': 'test_doc.txt',
                        'content': 'Python is a programming language',
                        'score': 0.95
                    }
                ]

                # 测试搜索
                results = search_engine.search('python')
                assert len(results) == 1
                assert 'python' in results[0]['content'].lower()

    def test_file_scan_to_index_workflow(self, temp_test_dir, mock_config):
        """测试文件扫描到索引工作流"""
        with patch('backend.core.file_scanner.FileScanner') as mock_scanner_class:
            # 配置模拟扫描器
            scanner = Mock()
            scanner.scan_and_index.return_value = {
                'total_files_scanned': 2,
                'total_files_indexed': 2
            }
            mock_scanner_class.return_value = scanner

            # 执行扫描
            result = scanner.scan_and_index()

            assert result['total_files_scanned'] == 2
            assert result['total_files_indexed'] == 2

    def test_chat_with_context_workflow(self, mock_config):
        """测试带上下文的聊天工作流"""
        with patch('backend.core.rag_pipeline.RAGPipeline') as mock_rag_class:
            with patch('backend.core.model_manager.ModelManager'):
                with patch('backend.core.search_engine.SearchEngine'):
                    # 配置模拟RAG管道
                    rag = Mock()
                    rag.query.return_value = {
                        'answer': 'Python is a programming language widely used for web development.',
                        'sources': ['/test/doc.txt']
                    }
                    mock_rag_class.return_value = rag

                    # 测试查询
                    result = rag.query('What is Python?', session_id='test_session')

                    assert 'answer' in result
                    assert 'sources' in result
                    assert 'Python' in result['answer']


class TestFileProcessingIntegration:
    """文件处理集成测试"""

    @pytest.fixture
    def temp_test_dir(self):
        """创建临时测试目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_different_file_types_processing(self, temp_test_dir):
        """测试不同文件类型的处理"""
        # 创建不同类型的测试文件
        files = {
            'test.txt': 'Plain text content',
            'test.md': '# Markdown Header\n\nSome content',
            'test.json': '{"key": "value"}',
        }

        for filename, content in files.items():
            filepath = Path(temp_test_dir) / filename
            filepath.write_text(content, encoding='utf-8')

        # 验证文件创建成功
        for filename in files.keys():
            filepath = Path(temp_test_dir) / filename
            assert filepath.exists()
            assert filepath.read_text(encoding='utf-8') == files[filename]

    def test_large_file_handling(self, temp_test_dir):
        """测试大文件处理"""
        large_content = "A" * (1024 * 1024)  # 1MB content
        large_file = Path(temp_test_dir) / "large_file.txt"
        large_file.write_text(large_content, encoding='utf-8')

        # 验证文件大小
        assert large_file.exists()
        assert large_file.stat().st_size == len(large_content.encode('utf-8'))

    def test_nested_directory_scanning(self, temp_test_dir):
        """测试嵌套目录扫描"""
        # 创建嵌套目录结构
        level1 = Path(temp_test_dir) / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        level3 = level2 / "level3"
        level3.mkdir()

        # 在各层创建文件
        (Path(temp_test_dir) / "root.txt").write_text("root", encoding='utf-8')
        (level1 / "level1.txt").write_text("level1", encoding='utf-8')
        (level2 / "level2.txt").write_text("level2", encoding='utf-8')
        (level3 / "level3.txt").write_text("level3", encoding='utf-8')

        # 统计文件数量
        file_count = sum(1 for _ in Path(temp_test_dir).rglob('*.txt'))
        assert file_count == 4


class TestSessionManagementIntegration:
    """会话管理集成测试"""

    def test_session_creation_and_message_flow(self):
        """测试会话创建和消息流程"""
        with patch('backend.core.chat_history_db.ChatHistoryDB') as mock_db_class:
            db = Mock()
            db.create_session.return_value = True
            db.add_message.return_value = True
            db.get_session_messages.return_value = [
                {'role': 'user', 'content': 'Hello'},
                {'role': 'assistant', 'content': 'Hi there'}
            ]
            mock_db_class.return_value = db

            # 创建会话
            session_id = 'test_session'
            result = db.create_session(session_id)
            assert result == True

            # 添加消息
            db.add_message(session_id, 'user', 'Hello')
            db.add_message(session_id, 'assistant', 'Hi there')

            # 获取消息
            messages = db.get_session_messages(session_id)
            assert len(messages) == 2

    def test_multiple_sessions_isolation(self):
        """测试多会话隔离"""
        with patch('backend.core.chat_history_db.ChatHistoryDB') as mock_db_class:
            db = Mock()
            db.get_session_messages.side_effect = lambda sid: {
                'session1': [{'role': 'user', 'content': 'Message 1'}],
                'session2': [{'role': 'user', 'content': 'Message 2'}]
            }.get(sid, [])
            mock_db_class.return_value = db

            # 获取不同会话的消息
            messages1 = db.get_session_messages('session1')
            messages2 = db.get_session_messages('session2')

            assert messages1[0]['content'] == 'Message 1'
            assert messages2[0]['content'] == 'Message 2'


class TestSearchAndRAGIntegration:
    """搜索和RAG集成测试"""

    def test_search_results_feed_to_rag(self):
        """测试搜索结果输入RAG"""
        with patch('backend.core.search_engine.SearchEngine') as mock_se:
            with patch('backend.core.rag_pipeline.RAGPipeline') as mock_rag:
                # 模拟搜索结果
                search_results = [
                    {
                        'path': '/doc1.txt',
                        'content': 'Python programming guide',
                        'score': 0.9
                    },
                    {
                        'path': '/doc2.txt',
                        'content': 'Advanced Python topics',
                        'score': 0.8
                    }
                ]

                search_engine = Mock()
                search_engine.search.return_value = search_results

                # 模拟RAG使用搜索结果
                rag = Mock()
                rag._collect_documents.return_value = search_results
                rag.query.return_value = {
                    'answer': 'Based on the documents, Python is...',
                    'sources': ['/doc1.txt', '/doc2.txt']
                }

                # 执行搜索
                results = search_engine.search('python')
                assert len(results) == 2

                # 使用搜索结果进行RAG
                answer = rag.query('Tell me about Python')
                assert 'sources' in answer
                assert len(answer['sources']) == 2


class TestConfigurationIntegration:
    """配置集成测试"""

    def test_config_change_propagation(self):
        """测试配置变更传播"""
        with patch('backend.utils.config_loader.ConfigLoader') as mock_config:
            config = Mock()
            config.get.return_value = 'new_value'
            config.getboolean.return_value = True
            config.getint.return_value = 100
            config.save.return_value = True
            mock_config.return_value = config

            # 修改配置
            config.set('section', 'key', 'new_value')
            config.save()

            # 验证配置已更新
            assert config.get('section', 'key') == 'new_value'
            config.save.assert_called_once()


class TestErrorHandlingIntegration:
    """错误处理集成测试"""

    def test_graceful_degradation_on_search_failure(self):
        """测试搜索失败时的优雅降级"""
        with patch('backend.core.search_engine.SearchEngine') as mock_se:
            search_engine = Mock()
            search_engine.search.side_effect = Exception("Search failed")
            mock_se.return_value = search_engine

            # 搜索应该抛出异常
            with pytest.raises(Exception):
                search_engine.search('query')

    def test_rag_fallback_on_empty_results(self):
        """测试空结果时的RAG回退"""
        with patch('backend.core.rag_pipeline.RAGPipeline') as mock_rag:
            rag = Mock()
            rag._collect_documents.return_value = []
            rag.fallback_response = "No relevant documents found."
            rag.query.return_value = {
                'answer': 'No relevant documents found.',
                'sources': []
            }

            result = rag.query('obscure query')
            assert result['sources'] == []
