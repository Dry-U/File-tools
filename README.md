# 智能文件检索与问答系统

基于 Python 和 PyQt5 的本地文件智能管理工具，提供高效文件扫描、语义检索和 AI 增强问答功能。

## 核心特性

-  **混合检索**：结合 Whoosh 全文检索和 FAISS 向量检索
-  **智能问答**：基于 RAG 技术的文档智能问答
-  **多格式支持**：PDF、Word、Excel、Markdown 等多种文档格式
-  **实时监控**：自动监控文件变化并增量更新索引
-  **现代界面**：PyQt5 构建的跨平台桌面应用

## 技术栈

- **编程语言**：Python 3.9+
- **GUI 框架**：PyQt5
- **文本索引**：Whoosh
- **向量检索**：FAISS
- **AI 模型**：Sentence-BERT (嵌入), LLaMA (本地推理)
- **文档处理**：PyPDF2, python-docx, pandas
- **文件监控**：Watchdog

## 项目结构

```
File-tools/
├── src/                    # 源代码
│   ├── core/               # 核心业务逻辑
│   │   ├── document_parser.py      # 文档解析器
│   │   ├── file_scanner.py         # 文件扫描器
│   │   ├── file_monitor.py         # 文件监控器
│   │   ├── index_manager.py        # 索引管理器
│   │   ├── search_engine.py        # 搜索引擎
│   │   ├── vector_engine.py        # 向量引擎
│   │   ├── model_manager.py        # 模型管理器
│   │   ├── rag_pipeline.py         # RAG 问答流水线
│   │   ├── smart_indexer.py        # 智能索引器
│   │   └── universal_parser.py     # 通用解析器
│   ├── ui/                 # 用户界面
│   │   ├── main_window.py          # 主窗口
│   │   └── components.py           # UI 组件
│   └── utils/              # 工具模块
│       ├── config_loader.py        # 配置加载
│       └── logger.py               # 日志系统
├── tests/                  # 测试代码
├── data/                   # 数据存储
│   ├── index/              # 文本索引
│   ├── faiss_index/        # 向量索引
│   ├── metadata/           # 元数据
│   └── cache/              # 缓存文件
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

### 运行

```bash
python main.py
```

## 核心功能

### 1. 文件扫描与索引

- 自动扫描指定目录下的文档
- 支持增量索引和实时更新
- 多格式文档内容提取

### 2. 混合检索

- **关键词检索**：基于 Whoosh 的全文检索
- **语义检索**：基于 FAISS 的向量相似度检索
- **混合排序**：结合文本和语义相关性

### 3. 智能问答

- 基于检索增强生成（RAG）技术
- 支持本地 LLaMA 模型或在线 API
- 提供答案来源和文档引用

### 4. 文件监控

- 实时监控文件系统变化
- 自动触发索引更新
- 支持批量处理优化性能

## 性能指标

- 关键词检索：< 1 秒
- 语义检索：< 3 秒
- 问答生成：< 5 秒
- 支持规模：10 万+ 文档

## 开发与测试

```bash
# 运行测试
pytest tests/

# 性能测试
pytest tests/test_performance.py -v
```

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 作者：Darian
- 邮箱：Dar1an@126.com
- 项目主页：https://github.com/Dry-U/File-tools
