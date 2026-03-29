#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试配置验证模块"""
from backend.utils.config_validator import (
    ValidationIssue,
    ValidationResult,
    ConfigValidator,
    validate_config_or_warn,
)


class TestValidationIssue:
    """测试验证问题类"""

    def test_issue_creation(self):
        """测试创建验证问题"""
        issue = ValidationIssue(
            level="error",
            message="Test error",
            section="test",
            key="key",
            suggestion="Fix it"
        )
        assert issue.level == "error"
        assert issue.message == "Test error"
        assert issue.section == "test"
        assert issue.key == "key"
        assert issue.suggestion == "Fix it"


class TestValidationResult:
    """测试验证结果类"""

    def test_empty_result(self):
        """测试空结果"""
        result = ValidationResult()
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error(self):
        """测试添加错误"""
        result = ValidationResult()
        result.add_error("Test error", "section", "key", "Fix it")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Test error"

    def test_add_warning(self):
        """测试添加警告"""
        result = ValidationResult()
        result.add_warning("Test warning", "section", "key", "Consider it")

        assert result.is_valid is True
        assert len(result.warnings) == 1

    def test_merge(self):
        """测试合并结果"""
        result1 = ValidationResult()
        result1.add_error("Error 1", "section1")

        result2 = ValidationResult()
        result2.add_error("Error 2", "section2")
        result2.add_warning("Warning 1", "section3")

        result1.merge(result2)

        assert len(result1.errors) == 2
        assert len(result1.warnings) == 1


class TestConfigValidator:
    """测试配置验证器"""

    def test_validate_required_sections(self):
        """测试验证必需章节"""
        validator = ConfigValidator()
        config = {}  # 空配置

        result = validator.validate(config)

        # 应该产生关于缺失章节的错误
        assert len(result.errors) > 0

    def test_validate_valid_config(self):
        """测试验证有效配置"""
        validator = ConfigValidator()
        config = {
            "file_scanner": {
                "scan_paths": ["/test"],
                "max_file_size": 100
            },
            "search": {
                "text_weight": 0.6,
                "vector_weight": 0.4
            }
        }

        result = validator.validate(config)

        # 应该通过验证或有警告但没有错误
        assert len(result.errors) == 0

    def test_validate_scan_paths(self):
        """测试验证扫描路径"""
        validator = ConfigValidator()

        # 有效路径
        assert validator._validate_scan_paths(["/test"]) is True

        # 空列表
        assert validator._validate_scan_paths([]) is False

        # 测试空字符串路径的边界情况
        assert validator._validate_scan_paths([""]) is False

    def test_validate_numeric_ranges(self):
        """测试验证数值范围"""
        validator = ConfigValidator()

        # 有效值
        assert validator._validate_numeric_ranges(
            {"text_weight": 0.5, "vector_weight": 0.5}
        ) is True

        # 超出范围
        assert validator._validate_numeric_ranges(
            {"text_weight": 1.5}  # > 1.0
        ) is False

    def test_validate_ai_model_config(self):
        """测试验证 AI 模型配置"""
        validator = ConfigValidator()
        config = {
            "ai_model": {
                "provider": "siliconflow",
                "api_url": "https://api.example.com",
                "api_key": "test-key"
            }
        }

        result = validator.validate(config)

        # 如果有 AI 模型配置，应该验证其有效性
        assert isinstance(result, ValidationResult)


class TestValidateConfigOrWarn:
    """测试便捷验证函数"""

    def test_valid_config(self, caplog):
        """测试有效配置"""
        config = {
            "file_scanner": {
                "scan_paths": ["/test"],
            },
            "search": {}
        }

        with caplog.at_level("WARNING"):
            validate_config_or_warn(config)

        # 有效配置不应产生警告
        assert "配置验证失败" not in caplog.text
