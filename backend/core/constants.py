#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
核心模块常量定义

此模块包含整个应用使用的常量定义，集中管理以避免硬编码值散布在代码中。
"""

# ============================================================================
# 默认配置常量
# ============================================================================

DEFAULT_MAX_WORKERS = 16
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_FILE_SIZE_MB = 100

# ============================================================================
# 评分权重常量 (搜索重排)
# ============================================================================

# 默认重排权重
DEFAULT_RERANK_BASE_WEIGHT = 0.30
DEFAULT_RERANK_FILENAME_WEIGHT = 0.40
DEFAULT_RERANK_KEYWORD_WEIGHT = 0.15
DEFAULT_RERANK_RECENCY_WEIGHT = 0.10
DEFAULT_RERANK_LENGTH_WEIGHT = 0.05

# 确保权重总和为1.0的验证
assert (
    abs(
        DEFAULT_RERANK_BASE_WEIGHT
        + DEFAULT_RERANK_FILENAME_WEIGHT
        + DEFAULT_RERANK_KEYWORD_WEIGHT
        + DEFAULT_RERANK_RECENCY_WEIGHT
        + DEFAULT_RERANK_LENGTH_WEIGHT
        - 1.0
    )
    < 1e-6
), "重排权重总和必须等于1.0"

# ============================================================================
# 文件名变体关键词
# ============================================================================

FILENAME_VARIANT_KEYWORDS = ["说明", "文档", "指南", "手册", "介绍", "简介"]

# ============================================================================
# 评分阈值常量
# ============================================================================

KEYWORD_SCORE_MAX = 30
LENGTH_PENALTY_THRESHOLD_HIGH = 10000
LENGTH_PENALTY_THRESHOLD_LOW = 5000

# ============================================================================
# 搜索相关常量
# ============================================================================

DEFAULT_MAX_RESULTS = 50
DEFAULT_TEXT_WEIGHT = 0.6
DEFAULT_VECTOR_WEIGHT = 0.4
DEFAULT_CACHE_TTL = 3600  # 秒
DEFAULT_CACHE_SIZE = 1000

# ============================================================================
# 加密相关常量
# ============================================================================

# OWASP 2023 推荐的 PBKDF2 迭代次数
PBKDF2_ITERATIONS = 480000
PBKDF2_KEY_LENGTH = 32

# ============================================================================
# 限流相关常量
# ============================================================================

DEFAULT_RATE_LIMIT_MAX_ENTRIES = 10000
DEFAULT_RATE_LIMIT_CLEANUP_INTERVAL = 3600  # 秒

# ============================================================================
# 文件预览相关常量
# ============================================================================

DEFAULT_MAX_PREVIEW_SIZE = 5242880  # 5MB
MAX_PREVIEW_LENGTH = 500000  # 字符 - 预览完整文档内容

# ============================================================================
# MIME 类型白名单 (用于文件预览安全)
# ============================================================================

ALLOWED_MIME_TYPES = frozenset(
    [
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/xml",
        "application/json",
        "application/xml",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
    ]
)

# ============================================================================
# 日志相关常量
# ============================================================================

LOG_FREQUENCY = 50  # 每处理50个文件记录一次日志
PROGRESS_FREQUENCY = 20  # 每20%报告一次进度
LOG_SAFE_MAX_LENGTH = 50  # 安全日志中路径的最大长度
