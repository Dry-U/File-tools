# File Tools - 智能文件检索与问答系统

基于 Python 的本地文件智能管理工具，提供高效文件扫描、语义检索和 AI 增强问答功能。

## 核心特性

- **混合检索**：结合 Tantivy 全文检索和 HNSWLib 向量检索
- **智能问答**：基于 RAG 技术的文档智能问答，支持会话管理
- **多格式支持**：PDF、Word、Excel、PPT、Markdown 等多种文档格式
- **实时监控**：自动监控文件变化并增量更新索引
- **设置持久化**：前端设置可直接保存到配置文件
- **历史记录**：智能问答支持多会话历史记录
- **日志**：结构化日志记录，支持 JSON 格式和上下文追踪
- **高性能**：优化的索引和搜索算法，支持大规模文档库

## 技术栈

- **核心框架 (Core Framework):** `FastAPI` + `Pywebview`
  - **理由:** FastAPI 提供高性能异步 API 服务，Pywebview 将 Web 界面封装为原生桌面窗口。
  - **架构:** API 层采用模块化路由设计，按功能划分为搜索、聊天、配置、目录管理等独立模块，便于维护和扩展。
- **全文检索 (Full-Text Search):** `tantivy`
  - **理由:** 基于 Rust 的高性能搜索引擎，提供卓越的索引和查询速度，内存占用低。
- **向量检索 (Vector Search):** `hnswlib`
  - **理由:** 轻量级、零依赖的向量检索库，性能优异且易于在 Windows/Linux/macOS 等多平台部署。
- **嵌入模型 (Embedding Model):** `fastembed` with `bge-small-zh` 或 `ModelScope`
  - **理由:** 专为速度优化的嵌入计算库，支持多种模型提供商，资源消耗小。
- **LLM 推理 (LLM Inference):** `llama-cpp-python` (本地) 或 OpenAI 兼容 API (远程)
  - **策略:** 默认关闭，按需启用，以节约资源。
- **文档处理 (Document Processing):** `PyMuPDF`, `pdfplumber`, `python-docx`, `openpyxl`, `markdown`
  - **策略:** 采用优化的解析链（PyMuPDF + pdfplumber），10秒超时控制，避免大文件阻塞。
- **前端资源 (Frontend):** `Bootstrap`, 原生 `JS`, `bootstrap-icons`
  - **策略:** 保持前端资源的轻量化，通过 Pywebview 原生窗口呈现。

## 项目结构

