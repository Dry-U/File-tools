# File-tools
本地文件智能助手 - 高效管理、检索与分析本地文件

## 项目概述
File-tools是一个本地文件智能管理工具，提供文件扫描、内容解析、语义检索和AI增强分析功能。通过结合本地LLM模型，帮助用户更高效地管理和利用本地文档资源。

## 项目结构
```
File-tools/
├── .gitignore                # Git忽略规则
├── .idea/                    # IDE配置文件
├── Dockerfile                # Docker构建文件
├── LICENSE                   # 许可证文件
├── README.md                 # 项目说明文档
├── app.py                    # 应用入口
├── config.yaml               # 项目配置文件
├── docker-compose.yaml       # Docker编排配置
├── docs/                     # 项目文档
│   └── 需求文档v3(最终版).md   # 需求规格说明书
├── pyproject.toml            # Python项目配置
├── src/                      # 源代码
│   ├── api/                  # API接口层
│   │   ├── app.py            # API应用
│   │   ├── auth.py           # 认证相关
│   │   ├── models.py         # 数据模型
│   │   └── routes.py         # 路由定义
│   ├── core/                 # 核心业务逻辑
│   │   ├── file_scanner.py   # 文件扫描器
│   │   ├── inference_optimizer.py # 推理优化器
│   │   ├── model_manager.py  # 模型管理器
│   │   ├── privacy_filter.py # 隐私过滤器
│   │   ├── rag_pipeline.py   # RAG流水线
│   │   ├── security_manager.py # 安全管理器
│   │   ├── smart_indexer.py  # 智能索引器
│   │   ├── universal_parser.py # 通用解析器
│   │   ├── vector_engine.py  # 向量引擎
│   │   └── vram_manager.py   # 显存管理器
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
- **文件扫描器**：实时监控文件系统变化，支持增量扫描
- **通用解析器**：支持多种文档格式解析（PDF、Word、Excel等）
- **智能索引器**：高效构建文件索引，支持上下文感知

### 2. AI增强模块
- **模型管理器**：本地LLM模型加载与管理
- **RAG流水线**：检索增强生成，提升回答准确性
- **推理优化器**：优化模型推理性能
- **显存管理器**：智能管理GPU显存，支持多模型切换

### 3. 系统安全模块
- **隐私过滤器**：自动识别和过滤敏感信息
- **安全管理器**：访问控制和数据保护

### 4. 基础设施
- **配置加载器**：灵活的配置管理
- **日志系统**：企业级日志记录与分析

## 快速开始

### 环境要求
- Python 3.9+
- 推荐配置：16GB内存，NVIDIA显卡(可选，用于加速LLM推理)

### 安装依赖
```bash
# 使用uv包管理器
uv sync

# 或使用pip
pip install -r requirements.txt
```

### 配置
编辑`config.yaml`文件设置相关参数，包括：
- 文件扫描路径
- 模型配置
- 向量存储设置

### 运行
```bash
python app.py
```

## 容器化部署
```bash
docker-compose up -d
```

## 技术栈
- **后端**：Python, FastAPI
- **AI模型**：llama.cpp, llama-cpp-python
- **向量存储**：FAISS
- **文档处理**：PyPDF2, python-docx


## 测试
```bash
pytest tests/
```
