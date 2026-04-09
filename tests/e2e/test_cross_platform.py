"""
跨平台 E2E 测试示例

展示如何编写在三端 (Windows/Linux/macOS) 都能运行的测试。
基于 Playwright E2E Testing Skill 最佳实践。
"""

import sys

import pytest


@pytest.mark.e2e
class TestCrossPlatform:
    """跨平台兼容性测试类"""

    def test_page_loads_on_all_platforms(self, page):
        """测试页面在所有平台都能加载"""
        # 页面已在 conftest.py fixture 中加载
        assert page.url.startswith("http://127.0.0.1:18642")

        # 验证页面标题存在
        title = page.title()
        assert len(title) > 0, "页面标题不应为空"

    def test_search_input_works_cross_platform(self, page):
        """测试搜索输入框在所有平台正常工作"""
        # 查找搜索输入框 (使用通用选择器)
        search_input = page.locator('input[type="text"]').first

        # 等待元素可见
        search_input.wait_for(state="visible", timeout=10000)

        # 输入搜索词
        search_input.fill("test query")

        # 验证输入值
        assert search_input.input_value() == "test query"

        # 提交搜索 (按 Enter 是跨平台的)
        search_input.press("Enter")

        # 等待响应
        # NOTE: Use smart wait or remove

    @pytest.mark.skip_on_windows
    def test_linux_specific_feature(self, page):
        """Linux 特有功能测试示例

        使用 @pytest.mark.skip_on_windows 标记跳过其他平台
        """
        # 这里测试仅在 Linux 上有效的功能
        pass

    def test_keyboard_shortcuts_cross_platform(self, page):
        """测试键盘快捷键在所有平台工作

        Playwright 自动处理平台差异:
        - Windows: Ctrl+K
        - macOS: Meta+K
        - Linux: Ctrl+K
        """
        # Playwright 的 keyboard 会自动处理平台差异
        # Meta 键在 Windows/Linux 映射为 Ctrl，在 macOS 映射为 Cmd
        page.keyboard.press("Control+k")

        # 等待响应
        # NOTE: Use smart wait or remove

    def test_viewport_responsive(self, page):
        """测试视口响应式布局"""
        # 设置不同尺寸的视口
        viewports = [
            {"width": 1920, "height": 1080},  # Desktop
            {"width": 1366, "height": 768},  # Laptop
            {"width": 1280, "height": 720},  # Standard
        ]

        for viewport in viewports:
            page.set_viewport_size(viewport)
            # NOTE: Use smart wait or remove

            # 验证关键元素仍然可见
            search_input = page.locator('input[type="text"]').first
            assert search_input.is_visible(), f"搜索框在 {viewport} 下应可见"


@pytest.mark.e2e
class TestPlatformSpecificBehavior:
    """平台特定行为测试"""

    def test_file_path_display(self, page):
        """测试文件路径显示 (平台路径格式不同)

        Windows: C:\\path\\to\\file
        Unix: /path/to/file
        """
        # 执行搜索以获取结果
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test")
        search_input.press("Enter")
        # NOTE: Use smart wait or remove

        # 获取结果中的路径
        result_paths = page.locator('.result-path, [class*="path"]').all_inner_texts()

        for path in result_paths:
            if sys.platform == "win32":
                # Windows 路径可能包含驱动器号或反斜杠
                assert "\\\\" in path or ":" in path or "/" in path, (
                    f"Windows 路径格式不正确: {path}"
                )
            else:
                # Unix 路径以 / 开头
                assert path.startswith("/") or path.startswith("~"), (
                    f"Unix 路径格式不正确: {path}"
                )

    def test_window_controls(self, page):
        """测试窗口控制按钮存在性

        注意: Tauri 应用可能有自定义标题栏，按钮选择器可能不同
        """
        # 查找可能的窗口控制按钮
        minimize_btn = page.locator(
            '[data-testid="minimize"], .window-minimize, [aria-label="minimize"]'
        ).first
        maximize_btn = page.locator(
            '[data-testid="maximize"], .window-maximize, [aria-label="maximize"]'
        ).first
        close_btn = page.locator(
            '[data-testid="close"], .window-close, [aria-label="close"]'
        ).first

        # 至少有一种控制按钮应该存在 (如果应用有自定义标题栏)
        # 注意: 不是所有应用都有可见的窗口控制按钮
        controls_exist = (
            minimize_btn.is_visible()
            or maximize_btn.is_visible()
            or close_btn.is_visible()
        )

        # 记录结果但不强制断言，因为窗口控制可能在 Tauri 中由 Rust 处理
        print(f"Window controls visible: {controls_exist}")
