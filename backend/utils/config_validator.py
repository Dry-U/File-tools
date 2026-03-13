#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置验证模块

在应用启动时验证配置的有效性，提供友好的错误提示。
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from backend.core.exceptions import ConfigValidationError
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """验证问题"""
    severity: str  # 'error', 'warning', 'info'
    code: str
    message: str
    field: Optional[str] = None
    suggestion: Optional[str] = None


class ConfigValidator:
    """配置验证器"""

    # 必要的配置节
    REQUIRED_SECTIONS = [
        'system',
        'file_scanner',
        'search',
        'monitor',
        'embedding',
        'ai_model',
        'rag',
        'interface',
        'advanced',
        'index',
    ]

    # 必要的配置项
    REQUIRED_FIELDS = {
        'system': ['data_dir', 'log_dir'],
        'file_scanner': ['scan_paths'],
        'search': ['text_weight', 'vector_weight'],
    }

    def __init__(self, config_loader):
        self.config = config_loader
        self.issues: List[ValidationIssue] = []

    def validate(self) -> Tuple[bool, List[ValidationIssue]]:
        """
        执行完整验证

        Returns:
            tuple: (是否通过, 问题列表)
        """
        self.issues = []

        # 1. 验证必要配置节
        self._validate_required_sections()

        # 2. 验证必要配置项
        self._validate_required_fields()

        # 3. 验证路径可写性
        self._validate_paths()

        # 4. 验证扫描路径
        self._validate_scan_paths()

        # 5. 验证AI模型配置
        self._validate_ai_model_config()

        # 6. 验证权限
        self._validate_permissions()

        # 7. 验证数值范围
        self._validate_numeric_ranges()

        # 8. 验证依赖项
        self._validate_dependencies()

        has_errors = any(i.severity == 'error' for i in self.issues)
        return not has_errors, self.issues

    def _validate_required_sections(self) -> None:
        """验证必要的配置节是否存在"""
        for section in self.REQUIRED_SECTIONS:
            if section not in self.config.config:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='MISSING_SECTION',
                    message=f'配置节 [{section}] 不存在，将使用默认值',
                    field=section,
                    suggestion=f'在配置文件中添加 [{section}] 节'
                ))

    def _validate_required_fields(self) -> None:
        """验证必要的配置项"""
        for section, fields in self.REQUIRED_FIELDS.items():
            if section not in self.config.config:
                continue

            for field in fields:
                value = self.config.get(section, field, None)
                if value is None or value == '':
                    self.issues.append(ValidationIssue(
                        severity='error' if section in ['system'] else 'warning',
                        code='MISSING_REQUIRED_FIELD',
                        message=f'必要配置项缺失: [{section}].{field}',
                        field=f'{section}.{field}',
                        suggestion=f'在配置文件中设置 {section}.{field}'
                    ))

    def _validate_paths(self) -> None:
        """验证路径配置"""
        path_fields = [
            ('system', 'data_dir'),
            ('system', 'log_dir'),
            ('system', 'cache_dir'),
            ('system', 'temp_dir'),
            ('index', 'tantivy_path'),
            ('index', 'hnsw_path'),
            ('index', 'metadata_path'),
        ]

        for section, field in path_fields:
            path_str = self.config.get(section, field, None)
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
                        self.issues.append(ValidationIssue(
                            severity='error',
                            code='PATH_NOT_WRITABLE',
                            message=f'无法创建目录 {parent}: 权限不足',
                            field=f'{section}.{field}',
                            suggestion='检查目录权限或更改配置路径'
                        ))
                        continue

                # 检查是否可写
                if path.exists():
                    if not os.access(path, os.W_OK):
                        self.issues.append(ValidationIssue(
                            severity='error',
                            code='PATH_NOT_WRITABLE',
                            message=f'目录不可写: {path}',
                            field=f'{section}.{field}',
                            suggestion='更改目录权限或修改配置路径'
                        ))

            except Exception as e:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='PATH_VALIDATION_ERROR',
                    message=f'路径验证失败: {path} - {e}',
                    field=f'{section}.{field}'
                ))

    def _validate_scan_paths(self) -> None:
        """验证扫描路径配置"""
        scan_paths = self.config.get('file_scanner', 'scan_paths', [])

        if not scan_paths:
            self.issues.append(ValidationIssue(
                severity='warning',
                code='NO_SCAN_PATHS',
                message='未配置扫描路径，应用将无法索引文件',
                field='file_scanner.scan_paths',
                suggestion='在设置中添加至少一个扫描目录'
            ))
            return

        paths = scan_paths if isinstance(scan_paths, list) else [scan_paths]

        for path_str in paths:
            path = Path(str(path_str)).expanduser()

            if not path.exists():
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='SCAN_PATH_NOT_EXISTS',
                    message=f'扫描路径不存在: {path}',
                    field='file_scanner.scan_paths',
                    suggestion=f'创建目录或从配置中移除: {path}'
                ))
            elif not path.is_dir():
                self.issues.append(ValidationIssue(
                    severity='error',
                    code='SCAN_PATH_NOT_DIR',
                    message=f'扫描路径不是目录: {path}',
                    field='file_scanner.scan_paths'
                ))
            elif not os.access(path, os.R_OK):
                self.issues.append(ValidationIssue(
                    severity='error',
                    code='SCAN_PATH_NOT_READABLE',
                    message=f'扫描路径不可读: {path}',
                    field='file_scanner.scan_paths',
                    suggestion='检查目录读取权限'
                ))

    def _validate_ai_model_config(self) -> None:
        """验证AI模型配置"""
        enabled = self.config.getboolean('ai_model', 'enabled', False)
        if not enabled:
            return

        mode = self.config.get('ai_model', 'mode', 'local')

        if mode == 'api':
            api_key = self.config.get('ai_model', 'api', {}).get('api_key', '')
            if not api_key:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='API_KEY_MISSING',
                    message='API模式已启用但未配置API密钥',
                    field='ai_model.api.api_key',
                    suggestion='在设置中配置API密钥'
                ))

            api_url = self.config.get('ai_model', 'api', {}).get('api_url', '')
            if not api_url:
                self.issues.append(ValidationIssue(
                    severity='error',
                    code='API_URL_MISSING',
                    message='API模式需要配置API URL',
                    field='ai_model.api.api_url'
                ))

        # 检查依赖
        try:
            import requests
        except ImportError:
            self.issues.append(ValidationIssue(
                severity='error',
                code='MISSING_DEPENDENCY',
                message='AI功能需要 requests 库: pip install requests',
                field='ai_model.enabled'
            ))

    def _validate_permissions(self) -> None:
        """验证运行权限"""
        # 检查是否为管理员/root运行（不建议）
        if os.name == 'nt':
            try:
                import ctypes
                if ctypes.windll.shell32.IsUserAnAdmin():
                    self.issues.append(ValidationIssue(
                        severity='info',
                        code='RUNNING_AS_ADMIN',
                        message='应用以管理员权限运行（通常不需要）',
                        suggestion='考虑使用普通用户权限运行'
                    ))
            except Exception:
                pass
        else:
            if os.geteuid() == 0:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='RUNNING_AS_ROOT',
                    message='应用以 root 权限运行，存在安全风险',
                    suggestion='使用普通用户运行应用'
                ))

    def _validate_numeric_ranges(self) -> None:
        """验证数值范围"""
        validations = [
            ('search', 'text_weight', 0.0, 1.0),
            ('search', 'vector_weight', 0.0, 1.0),
            ('file_scanner', 'max_file_size', 1, 10000),
            ('interface', 'max_preview_size', 1024, 100 * 1024 * 1024),
        ]

        for section, field, min_val, max_val in validations:
            try:
                value = self.config.getfloat(section, field, None)
                if value is None:
                    continue

                if value < min_val or value > max_val:
                    self.issues.append(ValidationIssue(
                        severity='warning',
                        code='NUMERIC_RANGE_ERROR',
                        message=f'配置值超出范围: [{section}].{field} = {value} (应在 {min_val}-{max_val} 之间)',
                        field=f'{section}.{field}',
                        suggestion=f'调整配置值到有效范围'
                    ))
            except (ValueError, TypeError):
                self.issues.append(ValidationIssue(
                    severity='error',
                    code='NUMERIC_TYPE_ERROR',
                    message=f'配置值类型错误: [{section}].{field}',
                    field=f'{section}.{field}'
                ))

        # 验证权重之和
        try:
            text_weight = self.config.getfloat('search', 'text_weight', 0.6)
            vector_weight = self.config.getfloat('search', 'vector_weight', 0.4)
            if abs(text_weight + vector_weight - 1.0) > 0.01:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    code='WEIGHT_SUM_ERROR',
                    message=f'搜索权重之和不等于1.0: {text_weight + vector_weight}',
                    field='search.text_weight/search.vector_weight',
                    suggestion='调整权重使 text_weight + vector_weight = 1.0'
                ))
        except Exception:
            pass

    def _validate_dependencies(self) -> None:
        """验证必要的依赖项"""
        critical_dependencies = [
            ('tantivy', '搜索引擎核心库'),
            ('numpy', '数值计算库'),
            ('yaml', 'YAML配置解析'),
        ]

        for module, description in critical_dependencies:
            try:
                __import__(module)
            except ImportError:
                self.issues.append(ValidationIssue(
                    severity='error',
                    code='MISSING_CRITICAL_DEPENDENCY',
                    message=f'缺少必要依赖: {module} ({description})',
                    suggestion=f'pip install {module}'
                ))

    def print_report(self) -> None:
        """打印验证报告"""
        if not self.issues:
            logger.info("✓ 配置验证通过，未发现问题")
            return

        errors = [i for i in self.issues if i.severity == 'error']
        warnings = [i for i in self.issues if i.severity == 'warning']
        infos = [i for i in self.issues if i.severity == 'info']

        if errors:
            logger.error(f"\n配置验证发现 {len(errors)} 个错误:")
            for issue in errors:
                logger.error(f"  ✗ [{issue.code}] {issue.message}")
                if issue.suggestion:
                    logger.error(f"    建议: {issue.suggestion}")

        if warnings:
            logger.warning(f"\n配置验证发现 {len(warnings)} 个警告:")
            for issue in warnings:
                logger.warning(f"  ⚠ [{issue.code}] {issue.message}")
                if issue.suggestion:
                    logger.warning(f"    建议: {issue.suggestion}")

        if infos:
            logger.info(f"\n配置验证提示 ({len(infos)} 个):")
            for issue in infos:
                logger.info(f"  ℹ [{issue.code}] {issue.message}")


def validate_config_on_startup(config_loader) -> bool:
    """
    启动时验证配置的便捷函数

    Returns:
        bool: 是否通过验证（无错误）
    """
    validator = ConfigValidator(config_loader)
    passed, issues = validator.validate()
    validator.print_report()

    if not passed:
        raise ConfigValidationError(
            "配置验证失败，请修复上述错误后重试",
            validation_errors=[
                {"code": i.code, "message": i.message, "field": i.field}
                for i in issues if i.severity == 'error'
            ]
        )

    return True
