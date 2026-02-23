#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试Web API初始化，无需完整启动
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("测试Web API初始化...")

try:
    from backend.utils.config_loader import ConfigLoader
    print("[OK] ConfigLoader导入成功")

    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    print("[OK] Logger导入和初始化成功")

    import backend.api.api
    print("[OK] Web API模块导入成功")

    from backend.api.api import app
    print("[OK] App导入成功")

    print("\n所有组件加载成功!")
    print("运行命令: python -m uvicorn backend.api.api:app --host 127.0.0.1 --port 8000")

except ImportError as e:
    print(f"[错误] 导入错误: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"[错误] 其他错误: {e}")
    import traceback
    traceback.print_exc()