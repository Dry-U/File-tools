# File Tools - 开发者文档

## 项目架构

### 整体架构
```
File-tools/
├── backend/                # 后端服务
│   ├── api/                # API接口层（模块化设计）
│   │   ├── main.py         # FastAPI应用主文件
│   │   ├── models.py       # 请求/响应模型
│   │   ├── dependencies.py # 依赖注入函数
│   │   └── routes/         # 路由模块
│   │       ├── search.py   # 搜索/预览路由
│   │       ├── chat.py     # 聊天/会话路由
│   │       ├── config.py   # 配置管理路由
│   │       ├── directory.py# 目录管理路由
│   │       └── system.py   # 系统/健康检查路由
│   ├── core/               # 核心业务逻辑
│   │   ├── document_parser.py      # 文档解析器（PDF/Word/Excel/PPT/MD）
│   │   ├── file_scanner.py         # 文件扫描器
│   │   ├── file_monitor.py         # 文件监控器（watchdog）
│   │   ├── index_manager.py        # 索引管理器（Tantivy + HNSWLib）
│   │   ├── search_engine.py        # 搜索引擎（混合检索）
│   │   ├── model_manager.py        # 模型管理器（LLM 接入）
│   │   ├── rag_pipeline.py         # RAG 问答流水线
│   │   ├── chat_history_db.py      # 聊天历史持久化（SQLite）
│   │   ├── query_processor.py      # 查询预处理与分词
│   │   ├── privacy_guard.py        # 隐私保护（敏感路径过滤）
│   │   ├── sharded_cache.py        # 缓存（基于 cachetools TTLCache）
│   │   ├── vram_manager.py         # VRAM 感知的上下文管理
│   │   ├── constants.py            # 全局常量定义
│   │   └── exceptions.py           # 自定义异常体系
│   └── utils/              # 工具模块
│       ├── config_loader.py        # 配置加载与类型安全访问
│       ├── config_validator.py     # 配置值校验器
│       ├── logger.py               # 企业级结构化日志系统
│       ├── app_paths.py            # 路径解析与数据目录管理
│       ├── metrics.py              # 性能指标采集（Prometheus 兼容）
│       └── network.py              # 网络工具（端口检测等）
├── frontend/               # 前端界面
│   ├── index.html          # 主页面
│   └── static/             # 静态资源
│       ├── css/style.css   # 样式表
│       └── js/             # JS 功能模块
│           ├── main.js     # 应用入口
│           ├── flatpickr-zh.js  # 日期选择器中文化
│           └── modules/    # 功能模块
│               ├── chat.js         # 聊天功能
│               ├── search.js       # 搜索功能
│               ├── settings.js     # 设置面板
│               ├── directory.js    # 目录管理
│               ├── ui.js           # UI 交互
│               └── utils.js        # 公共工具函数
├── tests/                  # 测试代码（分层结构）
│   ├── unit/               # 单元测试
│   ├── integration/        # 集成测试
│   ├── api/                # API 测试
│   └── e2e/                # 端到端测试（Playwright）
├── data/                   # 运行时数据（不纳入版本控制）
│   ├── tantivy_index/      # Tantivy 索引文件
│   ├── hnsw_index/         # HNSWLib 向量索引
│   ├── metadata/           # 索引元数据（schema 版本等）
│   ├── models/             # 嵌入模型文件
│   ├── cache/              # 磁盘缓存
│   └── temp/               # 临时文件
├── docs/                   # 项目文档
│   ├── DEVELOPER_GUIDE.md  # 开发者文档
│   └── USAGE_GUIDE.md      # 使用手册
├── scripts/                # 辅助脚本
│   └── version_manager.py  # 版本管理工具
├── config.yaml             # 配置文件
├── main.py                 # 应用入口（Pywebview + FastAPI）
├── build.bat               # Nuitka 构建脚本
├── build_nuitka.py         # Nuitka 构建脚本（Python）
├── pyproject.toml          # 项目配置与依赖管理
└── uv.lock                 # 依赖锁定文件（请提交到版本控制）
```

## 核心模块详解

> **说明**：以下为主要核心模块说明。完整的类/方法签名参见各模块源文件 docstring。

### 1. IndexManager (索引管理器)

#### 功能
- 管理双重索引系统（Tantivy全文索引 + HNSWLib向量索引）
- 处理文档的添加、更新、删除
- 提供搜索接口

#### 关键方法
- `add_document(document)`: 添加文档到索引
- `update_document(document)`: 更新文档索引
- `delete_document(file_path)`: 从索引中删除文档
- `search_text(query, limit, filters)`: 文本搜索
- `search_vector(query, limit)`: 向量搜索
- `get_document_content(path)`: 获取文档内容

