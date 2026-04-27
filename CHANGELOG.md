# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 支持多提供商 API Keys 缓存（SiliconFlow、DeepSeek、Custom）
- 新增 `model_size_params` 自动检测本地模型大小（1B/3B/7B/13B/70B）

### Changed
- **配置保存修复**：scan_paths 和 monitor.directories 为空时不再自动填充 Documents 路径
- **本地模型默认端口**：从 `8000` 改为 `11434`（Ollama 默认端口）
- 统一采样参数结构：`ai_model.sampling` 和 `ai_model.penalties` 层级
- ConfigLoader 支持自动创建用户数据目录

### Fixed
- 修复配置保存后 scan_paths/directories 被重置为空的问题
- 修复 `api_key` 返回时未正确掩码的问题
- 修复文件监控目录遍历攻击安全漏洞

### Security
- 目录路径验证增强（防止路径遍历攻击）
- API Keys 返回时强制掩码处理

## [1.1.2] - 2026-04-15

### Added
- Added changelogen script for automated changelog generation
- Added macOS x64 build to CI pipeline
- Added Rust cache for faster CI builds
- Added Release Drafter configuration for automated releases

### Changed
- Improved CI/CD pipeline with parallel testing and optimized build caching
- Enhanced embedding and search configurations
- Improved memory management in vector operations
- Refined documentation structure based on open source best practices
- Updated Ruff configuration to eliminate linting warnings

### Fixed
- Fixed API keys exposure in /config response (security fix)
- Fixed race condition in search by passing query as parameter
- Fixed nested lock deadlock risk in index_manager
- Fixed USAGE_GUIDE.md ai_model config example
- Fixed E2E test stability by replacing fixed waits with smart polling

### Performance
- Cached file content in search_vector to avoid repeated I/O

## [1.1.1] - 2025-04-10

### Added
- Added comprehensive E2E testing with pytest-playwright
- Added accessibility testing with axe-core
- Added performance benchmarking tests
- Added Allure reporting for test results

### Changed
- Migrated from pip to uv for dependency management
- Updated Python version support to 3.9-3.12
- Improved error handling with custom exception classes
- Enhanced logging with structured JSON format

### Fixed
- Fixed file monitor memory leaks
- Fixed document parser timeout handling
- Fixed RAG pipeline context management issues
- Fixed search engine result deduplication

## [1.1.0] - 2025-03-15

### Added
- Added RAG (Retrieval-Augmented Generation) pipeline for intelligent Q&A
- Added multi-session chat history with SQLite backend
- Added hybrid search combining BM25 and vector similarity
- Added file type filtering in search results
- Added real-time file monitoring with watchdog
- Added system tray integration

### Changed
- Replaced Whoosh with Tantivy for full-text search
- Migrated from HNSW to HNSWLib for vector search
- Refactored configuration system with YAML support
- Improved frontend UI with Bootstrap 5

### Fixed
- Fixed PDF parsing memory issues
- Fixed concurrent file scanning race conditions
- Fixed Windows path handling in file scanner
- Fixed embedding cache invalidation

## [1.0.0] - 2025-01-20

### Added
- Initial release of FileTools
- Full-text search with Whoosh
- Basic vector search with HNSW
- File scanning and indexing
- Document parsing for PDF, Word, Excel, PowerPoint
- Tauri-based desktop application
- FastAPI backend server
- Configuration management
- Basic web UI

### Features
- Local file indexing and search
- Multi-format document support
- Cross-platform support (Windows, Linux, macOS)
- PyInstaller packaging for Python backend
- NSIS and MSI installer generation

---

## Release Notes Format

Each release follows this format:

```
## [Version] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Now removed features

### Fixed
- Bug fixes

### Security
- Security improvements
```

## Versioning Guide

- **MAJOR**: Breaking changes that require user action
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

## Support

For upgrade assistance or questions about changes:
- GitHub Issues: https://github.com/Dariandai/File-tools/issues
- Email: Dar1an@126.com
