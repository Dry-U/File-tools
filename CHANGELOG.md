# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added cross-platform E2E testing support with Playwright
- Added Rust cache for faster CI builds
- Added dependabot configuration for automated dependency updates
- Added code signing configuration placeholders for Windows and macOS
- Added Linux E2E tests in CI pipeline

### Changed
- Improved CI/CD pipeline with parallel testing across Windows, Linux, and macOS
- Updated Ruff configuration to eliminate linting warnings
- Enhanced E2E test stability by replacing fixed waits with smart polling
- Refined documentation structure based on open source best practices

### Fixed
- Fixed E501 line too long errors across backend codebase
- Fixed artifact download issues in E2E tests by adding version resolution step
- Fixed missing icon files for cross-platform builds
- Fixed MSI language configuration for Chinese localization

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
- GitHub Issues: https://github.com/Dry-U/File-tools/issues
- Email: Dar1an@126.com
