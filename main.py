#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - Tauri 后端入口

FastAPI 服务，由 Tauri 窗口加载。
"""

import os
import sys

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    import io

    if sys.stdout and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    else:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    else:
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")

import socket
import warnings

# 抑制 jieba pkg_resources 弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

from backend.utils.logger import setup_logger

logger = setup_logger()


def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


DEFAULT_PORT = 18642  # 不常见的端口，避免与常见应用冲突


def find_available_port(start=None, end=None):
    """查找可用端口

    优先级:
    1. FILETOOLS_PORT 环境变量
    2. 默认端口 18642 (如果可用)
    3. 18642-18652 范围内找可用端口
    """
    # 1. 环境变量指定
    env_port = os.environ.get("FILETOOLS_PORT")
    if env_port:
        try:
            port = int(env_port)
            if not is_port_in_use(port):
                logger.info(f"使用环境变量指定的端口: {port}")
                return port
        except ValueError:
            pass

    # 2. 默认端口
    start = start or DEFAULT_PORT
    end = end or (start + 10)

    for p in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            s.close()
            logger.info(f"找到可用端口: {p}")
            return p
        except OSError:
            continue

    # 3. 系统分配随机端口
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    logger.info(f"使用系统分配的随机端口: {port}")
    return port


def get_port_file_path():
    """获取端口文件的路径（用于 Rust 读取实际端口）"""
    # 使用 tempfile 目录，确保跨平台兼容
    import tempfile

    return os.path.join(tempfile.gettempdir(), "filetools_backend_port.txt")


def write_backend_port(port):
    """将后端实际端口写入文件，供 Rust 读取用于优雅关闭"""
    port_file = get_port_file_path()
    try:
        with open(port_file, "w", encoding="utf-8") as f:
            f.write(str(port))
        logger.info(f"后端端口已写入: {port_file} = {port}")
    except Exception as e:
        logger.warning(f"写入端口文件失败: {e}")


def start_fastapi_server(port):
    """启动 FastAPI 服务器"""
    import uvicorn

    from backend.api.main import app

    logger.info(f"FastAPI 启动于端口 {port}")

    # 将实际端口写入环境变量，供其他组件使用
    os.environ["FILETOOLS_ACTUAL_PORT"] = str(port)

    # 将实际端口写入文件，供 Rust 读取用于优雅关闭
    write_backend_port(port)

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    server.run()


def main():
    """主函数 - 启动 FastAPI 服务供 Tauri 使用"""
    port = find_available_port()
    start_fastapi_server(port)


if __name__ == "__main__":
    main()
