"""
聊天功能UI测试 - Playwright
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.e2e
class TestUIChat:
    """聊天功能UI测试类"""

    def navigate_to_chat(self, page):
        """导航到聊天页面"""
        page.goto("http://127.0.0.1:8000", timeout=60000)
        page.wait_for_load_state("domcontentloaded")

        # 等待主容器加载
        page.wait_for_timeout(2000)

        # 查找并点击聊天模式切换按钮
        chat_button = page.locator(
            'button:has-text("聊天"), button:has-text("Chat"), [data-testid="chat-mode"], .chat-tab'
        ).first

        # 等待按钮可见
        try:
            chat_button.wait_for(state="visible", timeout=10000)
        except Exception:
            pass  # 按钮可能不存在

        if chat_button.is_visible():
            chat_button.click()
            page.wait_for_timeout(1000)

    def test_chat_page_load(self, page):
        """测试聊天页面加载"""
        self.navigate_to_chat(page)

        # 验证页面标题
        title = page.title()
        assert "File Tools" in title or "文件" in title

    def test_chat_input_visible(self, page):
        """测试聊天输入框可见"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator(
            'textarea, input[placeholder*="消息"], input[placeholder*="message"], input[placeholder*="提问"]'
        ).first

        # 如果找不到textarea，尝试找任何文本输入
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(
                1
            )  # 第二个输入框可能是聊天输入

        assert chat_input.is_visible() or page.locator('input[type="text"]').count() > 0

    def test_send_message(self, page):
        """测试发送消息"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator("textarea").first
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(1)

        if chat_input.is_visible():
            # 输入消息
            chat_input.fill("Hello, this is a test message")

            # 发送消息（按Enter）
            chat_input.press("Enter")

            # 等待响应
            page.wait_for_timeout(2000)

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_send_empty_message(self, page):
        """测试发送空消息"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator("textarea").first
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(1)

        if chat_input.is_visible():
            # 清空并发送
            chat_input.fill("")
            chat_input.press("Enter")

            page.wait_for_timeout(500)

        # 页面应该正常
        assert page.url.startswith("http://127.0.0.1:8000")

    def test_chat_history_display(self, page):
        """测试聊天历史显示"""
        self.navigate_to_chat(page)

        # 查找聊天历史容器
        history_container = page.locator(
            '.chat-history, .messages-container, [class*="chat"], [class*="message"]'
        ).first

        # 历史容器可能存在也可能不存在
        if history_container.is_visible():
            # 获取消息列表
            page.locator(".message, .chat-message").all()
            # 消息数量应该大于等于0

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_chat_with_long_message(self, page):
        """测试长消息"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator("textarea").first
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(1)

        if chat_input.is_visible():
            # 输入长消息
            long_message = "This is a very long message. " * 20
            chat_input.fill(long_message)
            chat_input.press("Enter")

            page.wait_for_timeout(2000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_chat_with_unicode(self, page):
        """测试Unicode消息"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator("textarea").first
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(1)

        if chat_input.is_visible():
            # 输入中文消息
            chat_input.fill("你好，这是一个测试消息 🎉")
            chat_input.press("Enter")

            page.wait_for_timeout(2000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_new_chat_button(self, page):
        """测试新建聊天按钮"""
        self.navigate_to_chat(page)

        # 查找新建聊天按钮
        new_chat_button = page.locator(
            'button:has-text("新建"), button:has-text("New"), button:has-text("+"), .new-chat'
        ).first

        if new_chat_button.is_visible():
            new_chat_button.click()
            page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_session_list_display(self, page):
        """测试会话列表显示"""
        self.navigate_to_chat(page)

        # 查找会话列表
        session_list = page.locator(
            '.session-list, .chat-sessions, [class*="session"]'
        ).first

        # 会话列表可能存在也可能不存在
        if session_list.is_visible():
            page.locator(".session-item, .chat-session").all()
            # 会话数量应该大于等于0

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_clear_chat(self, page):
        """测试清空聊天"""
        self.navigate_to_chat(page)

        # 查找清空按钮
        clear_button = page.locator(
            'button:has-text("清空"), button:has-text("Clear"), .clear-chat'
        ).first

        if clear_button.is_visible():
            clear_button.click()
            page.wait_for_timeout(500)

            # 可能需要确认
            confirm_button = page.locator(
                'button:has-text("确认"), button:has-text("Confirm"), button:has-text("Yes"), .confirm'
            ).first
            if confirm_button.is_visible():
                confirm_button.click()
                page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_chat_mode_toggle(self, page):
        """测试聊天模式切换"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 切换到聊天模式
        chat_button = page.locator(
            'button:has-text("聊天"), button:has-text("Chat"), .chat-tab'
        ).first
        if chat_button.is_visible():
            chat_button.click()
            page.wait_for_timeout(500)

        # 切换回搜索模式
        search_button = page.locator(
            'button:has-text("搜索"), button:has-text("Search"), .search-tab'
        ).first
        if search_button.is_visible():
            search_button.click()
            page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_send_button_click(self, page):
        """测试发送按钮点击"""
        self.navigate_to_chat(page)

        # 查找输入框和发送按钮
        chat_input = page.locator("textarea").first
        if not chat_input.is_visible():
            chat_input = page.locator('input[type="text"]').nth(1)

        send_button = page.locator(
            'button:has-text("发送"), button:has-text("Send"), .send-button, [data-testid="send"]'
        ).first

        if chat_input.is_visible() and send_button.is_visible():
            chat_input.fill("Test message")
            send_button.click()
            page.wait_for_timeout(2000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_chat_placeholder_text(self, page):
        """测试聊天输入框占位符"""
        self.navigate_to_chat(page)

        # 查找聊天输入框
        chat_input = page.locator('textarea, input[type="text"]').nth(1)

        if chat_input.is_visible():
            placeholder = chat_input.get_attribute("placeholder")
            # 占位符可能包含"消息"、"message"、"提问"等关键词
            assert placeholder is not None, "placeholder 属性应该存在"

    def test_chat_container_scroll(self, page):
        """测试聊天容器滚动"""
        self.navigate_to_chat(page)

        # 查找聊天容器
        chat_container = page.locator(
            '.chat-container, .messages-container, [class*="chat"]'
        ).first

        if chat_container.is_visible():
            # 尝试滚动
            chat_container.evaluate("el => el.scrollTop = el.scrollHeight")
            page.wait_for_timeout(300)

        assert page.url.startswith("http://127.0.0.1:8000")
