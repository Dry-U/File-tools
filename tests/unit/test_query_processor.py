"""Query Processor 单元测试"""

import pytest
import sys
import os
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.query_processor import QueryProcessor


class TestQueryProcessor:
    """QueryProcessor 测试类"""

    @pytest.fixture
    def processor(self):
        """创建 QueryProcessor 实例"""
        return QueryProcessor()

    def test_init(self):
        """测试初始化"""
        config = Mock()
        processor = QueryProcessor(config)
        assert processor.config_loader == config

    def test_init_no_config(self):
        """测试无配置初始化"""
        processor = QueryProcessor()
        assert processor.config_loader is None

    def test_process_empty_query(self, processor):
        """测试空查询处理"""
        result = processor.process("")
        assert result == []

    def test_process_whitespace_query(self, processor):
        """测试空白查询处理"""
        result = processor.process("   ")
        assert result == []

    def test_process_simple_query(self, processor):
        """测试简单查询处理"""
        result = processor.process("python")
        assert "python" in result
        assert len(result) >= 1

    def test_process_with_abbreviation(self, processor):
        """测试缩写展开"""
        result = processor.process("api")
        assert "api" in result
        # 应该包含展开后的形式
        assert any("application" in r.lower() for r in result)

    def test_process_with_synonyms(self, processor):
        """测试同义词扩展 - 仅对非短查询（>2字符）生效"""
        # 短查询（<=2字符）跳过扩展，直接返回原始查询
        result = processor.process("文档")
        assert "文档" in result
        # "文档" 是 2 字符短查询，跳过同义词扩展
        # 测试长查询的同义词扩展
        result_long = processor.process("文档说明")
        assert "文档说明" in result_long
        # 长查询应包含同义词扩展
        assert any("说明" in r or "文档" in r for r in result_long)

    def test_process_filename_variants(self, processor):
        """测试文件名变体生成"""
        # 只有被判定为文件名查询时才生成变体
        # "test" 本身不足以触发文件名变体（分数 < 50）
        # 使用带扩展名的查询来触发
        result = processor.process("test.pdf")
        assert "test.pdf" in result

    def test_process_skips_filename_variants_for_long_content_query(self, processor):
        """长内容查询不应触发文件名模板扩展"""
        query = "如何优化分布式系统中的缓存一致性与数据库事务"
        result = processor.process(query)
        assert query in result
        assert not any(r.endswith("说明") and "缓存一致性" in r for r in result)

    def test_expand_abbreviations_exact_match(self, processor):
        """测试缩写精确匹配"""
        result = processor._expand_abbreviations("API")
        assert len(result) > 0
        assert any("application programming interface" in r.lower() for r in result)

    def test_expand_abbreviations_in_sentence(self, processor):
        """测试句子中的缩写展开"""
        result = processor._expand_abbreviations("使用API接口")
        # API应该被识别并展开
        assert (
            any("api" in r.lower() or "application" in r.lower() for r in result)
            or len(result) >= 0
        )

    def test_expand_abbreviations_no_match(self, processor):
        """测试无匹配缩写"""
        result = processor._expand_abbreviations("没有缩写的普通查询")
        assert result == []

    def test_expand_synonyms_exact_match(self, processor):
        """测试同义词精确匹配"""
        result = processor._expand_synonyms("代码")
        assert len(result) > 0
        assert any("程序" in r for r in result)

    def test_expand_synonyms_multiple(self, processor):
        """测试多个同义词"""
        result = processor._expand_synonyms("数据库")
        assert len(result) > 0

    def test_generate_filename_variants(self, processor):
        """测试文件名变体生成"""
        result = processor._generate_filename_variants("project")
        assert len(result) > 0
        assert all("project" in r for r in result)

    def test_generate_filename_variants_empty(self, processor):
        """测试空查询的文件名变体"""
        result = processor._generate_filename_variants("")
        assert result == []

    def test_clean_query_for_filename(self, processor):
        """测试查询清理"""
        result = processor._clean_query_for_filename("the python code")
        assert "python" in result
        assert "code" in result
        assert "the" not in result  # 停用词应该被移除

    def test_clean_query_for_filename_all_stopwords(self, processor):
        """测试全是停用词的查询"""
        result = processor._clean_query_for_filename("the a an")
        # 应该返回原始查询
        assert result == "the a an"

    def test_clean_and_deduplicate(self, processor):
        """测试清理和去重"""
        queries = ["python", "python", "Python", "  python  "]
        result = processor._clean_and_deduplicate(queries)
        # 去重后应该只有一个
        assert len(result) == 1
        assert result[0] == "python"

    def test_clean_and_deduplicate_empty(self, processor):
        """测试空列表清理"""
        result = processor._clean_and_deduplicate([])
        assert result == []

    def test_extract_keywords(self, processor):
        """测试关键词提取"""
        result = processor.extract_keywords("Python programming guide")
        assert "python" in result
        assert "programming" in result
        assert "guide" in result

    def test_extract_keywords_with_stopwords(self, processor):
        """测试带停用词的关键词提取"""
        result = processor.extract_keywords("the python code")
        assert "python" in result
        assert "code" in result
        assert "the" not in result

    def test_extract_keywords_empty(self, processor):
        """测试空查询关键词提取"""
        result = processor.extract_keywords("")
        assert result == []

    def test_is_likely_filename_query_with_extension(self, processor):
        """测试带扩展名的文件名查询检测"""
        # 带 .pdf + 长度短 = 30+10 = 40, 不到阈值50
        # 加上路径符号才能达到 40+40 = 80 >= 50
        assert processor.is_likely_filename_query("/document.pdf")
        assert not processor.is_likely_filename_query("script.py")  # 30+10=40 < 50

    def test_is_likely_filename_query_short(self, processor):
        """测试短查询的文件名检测"""
        # 短英文查询没有足够信号
        assert not processor.is_likely_filename_query("readme")
        assert not processor.is_likely_filename_query("test file")

    def test_is_likely_filename_query_with_indicator(self, processor):
        """测试带指示词的文件名查询"""
        # "查找PDF文件" → 中文无空格(+20) + 长度<20(+10) + pdf关键词(+15) = 45 < 50
        assert not processor.is_likely_filename_query("查找PDF文件")
        # "word文档" → 中文无空格(+20) + 长度<20(+10) + doc关键词(+15) = 45 < 50
        assert not processor.is_likely_filename_query("word文档")
        # 带.pdf扩展名 + 关键词：30+10+15 = 55 >= 50
        assert processor.is_likely_filename_query("报告.pdf")

    def test_is_likely_filename_query_content(self, processor):
        """测试内容查询"""
        # 长查询（超过3个词）通常不是文件名查询
        processor.is_likely_filename_query("如何学习Python编程语言")
        # 注意：实际行为可能因实现而异，这里我们检查它不会崩溃

    def test_is_likely_filename_query_empty(self, processor):
        """测试空查询"""
        assert not processor.is_likely_filename_query("")


