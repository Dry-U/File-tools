# File-tools
本地文件助手

## 项目结构说明

```
File-tools/
├── backend/                    # 后端代码
│   ├── core/                   # 核心业务逻辑
│   │   ├── __init__.py         # Python包初始化文件
│   │   └── service.py          # 核心服务实现
│   ├── api/                    # API接口层
│   │   ├── __init__.py         # Python包初始化文件
│   │   └── routes.py           # API路由定义
│   ├── models/                 # 数据模型
│   │   ├── __init__.py         # Python包初始化文件
│   │   └── base.py             # 基础模型定义
│   └── utils/                 # 工具函数
│       ├── __init__.py         # Python包初始化文件
│       └── helpers.py          # 辅助工具函数
├── frontend/                  # 前端代码
│   └── src/                   # 前端源代码
│       ├── components/        # Vue/React组件
│       │   └── HelloWorld.vue # 示例组件
│       ├── views/             # 页面视图
│       │   └── Home.vue       # 首页视图
│       ├── assets/            # 静态资源
│       ├── main.js            # 前端入口文件
│       └── App.vue            # 根组件
├── config/                    # 配置文件
│   ├── settings.yaml          # 应用配置
│   └── database.yaml          # 数据库配置
├── docs/                      # 项目文档
│   └── architecture.md        # 架构设计文档
├── tests/                     # 测试代码
│   ├── unit/                  # 单元测试
│   │   └── test_core.py       # 核心业务测试
│   └── integration/           # 集成测试
│       └── test_api.py        # API接口测试
├── .gitignore                # Git忽略规则
├── requirements.txt          # Python依赖
├── setup.py                  # 项目安装配置
├── Dockerfile                # Docker构建文件
└── docker-compose.yaml       # Docker编排配置
```

### 各目录功能说明

1. **backend**: 包含所有后端相关代码，采用模块化设计
   - core/: 核心业务逻辑实现
   - api/: RESTful API接口定义
   - models/: 数据模型定义
   - utils/: 公共工具函数

2. **frontend**: 前端项目代码，采用Vue/React结构
   - src/: 前端源代码目录
     - components/: 可复用组件
     - views/: 页面级组件
     - assets/: 静态资源

3. **config**: 项目配置文件
   - settings.yaml: 应用运行时配置
   - database.yaml: 数据库连接配置

4. **docs**: 项目文档
   - architecture.md: 系统架构设计文档

5. **tests**: 自动化测试
   - unit/: 单元测试
   - integration/: 集成测试

6. **根目录文件**:
   - .gitignore: 版本控制忽略规则
   - requirements.txt: Python依赖包列表
   - setup.py: 项目安装配置
   - Dockerfile: 容器化构建配置
   - docker-compose.yaml: 多容器服务编排