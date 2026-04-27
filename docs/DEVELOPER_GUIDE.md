# FileTools - 开发者指南

## 项目架构

### 整体架构

```
File-tools/
├── src-tauri/                    # Tauri 桌面应用 (Rust)
│   ├── Cargo.toml               # Rust 依赖
│   ├── tauri.conf.json          # Tauri 配置
│   ├── build.rs                 # 构建脚本
│   ├── bin/                     # PyInstaller 打包的后端
│   │   └── filetools-backend.exe
│   ├── src/
│   │   ├── main.rs             # 主入口 (启动 Python 后端)
│   │   └── lib.rs              # 库入口
│   ├── capabilities/            # Tauri 权限配置
│   │   └── main.json
│   └── icons/                   # 应用图标
│
├── backend/                      # Python 后端
│   ├── api/                     # API 接口层
│   │   ├── main.py             # FastAPI 应用 (657 行)
│   │   ├── models.py           # 请求/响应模型
│   │   ├── dependencies.py     # 依赖注入
│   │   └── routes/             # 路由模块
│   │       ├── search.py       # 搜索/预览
│   │       ├── chat.py         # 聊天/会话
│   │       ├── config.py       # 配置管理
│   │       ├── directory.py     # 目录管理
│   │       └── system.py       # 系统路由
│   │
│   ├── core/                   # 核心业务逻辑
│   │   ├── document_parser.py  # 文档解析
│   │   ├── file_scanner.py     # 文件扫描
│   │   ├── file_monitor.py     # 文件监控
│   │   ├── index_manager.py    # 索引管理
│   │   ├── search_engine.py   # 搜索引擎
│   │   ├── rag_pipeline.py     # RAG 流水线
│   │   ├── query_processor.py  # 查询处理器
│   │   ├── embedding_manager.py # 嵌入管理
│   │   └── vram_manager.py    # VRAM 管理
│   │
│   └── utils/                  # 工具模块
│       ├── config_loader.py    # 配置加载
│       ├── logger.py           # 日志系统
│       └── app_paths.py        # 路径工具
│
├── frontend/                    # 前端界面
│   ├── index.html
│   └── static/                 # 静态资源
│       ├── css/style.css       # 样式表
│       └── js/
│           ├── main.js          # 主入口
│           └── modules/        # JavaScript 模块
│               ├── tauri-api.js   # Tauri API 封装
│               ├── search.js      # 搜索模块
│               ├── chat.js         # 聊天模块
│               ├── settings.js     # 设置模块
│               ├── directory.js    # 目录模块
│               ├── ui.js           # UI 工具
│               └── utils.js        # 通用工具
│
├── tests/                      # 测试代码
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   ├── api/                   # API 测试
│   └── e2e/                   # E2E 测试
│
├── scripts/                    # 工具脚本
├── data/                      # 运行时数据
├── docs/                      # 项目文档
├── build_pyinstaller.py      # PyInstaller 构建脚本
├── main.py                   # Python FastAPI 入口
├── pyproject.toml            # Python 依赖
└── package.json            # Node.js 依赖
```

---

## 核心模块详解

### 1. IndexManager (索引管理器)

**功能**
- 管理双重索引系统（Tantivy 全文索引 + HNSWLib 向量索引）
- 处理文档的添加、更新、删除
- 提供搜索接口

**关键方法**
- `add_document(document)` - 添加文档到索引
- `update_document(document)` - 更新文档索引
- `delete_document(file_path)` - 从索引中删除文档
- `search_text(query, limit, filters)` - 文本搜索
- `search_vector(query, limit)` - 向量搜索
- `get_document_content(path)` - 获取文档内容

**设计要点**
- 使用 Tantivy 进行高性能全文检索
- 使用 HNSWLib 进行快速向量相似度搜索
- 支持中文分词（jieba）
- 实现单字符检索能力

### 2. SearchEngine (搜索引擎)

**功能**
- 整合文本搜索和向量搜索结果
- 实现混合检索算法
- 提供高级搜索功能

**关键方法**
- `search(query, filters)` - 执行混合搜索
- `_search_text(query, filters)` - 执行文本搜索
- `_search_vector(query, filters)` - 执行向量搜索
- `_combine_results(text_results, vector_results)` - 合并搜索结果

**设计要点**
- 使用 RRF（倒数排名融合）合并文本和向量搜索结果
- 实现 BM25 算法进行文本评分
- 提供结果去重和排序功能
- 支持高级过滤器

### 3. FileScanner (文件扫描器)

**功能**
- 扫描指定目录下的文档
- 识别支持的文件类型
- 调用索引管理器进行索引

