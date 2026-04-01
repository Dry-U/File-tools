"""E2E测试配置"""

import pytest


@pytest.fixture(scope="session")
def base_url():
    """测试服务器基础URL"""
    return "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def browser_launch_options():
    """浏览器启动选项"""
    return {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}


@pytest.fixture(scope="session")
def viewport_size():
    """视口大小"""
    return {"width": 1280, "height": 720}


@pytest.fixture
def page(page):
    """增强的page fixture，带有默认等待"""
    # 等待 DOM content loaded 而不是 networkidle，后者可能不够
    page.set_default_timeout(10000)
    return page
