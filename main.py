#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件"""
import sys
import os

# 修复 torch DLL 加载问题：将 torch lib 目录添加到 PATH
try:
    venv_path = os.path.dirname(sys.executable)
    torch_lib_path = os.path.join(venv_path, 'Lib', 'site-packages', 'torch', 'lib')
    if os.path.exists(torch_lib_path):
        # 添加到 PATH 环境变量
        os.environ['PATH'] = torch_lib_path + os.pathsep + os.environ.get('PATH', '')
        # 如果支持，也添加到 DLL 目录
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(torch_lib_path)
except Exception as e:
    print(f"警告：无法添加 torch DLL 目录：{e}")

def run_web_ui():
    """Run the web UI version of the application"""
    from run_web import run_web_interface
    import uvicorn
    from backend.api.api import app

    # Initialize logger
    from backend.utils.logger import setup_logger
    logger = setup_logger()
    logger.info("Web application (FastAPI)启动")

    # Run the web interface
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def main():
    """Main function - Application entry point for web interface"""
    print("启动 Web 界面...")
    run_web_ui()


if __name__ == "__main__":
    main()