#### 设计要点
- 使用Tantivy进行高性能全文检索
- 使用HNSWLib进行快速向量相似度搜索
- 支持中文分词（jieba）
- 实现单字符检索能力

### 2. SearchEngine (搜索引擎)

#### 功能
- 整合文本搜索和向量搜索结果
- 实现混合检索算法
- 提供高级搜索功能

#### 关键方法
- `search(query, filters)`: 执行混合搜索
- `_search_text(query, filters)`: 执行文本搜索
- `_search_vector(query, filters)`: 执行向量搜索
- `_combine_results(text_results, vector_results)`: 合并搜索结果

#### 设计要点
- 使用 RRF（倒数排名融合）合并文本和向量搜索结果
- 实现BM25算法进行文本评分
- 提供结果去重和排序功能
- 支持高级过滤器

### 3. FileScanner (文件扫描器)

#### 功能
- 扫描指定目录下的文档
- 识别支持的文件类型
- 调用索引管理器进行索引

#### 关键方法
- `scan_and_index()`: 扫描并索引所有文件
- `_should_index(path)`: 判断是否应索引文件
- `_index_file(file_path)`: 索引单个文件
- `get_supported_file_types()`: 获取支持的文件类型

#### 设计要点
- 支持多线程扫描
- 实现文件过滤机制
- 提供进度回调功能
- 支持增量索引

### 4. RAGPipeline (RAG问答管道)

#### 功能
- 管理对话历史
- 执行文档检索
- 生成AI回答

#### 关键方法
- `query(query, session_id)`: 执行问答查询
- `_collect_documents(query)`: 收集相关文档
- `_build_prompt(query, documents, history_text)`: 构建提示词
- `_remember_turn(session_id, query, answer)`: 记录对话轮次

#### 设计要点
- 实现上下文管理
- 支持多轮对话
- 提供文档聚合功能
- 实现智能回答生成

### 5. DirectoryManager (目录管理)

#### 功能
- 管理扫描路径和监控目录
- 提供目录浏览对话框
- 目录状态跟踪

#### 关键方法
- `get_directories()`: 获取所有管理的目录
- `add_directory(path)`: 添加新目录
- `remove_directory(path)`: 移除目录
- `browse_directory()`: 打开系统目录选择对话框

#### 设计要点
- 路径安全验证（防止路径遍历）
- 统一处理扫描路径和监控目录
- 实时状态显示（存在性、扫描状态、监控状态、文件数）
- 支持 Windows/Linux/macOS 文件对话框

### 6. ChatHistoryDB (聊天历史数据库)

#### 功能
- 以 SQLite 持久化存储会话与消息历史
- 多会话管理（创建、查询、删除）

#### 设计要点
- 数据库文件路径 `data/chat_history.db`，不纳入版本控制
- 异步安全读写操作

### 7. ShardedCache (缓存)

#### 功能
- 基于 cachetools TTLCache 的线程安全缓存
- 支持 TTL 过期与容量限制
- 替代原有的自定义分片缓存实现，降低锁竞争

### 8. QueryProcessor (查询处理器)

#### 功能
- 对输入查询进行预处理：中文分词（jieba）、关键词提取、停用词过滤
- 为文本搜索和向量搜索生成最优查询表示

### 9. PrivacyGuard (隐私保护)

#### 功能
- 过滤敏感文件路径（系统目录、私钥文件等）
- 对扫描结果中的敏感信息进行脱敏处理

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

#### 路由注册（main.py）

