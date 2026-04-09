#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置验证模块

在应用启动时验证配置的有效性，提供友好的错误提示。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.exceptions import ConfigValidationError
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """验证问题"""

    level: str = "error"  # 'error', 'warning', 'info'
    message: str = ""
    section: Optional[str] = None
    key: Optional[str] = None
    suggestion: Optional[str] = None
    code: Optional[str] = None  # 向后兼容


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool = True
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    infos: List[ValidationIssue] = field(default_factory=list)  # 向后兼容
    issues: List[ValidationIssue] = field(default_factory=list)  # 向后兼容

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.infos is None:
            self.infos = []
        if self.issues is None:
            self.issues = []

    def add_error(
        self,
        message: str,
        section: Optional[str] = None,
        key: Optional[str] = None,
        suggestion: Optional[str] = None,
        code: Optional[str] = None,
    ):
        """添加错误"""
        issue = ValidationIssue(
            level="error",
            message=message,
            section=section,
            key=key,
            suggestion=suggestion,
            code=code,
        )
        self.errors.append(issue)
        self.issues.append(issue)
        self.is_valid = False

    def add_warning(
        self,
        message: str,
        section: Optional[str] = None,
        key: Optional[str] = None,
        suggestion: Optional[str] = None,
        code: Optional[str] = None,
    ):
        """添加警告"""
        issue = ValidationIssue(
            level="warning",
            message=message,
            section=section,
            key=key,
            suggestion=suggestion,
            code=code,
        )
        self.warnings.append(issue)
        self.issues.append(issue)

    def add_info(
        self,
        message: str,
        section: Optional[str] = None,
        key: Optional[str] = None,
        suggestion: Optional[str] = None,
        code: Optional[str] = None,
    ):
        """添加信息（向后兼容）"""
        issue = ValidationIssue(
            level="info",
            message=message,
            section=section,
            key=key,
            suggestion=suggestion,
            code=code,
        )
        self.infos.append(issue)
        self.issues.append(issue)

    def add_issue(self, issue: ValidationIssue):
        """添加验证问题（向后兼容）"""
        if issue.level == "error":
            self.errors.append(issue)
            self.is_valid = False
        elif issue.level == "warning":
            self.warnings.append(issue)
        elif issue.level == "info":
            self.infos.append(issue)
        self.issues.append(issue)

    def merge(self, other: "ValidationResult"):
        """合并另一个结果"""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.infos.extend(other.infos)
        self.issues.extend(other.issues)
        if other.errors:
            self.is_valid = False

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0