```
File-tools/
├── backend/                # 后端服务
│   ├── api/                # API接口层
│   │   ├── main.py         # FastAPI应用主文件
│   │   ├── models.py       # 请求/响应模型
│   │   ├── dependencies.py # 依赖注入
│   │   └── routes/         # 路由模块
│   │       ├── search.py   # 搜索/预览
│   │       ├── chat.py     # 聊天/会话
│   │       ├── config.py   # 配置管理
│   │       ├── directory.py# 目录管理
│   │       └── system.py   # 健康检查
│   ├── core/               # 核心业务逻辑
│   │   ├── document_parser.py      # 文档解析器
│   │   ├── file_scanner.py         # 文件扫描器
│   │   ├── file_monitor.py         # 文件监控器
│   │   ├── index_manager.py        # 索引管理器
│   │   ├── search_engine.py        # 搜索引擎
│   │   ├── model_manager.py        # 模型管理器
│   │   ├── rag_pipeline.py         # RAG 问答流水线
│   │   ├── text_chunker.py         # 文本分块器
│   │   ├── chat_history_db.py      # 聊天历史数据库
│   │   ├── query_processor.py      # 查询处理器
│   │   ├── privacy_guard.py        # 隐私保护
│   │   ├── sharded_cache.py        # 缓存（基于 cachetools TTLCache）
│   │   ├── vram_manager.py         # VRAM 管理器
│   │   ├── constants.py            # 常量定义
│   │   └── exceptions.py           # 自定义异常
│   └── utils/              # 工具模块
│       ├── config_loader.py        # 配置加载
│       ├── config_validator.py     # 配置验证
│       ├── logger.py               # 日志系统
│       ├── app_paths.py            # 路径管理
│       ├── metrics.py              # 性能指标
│       └── network.py              # 网络工具
├── frontend/               # 前端界面
│   ├── index.html          # 主页面
│   └── static/             # 静态资源
│       ├── css/style.css   # 样式表
│       └── js/             # JS模块
│           ├── main.js     # 入口
│           └── modules/    # 功能模块
├── tests/                  # 测试代码
│   ├── unit/               # 单元测试
│   ├── integration/        # 集成测试
│   ├── api/                # API测试
│   └── e2e/                # 端到端测试
├── data/                   # 运行时数据（不纳入版本控制）
│   ├── tantivy_index/      # Tantivy 索引
│   ├── hnsw_index/         # HNSWLib 索引
│   ├── metadata/           # 元数据
│   ├── models/             # 嵌入模型文件
│   ├── cache/              # 缓存文件
│   └── temp/               # 临时文件
├── docs/                   # 项目文档
│   ├── DEVELOPER_GUIDE.md  # 开发者文档
│   └── USAGE_GUIDE.md      # 使用手册
├── scripts/                # 辅助脚本
│   ├── version_manager.py  # 版本管理
│   ├── build_installer.py  # 安装包构建
│   ├── run_tests.py        # 测试运行
│   ├── allure_report.py    # Allure 报告管理
│   └── install_allure.py   # Allure CLI 安装
├── config.yaml             # 配置文件
├── main.py                 # 应用入口
├── build.bat               # 构建脚本（Windows EXE）
├── file-tools.spec         # PyInstaller 配置
├── pyproject.toml          # 项目配置与依赖
└── uv.lock                 # 依赖锁定文件
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
  enabled: true  # 启用 AI 问答功能
  mode: "api"  # "local" 或 "api"
  api:
    provider: "siliconflow"  # 或 "deepseek", "custom"
    api_url: "https://api.siliconflow.cn/v1/chat/completions"
    api_key: "your-api-key"
    model_name: "deepseek-ai/DeepSeek-V2.5"
  sampling:
    temperature: 0.7
    max_tokens: 2048

file_scanner:
  scan_paths:
    - "C:/Users/YourName/Documents"

monitor:
  enabled: true
  directories:
    - "C:/Users/YourName/Documents"

search:
  text_weight: 0.6
  vector_weight: 0.4
```

启动应用：

```bash
# 启动桌面应用（推荐）
uv run python main.py

# 或直接使用 python (需确保依赖已安装)
python main.py
```

启动后会打开一个标题为「File Tools」的原生桌面窗口。
API 服务在 `http://127.0.0.1:8000` 上运行；若端口被占用，将自动选择 `8001–8010` 中的可用端口。

**API 端点：**

系统：
- 健康检查：`GET /api/health`
- 就绪检查：`GET /api/health/ready`
- 存活检查：`GET /api/health/live`
- 重建索引：`POST /api/rebuild-index`
- 重建进度：`GET /api/rebuild-progress`
- 流式重建：`POST /api/rebuild-index/stream`
- 版本信息：`GET /api/version`
- 初始化状态：`GET /api/initialization-status`

搜索：
- 搜索：`POST /api/search`
- 文件预览：`POST /api/preview`

对话：
- 问答：`POST /api/chat`
- 获取会话列表：`GET /api/sessions`
- 删除会话：`DELETE /api/sessions/{session_id}`
- 获取会话消息：`GET /api/sessions/{session_id}/messages`

配置：
- 获取配置：`GET /api/config`
- 更新配置：`POST /api/config`
- 测试模型连接：`GET /api/model/test`

