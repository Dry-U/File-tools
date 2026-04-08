# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供代码库工作指南。

## ⚠️ 重要：依赖管理

**必须使用 uv 管理所有 Python 依赖**：
```bash
# 创建虚拟环境
uv venv .venv

# 安装/更新依赖
uv sync

# 添加新依赖
uv add <package>

# 移除依赖
uv remove <package>

# 重建环境（依赖损坏时）
uv venv .venv --python 3.12 && uv sync
```

**禁止使用 pip/conda 等其他方式管理依赖**

## 项目架构

FileTools 是一个混合文件检索与 RAG（检索增强生成）系统，采用双重引擎搜索架构：

### 双重引擎搜索
- **文本搜索** (Tantivy - Rust 实现)：BM25 评分，支持精确匹配、模糊搜索、中文单字符搜索
- **向量搜索** (HNSWLib)：通过嵌入模型（fastembed/bge-small-zh 或 modelscope）实现语义相似度搜索
- **混合评分** (`backend/core/search_engine.py`)：归一化合并两种分数，默认 60% 文本 + 40% 向量，文件名匹配 +15-95  boost

### 核心流程
```
Tauri Desktop (Rust)
    ↓ 启动 Python 子进程
main.py → FastAPI Server (默认端口 18642)
    ↓
Startup → [IndexManager, SearchEngine, FileScanner, FileMonitor, RAGPipeline]
    ↓
FileScanner.scan_and_index() → DocumentParser → IndexManager.add_document()
    ↓
SearchEngine.search() → [search_text(), search_vector()] → _combine_results()
    ↓
RAGPipeline.query() → SearchEngine → ModelManager.generate()
    ↓
WebView2 ← FastAPI API ← 前端 (HTML/JS)
```

## 快速命令

### 运行应用

**Tauri Desktop Mode (推荐):**
```bash
# 启动 Tauri 开发模式
npm run tauri dev
```

**Python Server Only (调试 API):**
```bash
python main.py
```
自动在 http://127.0.0.1:18642 打开浏览器

### 开发命令
```bash
# 安装依赖
uv sync

# 运行所有测试
pytest tests/

# 按类别运行
pytest tests/unit/ -v          # 单元测试
pytest tests/integration/ -v   # 集成测试
pytest tests/api/ -v           # API 测试
pytest tests/e2e/ -v          # E2E 测试

# 性能测试
pytest tests/integration/test_performance.py -v

# 生成 Allure 报告
python scripts/run_tests.py --allure
python scripts/run_tests.py unit --allure
```

### 构建桌面应用

**Tauri 构建 (推荐):**
```bash
# 安装依赖
npm install

# 开发模式
npm run tauri dev

# 生产构建
npm run tauri build
```

**分步构建:**
```bash
python build_pyinstaller.py    # 1. 构建 Python 后端
npm run tauri build           # 2. 构建 Tauri + 安装包
```

**构建产物:**
- `src-tauri/target/release/filetools.exe` - Tauri 可执行文件
- `src-tauri/target/release/bundle/nsis/*.exe` - NSIS 安装包
- `src-tauri/target/release/bundle/msi/*.msi` - MSI 安装包

## 核心模块

### IndexManager (`backend/core/index_manager.py`)
- 管理双重索引系统（Tantivy 全文索引 + HNSWLib 向量索引）
- 处理文档的添加、更新、删除
- 关键方法：`add_document()`, `search_text()`, `search_vector()`

### SearchEngine (`backend/core/search_engine.py`)
- 整合文本搜索和向量搜索结果
- 使用 RRF（倒数排名融合）合并结果
- 关键方法：`search()`, `_combine_results()`

### FileScanner (`backend/core/file_scanner.py`)
- 扫描指定目录下的文档
- 支持多线程扫描和增量索引
- 关键方法：`scan_and_index()`, `_should_index()`

### RAGPipeline (`backend/core/rag_pipeline.py`)
- 管理对话历史，执行文档检索，生成 AI 回答
- 实现上下文管理和多轮对话
- 关键方法：`query()`, `_collect_documents()`