class ConfigValidator:
    """配置验证器"""

    # 必要的配置节
    REQUIRED_SECTIONS = [
        "system",
        "file_scanner",
        "search",
        "monitor",
        "embedding",
        "ai_model",
        "rag",
        "interface",
        "advanced",
        "index",
    ]

    # 必要的配置项
    REQUIRED_FIELDS = {
        "system": ["data_dir", "log_dir"],
        "file_scanner": ["scan_paths"],
        "search": ["text_weight", "vector_weight"],
    }

    def __init__(self, config_loader=None):
        self.config_loader = config_loader
        self.issues: List[ValidationIssue] = []
        self.config: Dict[str, Any] = {}

    def validate(self, config: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        执行完整验证

        Args:
            config: 配置字典（如果提供）或从 config_loader 获取

        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult()

        # 使用传入的配置或从 config_loader 获取
        if config is not None:
            self.config = config
        elif self.config_loader is not None:
            self.config = getattr(self.config_loader, "config", {})
        else:
            result.add_error("未提供配置或配置加载器")
            return result

        # 1. 验证必要配置节
        self._validate_required_sections(result)

        # 2. 验证必要配置项
        self._validate_required_fields(result)

        # 3. 验证路径可写性
        self._validate_paths(result)

        # 4. 验证扫描路径
        self._validate_scan_paths_from_config(result)

        # 5. 验证AI模型配置
        self._validate_ai_model_config(result)

        # 6. 验证权限
        self._validate_permissions(result)

        # 7. 验证数值范围
        self._validate_numeric_ranges_from_config(result)

        # 8. 验证依赖项
        self._validate_dependencies(result)

        return result

    def _get_value(self, section: str, key: str, default=None):
        """从配置中获取值"""
        if self.config_loader is not None:
            return self.config_loader.get(section, key, default)

        section_data = self.config.get(section, {})
        if isinstance(section_data, dict):
            return section_data.get(key, default)
        return default

    def _getboolean(self, section: str, key: str, default=False):
        """获取布尔值"""
        value = self._get_value(section, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    def _getfloat(self, section: str, key: str, default: Optional[float] = 0.0):
        """获取浮点值"""
        value = self._get_value(section, key, default)
        if value is None:
            return default if default is not None else 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return default if default is not None else 0.0

    def _validate_required_sections(self, result: ValidationResult) -> None:
        """验证必要的配置节是否存在"""
        # 核心必需章节（没有这些章节会报错）
        critical_sections = ["file_scanner", "search"]

        for section in self.REQUIRED_SECTIONS:
            if section not in self.config:
                if section in critical_sections:
                    result.add_error(
                        message=f"必要配置节缺失: [{section}]",
                        section=section,
                        code="MISSING_SECTION",
                        suggestion=f"在配置文件中添加 [{section}] 节",
                    )
                else:
                    result.add_warning(
                        message=f"配置节 [{section}] 不存在，将使用默认值",
                        section=section,
                        code="MISSING_SECTION",
                        suggestion=f"在配置文件中添加 [{section}] 节",
                    )

    def _validate_required_fields(self, result: ValidationResult) -> None:
        """验证必要的配置项"""
        for section, fields in self.REQUIRED_FIELDS.items():
            if section not in self.config:
                continue

            for field_name in fields:
                value = self._get_value(section, field_name, None)
                if value is None or value == "":
                    is_critical = section in ["system"]
                    if is_critical:
                        result.add_error(
                            message=f"必要配置项缺失: [{section}].{field_name}",
                            section=section,
                            key=field_name,
                            code="MISSING_REQUIRED_FIELD",
                            suggestion=f"在配置文件中设置 {section}.{field}",
                        )
                    else:
                        result.add_warning(
                            message=f"必要配置项缺失: [{section}].{field_name}",
                            section=section,
                            key=field_name,
                            code="MISSING_REQUIRED_FIELD",
                            suggestion=f"在配置文件中设置 {section}.{field_name}",
                        )

    def _validate_paths(self, result: ValidationResult) -> None:
        """验证路径配置"""
        path_fields = [
            ("system", "data_dir"),
            ("system", "log_dir"),
            ("system", "cache_dir"),
            ("system", "temp_dir"),
            ("index", "tantivy_path"),
            ("index", "hnsw_path"),
            ("index", "metadata_path"),
        ]

        for section, field_name in path_fields:
            path_str = self._get_value(section, field_name, None)
            if not path_str:
                continue

            path = Path(str(path_str))

            # 检查是否为绝对路径
            if not path.is_absolute():
                path = path.resolve()

            # 检查路径是否可创建/可写
            try:
                parent = path.parent
                if not parent.exists():
                    # 检查是否可以创建父目录
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                    except PermissionError:
                        result.add_error(
                            message=f"无法创建目录 {parent}: 权限不足",
                            section=f"{section}.{field}",
                            code="PATH_NOT_WRITABLE",
                            suggestion="检查目录权限或更改配置路径",
                        )
                        continue

                # 检查是否可写
                if path.exists():
                    if not os.access(path, os.W_OK):
                        result.add_error(
                            message=f"目录不可写: {path}",
                            section=f"{section}.{field}",
                            code="PATH_NOT_WRITABLE",
                            suggestion="更改目录权限或修改配置路径",
                        )

            except Exception as e:
                result.add_warning(
                    message=f"路径验证失败: {path} - {e}",
                    section=f"{section}.{field}",
                    code="PATH_VALIDATION_ERROR",
                )

    def _validate_scan_paths_from_config(self, result: ValidationResult) -> None:
        """从配置验证扫描路径"""
        scan_paths = self._get_value("file_scanner", "scan_paths", [])
        # 确保是列表类型
        if not isinstance(scan_paths, list):
            scan_paths = [scan_paths] if scan_paths else []
        self._validate_scan_paths(scan_paths, result)

    def _validate_scan_paths(
        self, scan_paths: List[str], result: Optional[ValidationResult] = None
    ) -> bool:
        """
        验证扫描路径配置

        Args:
            scan_paths: 扫描路径列表
            result: 验证结果对象（可选）

        Returns:
            bool: 是否有效
        """
        if result is None:
            result = ValidationResult()

        if not scan_paths:
            result.add_warning(
                message="未配置扫描路径，应用将无法索引文件",
                section="file_scanner.scan_paths",
                code="NO_SCAN_PATHS",
                suggestion="在设置中添加至少一个扫描目录",
            )
            return False

        paths = scan_paths if isinstance(scan_paths, list) else [scan_paths]

        # 过滤空字符串路径
        paths = [p for p in paths if p and str(p).strip()]
        if not paths:
            result.add_warning(
                message="扫描路径均为空值，应用将无法索引文件",
                section="file_scanner.scan_paths",
                code="EMPTY_SCAN_PATHS",
                suggestion="在设置中添加至少一个有效的扫描目录",
            )
            return False

        for path_str in paths:
            path = Path(str(path_str)).expanduser()

            if not path.exists():
                result.add_warning(
                    message=f"扫描路径不存在: {path}",
                    section="file_scanner.scan_paths",
                    code="SCAN_PATH_NOT_EXISTS",
                    suggestion=f"创建目录或从配置中移除: {path}",
                )
            elif not path.is_dir():
                result.add_error(
                    message=f"扫描路径不是目录: {path}",
                    section="file_scanner.scan_paths",
                    code="SCAN_PATH_NOT_DIR",
                )
            elif not os.access(path, os.R_OK):
                result.add_error(
                    message=f"扫描路径不可读: {path}",
                    section="file_scanner.scan_paths",
                    code="SCAN_PATH_NOT_READABLE",
                    suggestion="检查目录读取权限",
                )

        return len(result.errors) == 0

    def _validate_ai_model_config(self, result: ValidationResult) -> None:
        """验证AI模型配置"""
        enabled = self._getboolean("ai_model", "enabled", False)
        if not enabled:
            return

        mode = self._get_value("ai_model", "mode", "local")

        if mode == "api":
            api_config = self._get_value("ai_model", "api", {})
            api_key = (
                api_config.get("api_key", "") if isinstance(api_config, dict) else ""
            )
            if not api_key:
                result.add_warning(
                    message="API模式已启用但未配置API密钥",
                    section="ai_model.api.api_key",
                    code="API_KEY_MISSING",
                    suggestion="在设置中配置API密钥",
                )

            api_url = (
                api_config.get("api_url", "") if isinstance(api_config, dict) else ""
            )
            if not api_url:
                result.add_error(
                    message="API模式需要配置API URL",
                    section="ai_model.api.api_url",
                    code="API_URL_MISSING",
                )

        # 检查依赖
        if not any("requests" in str(spec) for spec in globals()):
            # 检查 requests 是否已导入（通过 importlib）
            try:
                import importlib.util

                spec = importlib.util.find_spec("requests")
                if spec is None:
                    raise ImportError()
            except (ImportError, ValueError):
                result.add_error(
                    message="AI功能需要 requests 库: pip install requests",
                    section="ai_model.enabled",
                    code="MISSING_DEPENDENCY",
                )

    def _validate_permissions(self, result: ValidationResult) -> None:
        """验证运行权限"""
        # 检查是否为管理员/root运行（不建议）
        if os.name == "nt":
            try:
                import ctypes

                if ctypes.windll.shell32.IsUserAnAdmin():
                    result.add_info(
                        message="应用以管理员权限运行（通常不需要）",
                        section="system",
                        code="RUNNING_AS_ADMIN",
                        suggestion="考虑使用普通用户权限运行",
                    )
            except Exception:
                pass
        else:
            try:
                if os.geteuid() == 0:
                    result.add_warning(
                        message="应用以 root 权限运行，存在安全风险",
                        section="system",
                        code="RUNNING_AS_ROOT",
                        suggestion="使用普通用户运行应用",
                    )
            except AttributeError:
                pass

    def _validate_numeric_ranges_from_config(self, result: ValidationResult) -> None:
        """从配置验证数值范围"""
        validations = [
            ("search", "text_weight", 0.0, 1.0),
            ("search", "vector_weight", 0.0, 1.0),
            ("file_scanner", "max_file_size", 1, 10000),
            ("interface", "max_preview_size", 1024, 100 * 1024 * 1024),
        ]

        for section, key, min_val, max_val in validations:
            try:
                value = self._getfloat(section, key, None)
                if value is None:
                    continue

                if value < min_val or value > max_val:
                    msg = (
                        f"配置值超出范围: [{section}].{key} = {value} "
                        f"(应在 {min_val}-{max_val} 之间)"
                    )
                    result.add_warning(
                        message=msg,
                        section=f"{section}.{key}",
                        code="NUMERIC_RANGE_ERROR",
                        suggestion="调整配置值到有效范围",
                    )
            except (ValueError, TypeError):
                result.add_error(
                    message=f"配置值类型错误: [{section}].{key}",
                    section=f"{section}.{key}",
                    code="NUMERIC_TYPE_ERROR",
                )

        # 验证权重之和
        try:
            text_weight = self._getfloat("search", "text_weight", 0.6)
            vector_weight = self._getfloat("search", "vector_weight", 0.4)
            if abs(text_weight + vector_weight - 1.0) > 0.01:
                result.add_warning(
                    message=f"搜索权重之和不等于1.0: {text_weight + vector_weight}",
                    section="search.text_weight/search.vector_weight",
                    code="WEIGHT_SUM_ERROR",
                    suggestion="调整权重使 text_weight + vector_weight = 1.0",
                )
        except Exception:
            pass

    def _validate_numeric_ranges(self, config: Dict[str, Any]) -> bool:
        """
        验证数值范围（用于测试API）

        Args:
            config: 配置字典（支持扁平结构）

        Returns:
            bool: 是否有效
        """
        result = ValidationResult()
        self.config = config

        # 支持扁平配置结构（测试用）
        validations = [
            ("text_weight", 0.0, 1.0),
            ("vector_weight", 0.0, 1.0),
        ]

        for key, min_val, max_val in validations:
            try:
                value = config.get(key)
                if value is None:
                    continue

                value = float(value)
                if value < min_val or value > max_val:
                    msg = (
                        f"配置值超出范围: {key} = {value} "
                        f"(应在 {min_val}-{max_val} 之间)"
                    )
                    result.add_warning(
                        message=msg,
                        section=key,
                        code="NUMERIC_RANGE_ERROR",
                    )
            except (ValueError, TypeError):
                result.add_error(
                    message=f"配置值类型错误: {key}",
                    section=key,
                    code="NUMERIC_TYPE_ERROR",
                )

        return len(result.errors) == 0 and not result.has_warnings()

    def _validate_dependencies(self, result: ValidationResult) -> None:
        """验证必要的依赖项"""
        critical_dependencies = [
            ("tantivy", "搜索引擎核心库"),
            ("numpy", "数值计算库"),
            ("yaml", "YAML配置解析"),
        ]

        for module, description in critical_dependencies:
            try:
                __import__(module)
            except ImportError:
                result.add_error(
                    message=f"缺少必要依赖: {module} ({description})",
                    code="MISSING_CRITICAL_DEPENDENCY",
                    suggestion=f"pip install {module}",
                )

    def print_report(self, result: Optional[ValidationResult] = None) -> None:
        """打印验证报告"""
        if result is None:
            # 向后兼容：使用旧版验证结果
            errors = [i for i in self.issues if i.level == "error"]
            warnings = [i for i in self.issues if i.level == "warning"]
            infos = [i for i in self.issues if i.level == "info"]
        else:
            errors = result.errors
            warnings = result.warnings
            infos = result.infos

        if not errors and not warnings and not infos:
            logger.info("✓ 配置验证通过，未发现问题")
            return

        if errors:
            logger.error(f"\n配置验证发现 {len(errors)} 个错误:")
            for issue in errors:
                logger.error(f"  ✗ [{issue.code or 'ERROR'}] {issue.message}")
                if issue.suggestion:
                    logger.error(f"    建议: {issue.suggestion}")

        if warnings:
            logger.warning(f"\n配置验证发现 {len(warnings)} 个警告:")
            for issue in warnings:
                logger.warning(f"  ⚠ [{issue.code or 'WARN'}] {issue.message}")
                if issue.suggestion:
                    logger.warning(f"    建议: {issue.suggestion}")

        if infos:
            logger.info(f"\n配置验证提示 ({len(infos)} 个):")
            for issue in infos:
                logger.info(f"  ℹ [{issue.code or 'INFO'}] {issue.message}")


def validate_config_on_startup(config_loader) -> bool:
    """
    启动时验证配置的便捷函数

    Args:
        config_loader: 配置加载器

    Returns:
        bool: 是否通过验证（无错误）
    """
    validator = ConfigValidator(config_loader)
    result = validator.validate()
    validator.print_report(result)

    if result.has_errors():
        raise ConfigValidationError(
            "配置验证失败，请修复上述错误后重试",
            validation_errors=[
                {
                    "code": i.code,
                    "message": i.message,
                    "section": i.section,
                    "key": i.key,
                }
                for i in result.errors
            ],
        )

    return True


def validate_config_or_warn(config: Dict[str, Any]) -> ValidationResult:
    """
    验证配置并返回结果（不抛出异常）

    Args:
        config: 配置字典

    Returns:
        ValidationResult: 验证结果
    """
    validator = ConfigValidator()
    result = validator.validate(config)

    # 打印警告
    for warning in result.warnings:
        logger.warning(f"配置警告: {warning.message}")

    return result
