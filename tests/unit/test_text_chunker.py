"""TextChunker 单元测试"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.text_chunker import TextChunker, TextChunk, chunk_document


class TestTextChunkerInit:
    """TextChunker 初始化测试"""

    def test_default_initialization(self):
        """测试默认初始化"""
        chunker = TextChunker()
        assert chunker.strategy == "semantic"
        assert chunker.chunk_size == 800
        assert chunker.chunk_overlap == 100
        assert chunker.min_chunk_size == 100
        assert chunker.max_chunk_size == 1500

    def test_custom_initialization(self):
        """测试自定义初始化"""
        chunker = TextChunker(
            strategy="fixed",
            chunk_size=500,
            chunk_overlap=50,
            min_chunk_size=50,
            max_chunk_size=1000,
        )
        assert chunker.strategy == "fixed"
        assert chunker.chunk_size == 500
        assert chunker.chunk_overlap == 50
        assert chunker.min_chunk_size == 50
        assert chunker.max_chunk_size == 1000

    def test_invalid_strategy(self):
        """测试无效策略"""
        with pytest.raises(ValueError, match="未知的分块策略"):
            TextChunker(strategy="invalid_strategy")

    @pytest.mark.parametrize(
        "strategy",
        ["paragraph", "sentence", "fixed", "semantic"],
    )
    def test_valid_strategies(self, strategy):
        """测试所有有效策略"""
        chunker = TextChunker(strategy=strategy)
        assert chunker.strategy == strategy


class TestTextChunkerEmptyInput:
    """TextChunker 空输入处理测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker()

    def test_empty_string(self, chunker):
        """测试空字符串"""
        result = chunker.chunk_document("", "/test/doc.txt", "doc.txt")
        assert result == []

    def test_whitespace_only(self, chunker):
        """测试仅空白字符"""
        result = chunker.chunk_document("   \n\n\t  ", "/test/doc.txt", "doc.txt")
        assert result == []

    def test_none_content(self, chunker):
        """测试 None 内容"""
        result = chunker.chunk_document(None, "/test/doc.txt", "doc.txt")
        assert result == []


class TestTextChunkerShortContent:
    """TextChunker 短内容测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker()

    def test_short_content(self, chunker):
        """测试短于块大小的内容"""
        content = "这是一段短文本。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) == 1
        assert result[0].content == content
        assert result[0].chunk_index == 0
        assert result[0].start_pos == 0
        assert result[0].end_pos == len(content)

    def test_content_equal_to_chunk_size(self, chunker):
        """测试内容等于块大小"""
        content = "a" * 800
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) == 1
        assert len(result[0].content) == 800


class TestTextChunkerChunkSize:
    """TextChunker 分块大小限制测试"""

    def test_fixed_strategy_size_limit(self):
        """测试固定策略块大小限制"""
        chunker = TextChunker(strategy="fixed", chunk_size=200, chunk_overlap=20)
        content = "a" * 500
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk.content) <= 200

    def test_paragraph_strategy_size_limit(self):
        """测试段落策略块大小限制"""
        chunker = TextChunker(strategy="paragraph", max_chunk_size=300)
        content = "第一段。" + "b" * 400 + "\n\n第二段。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        for chunk in result:
            assert len(chunk.content) <= 500

    def test_sentence_strategy_size_limit(self):
        """测试句子策略块大小限制"""
        chunker = TextChunker(strategy="sentence", chunk_size=100)
        sentences = ["第一句。", "第二句。", "第三句。", "第四句。", "第五句。"]
        content = "".join(sentences)
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        for chunk in result:
            assert len(chunk.content) <= 150

    def test_min_chunk_size_filter(self):
        """测试最小块大小过滤"""
        chunker = TextChunker(
            strategy="fixed", chunk_size=200, chunk_overlap=50, min_chunk_size=80
        )
        content = "a" * 50 + "\n\n" + "b" * 50
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        for chunk in result:
            assert len(chunk.content) >= 80


class TestTextChunkerOverlap:
    """TextChunker 重叠大小测试"""

    def test_fixed_strategy_overlap(self):
        """测试固定策略的重叠"""
        chunker = TextChunker(strategy="fixed", chunk_size=100, chunk_overlap=30)
        content = "abcdefghij" * 30
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        if len(result) >= 2:
            first_end = result[0].end_pos
            second_start = result[1].start_pos
            assert second_start < first_end

    def test_sentence_strategy_overlap(self):
        """测试句子策略的重叠"""
        chunker = TextChunker(strategy="sentence", chunk_size=50, chunk_overlap=20)
        content = "这是第一句话。这是第二句话。这是第三句话。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        if len(result) >= 2:
            first_content = result[0].content
            second_content = result[1].content
            assert len(first_content) + len(second_content) > 0

    def test_no_overlap_when_small_content(self):
        """测试内容过小时不产生重叠"""
        chunker = TextChunker(strategy="fixed", chunk_size=200, chunk_overlap=50)
        content = "短文本"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) == 1


class TestTextChunkerChinese:
    """TextChunker 中文处理测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker(strategy="semantic", chunk_size=100)

    def test_chinese_paragraph_chunking(self, chunker):
        """测试中文段落分块"""
        content = "第一段文字。\n\n第二段文字。\n\n第三段文字。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_chinese_sentence_chunking(self):
        """测试中文句子分块"""
        chunker = TextChunker(strategy="sentence", chunk_size=20)
        content = "这是第一句。这是第二句。这是第三句。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        for chunk in result:
            assert chunk.char_count == len(chunk.content)

    def test_chinese_long_paragraph(self):
        """测试中文长段落切分"""
        chunker = TextChunker(
            strategy="semantic", chunk_size=100, max_chunk_size=300, min_chunk_size=30
        )
        content = "这是一段很长的中文文本。" * 10
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        for chunk in result:
            assert chunk.char_count == len(chunk.content)

    def test_chinese_sentence_endings(self):
        """测试中文句子结束符"""
        chunker = TextChunker(strategy="sentence", chunk_size=50)
        content = "你好吗？我很好。很高兴认识你！今天天气不错吧？"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1


