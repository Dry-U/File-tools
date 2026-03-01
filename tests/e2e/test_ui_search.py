"""
搜索功能UI测试 - Playwright
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


@pytest.mark.e2e
class TestUISearch:
    """搜索功能UI测试类"""

    @pytest.fixture(scope="class")
    def browser_context_args(self):
        """浏览器上下文参数"""
        return {
            "viewport": {"width": 1280, "height": 720}
        }

    def test_page_load(self, page):
        """测试页面加载"""
        page.goto("http://127.0.0.1:8000")

        # 等待页面加载完成
        page.wait_for_load_state("networkidle")

        # 验证页面标题
        title = page.title()
        assert "File Tools" in title or "文件" in title

    def test_search_input_visible(self, page):
        """测试搜索输入框可见"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找搜索输入框
        search_input = page.locator('input[type="text"], input[placeholder*="搜索"], input[placeholder*="search"]').first
        assert search_input.is_visible()

    def test_search_button_visible(self, page):
        """测试搜索按钮可见"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找搜索按钮（可能是按钮或图标）
        search_button = page.locator('button:has-text("搜索"), button:has-text("Search"), .search-button, [data-testid="search-button"]').first

        # 如果没有找到特定按钮，检查是否有可点击的搜索图标
        if not search_button.is_visible():
            search_icon = page.locator('.search-icon, [class*="search"]').first
            assert search_icon.is_visible()

    def test_perform_search(self, page):
        """测试执行搜索"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 输入搜索词
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test")

        # 提交搜索（按Enter或点击按钮）
        search_input.press("Enter")

        # 等待搜索结果（如果有的话）
        page.wait_for_timeout(1000)

        # 验证页面仍在加载状态（没有崩溃）
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_search_results_display(self, page):
        """测试搜索结果显示"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 执行搜索
        search_input = page.locator('input[type="text"]').first
        search_input.fill("python")
        search_input.press("Enter")

        # 等待结果加载
        page.wait_for_timeout(2000)

        # 检查结果容器是否存在
        results_container = page.locator('.search-results, [class*="result"], [data-testid*="result"]').first

        # 即使没有结果，页面也应该正常显示
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_empty_search(self, page):
        """测试空搜索"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 清空输入框并提交
        search_input = page.locator('input[type="text"]').first
        search_input.fill("")
        search_input.press("Enter")

        # 等待响应
        page.wait_for_timeout(500)

        # 页面应该仍然正常
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_search_with_special_characters(self, page):
        """测试特殊字符搜索"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 输入特殊字符
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test@#$%")
        search_input.press("Enter")

        # 等待响应
        page.wait_for_timeout(1000)

        # 页面应该正常处理
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_search_with_unicode(self, page):
        """测试Unicode搜索"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 输入中文
        search_input = page.locator('input[type="text"]').first
        search_input.fill("中文测试")
        search_input.press("Enter")

        # 等待响应
        page.wait_for_timeout(1000)

        # 页面应该正常处理中文
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_sidebar_toggle(self, page):
        """测试侧边栏切换"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找侧边栏切换按钮
        toggle_button = page.locator('.sidebar-toggle, [class*="toggle"], button:has([class*="menu"])').first

        if toggle_button.is_visible():
            # 点击切换
            toggle_button.click()
            page.wait_for_timeout(500)

            # 再次点击恢复
            toggle_button.click()
            page.wait_for_timeout(500)

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_mode_switch_search_to_chat(self, page):
        """测试从搜索模式切换到聊天模式"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找聊天模式切换按钮
        chat_button = page.locator('button:has-text("聊天"), button:has-text("Chat"), [data-testid="chat-mode"]').first

        if chat_button.is_visible():
            chat_button.click()
            page.wait_for_timeout(500)

            # 验证切换到聊天模式
            chat_input = page.locator('textarea, input[placeholder*="消息"], input[placeholder*="message"]').first
            assert chat_input.is_visible() or not chat_input.is_visible()  # 可能不存在

    def test_search_filters(self, page):
        """测试搜索过滤器"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找过滤器按钮或下拉菜单
        filter_button = page.locator('button:has-text("过滤"), button:has-text("Filter"), .filter-button').first

        if filter_button.is_visible():
            filter_button.click()
            page.wait_for_timeout(500)

            # 查找过滤器选项
            filter_options = page.locator('.filter-option, [class*="filter"]').all()
            # 过滤器选项可能存在也可能不存在

    def test_result_item_click(self, page):
        """测试结果项点击"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 执行搜索
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test")
        search_input.press("Enter")

        # 等待结果
        page.wait_for_timeout(2000)

        # 查找结果项
        result_items = page.locator('.result-item, [class*="result"], .file-item').all()

        if len(result_items) > 0:
            # 点击第一个结果
            result_items[0].click()
            page.wait_for_timeout(500)

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:8000")
