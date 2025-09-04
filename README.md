# 智能文件检索与问答系统

## 项目概述
这是一个基于PyQt5的智能文件检索与问答系统，提供高效的文件扫描、内容解析、语义检索和AI增强分析功能。通过结合现代检索技术和本地/在线大语言模型，帮助用户更高效地管理和利用本地文档资源。

## 项目结构
```
File-tools/
├── .gitignore                # Git忽略规则
├── .idea/                    # IDE配置文件
├── LICENSE                   # 许可证文件
├── README.md                 # 项目说明文档
├── config.yaml               # 项目配置文件
├── config_debug.py           # 调试配置
├── data/                     # 数据存储目录
│   ├── cache/                # 缓存文件
│   ├── faiss_index/          # FAISS向量索引
│   ├── index/                # 索引文件
│   ├── metadata/             # 元数据存储
│   ├── temp/                 # 临时文件
│   └── whoosh_index/         # Whoosh文本索引
├── docs/                     # 项目文档
│   └── 智能文件检索与问答系统.md  # 系统文档
├── icons/                    # 图标资源
├── main.py                   # 应用入口
├── pyproject.toml            # Python项目配置
├── src/                      # 源代码
│   ├── core/                 # 核心业务逻辑
│   │   ├── document_parser.py   # 文档解析器
│   │   ├── file_monitor.py      # 文件监控器
│   │   ├── file_scanner.py      # 文件扫描器
│   │   ├── index_manager.py     # 索引管理器
│   │   ├── model_manager.py     # 模型管理器
│   │   ├── rag_pipeline.py      # RAG问答管道
│   │   ├── search_engine.py     # 搜索引擎
│   │   ├── smart_indexer.py     # 智能索引器
│   │   ├── universal_parser.py  # 通用解析器
│   │   ├── vector_engine.py     # 向量引擎
│   │   └── vram_manager.py      # 显存管理器
│   ├── ui/                   # 用户界面
│   │   ├── components.py     # UI组件
│   │   └── main_window.py    # 主窗口
│   └── utils/                # 工具函数
│       ├── config_loader.py  # 配置加载器
│       └── logger.py         # 日志系统
├── tests/                    # 测试代码
│   ├── conftest.py           # 测试配置
│   ├── test_file_scanner.py  # 文件扫描器测试
│   ├── test_performance.py   # 性能测试
│   └── test_rag_workflow.py  # RAG工作流测试
└── uv.lock                   # 依赖锁文件
```

## 核心功能模块

### 1. 文件处理模块
- **文件扫描器**：扫描文件系统并识别可索引文件，支持配置扫描路径和排除模式
- **文件监控器**：监控文件系统变化，使用Watchdog库实现文件系统事件监控
- **文档解析器**：处理多种格式文档的内容提取和元数据提取，支持PDF、Word、Excel、文本、Markdown等格式
- **通用解析器**：多格式文档解析器，包含语义分块功能，使用Sentence-BERT进行上下文感知分块

### 2. 索引与检索模块
- **索引管理器**：管理Whoosh文本索引和FAISS向量索引，负责创建、更新和查询索引
- **搜索引擎**：集成文本搜索和向量搜索功能，执行文件搜索和结果排序
- **智能索引器**：智能增量索引器，缓冲变化并批量处理，优化索引更新性能
- **向量引擎**：文档嵌入和FAISS索引管理，负责向量化文档并管理向量索引

### 3. AI增强模块
- **模型管理器**：管理LLM模型加载和推理，支持本地推理和WSL API回退
- **RAG流水线**：RAG问答管道，使用LangChain实现，执行检索+生成，提供智能问答功能

### 4. 用户界面模块
- **主窗口**：实现应用程序的主窗口布局和交互逻辑
- **搜索组件**：提供搜索框、搜索结果视图等UI组件
- **主题管理器**：支持切换应用程序主题
- **文件预览器**：提供文件内容预览功能

### 5. 基础设施
- **配置加载器**：灵活的配置管理，支持从YAML文件加载配置
- **日志系统**：企业级日志记录与分析，支持多级别日志和日志轮转

## 快速开始

### 环境要求
- Python 3.9+
- PyQt5
- 推荐配置：8GB内存

### 安装依赖
```bash
# 使用uv包管理器
uv sync

# 或使用pip
pip install -r requirements.txt
```

### 配置
编辑`config.yaml`文件设置相关参数，包括：
- 文件扫描路径（file_scanner.scan_paths）
- 监控设置（monitor.enabled，monitor.directories）
- 搜索配置（search.max_results，search.text_weight等）
- 界面设置（interface.theme，interface.language等）

### 运行
```bash
python main.py
```

## 技术栈
- **编程语言**：Python
- **GUI框架**：PyQt5
- **文本索引**：Whoosh
- **向量存储**：FAISS
- **文档处理**：PyPDF2, python-docx, pandas
- **AI模型**：Sentence-BERT (用于嵌入), 本地/在线LLM (用于问答)
- **文件监控**：Watchdog

## 功能特点
1. **多格式支持**：支持PDF、Word、Excel、文本、Markdown等多种文件格式
2. **混合检索**：结合文本搜索和语义搜索，提供更精确的检索结果
3. **实时监控**：可选的文件系统实时监控功能，支持增量更新
4. **中文字体支持**：自动配置中文字体，确保良好的显示效果
5. **主题切换**：支持明暗主题切换，提供舒适的使用体验
6. **智能问答**：结合RAG技术，提供基于文档内容的智能问答

## 测试
```bash
pytest tests/
```

## 许可证
本项目采用MIT许可证。
