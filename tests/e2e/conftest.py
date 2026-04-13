"""E2E测试配置 - 跨平台支持

基于 Playwright E2E Testing Skill 最佳实践:
- 自动处理 Linux 无头模式 (xvfb)
- 跨平台一致的浏览器配置
- 失败时自动截图和录制
"""

import os
import subprocess
import sys
import time

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


@pytest.fixture(scope="session")
def _ensure_server_running(base_url):
    """确保测试服务器已启动（session级别，只执行一次）

    如果服务器未运行：
    - 在 CI 环境中：等待 30 秒后超时（CI 应自行启动服务器）
    - 在本地环境中：自动启动服务器进程
    """
    import urllib.error
    import urllib.request

    health_url = f"{base_url}/api/health"
    start_time = time.time()

    # 先检查服务器是否已运行
    for i in range(6):  # 最多等待 3 秒
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    elapsed = time.time() - start_time
                    print(f"\n[E2E] 服务器已就绪 (耗时 {elapsed:.1f}s)")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            pass
        time.sleep(0.5)

    # 服务器未运行，尝试本地启动
    if os.environ.get("CI"):
        # CI 环境：等待服务器启动（由 CI workflow 负责启动）
        print("\n[E2E] CI 环境：等待外部启动的服务器...")
        for i in range(60):  # 最多等待 30 秒
            try:
                req = urllib.request.Request(health_url)
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        elapsed = time.time() - start_time
                        print(f"[E2E] CI 服务器就绪 (耗时 {elapsed:.1f}s)")
                        return True
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                OSError,
            ):
                pass
            time.sleep(0.5)
        import warnings
        warnings.warn("[E2E] CI 环境中服务器未启动，测试可能失败")
        return False

    # 本地环境：自动启动服务器
    print("\n[E2E] 本地环境：自动启动服务器...")
    server_process = None
    try:
        # 查找项目根目录的 main.py
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_py = os.path.join(project_root, "main.py")

        if not os.path.exists(main_py):
            pytest.exit(f"[E2E] 未找到 main.py: {main_py}")

        # 在后台启动服务器
        server_process = subprocess.Popen(
            [sys.executable, main_py],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待服务器就绪
        for i in range(60):  # 最多等待 30 秒
            try:
                req = urllib.request.Request(health_url)
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        elapsed = time.time() - start_time
                        print(f"[E2E] 本地服务器启动成功 (耗时 {elapsed:.1f}s)")
                        return True
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                OSError,
            ):
                pass
            time.sleep(0.5)

        pytest.exit(f"[E2E] 服务器启动超时（30秒）")

    except Exception as e:
        if server_process:
            server_process.terminate()
        pytest.exit(f"[E2E] 启动服务器失败: {e}")


@pytest.fixture(autouse=True)
def _setup_test_environment(page, base_url, _ensure_server_running):
    """每个测试用例的通用设置 - 智能导航

    依赖 _ensure_server_running 确保服务器已就绪后再导航。
    如果当前不在目标URL上，则自动导航到 base_url。
    """
    # 设置默认超时
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)

    # 检查当前URL，如果不在目标页面上则导航
    current_url = page.url
    if not current_url.startswith(base_url):
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
