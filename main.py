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
import atexit
import signal

# 修复 pythonnet 退出报错：禁用 clr 的 atexit 回调
os.environ['PYTHONNET_SHUTDOWN_MODE'] = 'Soft'

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

    # 设置退出标志
    exit_event = threading.Event()

    # 信号处理函数
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，准备退出...")
        exit_event.set()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 注册 atexit 处理程序，确保优雅退出
    def cleanup():
        try:
            logger.info("执行清理操作...")
            # 禁用 pythonnet 的默认清理，避免 KeyboardInterrupt 报错
            if 'clr' in sys.modules:
                import clr
                clr.System.GC.Collect()
                clr.System.GC.WaitForPendingFinalizers()
        except Exception as e:
            pass

    atexit.register(cleanup)

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

    # 注册窗口关闭事件
    def on_closing():
        logger.info("窗口关闭事件触发")
        exit_event.set()
        return True

    window.events.closing += on_closing

    # 在后台线程中检查退出信号
    def check_exit():
        while not exit_event.is_set():
            exit_event.wait(0.5)
        logger.info("退出信号已设置，关闭窗口...")
        window.destroy()

    exit_thread = threading.Thread(target=check_exit, daemon=True)
    exit_thread.start()

    # 尝试使用 Edge Chromium 引擎（如果可用）
    # GUI 参数: 'qt' 或 'gtk' 或 'cef' 或 'edgechromium' 或 'edgehtml' 或 'mshtml'
    try:
        # Windows 优先使用 edgechromium（Edge WebView2）
        import platform
        if platform.system() == 'Windows':
            webview.start(gui='edgechromium', debug=False)
        else:
            webview.start()
    except Exception as e:
        logger.warning(f"Edge Chromium 启动失败，尝试默认引擎: {e}")
        webview.start()

    # 标记退出事件，确保后台线程退出
    exit_event.set()
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