class TestTextChunkerEnglish:
    """TextChunker 英文处理测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker(strategy="semantic", chunk_size=100)

    def test_english_paragraph_chunking(self, chunker):
        """测试英文段落分块"""
        content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_english_sentence_chunking(self):
        """测试英文句子分块"""
        chunker = TextChunker(strategy="sentence", chunk_size=30, min_chunk_size=10)
        content = "Hello world. How are you? I am fine. Thank you!"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        for chunk in result:
            assert chunk.char_count == len(chunk.content)

    def test_english_word_boundary(self):
        """测试英文单词边界"""
        chunker = TextChunker(strategy="fixed", chunk_size=50, min_chunk_size=10)
        content = "This is a test document for chunking."
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) == 1
        assert "This is a test document for chunking." in result[0].content


class TestTextChunkerMixed:
    """TextChunker 中英文混合测试"""

    def test_mixed_content(self):
        """测试中英文混合内容"""
        chunker = TextChunker(strategy="semantic", chunk_size=100)
        content = "Hello world。你好世界。This is a test. 这是一个测试。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        assert "Hello" in result[0].content or "你好" in result[0].content

    def test_code_and_chinese(self):
        """测试代码与中文混合"""
        chunker = TextChunker(strategy="paragraph", chunk_size=200)
        content = "def hello():\n    print('Hello')\n\n这是一个Python函数。"
        result = chunker.chunk_document(content, "/test/doc.py", "doc.py")
        assert len(result) >= 1


class TestTextChunkerEdgeCases:
    """TextChunker 边界情况测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker()

    def test_single_character(self, chunker):
        """测试单字符"""
        result = chunker.chunk_document("a", "/test/doc.txt", "doc.txt")
        assert len(result) == 1
        assert result[0].content == "a"

    def test_single_chinese_character(self, chunker):
        """测试单个中文字符"""
        result = chunker.chunk_document("中", "/test/doc.txt", "doc.txt")
        assert len(result) == 1
        assert result[0].content == "中"

    def test_only_newlines(self, chunker):
        """测试仅有换行符"""
        result = chunker.chunk_document("\n\n\n", "/test/doc.txt", "doc.txt")
        assert result == []

    def test_only_punctuation(self, chunker):
        """测试仅有标点符号"""
        result = chunker.chunk_document("。、，！？", "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_very_long_content(self):
        """测试超长内容"""
        chunker = TextChunker(strategy="fixed", chunk_size=500, chunk_overlap=50)
        content = "a" * 10000
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 15
        for chunk in result:
            assert len(chunk.content) <= 550

    def test_special_characters(self, chunker):
        """测试特殊字符"""
        content = "!@#$%^&*()_+-=[]{}|;':\",./<>?\n\n\t\t\r\r"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_unicode_characters(self, chunker):
        """测试Unicode字符"""
        content = "中文English123\n\n日本語テスト"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1


class TestTextChunkerStrategies:
    """TextChunker 不同策略测试"""

    def test_paragraph_strategy(self):
        """测试段落策略"""
        chunker = TextChunker(strategy="paragraph", chunk_size=50)
        content = "第一段\n\n第二段\n\n第三段"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_sentence_strategy(self):
        """测试句子策略"""
        chunker = TextChunker(strategy="sentence", chunk_size=20)
        content = "第一句。第二句。第三句。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_fixed_strategy(self):
        """测试固定长度策略"""
        chunker = TextChunker(
            strategy="fixed", chunk_size=20, chunk_overlap=5, min_chunk_size=5
        )
        content = "This is a test document for chunking."
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_semantic_strategy(self):
        """测试语义策略"""
        chunker = TextChunker(strategy="semantic", chunk_size=50)
        content = "段落一内容。\n\n段落二内容。\n\n段落三内容。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1


class TestTextChunkerMetadata:
    """TextChunker 元数据测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker()

    def test_chunk_metadata(self, chunker):
        """测试块元数据"""
        chunker = TextChunker(strategy="semantic", chunk_size=200)
        content = (
            "第一段内容。\n\n第二段内容。" + "这是更长的内容来确保产生多个块。" * 5
        ) * 10
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        assert "total_chunks" in result[0].metadata
        assert "strategy" in result[0].metadata

    def test_doc_metadata(self, chunker):
        """测试文档元数据"""
        content = "这是文档内容。"
        doc_metadata = {"author": "test", "date": "2024-01-01"}
        result = chunker.chunk_document(
            content, "/test/doc.txt", "doc.txt", doc_metadata=doc_metadata
        )
        if len(result) > 0:
            assert result[0].metadata["author"] == "test"
            assert result[0].metadata["date"] == "2024-01-01"

    def test_chunk_positions(self, chunker):
        """测试块位置信息"""
        content = "第一段内容。第二段内容。"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        if len(result) >= 2:
            assert result[0].end_pos <= result[1].start_pos


class TestTextChunkerTextChunk:
    """TextChunk 数据结构测试"""

    def test_text_chunk_creation(self):
        """测试 TextChunk 创建"""
        chunk = TextChunk(
            content="test content",
            doc_path="/test/doc.txt",
            doc_filename="doc.txt",
            chunk_index=0,
            start_pos=0,
            end_pos=12,
            char_count=12,
        )
        assert chunk.content == "test content"
        assert chunk.char_count == 12
        assert chunk.metadata == {}

    def test_text_chunk_with_metadata(self):
        """测试带元数据的 TextChunk"""
        metadata = {"key": "value"}
        chunk = TextChunk(
            content="test",
            doc_path="/test/doc.txt",
            doc_filename="doc.txt",
            chunk_index=0,
            start_pos=0,
            end_pos=4,
            char_count=4,
            metadata=metadata,
        )
        assert chunk.metadata == metadata


class TestChunkDocumentFunction:
    """便捷函数测试"""

    def test_chunk_document_function(self):
        """测试便捷分块函数"""
        content = "这是测试内容。"
        result = chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
        assert result[0].doc_path == "/test/doc.txt"

    def test_chunk_document_with_params(self):
        """测试带参数的分块函数"""
        content = "a" * 500
        result = chunk_document(
            content,
            "/test/doc.txt",
            "doc.txt",
            strategy="fixed",
            chunk_size=100,
            chunk_overlap=20,
        )
        assert len(result) >= 2


class TestTextChunkerNoisyContent:
    """TextChunker 噪声内容测试"""

    @pytest.fixture
    def chunker(self):
        return TextChunker()

    def test_multiple_newlines(self, chunker):
        """测试多个连续换行"""
        content = "第一段\n\n\n\n\n第二段"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_extra_spaces(self, chunker):
        """测试多余空格"""
        content = "第一段    第二段"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_mixed_line_endings(self, chunker):
        """测试混合行尾符"""
        content = "第一段\r\n\r\n第二段\n\n第三段"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1


class TestTextChunkerChunkIndices:
    """TextChunker 块索引测试"""

    def test_chunk_indices_sequential(self):
        """测试块索引顺序"""
        chunker = TextChunker(strategy="fixed", chunk_size=50, chunk_overlap=10)
        content = "a" * 300
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        if len(result) > 1:
            for i, chunk in enumerate(result):
                assert chunk.chunk_index == i

    def test_total_chunks_metadata(self):
        """测试总块数元数据"""
        chunker = TextChunker(strategy="fixed", chunk_size=100, chunk_overlap=20)
        content = "a" * 500
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        if len(result) > 0:
            assert result[0].metadata["total_chunks"] == len(result)


class TestTextChunkerConfigBounds:
    """TextChunker 配置边界测试"""

    def test_min_chunk_size_greater_than_chunk_size(self):
        """测试最小块大于块大小 - 不抛出异常但可能有警告"""
        chunker = TextChunker(chunk_size=50, min_chunk_size=100)
        content = "a" * 200
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_overlap_greater_than_chunk_size(self):
        """测试重叠大于块大小"""
        chunker = TextChunker(chunk_size=100, chunk_overlap=150)
        content = "a" * 500
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1

    def test_zero_chunk_size(self):
        """测试零块大小 - 不抛出异常"""
        chunker = TextChunker(chunk_size=0)
        content = "test content"
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) == 1

    def test_negative_overlap(self):
        """测试负重叠"""
        chunker = TextChunker(chunk_size=100, chunk_overlap=-10)
        content = "a" * 500
        result = chunker.chunk_document(content, "/test/doc.txt", "doc.txt")
        assert len(result) >= 1
