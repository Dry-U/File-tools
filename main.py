#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件

使用 Pywebview 创建原生桌面窗口，在后台线程运行 FastAPI 服务。
"""
import sys
import os
import psutil
import requests
import time
import socket
import threading

# 修复 torch DLL 加载问题：将 torch lib 目录添加到 PATH
try:
    venv_path = os.path.dirname(sys.executable)
    torch_lib_path = os.path.join(
        venv_path, 'Lib', 'site-packages', 'torch', 'lib')
    if os.path.exists(torch_lib_path):
        os.environ['PATH'] = torch_lib_path + \
            os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(torch_lib_path)
except Exception as e:
    print(f"警告：无法添加 torch DLL 目录：{e}")


def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def find_available_port(start=8000, end=8010):
    """查找可用端口"""
    for p in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            continue
    return start


def find_existing_instance():
    """查找是否已有实例在运行"""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] != current_pid and 'main.py' in ' '.join(proc.info['cmdline'] or []):
                for port in range(8000, 8011):
                    if is_port_in_use(port):
                        try:
                            response = requests.get(
                                f"http://127.0.0.1:{port}/api/health", timeout=1)
                            if response.status_code == 200:
                                return port
                        except:
                            pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None


def wait_for_server_ready(url, max_wait=60):
    """等待服务器就绪"""
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{url}/api/health", timeout=1)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    try:
                        app_response = requests.get(url, timeout=1)
                        if app_response.status_code == 200:
                            return True
                    except:
                        pass
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def start_fastapi_server(port):
    """启动 FastAPI 服务器"""
    import uvicorn
    from backend.api.api import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()


def run_desktop_app():
    """运行桌面应用"""
    import webview

    from backend.utils.logger import setup_logger
    logger = setup_logger()
    logger.info("应用启动中...")

    port = find_available_port(8000, 8010)
    url = f"http://127.0.0.1:{port}"
    logger.info(f"服务端口: {port}")

    server_thread = threading.Thread(
        target=start_fastapi_server,
        args=(port,),
        daemon=True
    )
    server_thread.start()

    logger.info("等待服务就绪...")
    if wait_for_server_ready(url, max_wait=60):
        logger.info("服务就绪")
    else:
        logger.warning("服务启动超时，继续尝试")

    window = webview.create_window(
        title='File Tools',
        url=url,
        width=1280,
        height=800,
        min_size=(900, 600),
        text_select=True,
    )

    webview.start()
    logger.info("应用已退出")


def main():
    """主函数 - 应用程序入口点"""
    # 检查是否已有实例在运行
    existing_port = find_existing_instance()
    if existing_port:
        print(f"检测到已有实例在端口 {existing_port} 上运行")
        print("请关闭现有实例后再启动新实例，或使用现有窗口。")
        return

    print("启动桌面应用...")
    run_desktop_app()


if __name__ == "__main__":
    main()
