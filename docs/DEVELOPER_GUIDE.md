# File Tools - 开发者文档

## 项目架构

### 整体架构
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
│   │   └── rag_pipeline.py         # RAG 问答流水线
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
└── pyproject.toml          # 项目配置
```

## 核心模块详解

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
- 支持文本权重和向量权重调节
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

### 路由结构

```python
# API 路由前缀为 /api
api_router = APIRouter()

@api_router.get("/health")
async def health_check():
    ...

@api_router.post("/search")
async def search(...):
    ...

@api_router.post("/chat")
async def chat(...):
    ...

@api_router.get("/config")
async def get_config(...):
    ...

@api_router.post("/config")
async def update_config(...):
    ...

@api_router.get("/sessions")
async def get_sessions(...):
    ...

@api_router.delete("/sessions/{session_id}")
async def delete_session(...):
    ...
```

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

### 测试类型
- 单元测试：测试独立函数和方法
- 集成测试：测试模块间协作
- 性能测试：验证系统性能

### 测试覆盖
- 配置加载器测试
- 索引管理器测试
- 搜索引擎测试
- API 接口测试

## 打包与部署

### 打包方式
- 使用 PyInstaller 打包为 EXE
- 支持 Windows、macOS、Linux

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