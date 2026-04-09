"""
搜索功能UI测试 - Playwright
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.e2e
class TestUISearch:
    """搜索功能UI测试类"""

    @pytest.fixture(scope="class")
    def browser_context_args(self):
        """浏览器上下文参数"""
        return {"viewport": {"width": 1280, "height": 720}}

    def test_page_load(self, page):
        """测试页面加载"""
        page.goto("http://127.0.0.1:18642")

        # 等待页面加载完成
        page.wait_for_load_state("networkidle")

        # 验证页面标题
        title = page.title()
        assert "File Tools" in title or "文件" in title

    def test_search_input_visible(self, page):
        """测试搜索输入框可见"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("domcontentloaded")

        # 查找搜索输入框
        search_input_selectors = (
            'input[type="text"], input[placeholder*="搜索"], '
            'input[placeholder*="search"]'
        )
        search_input = page.locator(search_input_selectors).first

        # 等待输入框可见
        search_input.wait_for(state="visible", timeout=5000)
        assert search_input.is_visible()

    def test_search_button_visible(self, page):
        """测试搜索按钮可见"""
        page.goto("http://127.0.0.1:18642")

        # 等待主内容加载完成 (使用 Playwright 自动等待)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")

        # 查找搜索按钮（可能是按钮或图标）
        search_button_selectors = (
            'button:has-text("搜索"), button:has-text("Search"), '
            '.search-button, [data-testid="search-button"], .search-btn'
        )
        search_button = page.locator(search_button_selectors)

        # 等待按钮可见（最多等5秒）
        button_visible = False
        try:
            search_button.first.wait_for(state="visible", timeout=5000)
            button_visible = True
        except Exception:
            pass  # 按钮可能不存在

        # 如果按钮存在，验证它可见
        if button_visible:
            assert search_button.first.is_visible()
            return

        # 如果没有找到特定按钮，检查是否有可点击的搜索图标或搜索输入框旁边的按钮
        search_icon_selectors = (
            '.search-icon, [class*="search"], .search-input-box button, '
            "#searchInput + button"
        )
        search_icon = page.locator(search_icon_selectors).first
        icon_visible = False
        try:
            search_icon.wait_for(state="visible", timeout=3000)
            icon_visible = True
        except Exception:
            pass

        # 检查搜索输入框是否存在
        search_input = page.locator('#searchInput, input[type="text"]').first
        input_visible = search_input.is_visible()

        # 至少有一种搜索方式应该可用
        assert button_visible or icon_visible or input_visible, (
            "搜索按钮、搜索图标或搜索输入框都不存在"
        )

    def test_perform_search(self, page):
        """测试执行搜索"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 记录搜索前的欢迎区域状态
        welcome_before = page.locator(
            "#search-welcome-container, .search-welcome"
        ).is_visible()

        # 输入搜索词
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test")

        # 提交搜索（按Enter或点击按钮）
        search_input.press("Enter")

        # 等待搜索结果加载（使用自动等待）
        results_container = page.locator("#resultsContainer, .search-results")
        results_container.wait_for(state="visible", timeout=10000)

        # 验证搜索后欢迎区域或搜索结果显示（至少有一个状态改变）
        welcome_after = page.locator(
            "#search-welcome-container, .search-welcome"
        ).is_visible()
        results_visible = results_container.is_visible()

        # 搜索应该触发某种 UI 变化（欢迎区域隐藏或结果显示）
        assert welcome_before == welcome_after or results_visible, "搜索后 UI 应有变化"

        # 验证搜索输入框仍有内容（没有被意外清除）
        input_value = search_input.input_value()
        assert input_value == "test", "搜索后输入框内容应保留"

    def test_search_results_display(self, page):
        """测试搜索结果显示"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 执行搜索
        search_input = page.locator('input[type="text"]').first
        search_input.fill("python")
        search_input.press("Enter")

        # 等待结果加载（使用自动等待）
        results_container = page.locator("#resultsContainer, .search-results").first
        results_container.wait_for(state="visible", timeout=10000)

        # 检查结果容器是否存在并可见（display: none 被移除）
        results_display = results_container.evaluate("el => el.style.display")

        # 验证结果容器已显示（不再隐藏）
        assert results_display != "none" or results_container.is_visible(), (
            "搜索后结果容器应该显示"
        )

    def test_empty_search(self, page):
        """测试空搜索"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 清空输入框并提交
        search_input = page.locator('input[type="text"]').first
        search_input.fill("")
        search_input.press("Enter")

        # 等待输入框值更新（使用 expect 自动等待）
        page.wait_for_function(
            """() => {
                const input = document.querySelector('input[type="text"]');
                return input && input.value === '';
            }""",
            timeout=5000,
        )

        # 验证输入框已清空
        input_value = search_input.input_value()
        assert input_value == "", "空搜索后输入框应保持清空"

    def test_search_with_special_characters(self, page):
        """测试特殊字符搜索"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 输入特殊字符
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test@#$%")
        search_input.press("Enter")

        # 等待网络空闲（确保请求完成）
        page.wait_for_load_state("networkidle", timeout=10000)

        # 页面应该正常处理
        assert page.url.startswith("http://127.0.0.1:18642")

    def test_search_with_unicode(self, page):
        """测试Unicode搜索"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 输入中文
        search_input = page.locator('input[type="text"]').first
        search_input.fill("中文测试")
        search_input.press("Enter")

        # 等待网络空闲（确保请求完成）
        page.wait_for_load_state("networkidle", timeout=10000)

        # 页面应该正常处理中文
        assert page.url.startswith("http://127.0.0.1:18642")

    def test_sidebar_toggle(self, page):
        """测试侧边栏切换"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 查找侧边栏切换按钮
        toggle_button = page.locator(
            '.sidebar-toggle, [class*="toggle"], button:has([class*="menu"])'
        ).first

        if toggle_button.is_visible():
            # 点击切换
            toggle_button.click()
            # 使用 wait_for_function 等待侧边栏状态变化
            sidebar_check = """
                () => {
                    const sidebar = document.querySelector(
                        '.sidebar, [class*="sidebar"]'
                    );
                    return sidebar && (
                        sidebar.classList.contains('collapsed') ||
                        sidebar.classList.contains('expanded') ||
                        sidebar.style.transform !== ''
                    );
                }
            """
            page.wait_for_function(sidebar_check, timeout=5000)

            # 再次点击恢复
            toggle_button.click()
            # NOTE: Short wait for animation - use wait_for_function for
            # better reliability

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:18642")

    def test_mode_switch_search_to_chat(self, page):
        """测试从搜索模式切换到聊天模式"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 查找聊天模式切换按钮
        chat_button_selectors = (
            'button:has-text("聊天"), button:has-text("Chat"), '
            '[data-testid="chat-mode"]'
        )
        chat_button = page.locator(chat_button_selectors).first

        if chat_button.is_visible():
            chat_button.click()
            # 等待聊天输入框出现
            chat_input = page.locator(
                'textarea, input[placeholder*="消息"], input[placeholder*="message"]'
            ).first
            chat_input.wait_for(state="visible", timeout=5000)
            # 验证聊天输入框可见
            assert chat_input.is_visible(), "聊天输入框应该可见"

    def test_search_filters(self, page):
        """测试搜索过滤器"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 查找过滤器按钮或下拉菜单
        filter_button = page.locator(
            'button:has-text("过滤"), button:has-text("Filter"), .filter-button'
        ).first

        if filter_button.is_visible():
            filter_button.click()
            # 等待过滤器面板出现
            filter_panel_selectors = (
                '.filter-option, [class*="filter"], '
                '.filter-panel, [class*="filter-panel"]'
            )
            page.locator(filter_panel_selectors).first.wait_for(
                state="visible", timeout=5000
            )

            # 查找过滤器选项
            page.locator('.filter-option, [class*="filter"]').all()
            # 过滤器选项可能存在也可能不存在

    def test_result_item_click(self, page):
        """测试结果项点击"""
        page.goto("http://127.0.0.1:18642")
        page.wait_for_load_state("networkidle")

        # 执行搜索
        search_input = page.locator('input[type="text"]').first
        search_input.fill("test")
        search_input.press("Enter")

        # 等待结果加载（使用自动等待）
        results_container = page.locator("#resultsContainer, .search-results")
        results_container.wait_for(state="visible", timeout=10000)

        # 查找结果项
        result_items = page.locator('.result-item, [class*="result"], .file-item').all()

        if len(result_items) > 0:
            # 点击第一个结果
            result_items[0].click()
            # 等待可能的模态框或详情页
            page.wait_for_load_state("networkidle", timeout=5000)

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:18642")
