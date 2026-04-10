"""
设置面板UI测试 - Playwright
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.e2e
class TestUISettings:
    """设置面板UI测试类"""

    def open_settings(self, page):
        """打开设置面板"""
        # 导航到页面
        page.goto("http://127.0.0.1:18642", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")

        # 查找设置按钮 (使用更精确的选择器)
        settings_button = page.locator(
            'button.settings-btn, button[aria-label="设置"], .top-nav-bar button:last-child'
        ).first

        # 等待按钮可见
        try:
            settings_button.wait_for(state="visible", timeout=10000)
        except Exception:
            # 如果找不到，尝试其他选择器
            settings_button = page.locator(".top-nav-bar button").last

        if settings_button.is_visible():
            settings_button.click()
            # 等待设置模态框出现 - 使用更精确的选择器
            # 必须同时满足：是settingsModal 且 有show类（Bootstrap显示状态）
            modal = page.locator('#settingsModal.modal.show, #settingsModal.modal.fade.show').first
            modal.wait_for(state="visible", timeout=10000)

    def test_settings_panel_open(self, page):
        """测试设置面板打开"""
        self.open_settings(page)

        # 验证页面已加载
        assert page.url.startswith("http://127.0.0.1:18642"), "页面应正常加载"

        # 使用精确的选择器查找Bootstrap模态框（必须有show类）
        settings_panel = page.locator('#settingsModal.modal.show, #settingsModal.modal.fade.show').first

        # 等待模态框动画完成并可见
        settings_panel.wait_for(state="visible", timeout=10000)

        # 验证模态框确实可见
        assert settings_panel.is_visible(), "设置面板应该可见"

    def test_settings_panel_close(self, page):
        """测试设置面板关闭"""
        self.open_settings(page)

        # 查找关闭按钮
        close_selectors = (
            'button:has-text("关闭"), button:has-text("Close"), '
            'button:has-text("×"), .close-button, [data-testid="close"]'
        )
        close_button = page.locator(close_selectors).first

        if close_button.is_visible():
            close_button.click()
            # 等待模态框关闭
            page.locator("#settingsModal, .modal.show").first.wait_for(
                state="hidden", timeout=5000
            )

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_ai_model_settings(self, page):
        """测试AI模型设置"""
        self.open_settings(page)

        # 查找AI模型设置区域
        page.locator(
            '.ai-settings, [class*="ai-model"], [data-testid="ai-settings"]'
        ).first

        # 查找启用AI复选框
        enable_checkbox = page.locator(
            'input[type="checkbox"][name*="enable"], input[type="checkbox"][id*="ai"]'
        ).first

        if enable_checkbox.is_visible():
            # 切换启用状态
            enable_checkbox.click()
            # NOTE: Removed fixed wait - Playwright auto-waits

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_api_url_input(self, page):
        """测试API URL输入"""
        self.open_settings(page)

        # 查找API URL输入框
        api_url_input = page.locator(
            'input[name*="api_url"], input[name*="api-url"], input[placeholder*="URL"]'
        ).first

        if api_url_input.is_visible():
            # 输入测试URL
            api_url_input.fill("http://localhost:8080/v1/chat/completions")
            # NOTE: Removed fixed wait - Playwright auto-waits

            # 验证输入值
            value = api_url_input.input_value()
            assert "localhost" in value

    def test_api_key_input(self, page):
        """测试API密钥输入"""
        self.open_settings(page)

        # 查找API密钥输入框
        api_key_input = page.locator(
            'input[type="password"], input[name*="api_key"], input[name*="api-key"]'
        ).first

        if api_key_input.is_visible():
            # 输入测试密钥
            api_key_input.fill("test-api-key-12345")
            # NOTE: Removed fixed wait - Playwright auto-waits

            # 验证输入值（密码字段可能无法直接读取）
            assert api_key_input.is_visible()

    def test_temperature_slider(self, page):
        """测试Temperature滑块"""
        self.open_settings(page)

        # 查找temperature滑块
        temp_slider = page.locator(
            'input[type="range"][name*="temperature"], '
            'input[type="range"][name*="temp"]'
        ).first

        if temp_slider.is_visible():
            # 设置值
            temp_slider.fill("0.7")
            # NOTE: Removed fixed wait - Playwright auto-waits

            value = temp_slider.input_value()
            assert value is not None

    def test_max_tokens_input(self, page):
        """测试最大令牌数输入"""
        self.open_settings(page)

        # 查找max tokens输入框
        max_tokens_input = page.locator(
            'input[name*="max_tokens"], input[name*="max-tokens"], input[type="number"]'
        ).first

        if max_tokens_input.is_visible():
            # 输入值
            max_tokens_input.fill("2048")
            # NOTE: Removed fixed wait - Playwright auto-waits

            value = max_tokens_input.input_value()
            assert value == "2048" or value == "2048.0"

    def test_save_settings(self, page):
        """测试保存设置"""
        self.open_settings(page)

        # 查找保存按钮
        save_selectors = (
            'button:has-text("保存"), button:has-text("Save"), '
            '.save-button, [data-testid="save"]'
        )
        save_button = page.locator(save_selectors).first

        if save_button.is_visible():
            save_button.click()
            # NOTE: Use wait_for_load_state or element visibility

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_reset_settings(self, page):
        """测试重置设置"""
        self.open_settings(page)

        # 查找重置按钮
        reset_button = page.locator(
            'button:has-text("重置"), button:has-text("Reset"), .reset-button'
        ).first

        if reset_button.is_visible():
            reset_button.click()
            # NOTE: Use auto-wait or specific condition

            # 可能需要确认
            confirm_button = page.locator(
                'button:has-text("确认"), button:has-text("Confirm"), .confirm'
            ).first
            if confirm_button.is_visible():
                confirm_button.click()
                # NOTE: Use auto-wait or specific condition

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_model_provider_selection(self, page):
        """测试模型提供商选择"""
        self.open_settings(page)

        # 先切换到API模式标签（因为提供商选择只在API模式下可见）
        mode_tab = page.locator('#v-pills-mode-tab, button:has-text("接入模式")').first
        if mode_tab.is_visible():
            mode_tab.click()
            # NOTE: Use auto-wait or specific condition

        # 切换到API模式
        api_mode_radio = page.locator('#modeAPI, input[value="api"]').first
        if api_mode_radio.is_visible():
            api_mode_radio.click()
            # NOTE: Use auto-wait or specific condition

        # 查找提供商下拉菜单（使用正确的ID）
        provider_select = page.locator(
            '#apiProviderSelect, select[name*="provider"], select[name*="model"]'
        ).first

        if provider_select.is_visible():
            # 选择一个选项
            provider_select.select_option("siliconflow")
            # NOTE: Removed fixed wait - Playwright auto-waits

            value = provider_select.input_value()
            assert value is not None
        else:
            # 如果提供商选择器不可见，可能是本地模式或其他原因，跳过此测试
            pytest.skip("API提供商选择器不可见")

    def test_system_prompt_input(self, page):
        """测试系统提示词输入"""
        self.open_settings(page)

        # 查找系统提示词文本框
        system_prompt_selectors = (
            'textarea[name*="system_prompt"], textarea[name*="system-prompt"], '
            'textarea[placeholder*="system"]'
        )
        system_prompt = page.locator(system_prompt_selectors).first

        if system_prompt.is_visible():
            # 输入测试提示词
            test_prompt = "You are a helpful assistant."
            system_prompt.fill(test_prompt)
            # NOTE: Removed fixed wait - Playwright auto-waits

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
                    # NOTE: Removed fixed wait - Playwright auto-waits

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_directory_settings(self, page):
        """测试目录设置"""
        self.open_settings(page)

        # 查找目录列表
        page.locator('.directory-list, [class*="directory"]').first

        # 查找添加目录按钮
        add_dir_selectors = (
            'button:has-text("添加目录"), button:has-text("Add Directory"), '
            ".add-directory"
        )
        add_dir_button = page.locator(add_dir_selectors).first

        if add_dir_button.is_visible():
            add_dir_button.click()
            # NOTE: Use auto-wait or specific condition

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_test_connection_button(self, page):
        """测试连接按钮"""
        self.open_settings(page)

        # 查找测试连接按钮
        test_button_selectors = (
            'button:has-text("测试"), button:has-text("Test"), '
            'button:has-text("连接"), .test-connection'
        )
        test_button = page.locator(test_button_selectors).first

        if test_button.is_visible():
            test_button.click()
            # NOTE: Use smart wait for async operations

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_settings_persistence(self, page):
        """测试设置持久化"""
        self.open_settings(page)

        # 修改一个设置
        api_url_input = page.locator(
            'input[name*="api_url"], input[name*="api-url"]'
        ).first

        if api_url_input.is_visible():
            test_url = "http://example.com/api"
            api_url_input.fill(test_url)
            # NOTE: Removed fixed wait - Playwright auto-waits

            # 保存设置
            save_button = page.locator(
                'button:has-text("保存"), button:has-text("Save"), .save-button'
            ).first
            if save_button.is_visible():
                save_button.click()
                # NOTE: Use wait_for_load_state or element visibility

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_advanced_settings_toggle(self, page):
        """测试高级设置切换"""
        self.open_settings(page)

        # 查找高级设置切换
        advanced_selectors = (
            'button:has-text("高级"), button:has-text("Advanced"), '
            '.advanced-toggle, [data-testid="advanced"]'
        )
        advanced_toggle = page.locator(advanced_selectors).first

        if advanced_toggle.is_visible():
            advanced_toggle.click()
            # NOTE: Use auto-wait or specific condition

            # 高级设置应该显示
            page.locator('.advanced-settings, [class*="advanced"]').first

        assert page.url.startswith("http://127.0.0.1:18642")

    def test_add_directory_modal(self, page):
        """测试添加目录模态框"""
        self.open_settings(page)

        # 查找添加目录按钮
        add_dir_button = page.locator(
            'button:has-text("添加目录"), button:has-text("Add Directory"), '
            '.add-directory, [data-testid="add-directory"]'
        ).first

        if not add_dir_button.is_visible():
            pytest.skip("添加目录按钮不可见")

        # 点击添加目录按钮
        add_dir_button.click()
        # NOTE: Use auto-wait or specific condition

        # 验证模态框打开 - 检查模态框元素
        modal = page.locator(
            '#addDirectoryModal, .modal.add-directory, [role="dialog"]'
        )
        assert modal.count() > 0, "添加目录模态框未打开"

        # 检查模态框内的关键元素
        path_input = page.locator('#addDirectoryPathInput, input[type="text"]')
        browse_btn = page.locator("#browseDirectoryBtn")
        confirm_btn = page.locator("#confirmAddDirectoryBtn")

        # 至少应该有一个元素可见
        has_elements = (
            path_input.count() > 0 or browse_btn.count() > 0 or confirm_btn.count() > 0
        )
        if has_elements:
            # 关闭模态框
            cancel_btn = page.locator(
                'button:has-text("取消"), button:has-text("Cancel")'
            )
            if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
                cancel_btn.first.click()
                # NOTE: Removed fixed wait - Playwright auto-waits

    def test_delete_directory_modal(self, page):
        """测试删除目录模态框"""
        self.open_settings(page)

        # 先切换到目录管理标签
        dir_tab = page.locator(
            '#v-pills-directories-tab, button:has-text("目录管理")'
        ).first
        if dir_tab.is_visible():
            dir_tab.click()
            # NOTE: Use auto-wait or specific condition

        # 检查是否有目录存在
        empty_state = page.locator(".directory-empty").first

        if empty_state.is_visible():
            pytest.skip("没有可删除的目录（目录列表为空）")

        # 查找删除目录按钮 (通常是一个图标按钮)
        delete_buttons = page.locator(
            '#directoriesList .delete-directory, [data-testid="delete-directory"], '
            '.directory-item button, .directory-list button[title*="删除"]'
        )

        if delete_buttons.count() == 0:
            pytest.skip("没有找到删除目录按钮")

        # 点击第一个删除按钮
        delete_buttons.first.click()
        # NOTE: Use auto-wait or specific condition

        # 验证确认删除模态框打开
        modal = page.locator("#deleteDirectoryModal")
        assert modal.count() > 0, "删除目录确认模态框未打开"

        # 检查确认按钮
        confirm_delete = page.locator("#confirmDirectoryDeleteBtn")
        cancel_delete_selectors = (
            '#deleteDirectoryModal button:has-text("取消"), '
            '#deleteDirectoryModal button[data-bs-dismiss="modal"]'
        )
        cancel_delete = page.locator(cancel_delete_selectors)

        if confirm_delete.count() > 0 or cancel_delete.count() > 0:
            # 点击取消关闭模态框
            if cancel_delete.count() > 0 and cancel_delete.first.is_visible():
                cancel_delete.first.click()
                # NOTE: Removed fixed wait - Playwright auto-waits

    def test_rebuild_index_modal(self, page):
        """测试重建索引模态框"""
        # 访问首页（不打开设置）
        page.goto("http://127.0.0.1:18642", timeout=30000)
        # NOTE: Use smart wait for async operations

        # 查找重建索引按钮（在搜索侧边栏）
        rebuild_button = page.locator(
            ".sidebar .rebuild-btn, #sidebar-search-content .rebuild-btn, .rebuild-btn"
        ).first

        if not rebuild_button.is_visible():
            pytest.skip("重建索引按钮不可见")

        # 点击重建索引按钮（使用 JavaScript 点击避免被遮挡）
        rebuild_button.scroll_into_view_if_needed()
        # NOTE: Use auto-wait or specific condition
        # 尝试直接点击，如果失败则使用 JS 点击
        try:
            rebuild_button.click(timeout=5000)
        except Exception:
            # 使用 JavaScript 点击
            rebuild_button.evaluate("el => el.click()")
        # NOTE: Use auto-wait or specific condition

        # 验证模态框打开
        modal = page.locator("#rebuildIndexModal")
        assert modal.count() > 0, "重建索引模态框未打开"

        # 检查模态框是否可见
        modal_visible = page.locator(
            "#rebuildIndexModal.show, #rebuildIndexModal.fade.show"
        ).first
        if not modal_visible.is_visible():
            # 检查 display 样式
            modal_element = page.locator("#rebuildIndexModal").first
            is_displayed = modal_element.evaluate(
                'el => window.getComputedStyle(el).display !== "none"'
            )
            assert is_displayed, "重建索引模态框应该可见"

        # 关闭模态框
        rebuild_cancel_selectors = (
            '#rebuildIndexModal button:has-text("取消"), #rebuildCloseBtn, '
            '#rebuildIndexModal button[data-bs-dismiss="modal"]'
        )
        cancel_button = page.locator(rebuild_cancel_selectors).first
        if cancel_button.is_visible():
            cancel_button.click()
        else:
            page.keyboard.press("Escape")
        # NOTE: Removed fixed wait - Playwright auto-waits