**关键方法**
- `scan_and_index()` - 扫描并索引所有文件
- `_should_index(path)` - 判断是否应索引文件
- `_index_file(file_path)` - 索引单个文件
- `get_supported_file_types()` - 获取支持的文件类型

**设计要点**
- 支持多线程扫描
- 实现文件过滤机制
- 提供进度回调功能
- 支持增量索引

### 4. RAGPipeline (RAG 问答管道)

**功能**
- 管理对话历史
- 执行文档检索
- 生成 AI 回答

**关键方法**
- `query(query, session_id)` - 执行问答查询
- `_collect_documents(query)` - 收集相关文档
- `_build_prompt(query, documents, history_text)` - 构建提示词
- `_remember_turn(session_id, query, answer)` - 记录对话轮次

**设计要点**
- 实现上下文管理
- 支持多轮对话
- 提供文档聚合功能
- 实现智能回答生成

### 5. DirectoryManager (目录管理)

**功能**
- 管理扫描路径和监控目录
- 提供目录浏览对话框
- 目录状态跟踪

**关键方法**
- `get_directories()` - 获取所有管理的目录
- `add_directory(path)` - 添加新目录
- `remove_directory(path)` - 移除目录
- `browse_directory()` - 打开系统目录选择对话框

**设计要点**
- 路径安全验证（防止路径遍历）
- 统一处理扫描路径和监控目录
- 实时状态显示（存在性、扫描状态、监控状态、文件数）
- 支持 Windows/Linux/macOS 文件对话框

### 6. QueryProcessor (查询处理器)

**功能**
- 对输入查询进行预处理：中文分词（jieba）、关键词提取、停用词过滤
- 为文本搜索和向量搜索生成最优查询表示

### 7. EmbeddingManager (嵌入管理器)

**功能**
- 管理文本嵌入模型
- 支持 fastembed 和 modelscope 两种提供者
- 提供批量嵌入和缓存功能

---

## API 接口设计

### FastAPI 依赖注入系统

```python
def get_config_loader():
    """ConfigLoader 依赖注入"""
    if not hasattr(app.state, 'config_loader'):
        app.state.config_loader = ConfigLoader()
    return app.state.config_loader

def get_index_manager(config_loader = Depends(get_config_loader)):
    """IndexManager 依赖注入"""
    if not hasattr(app.state, 'index_manager'):
        from backend.core.index_manager import IndexManager
        app.state.index_manager = IndexManager(config_loader)
    return app.state.index_manager
```

### 路由结构（模块化设计）

API 路由按功能划分为独立模块，每个模块负责特定的功能域：

```
backend/api/routes/
├── search.py      # 搜索和预览 (/api/search, /api/preview)
├── chat.py        # 聊天和会话 (/api/chat, /api/sessions/*)
├── config.py      # 配置管理 (/api/config, /api/model/test)
├── directory.py   # 目录管理 (/api/directories/*)
└── system.py      # 系统接口 (/api/health/*, /api/rebuild-index)
```

#### 各模块主要端点

**Search 模块** (`search.py`):
- `POST /api/search` - 混合搜索
- `POST /api/preview` - 文件预览

**Chat 模块** (`chat.py`):
- `POST /api/chat` - 问答对话
- `GET /api/sessions` - 获取会话列表
- `DELETE /api/sessions/{session_id}` - 删除会话
- `GET /api/sessions/{session_id}/messages` - 获取会话消息

**Config 模块** (`config.py`):
- `GET /api/config` - 获取配置
- `POST /api/config` - 更新配置
- `GET /api/model/test` - 测试模型连接

**Directory 模块** (`directory.py`):
- `GET /api/directories` - 获取目录列表
- `POST /api/directories` - 添加目录
- `DELETE /api/directories` - 删除目录
- `POST /api/directories/browse` - 浏览目录（打开对话框）

**System 模块** (`system.py`):
- `GET /api/health` - 健康检查
- `GET /api/health/ready` - 就绪检查
- `GET /api/health/live` - 存活检查
- `POST /api/rebuild-index` - 重建索引

---

## 配置管理系统

### ConfigLoader 类

**功能**
- 加载 YAML 配置文件
- 提供类型安全的配置访问
- 实现配置验证和默认值

**关键方法**
- `get(section, key, default)` - 获取配置值
- `getint(section, key, default)` - 获取整数配置
- `getfloat(section, key, default)` - 获取浮点数配置
- `getboolean(section, key, default)` - 获取布尔值配置
- `update_config(updates)` - 更新配置

---

## 日志系统

### EnterpriseLogger 类

**功能**
- 结构化日志记录
- 支持上下文追踪
- 提供性能监控

**关键特性**
- 支持 JSON 格式日志
- 实现异步日志处理
- 提供日志上下文管理

