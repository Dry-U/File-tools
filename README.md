# 智能文件检索与问答系统

基于 Python 的本地文件智能管理工具，提供高效文件扫描、语义检索和 AI 增强问答功能。

## 核心特性

-  **混合检索**：结合 Tantivy 全文检索和 HNSWLib 向量检索
-  **智能问答**：基于 RAG 技术的文档智能问答
-  **多格式支持**：PDF、Word、Excel、Markdown 等多种文档格式
-  **实时监控**：自动监控文件变化并增量更新索引
-  **日志**：结构化日志记录，支持 JSON 格式和上下文追踪
-  **高性能**：优化的索引和搜索算法，支持大规模文档库

## 技术栈

- **核心框架 (Core Framework):** `FastAPI` + `Pywebview`
  - **理由:** FastAPI 提供高性能异步 API 服务，Pywebview 将 Web 界面封装为原生桌面窗口。
- **全文检索 (Full-Text Search):** `tantivy`
  - **理由:** 基于 Rust 的高性能搜索引擎，提供卓越的索引和查询速度，内存占用低。
- **向量检索 (Vector Search):** `hnswlib`
  - **理由:** 轻量级、零依赖的向量检索库，性能优异且易于在 Windows/Linux/macOS 等多平台部署。
- **嵌入模型 (Embedding Model):** `fastembed` with `bge-small-zh` 或 `ModelScope`
  - **理由:** 专为速度优化的嵌入计算库，支持多种模型提供商，资源消耗小。
- **LLM 推理 (LLM Inference):** `llama-cpp-python` (本地) 或 OpenAI 兼容 API (远程)
  - **策略:** 默认关闭，按需启用，以节约资源。
- **文档处理 (Document Processing):** `pdfminer.six`, `python-docx`, `openpyxl`, `markdown`
  - **策略:** 选用轻量级、专注的解析库，避免引入 `pandas` 等大型依赖。
- **前端资源 (Frontend):** `Bootstrap`, 原生 `JS`, `bootstrap-icons`
  - **策略:** 保持前端资源的轻量化，通过 Pywebview 原生窗口呈现。

## 项目结构

```
File-tools/
├── backend/                # 后端服务
│   ├── api/                # API接口层
│   │   └── api.py          # FastAPI应用主文件
│   ├── core/               # 核心业务逻辑
│   │   ├── document_parser.py      # 文档解析器
│   │   ├── file_scanner.py         # 文件扫描器
│   │   ├── file_monitor.py         # 文件监控器
│   │   ├── index_manager.py        # 索引管理器
│   │   ├── search_engine.py        # 搜索引擎
│   │   ├── model_manager.py        # 模型管理器
│   │   ├── rag_pipeline.py         # RAG 问答流水线
│   │   └── vram_manager.py         # VRAM 管理器
│   └── utils/              # 工具模块
│       ├── config_loader.py        # 配置加载
│       └── logger.py               # 日志系统
├── frontend/               # 前端界面
│   ├── index.html          # 主页面
│   └── static/             # 静态资源 (CSS/JS)
├── tests/                  # 测试代码
├── data/                   # 数据存储
│   ├── index/              # 文本索引
│   ├── tantivy_index/      # Tantivy 索引
│   ├── hnsw_index/         # HNSWLib 索引
│   ├── metadata/           # 元数据
│   ├── cache/              # 缓存文件
│   └── logs/               # 日志文件
├── docs/                   # 项目文档
├── config.yaml             # 配置文件
├── main.py                 # 应用入口
└── pyproject.toml          # 项目配置
```

## 快速开始

### 环境要求

- Python 3.9 或更高版本
- 8GB 内存（推荐）
- Windows 10/11, macOS 10.15+, 或 Linux

### 安装

```bash
# 克隆项目
git clone https://github.com/Dry-U/File-tools.git
cd File-tools

# 安装依赖（推荐使用 uv）
uv sync

# 或使用 pip
pip install -e .
```

### 配置

编辑 `config.yaml` 设置扫描路径和其他参数：

```yaml
ai_model:
  enabled: true  # 启用 AI 问答功能 (默认 false)
  provider: "wsl" # 或 "api"

file_scanner:
  scan_paths:
    - "C:/Users/YourName/Documents"

monitor:
  enabled: true
  directories:
    - "C:/Users/YourName/Documents"

interface:
  theme: "light"  # 或 "dark"
  language: "zh_CN"
```

启动应用：

```bash
# 启动桌面应用（推荐）
uv run python main.py

# 或直接使用 python (需确保依赖已安装)
python main.py
```

启动后会打开一个标题为「智能文件检索与问答系统」的原生桌面窗口。
API 服务在 `http://127.0.0.1:8000` 上运行；若端口被占用，将自动选择 `8001–8010` 中的可用端口。

**API 端点：**
- 健康检查：`GET /api/health`
- 重建索引：`POST /api/rebuild-index`
- 搜索：`POST /api/search`
- 问答：`POST /api/chat`
- 文件预览：`POST /api/preview`

## 核心功能

### 1. 文件扫描与索引

- 自动扫描指定目录下的文档
- 支持增量索引和实时更新
- 多格式文档内容提取
- 智能文件过滤（排除系统文件、媒体文件等）

### 2. 混合检索

- **关键词检索**：基于 Tantivy 的高性能全文检索
- **语义检索**：基于 HNSWLib 的向量相似度检索
- **混合排序**：按权重融合文本与向量分数，提升相关性
- **高级过滤**：支持文件类型、大小、日期等过滤条件

### 3. 智能问答 (Smart Chat)

- **交互式界面**：全新的聊天对话界面，支持上下文连续问答
- **RAG 技术**：基于检索增强生成，精准回答用户提问
- **引用溯源**：回答中包含来源文档引用，点击即可查看原文
- **模型支持**：支持本地模型或远程 API

### 4. 文件监控

- 实时监控文件系统变化
- 自动触发索引更新
- 支持批量处理优化性能

## 性能指标

- 关键词检索：< 1 秒
- 语义检索：< 3 秒
- 问答生成：< 5 秒
- 支持规模：10 万+ 文档
- 内存使用：优化的内存管理，支持大规模索引

## 使用指南

详细使用说明请参阅 [使用手册](docs/USAGE_GUIDE.md)

## 开发指南

开发相关文档请参阅 [开发者文档](docs/DEVELOPER_GUIDE.md)

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_config_loader.py

# 性能测试
pytest tests/test_performance.py -v
```

## 打包为 .exe

可以使用 PyInstaller 将应用程序打包为独立的 .exe 文件：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 使用 spec 文件打包
pyinstaller file-tools.spec

# 或者直接使用 build 脚本
./build_exe.bat  # Windows
```

打包后的可执行文件将在 `dist/` 目录中生成。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 作者：Darian
- 邮箱：Dar1an@126.com
- 项目主页：https://github.com/Dry-U/File-tools
