"""E2E测试配置 - 跨平台支持

基于 Playwright E2E Testing Skill 最佳实践:
- 自动处理 Linux 无头模式 (xvfb)
- 跨平台一致的浏览器配置
- 失败时自动截图和录制
"""

import os
import sys

import pytest


def _is_linux_display_available():
    """检查 Linux 是否有可用的显示环境"""
    if sys.platform != "linux":
        return True
    return (
        os.environ.get("DISPLAY") is not None
        or os.environ.get("WAYLAND_DISPLAY") is not None
    )


@pytest.fixture(scope="session")
def base_url():
    """测试服务器基础URL"""
    return "http://127.0.0.1:18642"


@pytest.fixture(scope="session")
def browser_launch_options():
    """浏览器启动选项 - 跨平台优化

    Skill 最佳实践:
    - headless=True 确保 CI 环境一致
    - --no-sandbox 解决 Linux 权限问题
    - --disable-dev-shm-usage 防止 Docker/CI 内存问题
    """
    options = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    }

    # Linux 无显示环境时强制使用 headless
    if sys.platform == "linux" and not _is_linux_display_available():
        options["headless"] = True

    return options


@pytest.fixture(scope="session")
def browser_context_args():
    """浏览器上下文参数 - 跨平台一致"""
    return {
        "viewport": {"width": 1280, "height": 720},
        "record_video_dir": "./test-results/videos/" if os.environ.get("CI") else None,
        "record_video_size": {"width": 1280, "height": 720},
    }


@pytest.fixture(scope="session")
def viewport_size():
    """视口大小"""
    return {"width": 1280, "height": 720}


@pytest.fixture(autouse=True)
def _setup_test_environment(page, base_url):
    """每个测试用例的通用设置"""
    # 设置默认超时
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)

    # 导航到基础 URL
    page.goto(base_url)
    page.wait_for_load_state("domcontentloaded")

    yield


# pytest-playwright 提供的 fixtures (不需要重新定义):
# - page: Playwright Page 对象
# - browser: Playwright Browser 对象
# - browser_context: Playwright BrowserContext 对象
# - playwright: Playwright 对象


def pytest_configure(config):
    """Pytest 配置 - 添加自定义 markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "flaky: marks tests as flaky (will be retried)")


def wait_for_app_ready(base_url: str, timeout: int = 30) -> bool:
    """等待应用启动就绪

    Args:
        base_url: 应用基础 URL
        timeout: 最大等待时间（秒）

    Returns:
        True 如果应用就绪，False 否则
    """
    import time
    import urllib.error
    import urllib.request

    health_url = f"{base_url}/api/health"
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            pass
        time.sleep(0.5)

    return False


def pytest_runtest_setup(item):
    """测试前检查 - 平台特定跳过"""
    # 如果标记为 skip_on_windows 且在 Windows 上，跳过
    skip_on_windows = item.get_closest_marker("skip_on_windows")
    if skip_on_windows and sys.platform == "win32":
        pytest.skip("Test skipped on Windows")

    # 如果标记为 skip_on_linux 且在 Linux 上，跳过
    skip_on_linux = item.get_closest_marker("skip_on_linux")
    if skip_on_linux and sys.platform == "linux":
        pytest.skip("Test skipped on Linux")

    # 如果标记为 skip_on_macos 且在 macOS 上，跳过
    skip_on_macos = item.get_closest_marker("skip_on_macos")
    if skip_on_macos and sys.platform == "darwin":
        pytest.skip("Test skipped on macOS")
