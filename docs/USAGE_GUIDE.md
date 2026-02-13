# File Tools - 使用手册

## 项目概述

File Tools 是一个基于Python的本地文件智能管理工具，提供高效文件扫描、语义检索和AI增强问答功能。

## 核心特性

- **混合检索**：结合Tantivy全文检索和HNSWLib向量检索
- **智能问答**：基于RAG技术的文档智能问答
- **多格式支持**：PDF、Word、Excel、PPT、Markdown等多种文档格式
- **设置持久化**：前端设置可直接保存到配置文件
- **历史记录**：智能问答支持多会话历史记录
- **实时监控**：自动监控文件变化并增量更新索引
- **日志记录**：结构化日志记录，支持JSON格式和上下文追踪

## 环境要求

- Python 3.9 或更高版本
- 8GB 内存（推荐）
- Windows 10/11, macOS 10.15+, 或 Linux

## 安装步骤

### 1. 克隆项目
```bash
git clone https://github.com/Dry-U/File-tools.git
cd File-tools
```

### 2. 安装依赖
```bash
# 推荐使用 uv
uv sync

# 或使用 pip
pip install -e .
```

### 3. 配置系统
编辑 `config.yaml` 设置扫描路径和其他参数：

```yaml
ai_model:
  enabled: true  # 启用 AI 问答功能
  interface_type: "wsl"  # 接口类型: wsl 或 api
  api_url: "http://localhost:8080/v1/chat/completions"
  api_key: ""
  api_model: "gpt-3.5-turbo"
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  max_tokens: 2048

file_scanner:
  scan_paths:
    - "C:/Users/YourName/Documents"
  file_types:
    document: [".txt", ".md", ".pdf", ".doc", ".docx"]
    spreadsheet: [".xls", ".xlsx", ".csv"]
    presentation: [".ppt", ".pptx"]
    archive: [".zip", ".rar", ".7z"]

monitor:
  enabled: true
  directories:
    - "C:/Users/YourName/Documents"

search:
  text_weight: 0.6
  vector_weight: 0.4
```

## 启动应用

### 方式一：桌面应用（推荐）
```bash
uv run python main.py
```

### 方式二：直接运行
```bash
python main.py
```

启动后会打开一个标题为「File Tools」的原生桌面窗口。
API 服务在 `http://127.0.0.1:8000` 上运行；若端口被占用，将自动选择 `8001–8010` 中的可用端口。

## 功能使用指南

### 1. 文件搜索功能

#### 基本搜索
- 在搜索框中输入关键词
- 系统将同时执行文本搜索和向量搜索
- 结果按相关性排序显示

#### 高级过滤
- **文件类型过滤**：点击侧边栏的文件类型按钮
- **文件大小过滤**：在侧边栏设置最小/最大文件大小
- **日期范围过滤**：通过高级选项设置

#### 搜索语法
- 支持中文分词搜索
- 支持模糊匹配
- 支持文件名和内容混合搜索

### 2. 智能问答功能

#### 开始问答
- 点击顶部标签切换到"智能问答"模式
- 在底部输入框中输入问题
- 系统将检索相关文档并生成回答

#### 会话管理
- 系统支持多轮对话，自动保持上下文
- 侧边栏显示历史会话列表，点击可切换会话
- 点击"新建对话"创建新会话
- 会话信息在服务器端维护，刷新页面后仍然保留
- 使用"重置"命令清空当前对话历史

#### 问答技巧
- 提问时尽量具体明确
- 可以询问文档中的具体内容
- 系统会引用相关文档来源

### 3. 系统管理

#### 重建索引
- 点击侧边栏的"重建索引"按钮
- 重新扫描所有配置的文件夹
- 更新搜索和问答系统的索引

#### 设置管理
- 点击右上角的齿轮图标打开设置面板
- **采样参数**：调整 temperature、top_p、max_tokens 等
- **惩罚参数**：设置 frequency_penalty、presence_penalty 等
- **接入模式**：切换 WSL 本地模式或 API 远程模式
- 点击"保存更改"将设置持久化到配置文件

## API 接口

### 健康检查
```
GET /api/health
```

### 重建索引
```
POST /api/rebuild-index
```

### 搜索接口
```
POST /api/search
{
  "query": "搜索关键词",
  "filters": {}
}
```

### 问答接口
```
POST /api/chat
{
  "query": "问题",
  "session_id": "会话ID"
}
```

### 文件预览
```
POST /api/preview
{
  "path": "文件路径"
}
```

### 获取配置
```
GET /api/config
```

### 更新配置
```
POST /api/config
{
  "ai_model": {
    "temperature": 0.7,
    "api_url": "http://localhost:8080/v1/chat/completions"
  }
}
```

### 获取会话列表
```
GET /api/sessions
```

### 删除会话
```
DELETE /api/sessions/{session_id}
```

## 配置详解

### 系统配置 (system)
- `app_name`: 应用名称
- `data_dir`: 数据存储目录
- `log_level`: 日志级别

### 文件扫描配置 (file_scanner)
- `scan_paths`: 扫描路径列表
- `exclude_patterns`: 排除模式
- `max_file_size`: 最大文件大小(MB)
- `file_types`: 支持的文件类型

### 搜索配置 (search)
- `text_weight`: 文本搜索权重
- `vector_weight`: 向量搜索权重
- `max_results`: 最大返回结果数
- `enable_cache`: 是否启用缓存

### AI模型配置 (ai_model)
- `enabled`: 是否启用AI功能
- `interface_type`: 接口类型(wsl/api)
- `api_url`: API地址
- `temperature`: 生成温度

## 性能指标

- 关键词检索：< 1 秒
- 语义检索：< 3 秒
- 问答生成：< 5 秒
- 支持规模：10 万+ 文档

## 故障排除

### 常见问题

1. **启动失败**
   - 检查Python版本是否符合要求
   - 确认依赖包已正确安装

2. **搜索无结果**
   - 检查扫描路径配置是否正确
   - 确认文件类型在支持列表中

3. **AI问答不工作**
   - 检查AI模型配置
   - 确认API服务可访问

### 日志查看
- 日志文件位于 `./data/logs/`
- 可通过配置调整日志级别

## 打包发布

### 打包为EXE
```bash
# 使用PyInstaller打包
pyinstaller file-tools.spec

# 或运行打包脚本
./build_exe.bat  # Windows
```

## 开发指南

### 项目结构
```
File-tools/
├── backend/                # 后端服务
│   ├── api/                # API接口层
│   ├── core/               # 核心业务逻辑
│   └── utils/              # 工具模块
├── frontend/               # 前端界面
├── tests/                  # 测试代码
├── data/                   # 数据存储
└── docs/                   # 项目文档
```

### 核心模块

#### IndexManager (索引管理器)
- 双重索引：Tantivy全文索引 + HNSWLib向量索引
- 中文分词支持
- 单字符检索能力

#### SearchEngine (搜索引擎)
- 混合检索：文本搜索 + 向量搜索
- 智能排序：BM25算法 + 语义相似度
- 结果增强：文件名匹配增强

#### FileScanner (文件扫描器)
- 多格式支持：PDF、Word、Excel、文本等
- 智能过滤：排除系统文件、媒体文件
- 增量索引：支持文件变化检测

#### RAGPipeline (RAG问答管道)
- 上下文管理：智能管理对话历史
- 文档聚合：多文档信息提取和聚合
- 智能回答：基于检索结果的AI回答生成

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 作者：Darian
- 邮箱：Dar1an@126.com
- 项目主页：https://github.com/Dry-U/File-tools