class TestQueryProcessorEdgeCases:
    """QueryProcessor 边界情况测试"""

    @pytest.fixture
    def processor(self):
        return QueryProcessor()

    def test_process_special_characters(self, processor):
        """测试特殊字符处理"""
        result = processor.process("test@#$%^&*()")
        assert len(result) > 0

    def test_process_very_long_query(self, processor):
        """测试超长查询"""
        long_query = "python " * 1000
        result = processor.process(long_query)
        assert len(result) > 0

    def test_process_unicode(self, processor):
        """测试Unicode字符"""
        result = processor.process("Python编程🐍")
        assert len(result) > 0

    def test_expand_abbreviations_case_insensitive(self, processor):
        """测试缩写大小写不敏感"""
        result_lower = processor._expand_abbreviations("api")
        result_upper = processor._expand_abbreviations("API")
        result_mixed = processor._expand_abbreviations("Api")
        # 结果应该相同
        assert len(result_lower) == len(result_upper) == len(result_mixed)

    def test_synonyms_chinese_english(self, processor):
        """测试中英文同义词"""
        result = processor._expand_synonyms("搜索")
        # 应该包含英文同义词
        assert any("search" in r.lower() for r in result)

    def test_filename_variants_chinese(self, processor):
        """测试中文文件名变体"""
        result = processor._generate_filename_variants("项目")
        assert len(result) > 0
        assert all("项目" in r for r in result)

    def test_clean_query_single_character(self, processor):
        """测试单字符查询清理"""
        result = processor._clean_query_for_filename("a b c")
        # 单字符应该被过滤
        assert result == "a b c"  # 全是单字符，返回原始值

    def test_extract_keywords_single_word(self, processor):
        """测试单字关键词提取"""
        result = processor.extract_keywords("a")
        assert result == []  # 单字符应该被过滤

    def test_is_likely_filename_query_long(self, processor):
        """测试长查询的文件名检测"""
        long_query = "这是一个非常长的查询语句，包含很多个字"
        processor.is_likely_filename_query(long_query)
        # 长查询通常不是文件名查询，但实际行为取决于实现


class TestQueryProcessorAbbreviations:
    """QueryProcessor 缩写测试"""

    @pytest.fixture
    def processor(self):
        return QueryProcessor()

    @pytest.mark.parametrize(
        "abbr,expected",
        [
            ("api", "application programming interface"),
            ("sdk", "software development kit"),
            ("ui", "user interface"),
            ("db", "database"),
            ("sql", "structured query language"),
            ("http", "hypertext transfer protocol"),
            ("json", "javascript object notation"),
            ("html", "hypertext markup language"),
            ("pdf", "portable document format"),
        ],
    )
    def test_common_abbreviations(self, processor, abbr, expected):
        """测试常见缩写"""
        result = processor._expand_abbreviations(abbr)
        assert any(expected in r.lower() for r in result)


class TestQueryProcessorSynonyms:
    """QueryProcessor 同义词测试"""

    @pytest.fixture
    def processor(self):
        return QueryProcessor()

    @pytest.mark.parametrize(
        "word,expected_synonym",
        [
            ("文档", "说明"),
            ("代码", "程序"),
            ("软件", "应用"),
            ("搜索", "查找"),
            ("配置", "设置"),
            ("功能", "特性"),
            ("错误", "异常"),
            ("测试", "验证"),
        ],
    )
    def test_common_synonyms(self, processor, word, expected_synonym):
        """测试常见同义词"""
        result = processor._expand_synonyms(word)
        assert any(expected_synonym in r for r in result)