目录管理：
- 获取目录列表：`GET /api/directories`
- 添加目录：`POST /api/directories`
- 删除目录：`DELETE /api/directories`
- 浏览目录（打开对话框）：`POST /api/directories/browse`

## 核心功能

### 1. 文件扫描与索引

- 自动扫描指定目录下的文档
- 支持增量索引和实时更新
- 多格式文档内容提取（PyMuPDF + pdfplumber，10秒超时）
- 智能文件过滤（排除系统文件、媒体文件等）
- 索引重建进度实时反馈（支持 SSE 流式进度）

### 2. 混合检索

- **关键词检索**：基于 Tantivy 的高性能全文检索
- **语义检索**：基于 HNSWLib 的向量相似度检索
- **RRF 排序**：使用倒数排名融合（Reciprocal Rank Fusion）合并结果，提升相关性
- **高级过滤**：支持文件类型、大小、日期等过滤条件

### 3. 智能问答 (Smart Chat)

- **交互式界面**：全新的聊天对话界面，支持上下文连续问答
- **RAG 技术**：基于检索增强生成，精准回答用户提问
- **会话管理**：支持多会话管理，历史记录自动保存
- **引用溯源**：回答中包含来源文档引用，点击即可查看原文
- **模型支持**：支持本地模型（WSL）或远程 API（OpenAI 兼容）
- **参数调节**：支持 temperature、top_p、max_tokens 等采样参数实时调整

### 4. 文件监控

- 实时监控文件系统变化
- 自动触发索引更新
- 支持批量处理优化性能

### 5. 目录管理

- 图形界面添加/删除扫描目录
- 支持系统文件对话框浏览
- 目录状态实时显示（存在性、扫描状态、监控状态、文件数）
- 路径安全检查，防止路径遍历攻击

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

# 运行单元测试
pytest tests/unit/ -v

# 运行集成测试
pytest tests/integration/ -v

# 运行 API 测试
pytest tests/api/ -v

# 运行端到端测试
pytest tests/e2e/ -v

# 运行无障碍测试（需要启动服务）
pytest tests/e2e/test_accessibility.py -v

# 性能测试
pytest tests/integration/test_performance.py -v

# 生成 Allure 测试报告
python scripts/run_tests.py --allure

# 按分类运行并生成报告
python scripts/run_tests.py unit --allure
python scripts/run_tests.py integration --allure
```

### 测试报告

测试报告输出到 `reports/` 目录：
- HTML 报告：`reports/test_report.html`
- 覆盖率报告：`reports/coverage/index.html`
- Allure 报告：`reports/allure-report/index.html`

Allure 报告管理：
```bash
python scripts/allure_report.py generate  # 生成报告
python scripts/allure_report.py open      # 生成并打开报告
python scripts/allure_report.py serve     # 本地服务方式查看 (http://localhost:4040)
python scripts/allure_report.py clean     # 清理所有报告
```

## 打包为 .exe

可以使用 PyInstaller 将应用程序打包为独立的 .exe 文件：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 使用 build.bat 多版本构建
./build.bat cpu          # CPU 版本（默认，含完整 AI 功能）
./build.bat gpu          # GPU 版本（支持 CUDA 加速）
./build.bat slim         # Slim 版本（仅文件搜索，体积最小）
./build.bat cpu noupx    # 不使用 UPX 压缩
./build.bat cpu bump     # 构建并递增版本号
./build.bat cpu installer # 构建并创建 NSIS 安装包
```

多版本构建脚本支持以下参数：
- `cpu` - CPU 版本（默认）
- `gpu` - GPU 版本
- `slim` - 精简版本
- `noupx` - 禁用 UPX 压缩
- `bump` - 递增 VERSION 中的版本号
- `installer` - 创建 NSIS 安装包

打包后的可执行文件将在 `dist/` 目录中生成（目录名如 `FileTools-v1.0.0-cpu/`）。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 作者：Darian
- 邮箱：Dar1an@126.com
- 项目主页：https://github.com/Dry-U/File-tools
