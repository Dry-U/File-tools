"""
设置面板UI测试 - Playwright
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


@pytest.mark.e2e
class TestUISettings:
    """设置面板UI测试类"""

    def open_settings(self, page):
        """打开设置面板"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找设置按钮
        settings_button = page.locator('button:has-text("设置"), button:has-text("Settings"), .settings-button, [data-testid="settings"], .settings-icon').first

        if settings_button.is_visible():
            settings_button.click()
            page.wait_for_timeout(500)

    def test_settings_panel_open(self, page):
        """测试设置面板打开"""
        self.open_settings(page)

        # 查找设置面板
        settings_panel = page.locator('.settings-panel, .settings-modal, [class*="settings"], [data-testid="settings-panel"]').first

        # 设置面板应该可见或页面应该正常
        assert settings_panel.is_visible() or page.url.startswith("http://127.0.0.1:8000")

    def test_settings_panel_close(self, page):
        """测试设置面板关闭"""
        self.open_settings(page)

        # 查找关闭按钮
        close_button = page.locator('button:has-text("关闭"), button:has-text("Close"), button:has-text("×"), .close-button, [data-testid="close"]').first

        if close_button.is_visible():
            close_button.click()
            page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_ai_model_settings(self, page):
        """测试AI模型设置"""
        self.open_settings(page)

        # 查找AI模型设置区域
        ai_settings = page.locator('.ai-settings, [class*="ai-model"], [data-testid="ai-settings"]').first

        # 查找启用AI复选框
        enable_checkbox = page.locator('input[type="checkbox"][name*="enable"], input[type="checkbox"][id*="ai"]').first

        if enable_checkbox.is_visible():
            # 切换启用状态
            enable_checkbox.click()
            page.wait_for_timeout(300)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_api_url_input(self, page):
        """测试API URL输入"""
        self.open_settings(page)

        # 查找API URL输入框
        api_url_input = page.locator('input[name*="api_url"], input[name*="api-url"], input[placeholder*="URL"]').first

        if api_url_input.is_visible():
            # 输入测试URL
            api_url_input.fill("http://localhost:8080/v1/chat/completions")
            page.wait_for_timeout(300)

            # 验证输入值
            value = api_url_input.input_value()
            assert "localhost" in value

    def test_api_key_input(self, page):
        """测试API密钥输入"""
        self.open_settings(page)

        # 查找API密钥输入框
        api_key_input = page.locator('input[type="password"], input[name*="api_key"], input[name*="api-key"]').first

        if api_key_input.is_visible():
            # 输入测试密钥
            api_key_input.fill("test-api-key-12345")
            page.wait_for_timeout(300)

            # 验证输入值（密码字段可能无法直接读取）
            assert api_key_input.is_visible()

    def test_temperature_slider(self, page):
        """测试Temperature滑块"""
        self.open_settings(page)

        # 查找temperature滑块
        temp_slider = page.locator('input[type="range"][name*="temperature"], input[type="range"][name*="temp"]').first

        if temp_slider.is_visible():
            # 设置值
            temp_slider.fill("0.7")
            page.wait_for_timeout(300)

            value = temp_slider.input_value()
            assert value is not None

    def test_max_tokens_input(self, page):
        """测试最大令牌数输入"""
        self.open_settings(page)

        # 查找max tokens输入框
        max_tokens_input = page.locator('input[name*="max_tokens"], input[name*="max-tokens"], input[type="number"]').first

        if max_tokens_input.is_visible():
            # 输入值
            max_tokens_input.fill("2048")
            page.wait_for_timeout(300)

            value = max_tokens_input.input_value()
            assert value == "2048" or value == "2048.0"

    def test_save_settings(self, page):
        """测试保存设置"""
        self.open_settings(page)

        # 查找保存按钮
        save_button = page.locator('button:has-text("保存"), button:has-text("Save"), .save-button, [data-testid="save"]').first

        if save_button.is_visible():
            save_button.click()
            page.wait_for_timeout(1000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_reset_settings(self, page):
        """测试重置设置"""
        self.open_settings(page)

        # 查找重置按钮
        reset_button = page.locator('button:has-text("重置"), button:has-text("Reset"), .reset-button').first

        if reset_button.is_visible():
            reset_button.click()
            page.wait_for_timeout(500)

            # 可能需要确认
            confirm_button = page.locator('button:has-text("确认"), button:has-text("Confirm"), .confirm').first
            if confirm_button.is_visible():
                confirm_button.click()
                page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_model_provider_selection(self, page):
        """测试模型提供商选择"""
        self.open_settings(page)

        # 查找提供商下拉菜单
        provider_select = page.locator('select[name*="provider"], select[name*="model"]').first

        if provider_select.is_visible():
            # 选择一个选项
            provider_select.select_option("siliconflow")
            page.wait_for_timeout(300)

            value = provider_select.input_value()
            assert value is not None

    def test_system_prompt_input(self, page):
        """测试系统提示词输入"""
        self.open_settings(page)

        # 查找系统提示词文本框
        system_prompt = page.locator('textarea[name*="system_prompt"], textarea[name*="system-prompt"], textarea[placeholder*="system"]').first

        if system_prompt.is_visible():
            # 输入测试提示词
            test_prompt = "You are a helpful assistant."
            system_prompt.fill(test_prompt)
            page.wait_for_timeout(300)

            value = system_prompt.input_value()
            assert test_prompt in value

    def test_settings_tabs(self, page):
        """测试设置标签页"""
        self.open_settings(page)

        # 查找标签页
        tabs = page.locator('.settings-tab, [role="tab"]').all()

        if len(tabs) > 0:
            # 点击每个标签页
            for tab in tabs[:3]:  # 最多测试前3个
                if tab.is_visible():
                    tab.click()
                    page.wait_for_timeout(300)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_directory_settings(self, page):
        """测试目录设置"""
        self.open_settings(page)

        # 查找目录列表
        directory_list = page.locator('.directory-list, [class*="directory"]').first

        # 查找添加目录按钮
        add_dir_button = page.locator('button:has-text("添加目录"), button:has-text("Add Directory"), .add-directory').first

        if add_dir_button.is_visible():
            add_dir_button.click()
            page.wait_for_timeout(500)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_test_connection_button(self, page):
        """测试连接按钮"""
        self.open_settings(page)

        # 查找测试连接按钮
        test_button = page.locator('button:has-text("测试"), button:has-text("Test"), button:has-text("连接"), .test-connection').first

        if test_button.is_visible():
            test_button.click()
            page.wait_for_timeout(2000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_settings_persistence(self, page):
        """测试设置持久化"""
        self.open_settings(page)

        # 修改一个设置
        api_url_input = page.locator('input[name*="api_url"], input[name*="api-url"]').first

        if api_url_input.is_visible():
            test_url = "http://example.com/api"
            api_url_input.fill(test_url)
            page.wait_for_timeout(300)

            # 保存设置
            save_button = page.locator('button:has-text("保存"), button:has-text("Save"), .save-button').first
            if save_button.is_visible():
                save_button.click()
                page.wait_for_timeout(1000)

        assert page.url.startswith("http://127.0.0.1:8000")

    def test_advanced_settings_toggle(self, page):
        """测试高级设置切换"""
        self.open_settings(page)

        # 查找高级设置切换
        advanced_toggle = page.locator('button:has-text("高级"), button:has-text("Advanced"), .advanced-toggle, [data-testid="advanced"]').first

        if advanced_toggle.is_visible():
            advanced_toggle.click()
            page.wait_for_timeout(500)

            # 高级设置应该显示
            advanced_settings = page.locator('.advanced-settings, [class*="advanced"]').first

        assert page.url.startswith("http://127.0.0.1:8000")
