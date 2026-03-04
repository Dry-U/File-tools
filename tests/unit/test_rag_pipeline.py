"""RAG Pipeline 单元测试"""
import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch
import secrets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.rag_pipeline import RAGPipeline, DEFAULT_PROMPT


class TestRAGPipeline:
    """RAGPipeline 测试类"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = None
        config.getint.return_value = 120
        config.getboolean.return_value = False
        return config

    @pytest.fixture
    def mock_model_manager(self):
        """创建模拟模型管理器"""
        mm = Mock()
        mm.get_model_limits.return_value = {
            'max_docs': 5,
            'chunk_size': 2000,
            'max_context': 4000,
            'max_tokens': 500,
            'temperature': 0.7,
            'min_doc_score': 0.3
        }
        mm.get_mode.return_value = Mock(value='api')
        mm.generate.return_value = iter(["测试", "回答"])
        return mm

    @pytest.fixture
    def mock_search_engine(self):
        """创建模拟搜索引擎"""
        se = Mock()
        se.search.return_value = [
            {
                'path': '/test/doc1.txt',
                'filename': 'doc1.txt',
                'content': '测试文档内容',
                'score': 0.9
            }
        ]
        return se

    @pytest.fixture
    def rag_pipeline(self, mock_model_manager, mock_config, mock_search_engine):
        """创建 RAGPipeline 实例"""
        with patch('backend.core.rag_pipeline.ChatHistoryDB'):
            with patch('backend.core.rag_pipeline.VRAMManager'):
                with patch('backend.core.rag_pipeline.QueryProcessor'):
                    pipeline = RAGPipeline(mock_model_manager, mock_config, mock_search_engine)
                    return pipeline

    def test_init(self, rag_pipeline):
        """测试初始化"""
        assert rag_pipeline.model_manager is not None
        assert rag_pipeline.search_engine is not None
        assert rag_pipeline.max_history_turns == 6
        assert rag_pipeline.max_history_chars == 800

    def test_is_noise_query_empty(self, rag_pipeline):
        """测试空查询检测"""
        assert rag_pipeline._is_noise_query("") == True

    def test_is_noise_query_whitespace(self, rag_pipeline):
        """测试空白查询检测"""
        assert rag_pipeline._is_noise_query("   ") == True

    def test_is_noise_query_single_char(self, rag_pipeline):
        """测试单字符查询检测"""
        assert rag_pipeline._is_noise_query("a") == True

    def test_is_noise_query_repeated_char(self, rag_pipeline):
        """测试重复字符查询检测"""
        assert rag_pipeline._is_noise_query("aa") == True

    def test_is_noise_query_valid(self, rag_pipeline):
        """测试有效查询"""
        assert rag_pipeline._is_noise_query("python") == False

    def test_is_noise_query_chinese(self, rag_pipeline):
        """测试中文查询"""
        assert rag_pipeline._is_noise_query("你好") == False

    def test_strip_tags(self, rag_pipeline):
        """测试标签去除"""
        text = "<p>Hello</p><br>World"
        result = rag_pipeline._strip_tags(text)
        assert "<p>" not in result
        assert "Hello" in result

    def test_strip_tags_nbsp(self, rag_pipeline):
        """测试&nbsp;处理"""
        text = "Hello\xa0World"
        result = rag_pipeline._strip_tags(text)
        assert "\xa0" not in result

    def test_has_query_overlap_exact(self, rag_pipeline):
        """测试精确匹配"""
        assert rag_pipeline._has_query_overlap("python guide", "python") == True

    def test_has_query_overlap_token(self, rag_pipeline):
        """测试token匹配"""
        assert rag_pipeline._has_query_overlap("python_guide", "python guide") == True

    def test_has_query_overlap_no_match(self, rag_pipeline):
        """测试无匹配"""
        assert rag_pipeline._has_query_overlap("java guide", "python") == False

    def test_has_query_overlap_empty(self, rag_pipeline):
        """测试空查询"""
        assert rag_pipeline._has_query_overlap("", "test") == False
        assert rag_pipeline._has_query_overlap("test", "") == False

    def test_render_template(self, rag_pipeline):
        """测试模板渲染"""
        template = "Hello {query}"
        result = rag_pipeline._render_template(template, "World")
        assert result == "Hello World"

    def test_render_template_empty(self, rag_pipeline):
        """测试空模板"""
        result = rag_pipeline._render_template("", "test")
        assert result == ""

    def test_render_template_no_placeholder(self, rag_pipeline):
        """测试无占位符模板"""
        template = "Hello World"
        result = rag_pipeline._render_template(template, "test")
        assert result == "Hello World"

    def test_is_small_talk_greeting(self, rag_pipeline):
        """测试问候语检测"""
        rag_pipeline.greeting_keywords = ['hello', 'hi']
        assert rag_pipeline._is_small_talk("hello") == True

    def test_is_small_talk_normal(self, rag_pipeline):
        """测试正常查询"""
        rag_pipeline.greeting_keywords = ['hello']
        assert rag_pipeline._is_small_talk("python tutorial") == False

    def test_is_small_talk_empty(self, rag_pipeline):
        """测试空查询"""
        assert rag_pipeline._is_small_talk("") == True

    def test_remove_file_extension(self, rag_pipeline):
        """测试文件扩展名移除"""
        assert rag_pipeline._remove_file_extension("test.pdf") == "test"
        assert rag_pipeline._remove_file_extension("test.docx") == "test"
        assert rag_pipeline._remove_file_extension("test") == "test"

    def test_parse_entities_from_filename(self, rag_pipeline):
        """测试文件名实体解析"""
        entities = rag_pipeline._parse_entities_from_filename("author_paper")
        assert "paper" in entities

    def test_parse_entities_from_filename_short(self, rag_pipeline):
        """测试短文件名实体解析"""
        entities = rag_pipeline._parse_entities_from_filename("doc")
        assert "doc" in entities

    def test_format_document_section(self, rag_pipeline):
        """测试文档部分格式化"""
        doc = {
            'filename': 'test.txt',
            'path': '/test/test.txt',
            'score': 0.9,
            'content': 'Test content'
        }
        result = rag_pipeline._format_document_section(doc)
        assert 'test.txt' in result
        assert 'Test content' in result

    def test_calculate_context_budget_none(self, rag_pipeline):
        """测试None预算"""
        result = rag_pipeline._calculate_context_budget(None)
        assert result == rag_pipeline.max_context_chars_total

    def test_calculate_context_budget_value(self, rag_pipeline):
        """测试指定预算"""
        result = rag_pipeline._calculate_context_budget(1000)
        assert result == 1000

    def test_calculate_context_budget_negative(self, rag_pipeline):
        """测试负预算"""
        result = rag_pipeline._calculate_context_budget(-100)
        assert result == 0

    def test_format_prompt_with_template(self, rag_pipeline):
        """测试提示词格式化"""
        context = "Test context"
        query = "Test query"
        result = rag_pipeline._format_prompt_with_template(context, query)
        assert 'Test context' in result
        assert 'Test query' in result

    def test_format_prompt_with_template_invalid(self, rag_pipeline):
        """测试无效模板"""
        rag_pipeline.prompt_template = "Invalid {unknown} template"
        result = rag_pipeline._format_prompt_with_template("context", "query")
        # 应该回退到默认模板
        assert DEFAULT_PROMPT in result or 'context' in result

    def test_remove_repeated_content(self, rag_pipeline):
        """测试重复内容移除"""
        text = "Hello. Hello. World."
        result = rag_pipeline._remove_repeated_content(text)
        # 重复句子应该被移除
        assert result.count("Hello") == 1

    def test_post_process_answer(self, rag_pipeline):
        """测试回答后处理"""
        answer = "1. Point one\n2. Point two"
        result = rag_pipeline._post_process_answer(answer, [])
        assert '1.' not in result or '；' in result

    def test_post_process_answer_with_sources(self, rag_pipeline):
        """测试带来源的回答后处理"""
        answer = "Test answer"
        sources = ["/test/doc.txt"]
        result = rag_pipeline._post_process_answer(answer, sources)
        assert isinstance(result, str)

    def test_get_session_stats(self, rag_pipeline):
        """测试获取会话统计"""
        with patch.object(rag_pipeline.chat_db, 'get_session_messages', return_value=[
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]):
            stats = rag_pipeline.get_session_stats("test_session")
            assert stats['turn_count'] == 1
            assert stats['session_id'] == 'test_session'

    def test_clear_session(self, rag_pipeline):
        """测试清空会话"""
        with patch.object(rag_pipeline.chat_db, 'delete_session', return_value=True):
            result = rag_pipeline.clear_session("test_session")
            assert result == True

    def test_get_all_sessions(self, rag_pipeline):
        """测试获取所有会话"""
        with patch.object(rag_pipeline.chat_db, 'get_all_sessions', return_value=[
            {'session_id': 'sess1', 'title': 'Session 1'}
        ]):
            sessions = rag_pipeline.get_all_sessions()
            assert len(sessions) == 1

    def test_update_config(self, rag_pipeline):
        """测试更新配置"""
        rag_pipeline.update_config(max_docs=10)
        assert rag_pipeline.max_docs == 10

    def test_get_config(self, rag_pipeline):
        """测试获取配置"""
        config = rag_pipeline.get_config()
        assert 'max_docs' in config
        assert 'max_context_chars' in config


class TestRAGPipelineQuery:
    """RAGPipeline 查询测试"""

    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get.return_value = None
        config.getint.return_value = 120
        config.getboolean.return_value = False
        return config

    @pytest.fixture
    def mock_model_manager(self):
        mm = Mock()
        mm.get_model_limits.return_value = {
            'max_docs': 5,
            'chunk_size': 2000,
            'max_context': 4000,
            'max_tokens': 500,
            'temperature': 0.7,
            'min_doc_score': 0.3
        }
        mm.get_mode.return_value = Mock(value='api')
        mm.generate.return_value = iter(["测试", "回答"])
        return mm

    @pytest.fixture
    def mock_search_engine(self):
        se = Mock()
        se.search.return_value = [
            {
                'path': '/test/doc1.txt',
                'filename': 'doc1.txt',
                'content': '测试文档内容',
                'score': 0.9
            }
        ]
        return se

    @pytest.fixture
    def rag_pipeline(self, mock_model_manager, mock_config, mock_search_engine):
        with patch('backend.core.rag_pipeline.ChatHistoryDB'):
            with patch('backend.core.rag_pipeline.VRAMManager') as mock_vram:
                mock_vram_instance = Mock()
                mock_vram_instance.adjust_context_size.return_value = 2000
                mock_vram.return_value = mock_vram_instance
                with patch('backend.core.rag_pipeline.QueryProcessor'):
                    pipeline = RAGPipeline(mock_model_manager, mock_config, mock_search_engine)
                    pipeline.vram_manager = mock_vram_instance
                    return pipeline

    def test_query_reset_command(self, rag_pipeline):
        """测试重置命令"""
        rag_pipeline.reset_commands = ['重置', 'reset']
        result = rag_pipeline.query("重置")
        assert result['answer'] == rag_pipeline.reset_response

    def test_query_small_talk(self, rag_pipeline):
        """测试闲聊"""
        rag_pipeline.greeting_keywords = ['hello']
        result = rag_pipeline.query("hello")
        assert result['answer'] == rag_pipeline.greeting_response

    def test_query_noise(self, rag_pipeline):
        """测试噪声查询"""
        result = rag_pipeline.query("a")
        assert 'fallback' in result['answer'].lower() or '未找到' in result['answer']

    def test_query_empty_session(self, rag_pipeline):
        """测试空会话ID"""
        with patch.object(rag_pipeline, '_collect_documents', return_value=[]):
            with patch.object(rag_pipeline, '_build_history', return_value=('', 0)):
                result = rag_pipeline.query("test query")
                assert 'answer' in result
                assert 'sources' in result

    def test_query_with_documents(self, rag_pipeline):
        """测试带文档的查询"""
        with patch.object(rag_pipeline, '_collect_documents', return_value=[
            {'path': '/test/doc.txt', 'filename': 'doc.txt', 'content': 'Test', 'score': 0.9}
        ]):
            with patch.object(rag_pipeline, '_build_prompt', return_value='Test prompt'):
                result = rag_pipeline.query("test query")
                assert 'answer' in result

    def test_query_context_exhausted(self, rag_pipeline):
        """测试上下文耗尽"""
        rag_pipeline.max_context_chars_total = 100
        with patch.object(rag_pipeline, '_build_history', return_value=('x' * 150, 150)):
            result = rag_pipeline.query("test query")
            assert result['answer'] == rag_pipeline.context_exhausted_response


class TestRAGPipelineDocumentProcessing:
    """RAGPipeline 文档处理测试"""

    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get.return_value = None
        config.getint.return_value = 120
        config.getboolean.return_value = False
        return config

    @pytest.fixture
    def mock_model_manager(self):
        mm = Mock()
        mm.get_model_limits.return_value = {
            'max_docs': 5,
            'chunk_size': 2000,
            'max_context': 4000,
            'max_tokens': 500,
            'temperature': 0.7,
            'min_doc_score': 0.3
        }
        mm.get_mode.return_value = Mock(value='api')
        return mm

    @pytest.fixture
    def mock_search_engine(self):
        return Mock()

    @pytest.fixture
    def rag_pipeline(self, mock_model_manager, mock_config, mock_search_engine):
        with patch('backend.core.rag_pipeline.ChatHistoryDB'):
            with patch('backend.core.rag_pipeline.VRAMManager'):
                with patch('backend.core.rag_pipeline.QueryProcessor'):
                    return RAGPipeline(mock_model_manager, mock_config, mock_search_engine)

    def test_preprocess_content(self, rag_pipeline):
        """测试内容预处理"""
        content = "第一段\n\n第二段\n\n摘要: 这是摘要"
        query = "测试"
        result = rag_pipeline._preprocess_content(content, query)
        assert 'QUERY_TERM' in result or '测试' in result

    def test_calculate_multidimensional_relevance(self, rag_pipeline):
        """测试多维相关性计算"""
        query = "python"
        content = "Python programming guide"
        result = {'score': 0.8}
        filename = "python_guide.txt"
        score = rag_pipeline._calculate_multidimensional_relevance(query, content, result, filename)
        assert score > 0

    def test_calculate_semantic_relevance_fallback(self, rag_pipeline):
        """测试语义相关性回退"""
        query = "python"
        content = "Python programming"
        score = rag_pipeline._calculate_semantic_relevance(query, content)
        assert score >= 0
        assert score <= 100

    def test_select_optimal_documents(self, rag_pipeline):
        """测试最优文档选择"""
        candidates = [
            {'path': '/test/1.txt', 'filename': '1.txt', 'content': 'Content 1', 'score': 0.9},
            {'path': '/test/2.txt', 'filename': '2.txt', 'content': 'Content 2', 'score': 0.8}
        ]
        result = rag_pipeline._select_optimal_documents(candidates)
        assert len(result) <= 2

    def test_extract_relevant_fragments(self, rag_pipeline):
        """测试相关片段提取"""
        content = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        query = "第二段"
        result = rag_pipeline._extract_relevant_fragments(content, query, 1000)
        assert len(result) > 0

    def test_generate_document_summary(self, rag_pipeline):
        """测试文档摘要生成"""
        content = "标题: 测试文档\n\n摘要: 这是摘要\n\n正文内容..."
        result = rag_pipeline._generate_document_summary(content, 500)
        assert len(result) > 0


class TestRAGPipelineHistory:
    """RAGPipeline 历史记录测试"""

    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get.return_value = None
        config.getint.return_value = 120
        config.getboolean.return_value = False
        return config

    @pytest.fixture
    def mock_model_manager(self):
        mm = Mock()
        mm.get_model_limits.return_value = {
            'max_docs': 5,
            'chunk_size': 2000,
            'max_context': 4000,
            'max_tokens': 500,
            'temperature': 0.7,
            'min_doc_score': 0.3
        }
        mm.get_mode.return_value = Mock(value='api')
        return mm

    @pytest.fixture
    def mock_search_engine(self):
        return Mock()

    @pytest.fixture
    def rag_pipeline(self, mock_model_manager, mock_config, mock_search_engine):
        with patch('backend.core.rag_pipeline.ChatHistoryDB') as mock_db:
            mock_db_instance = Mock()
            mock_db.return_value = mock_db_instance
            with patch('backend.core.rag_pipeline.VRAMManager'):
                with patch('backend.core.rag_pipeline.QueryProcessor'):
                    pipeline = RAGPipeline(mock_model_manager, mock_config, mock_search_engine)
                    pipeline.chat_db = mock_db_instance
                    return pipeline

    def test_build_history_empty(self, rag_pipeline):
        """测试空历史"""
        rag_pipeline.chat_db.get_session_messages.return_value = []
        result, used = rag_pipeline._build_history("test_session", 1000)
        assert result == ''
        assert used == 0

    def test_build_history_with_messages(self, rag_pipeline):
        """测试带消息的历史"""
        rag_pipeline.chat_db.get_session_messages.return_value = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]
        result, used = rag_pipeline._build_history("test_session", 1000)
        assert 'Hello' in result
        assert 'Hi' in result

    def test_build_history_exceeds_budget(self, rag_pipeline):
        """测试超出预算的历史"""
        rag_pipeline.chat_db.get_session_messages.return_value = [
            {'role': 'user', 'content': 'A' * 500},
            {'role': 'assistant', 'content': 'B' * 500}
        ]
        result, used = rag_pipeline._build_history("test_session", 100)
        assert used <= 100

    def test_remember_turn(self, rag_pipeline):
        """测试记住对话轮次"""
        rag_pipeline.chat_db.session_exists.return_value = True
        rag_pipeline._remember_turn("test_session", "Hello", "Hi")
        rag_pipeline.chat_db.add_message.assert_any_call("test_session", 'user', "Hello")
        rag_pipeline.chat_db.add_message.assert_any_call("test_session", 'assistant', "Hi")

    def test_reset_session(self, rag_pipeline):
        """测试重置会话"""
        rag_pipeline._reset_session("test_session")
        rag_pipeline.chat_db.delete_session.assert_called_with("test_session")


class TestRAGPipelinePromptBuilding:
    """RAGPipeline 提示词构建测试"""

    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get.return_value = None
        config.getint.return_value = 120
        config.getboolean.return_value = False
        return config

    @pytest.fixture
    def mock_model_manager(self):
        mm = Mock()
        mm.get_model_limits.return_value = {
            'max_docs': 5,
            'chunk_size': 2000,
            'max_context': 4000,
            'max_tokens': 500,
            'temperature': 0.7,
            'min_doc_score': 0.3
        }
        mm.get_mode.return_value = Mock(value='api')
        return mm

    @pytest.fixture
    def mock_search_engine(self):
        return Mock()

    @pytest.fixture
    def rag_pipeline(self, mock_model_manager, mock_config, mock_search_engine):
        with patch('backend.core.rag_pipeline.ChatHistoryDB'):
            with patch('backend.core.rag_pipeline.VRAMManager'):
                with patch('backend.core.rag_pipeline.QueryProcessor'):
                    return RAGPipeline(mock_model_manager, mock_config, mock_search_engine)

    def test_build_prompt_empty(self, rag_pipeline):
        """测试空提示词"""
        result = rag_pipeline._build_prompt("query", [], "", None)
        assert result == ''

    def test_build_prompt_with_documents(self, rag_pipeline):
        """测试带文档的提示词"""
        documents = [
            {'filename': 'test.txt', 'path': '/test.txt', 'content': 'Test content', 'score': 0.9}
        ]
        result = rag_pipeline._build_prompt("query", documents, "", 1000)
        assert 'test.txt' in result
        assert 'Test content' in result

    def test_build_prompt_with_history(self, rag_pipeline):
        """测试带历史的提示词"""
        documents = [
            {'filename': 'test.txt', 'path': '/test.txt', 'content': 'Test', 'score': 0.9}
        ]
        result = rag_pipeline._build_prompt("query", documents, "Previous chat", 1000)
        assert 'Previous chat' in result

    def test_extract_key_entities(self, rag_pipeline):
        """测试关键实体提取"""
        documents = [
            {'filename': 'author_paper.pdf', 'path': '/test.pdf', 'content': 'Test', 'score': 0.9}
        ]
        result = rag_pipeline._extract_key_entities(documents)
        assert 'author' in result or 'paper' in result

    def test_truncate_content_if_needed(self, rag_pipeline):
        """测试内容截断"""
        section = "--- 文件: test.txt ---\n路径: /test.txt\n相关性: 0.9\n内容:\n" + "A" * 1000
        content = "A" * 1000
        result = rag_pipeline._truncate_content_if_needed(section, content, 500, 0)
        assert len(result) <= 500

    def test_truncate_content_no_truncate(self, rag_pipeline):
        """测试不需要截断"""
        section = "--- 文件: test.txt ---\n内容:\nShort content"
        content = "Short content"
        result = rag_pipeline._truncate_content_if_needed(section, content, 1000, 0)
        assert 'Short content' in result
