#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件

使用 Pywebview 创建原生桌面窗口，在后台线程运行 FastAPI 服务。
"""
import sys
import os

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    if sys.stdout and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    else:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
    if sys.stderr and hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    else:
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
import psutil
import requests
import time
import socket
import threading
import atexit
import signal

# 修复 pythonnet 退出报错：禁用 clr 的 atexit 回调
os.environ['PYTHONNET_SHUTDOWN_MODE'] = 'Soft'

# 修复 pycparser/ply 在 PyInstaller 冻结模式下的 YaccError
# 现在由 file-tools.spec 处理：将 lextab.py/yacctab.py 作为数据文件收集

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
    # 打包后进程名是 FileTools.exe，开发环境是 python main.py
    app_identity = "main.py"
    if getattr(sys, "frozen", False):
        app_identity = os.path.basename(sys.executable).lower()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline_str = ' '.join(proc.info['cmdline'] or [])
            if (proc.info['pid'] != current_pid and
                    (app_identity in cmdline_str or
                     app_identity in (proc.info.get('name') or '').lower())):
                for port in range(8000, 8011):
                    if is_port_in_use(port):
                        try:
                            response = requests.get(
                                f"http://127.0.0.1:{port}/api/health", timeout=1)
                            if response.status_code == 200:
                                return port
                        except requests.RequestException:
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
                    except requests.RequestException:
                        pass
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def start_fastapi_server(port):
    """启动 FastAPI 服务器"""
    import uvicorn
    from backend.api.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()


class WebViewAPI:
    """暴露给前端 JavaScript 调用的 API"""

    def open_external_link(self, url):
        """在外部浏览器打开链接"""
        import webbrowser
        try:
            webbrowser.open(url)
            return {"success": True, "message": "已在外部浏览器打开链接"}
        except Exception as e:
            return {"success": False, "message": f"打开链接失败: {e}"}

    def select_directory(self):
        """打开系统目录选择对话框"""
        import webview
        try:
            result = webview.windows[0].create_file_dialog(
                dialog_type=webview.FOLDER_DIALOG
            )
            if result and len(result) > 0:
                import os
                return {"success": True, "path": os.path.abspath(result[0]), "canceled": False}
            return {"success": True, "canceled": True}
        except Exception as e:
            return {"success": False, "message": f"选择目录失败: {e}"}


def run_desktop_app():
    """运行桌面应用"""
    import webview

    from backend.utils.logger import setup_logger
    logger = setup_logger()
    logger.info("应用启动中...")

    # 设置退出标志
    exit_event = threading.Event()
    window_ref = {'window': None, 'closed': False}

    # 信号处理函数
    def signal_handler(signum, _frame):
        logger.info(f"收到信号 {signum}，准备退出...")
        exit_event.set()
        # 直接关闭窗口，避免重复调用
        if window_ref['window'] and not window_ref['closed']:
            window_ref['closed'] = True
            try:
                window_ref['window'].destroy()
            except (RuntimeError, AttributeError):
                pass

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
                clr.System.GC.Collect()  # type: ignore
                clr.System.GC.WaitForPendingFinalizers()  # type: ignore
        except Exception:  # noqa: BLE001
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

    api = WebViewAPI()
    window = webview.create_window(
        title='File Tools',
        url=url,
        width=1280,
        height=800,
        min_size=(900, 600),
        text_select=True,
        js_api=api,
    )
    window_ref['window'] = window

    # 注册窗口关闭事件
    def on_closing():
        if window_ref['closed']:
            return True
        logger.info("窗口关闭事件触发")
        window_ref['closed'] = True
        exit_event.set()
        return True

    window.events.closing += on_closing

    # 在后台线程中检查退出信号
    def check_exit():
        while not exit_event.is_set():
            exit_event.wait(0.5)
        if not window_ref['closed']:
            logger.info("退出信号已设置，关闭窗口...")
            window_ref['closed'] = True
            try:
                window.destroy()
            except (RuntimeError, AttributeError):
                pass

    exit_thread = threading.Thread(target=check_exit, daemon=True)
    exit_thread.start()

    webview.start(debug=False)

    # 标记退出事件，确保后台线程退出
    window_ref['closed'] = True
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
