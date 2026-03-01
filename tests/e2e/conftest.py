"""E2E测试配置"""
import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


@pytest.fixture(scope="session")
def base_url():
    """测试服务器基础URL"""
    return "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def browser_launch_options():
    """浏览器启动选项"""
    return {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"]
    }


@pytest.fixture(scope="session")
def viewport_size():
    """视口大小"""
    return {"width": 1280, "height": 720}