```python
from backend.api.routes import search, chat, config, directory, system

app.include_router(search.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(directory.router, prefix="/api")
app.include_router(system.router, prefix="/api")
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

## 配置管理系统

### ConfigLoader 类

#### 功能
- 加载 YAML 配置文件
- 提供类型安全的配置访问
- 实现配置验证和默认值

#### 关键方法
- `get(section, key, default)`: 获取配置值
- `getint(section, key, default)`: 获取整数配置
- `getfloat(section, key, default)`: 获取浮点数配置
- `getboolean(section, key, default)`: 获取布尔值配置
- `update_config(updates)`: 更新配置

## 日志系统

### EnterpriseLogger 类

#### 功能
- 结构化日志记录
- 支持上下文追踪
- 提供性能监控

#### 关键特性
- 支持 JSON 格式日志
- 实现异步日志处理
- 提供日志上下文管理

## 前端架构

### 技术栈
- Bootstrap 5: UI 框架
- Bootstrap Icons: 图标库
- 原生 JavaScript: 交互逻辑

### 页面结构
- 双模式界面：文件搜索 + 智能问答
- 响应式设计
- 暗色主题（Llama Style）

### 组件结构
- 侧边栏：配置、过滤器、历史记录
- 主内容区：搜索结果或对话界面
- 设置模态框：采样参数、惩罚参数、接入模式
- 重建索引弹窗：带进度提示

### 功能特性
- **设置持久化**：前端设置通过 `/api/config` 保存到后端
- **会话管理**：聊天会话通过 `/api/sessions` 进行管理
- **实时状态**：健康检查、索引重建进度等

## 测试策略

### 测试分层结构

```
tests/
├── unit/               # 单元测试 - 测试独立函数和方法
│   ├── test_config_loader.py
│   ├── test_config_validator.py
│   ├── test_document_parser.py
│   ├── test_file_scanner.py
│   ├── test_async_file_scanner.py
│   ├── test_file_monitor.py
│   ├── test_index_manager.py
│   ├── test_search_engine.py
│   ├── test_rag_pipeline.py
│   ├── test_model_manager.py
│   ├── test_vram_manager.py
│   ├── test_query_processor.py
│   ├── test_privacy_guard.py
│   ├── test_chat_history_db.py
│   ├── test_sharded_cache.py
│   ├── test_metrics.py
│   ├── test_exceptions.py
│   ├── test_logger.py
│   ├── test_edge_cases.py      # 边界值测试
│   └── test_concurrency.py    # 并发安全测试
├── integration/        # 集成测试 - 测试模块间协作
│   ├── test_file_processing_integration.py
│   ├── test_rag_workflow.py
│   └── test_performance.py     # 性能基准测试
├── api/                # API 测试 - 测试 API 端点
│   ├── test_web_api.py
│   └── test_web_api_simple.py
└── e2e/                # 端到端测试 - 测试完整用户流程
    ├── test_ui_chat.py
    ├── test_ui_search.py
    ├── test_ui_settings.py
    └── test_accessibility.py  # 无障碍测试（Playwright + axe-core）
```

**测试辅助文件：**
- `tests/conftest.py` - pytest fixtures 和配置
- `tests/factories.py` - Mock 工厂类
- `tests/utils.py` - 测试工具函数

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

# 按分类运行并生成报告
python scripts/run_tests.py unit --allure
python scripts/run_tests.py integration --allure
```

### 测试报告 (Allure)

测试报告输出到 `reports/` 目录：
- HTML 报告：`reports/test_report.html`
- 覆盖率报告：`reports/coverage/index.html`
- Allure 结果：`reports/allure-results/`
- Allure 报告：`reports/allure-report/index.html`

Allure 报告管理：
```bash
python scripts/allure_report.py generate  # 从现有结果生成报告
python scripts/allure_report.py open      # 生成并打开报告
python scripts/allure_report.py serve     # 本地服务方式查看 (http://localhost:4040)
python scripts/allure_report.py clean     # 清理所有报告
```

### 测试覆盖目标
- 核心业务逻辑：> 80%
- 工具函数：> 60%
- API 端点：主要流程覆盖

## 打包与部署

### 打包方式
- 使用 Nuitka 打包为 EXE（Python → C → exe）
- 支持 Windows、Linux（macOS 需在 macOS 上构建）
& "D:\app\Inno Setup 6\ISCC.exe" "d:\Python_work\File-tools\scripts\build_inno_setup.iss"

### 部署考虑
- 依赖管理
- 配置文件处理
- 数据目录管理

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

## 扩展性设计

### 插件架构
- 模块化设计
- 依赖注入
- 配置驱动

### 可扩展点
- 新的文件格式支持
- 不同的AI模型集成
- 自定义搜索算法

## 错误处理

### 异常处理策略
- 全局异常处理器
- 模块级错误处理
- 用户友好的错误信息

### 日志记录
- 详细的错误日志
- 性能指标记录
- 调试信息支持

## 安全考虑

### 输入验证
- 路径遍历防护
- 文件类型验证
- 查询内容过滤

### 访问控制
- 文件访问权限检查
- API 访问限制
- 敏感信息保护

## 维护指南

### 日志监控
- 定期检查日志文件
- 监控性能指标
- 跟踪错误模式

### 数据管理
- 定期清理缓存
- 索引优化
- 备份策略

## 贡献指南

### 代码规范
- 遵循 PEP 8
- 类型注解
- 文档字符串

### 提交规范
- 清晰的提交信息
- 单一职责原则
- 测试覆盖率

## 版本管理

### 发布流程
- 代码审查
- 测试验证
- 文档更新

### 向后兼容
- API 稳定性
- 配置文件兼容
- 数据格式迁移