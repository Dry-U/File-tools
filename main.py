#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件"""
import sys
import os
import psutil
import requests
import time
import webbrowser
import socket
import threading

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

def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True

def find_existing_instance():
    """查找已运行的实例"""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 检查是否是同一个Python脚本
            if proc.info['pid'] != current_pid and 'main.py' in ' '.join(proc.info['cmdline'] or []):
                # 尝试获取端口号（假设在命令行参数中或默认端口）
                # 这里简化处理，只检查默认端口范围
                for port in range(8000, 8011):
                    if is_port_in_use(port):
                        try:
                            # 发送一个简单的请求测试
                            response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                            if response.status_code == 200:
                                return port
                        except:
                            pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def run_web_ui():
    """Run the web UI version of the application"""
    import uvicorn
    from backend.api.api import app

    # Initialize logger
    from backend.utils.logger import setup_logger
    logger = setup_logger()
    logger.info("Web application (FastAPI)启动")

    def _find_available_port(start=8000, end=8010):
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

    port = _find_available_port(8000, 8010)

    def open_browser_after_delay(url):
        """Open the default browser to the application after a delay to ensure server is ready"""
        # Wait for server to be ready by checking the health endpoint
        max_wait_time = 60  # seconds, increased to account for model loading
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get(f"{url}/api/health", timeout=1)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "healthy":
                        # Additional check to see if app is fully initialized
                        try:
                            app_response = requests.get(url, timeout=1)
                            if app_response.status_code == 200:
                                logger.info(f"Server is fully ready, opening browser at {url}")
                                webbrowser.open(url)
                                return
                        except:
                            pass
                    elif data.get("status") == "starting":
                        # If it's still starting, continue waiting
                        pass
            except requests.RequestException:
                pass
            time.sleep(2)

        logger.warning(f"Server did not respond as fully ready within {max_wait_time} seconds, opening browser anyway")
        webbrowser.open(url)

    # Start browser in a separate thread
    threading.Thread(target=open_browser_after_delay, args=(f"http://127.0.0.1:{port}",), daemon=True).start()

    logger.info(f"Web 端口: {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


def main():
    """Main function - Application entry point for web interface"""
    # 检查是否已有实例在运行
    existing_port = find_existing_instance()
    if existing_port:
        print(f"检测到已有实例在端口 {existing_port} 上运行，正在打开浏览器...")
        # Even if an instance is running, wait a bit and then open the browser
        # to ensure the server is fully loaded
        def open_existing():
            time.sleep(5)  # Give existing instance time to fully load
            webbrowser.open(f"http://127.0.0.1:{existing_port}")
        threading.Thread(target=open_existing, daemon=True).start()
        return

    print("启动 Web 界面...")
    run_web_ui()


if __name__ == "__main__":
    main()