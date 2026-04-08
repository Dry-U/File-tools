"""E2E测试配置"""

import pytest


@pytest.fixture(scope="session")
def base_url():
    """测试服务器基础URL"""
    return "http://127.0.0.1:18642"


@pytest.fixture(scope="session")
def browser_launch_options():
    """浏览器启动选项"""
    return {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}


@pytest.fixture(scope="session")
def viewport_size():
    """视口大小"""
    return {"width": 1280, "height": 720}


# 注意: page fixture 由 pytest-playwright 插件提供
# 不要重新定义，以免导致递归依赖