---

## 前端架构

### 技术栈
- Bootstrap 5: UI 框架
- Bootstrap Icons: 图标库
- 原生 JavaScript: 交互逻辑
- Tauri API: 桌面集成

### 页面结构
- 双模式界面：文件搜索 + 智能问答
- 响应式设计
- 暗色主题

### 组件结构
- 侧边栏：配置、过滤器、历史记录
- 主内容区：搜索结果或对话界面
- 设置模态框：采样参数、惩罚参数、接入模式
- 重建索引弹窗：带进度提示

### 功能特性
- **设置持久化**：前端设置通过 `/api/config` 保存到后端
- **会话管理**：聊天会话通过 `/api/sessions` 进行管理
- **实时状态**：健康检查、索引重建进度等

---

## 测试策略

### 测试分层结构

```
tests/
├── unit/               # 单元测试 - 测试独立函数和方法
│   ├── test_config_loader.py
│   ├── test_document_parser.py
│   ├── test_file_scanner.py
│   ├── test_file_monitor.py
│   ├── test_index_manager.py
│   ├── test_search_engine.py
│   ├── test_rag_pipeline.py
│   ├── test_query_processor.py
│   ├── test_logger.py
│   └── ...
├── integration/        # 集成测试 - 测试模块间协作
│   └── test_performance.py     # 性能基准测试
├── api/                # API 测试 - 测试 API 端点
│   └── test_web_api.py
└── e2e/                # 端到端测试 - 测试完整用户流程
    ├── test_ui_chat.py
    ├── test_ui_search.py
    ├── test_ui_settings.py
    └── test_accessibility.py  # 无障碍测试（Playwright + axe-core）
```

**测试辅助文件：**
- `tests/conftest.py` - pytest fixtures 和配置
- `tests/factories.py` - Mock 工厂类

### 运行测试

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

# 性能测试
pytest tests/integration/test_performance.py -v

# 生成 Allure 测试报告
python scripts/run_tests.py --allure
python scripts/run_tests.py unit --allure
```

### 测试报告 (Allure)

测试报告输出到 `reports/` 目录：
- HTML 报告：`reports/test_report.html`
- 覆盖率报告：`reports/coverage/index.html`
- Allure 结果：`reports/allure-results/`
- Allure 报告：`reports/allure-report/index.html`

---

## 打包与部署

### 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 3.9+ | 推荐 3.11/3.12 |
| Node.js | 18+ | Tauri CLI 需要 |
| Rust | 1.70+ | `rustup update` |
| uv | 最新 | `pip install uv` |

### 安装依赖

```bash
# 1. 克隆项目
git clone https://github.com/Dariandai/File-tools.git
cd File-tools

# 2. 安装 Python 依赖
uv sync

# 3. 安装 Node.js 依赖
npm install
```

### 本地构建流程

**方式一：一键构建（推荐）**

```bash
# 发布构建（生成 NSIS + MSI 安装包）
npm run tauri build
```

**方式二：仅开发模式**

```bash
# 热重载开发（不生成安装包）
npm run tauri dev
```

### 获取构建产物

```bash
# Windows 安装包
ls src-tauri/target/release/bundle/nsis/*.exe    # NSIS 安装程序
ls src-tauri/target/release/bundle/msi/*.msi     # MSI 安装包

# Windows 便携版（单文件 exe）
ls src-tauri/target/release/*.exe               # filetools.exe

# Python 后端 (PyInstaller)
ls src-tauri/bin/filetools-backend.exe          # 打包的后端
```

### 快速命令汇总

| 命令 | 说明 |
|------|------|
| `npm run tauri dev` | 开发模式（热重载） |
| `npm run tauri build` | 发布构建（生成安装包） |
| `python build_pyinstaller.py` | 仅构建 Python 后端 |

### 常见问题

**Q: `cargo check` 报错 "externalBin doesn't exist"**
```
A: 必须先运行 `python build_pyinstaller.py` 生成后端二进制文件
```

**Q: 构建失败，提示缺少模块**
```bash
uv sync
```

---

## 性能优化

### 索引优化
- Tantivy 索引合并
- HNSWLib 参数调优
- 缓存机制

### 搜索优化
- 查询缓存
- 结果缓存
- 并行搜索

### 内存管理
- VRAM 管理器
- 缓存大小控制
- 内存泄漏防护

---

## 扩展性设计

### 可扩展点
- 新的文件格式支持
- 不同的 AI 模型集成
- 自定义搜索算法

---

## 安全考虑

### 输入验证
- 路径遍历防护
- 文件类型验证
- 查询内容过滤

### 访问控制
- 文件访问权限检查
- API 访问限制
- 敏感信息保护