### DocumentParser (`backend/core/document_parser.py`)
- 文档解析链：PDF (PyMuPDF → pdfplumber → pdfminer → PyPDF2)、Word (python-docx → win32com)
- 每个解析器强制文件大小限制（10-100MB）防止内存问题
- 10 秒超时保护

### FileMonitor (`backend/core/file_monitor.py`)
- 使用 watchdog 的 Observer 模式
- 0.5 秒超时缓冲事件
- 委托给 `file_scanner.index_file()` 或回退到最小文档构造

## 全局状态

`backend/api/main.py` 使用模块级全局变量存储核心组件（在 `@app.on_event("startup")` 中初始化）：
```python
search_engine = None
file_scanner = None
index_manager = None
rag_pipeline = None
file_monitor = None
```

## 前端状态管理

- **Tauri 集成**：窗口控制（最小化/最大化/关闭）通过 Tauri 命令实现
- **设置持久化**：前端设置通过 `/api/config` 端点保存到 `config.yaml`
- **会话管理**：聊天会话通过 `/api/sessions` 管理，存储在 `RAGPipeline.session_histories`
- **模式切换**：双模式 UI（搜索/聊天），侧边栏内容切换

## Tauri 架构

**窗口控制** (`src-tauri/src/main.rs`)：
- `minimize_window` - 最小化窗口
- `toggle_maximize` - 最大化/还原切换
- `close_window` - 关闭窗口
- `is_maximized` - 查询窗口状态

**进程模型**：
- Tauri (Rust) 作为主进程，启动 Python FastAPI 子进程
- Python 运行于后台，提供 HTTP API
- WebView2 渲染前端，通过 HTTP 与 Python 通信

## Windows 特定代码

1. **DLL 加载** (`main.py`, `rag_pipeline.py`)：使用 `os.add_dll_directory()` 添加 Torch DLL 路径
2. **驱动器检测** (`file_monitor.py`)：未配置目录时使用 ctypes 枚举磁盘驱动器 (A-Z)
3. **COM 集成** (`document_parser.py`)：使用 win32com 解析旧版 .doc 和 Excel 回退

## 数据位置

- Tantivy 索引：`data/tantivy_index/`
- HNSW 向量索引：`data/hnsw_index/vector_index.bin`
- 向量元数据：`data/metadata/vector_metadata.json`
- Schema 版本：`data/metadata/schema_version.json`
- 日志：`data/logs/`
- 缓存：`data/cache/`

## API 端点

- `GET /` - 主页面
- `GET /api/health` - 健康检查 (`{"status": "healthy" | "starting"}`)
- `POST /api/search` - 搜索（支持 date_range, file_types 等过滤器）
- `POST /api/chat` - RAG 聊天（可选 session_id 用于会话历史）
- `POST /api/preview` - 文件预览
- `POST /api/rebuild-index` - 重建索引
- `GET /api/config` - 获取配置
- `POST /api/config` - 更新配置（持久化到 config.yaml）
- `GET /api/sessions` - 获取会话列表
- `DELETE /api/sessions/{session_id}` - 删除会话
- `/static/*` - 静态文件（来自 `frontend/static/`）

## 测试报告 (Allure)

报告生成到 `reports/` 目录：
- HTML 报告：`reports/test_report.html`
- 覆盖率：`reports/coverage/index.html`
- Allure 结果：`reports/allure-results/`
- Allure 报告：`reports/allure-report/index.html`

管理脚本：
```bash
python scripts/run_tests.py --allure
python scripts/run_tests.py unit --allure
python scripts/allure_report.py generate
python scripts/allure_report.py open
python scripts/allure_report.py serve
python scripts/allure_report.py clean
```

## 配置说明

关键配置节：
- `file_scanner.scan_paths`：索引目录列表（YAML 列表格式）
- `monitor.enabled`：是否启用 watchdog 文件监控
- `monitor.directories`：监控目录列表
- `search.text_weight` / `search.vector_weight`：混合搜索权重
- `embedding.provider`：`fastembed` 或 `modelscope`
- `ai_model.enabled`：启用 RAG 聊天
- `ai_model.interface_type`：`wsl` (Windows WSL) 或 `api` (远程)
- `ai_model.api_url`：远程 LLM API 端点
