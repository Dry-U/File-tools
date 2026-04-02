"""
无障碍测试 - Playwright

运行方式:
    pytest tests/e2e/test_accessibility.py -v

检查项:
- ARIA 标签和属性
- 模态框无障碍
- 标题层级
- 键盘导航
- 表单标签
- 图片 Alt 文本
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from playwright.sync_api import Page


# WCAG 2.1 AA 标准颜色对比度要求
MIN_CONTRAST_RATIO = 4.5  # 普通文本


@pytest.mark.e2e
class TestAccessibility:
    """无障碍测试类"""

    @pytest.fixture(scope="class")
    def browser_context_args(self):
        """浏览器上下文参数"""
        return {"viewport": {"width": 1280, "height": 720}}

    def test_aria_labels(self, page: Page):
        """测试 ARIA 标签存在性"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 检查主要交互元素是否有 ARIA 标签
        interactive_elements = page.locator(
            "button, [role='button'], input:not([type='hidden']), select, textarea"
        )

        count = interactive_elements.count()
        assert count > 0, "页面没有可交互元素"

        # 检查有 aria-label 或 aria-labelledby 的元素
        labeled = page.locator("[aria-label], [aria-labelledby], [aria-describedby]")
        labeled_count = labeled.count()

        print(f"\n可交互元素: {count}, 有 ARIA 标签: {labeled_count}")

        # 断言：至少有一些元素有 ARIA 标签
        assert labeled_count > 0, "没有发现带有 ARIA 标签的元素"

    def test_modal_accessibility(self, page: Page):
        """测试模态框无障碍属性"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找模态框（如果存在）
        modals = page.locator('[role="dialog"], .modal, [aria-modal="true"]')
        modal_count = modals.count()

        if modal_count > 0:
            print(f"\n发现 {modal_count} 个模态框")

            for i, modal in enumerate(modals.all()):
                has_role = modal.get_attribute("role")
                has_aria_modal = modal.get_attribute("aria-modal")
                has_labelledby = modal.get_attribute("aria-labelledby")

                print(f"\n  模态框 {i+1}:")
                print(f"    role: {has_role}")
                print(f"    aria-modal: {has_aria_modal}")
                print(f"    aria-labelledby: {has_labelledby}")

                # 验证无障碍属性
                if has_role:
                    assert has_role == "dialog", f"模态框 role 应为 'dialog'"
                if has_aria_modal:
                    assert has_aria_modal == "true", "aria-modal 应为 'true'"
        else:
            print("\n页面没有模态框（正常）")

    def test_heading_hierarchy(self, page: Page):
        """测试标题层级结构"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 获取所有标题
        headings = page.locator("h1, h2, h3, h4, h5, h6")
        heading_count = headings.count()

        if heading_count > 0:
            print(f"\n发现 {heading_count} 个标题")

            previous_level = 0
            for i, heading in enumerate(headings.all()):
                tag = heading.evaluate("el => el.tagName.toLowerCase()")
                level = int(tag[1])

                text = heading.inner_text()
                print(f"  {tag}: {text[:30]}...")

                if i > 0 and level > previous_level + 1:
                    print(f"    警告: 标题级别跳跃 (h{previous_level} -> h{level})")

                previous_level = level

            # 断言：最多只有一个 h1
            h1_count = page.locator("h1").count()
            assert h1_count <= 1, f"页面有 {h1_count} 个 h1，应该只有 1 个"
        else:
            print("\n没有发现标题元素")

    def test_keyboard_navigation(self, page: Page):
        """测试键盘导航"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 测试 Tab 键导航
        body = page.locator("body")
        body.click()

        # 按 Tab 键多次，检查是否能到达可聚焦元素
        focused_elements = []
        for _ in range(10):
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.tagName")
            if focused and focused.upper() not in [e.upper() for e in focused_elements]:
                focused_elements.append(focused.upper())

        print(f"\nTab 导航可到达的元素类型: {focused_elements}")

        # 验证至少有 Tab 可到达的元素
        assert len(focused_elements) > 0, "Tab 键无法导航到任何元素"

    def test_image_alt_text(self, page: Page):
        """测试图片 Alt 文本"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        images = page.locator("img")
        image_count = images.count()

        if image_count > 0:
            print(f"\n发现 {image_count} 个图片")

            for i, img in enumerate(images.all()):
                alt = img.get_attribute("alt")
                src = img.get_attribute("src") or "N/A"
                print(f"  图片 {i+1}: alt='{alt}', src={src[:50]}...")

                # 所有图片都应该有 alt 属性
                # alt="" 表示装饰性图片，alt 文本表示内容图片
                assert alt is not None, f"图片缺少 alt 属性: {src[:50]}"
        else:
            print("\n没有发现图片元素")

    def test_form_labels(self, page: Page):
        """测试表单标签"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找所有表单输入
        inputs = page.locator("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea")
        input_count = inputs.count()

        if input_count > 0:
            print(f"\n发现 {input_count} 个表单输入")

            for i, inp in enumerate(inputs.all()):
                input_type = inp.get_attribute("type") or "text"
                has_aria_label = inp.get_attribute("aria-label")
                has_aria_labelledby = inp.get_attribute("aria-labelledby")

                # 尝试找关联的 label
                input_id = inp.get_attribute("id")
                associated_label = 0
                if input_id:
                    associated_label = page.locator(f"label[for='{input_id}']").count()

                print(f"\n  输入 {i+1}: type={input_type}")
                print(f"    aria-label: {bool(has_aria_label)}")
                print(f"    aria-labelledby: {bool(has_aria_labelledby)}")
                print(f"    关联label: {associated_label > 0}")

                # 可视输入应该有某种标签关联
                is_visible = inp.is_visible()
                if is_visible:
                    has_label = bool(has_aria_label) or bool(has_aria_labelledby) or associated_label > 0
                    if not has_label:
                        print(f"    警告: 可视输入缺少无障碍标签")
        else:
            print("\n没有发现表单输入")

    def test_landmark_regions(self, page: Page):
        """测试页面区域标记"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 检查 HTML5 语义区域
        landmarks = page.locator("header, nav, main, footer, aside, [role='banner'], [role='navigation'], [role='main'], [role='contentinfo']")
        landmark_count = landmarks.count()

        print(f"\n发现 {landmark_count} 个区域标记")

        if landmark_count > 0:
            for i, landmark in enumerate(landmarks.all()):
                tag = landmark.evaluate("el => el.tagName.toLowerCase()")
                role = landmark.get_attribute("role") or "N/A"
                print(f"  {tag} (role={role})")

        # 断言：页面应该有 main 区域
        has_main = page.locator("main, [role='main']").count()
        assert has_main > 0, "页面缺少 main 区域"

    def test_skip_links(self, page: Page):
        """测试跳过链接（可选，但推荐）"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找跳过链接
        skip_links = page.locator("a[href^='#'], .skip-link, [class*='skip']")
        skip_count = skip_links.count()

        print(f"\n发现 {skip_count} 个跳过链接")

        if skip_count > 0:
            for i, link in enumerate(skip_links.all()):
                href = link.get_attribute("href") or ""
                text = link.inner_text()
                print(f"  链接 {i+1}: {text or href}")


# 便捷运行函数
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

    def test_aria_labels(self, page: Page):
        """测试 ARIA 标签存在性"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 检查主要交互元素是否有 ARIA 标签
        interactive_elements = page.locator(
            "button, [role='button'], input, select, textarea"
        )

        count = interactive_elements.count()
        assert count > 0, "页面没有可交互元素"

        # 检查至少有一个元素有 aria-label 或 aria-labelledby
        labeled = page.locator(
            "[aria-label], [aria-labelledby], [aria-describedby]"
        )
        labeled_count = labeled.count()

        print(f"\n可交互元素: {count}, 有 ARIA 标签: {labeled_count}")

        # 不强制要求所有元素都有标签，但至少应该有一些
        assert labeled_count > 0, "没有发现带有 ARIA 标签的元素"

    def test_modal_accessibility(self, page: Page):
        """测试模态框无障碍属性"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找模态框（如果存在）
        modals = page.locator('[role="dialog"], .modal, [aria-modal="true"]')
        modal_count = modals.count()

        if modal_count > 0:
            print(f"\n发现 {modal_count} 个模态框")

            for i, modal in enumerate(modals.all()):
                # 检查模态框属性
                has_role = modal.get_attribute("role")
                has_aria_modal = modal.get_attribute("aria-modal")
                has_labelledby = modal.get_attribute("aria-labelledby")

                print(f"\n  模态框 {i+1}:")
                print(f"    role: {has_role}")
                print(f"    aria-modal: {has_aria_modal}")
                print(f"    aria-labelledby: {has_labelledby}")

                # 验证无障碍属性
                if has_role:
                    assert has_role == "dialog", f"模态框 role 应为 'dialog'，实际为 '{has_role}'"
                if has_aria_modal:
                    assert has_aria_modal == "true", "aria-modal 应为 'true'"
        else:
            print("\n页面没有模态框（正常）")

    def test_heading_hierarchy(self, page: Page):
        """测试标题层级结构"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 获取所有标题
        headings = page.locator("h1, h2, h3, h4, h5, h6")
        heading_count = headings.count()

        if heading_count > 0:
            print(f"\n发现 {heading_count} 个标题")

            # 验证标题层级（不应该跳过 h1 直接到 h3）
            previous_level = 0
            for i, heading in enumerate(headings.all()):
                tag = heading.evaluate("el => el.tagName.toLowerCase()")
                level = int(tag[1])

                print(f"  {tag}: {heading.inner_text()[:30]}...")

                if i > 0 and level > previous_level + 1:
                    print(f"    警告: 标题级别跳跃 (从 h{previous_level} 到 h{level})")

                previous_level = level

            # 断言：最多只有一个 h1
            h1_count = page.locator("h1").count()
            assert h1_count <= 1, f"页面有 {h1_count} 个 h1，应该只有 1 个"
        else:
            print("\n没有发现标题元素")

    def test_keyboard_navigation(self, page: Page):
        """测试键盘导航"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 测试 Tab 键导航
        body = page.locator("body")
        body.click()

        # 按 Tab 键多次，检查是否能到达可聚焦元素
        focused_elements = []
        for _ in range(10):
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.tagName")
            if focused and focused not in focused_elements:
                focused_elements.append(focused)

        print(f"\nTab 导航可到达的元素类型: {focused_elements}")

        # 验证至少有 Tab 可到达的元素
        assert len(focused_elements) > 0, "Tab 键无法导航到任何元素"

    def test_color_contrast(self, page: Page):
        """测试颜色对比度（基础检查）"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 检查文本颜色和背景色是否存在
        # 这是一个基础检查，真正的对比度检查由 axe-core 完成
        styles = page.evaluate("""
            () => {
                const body = document.body;
                const style = window.getComputedStyle(body);
                return {
                    color: style.color,
                    backgroundColor: style.backgroundColor
                };
            }
        """)

        print(f"\n页面颜色: {styles['color']}")
        print(f"页面背景: {styles['backgroundColor']}")

        # 验证颜色不是透明的
        assert styles['color'] != "rgba(0, 0, 0, 0)", "文本颜色是透明的"
        assert styles['backgroundColor'] != "rgba(0, 0, 0, 0)", "背景颜色是透明的"

    def test_image_alt_text(self, page: Page):
        """测试图片 Alt 文本"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        images = page.locator("img")
        image_count = images.count()

        if image_count > 0:
            print(f"\n发现 {image_count} 个图片")

            for i, img in enumerate(images.all()):
                alt = img.get_attribute("alt")
                src = img.get_attribute("src") or "N/A"
                print(f"  图片 {i+1}: alt='{alt}', src={src[:50]}...")

                # 装饰性图片应该有空的 alt=""
                # 内容图片应该有 alt 文本
                if alt is None:
                    print(f"    警告: 图片缺少 alt 属性")
        else:
            print("\n没有发现图片元素")

    def test_form_labels(self, page: Page):
        """测试表单标签"""
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")

        # 查找所有表单输入
        inputs = page.locator("input:not([type='hidden']), textarea, select")
        input_count = inputs.count()

        if input_count > 0:
            print(f"\n发现 {input_count} 个表单输入")

            for i, inp in enumerate(inputs.all()):
                tag = inp.evaluate("el => el.tagName.toLowerCase()")
                input_type = inp.get_attribute("type") or "text"
                has_aria_label = inp.get_attribute("aria-label")
                has_aria_labelledby = inp.get_attribute("aria-labelledby")

                # 尝试找关联的 label
                label_id = inp.get_attribute("id")
                associated_label = None
                if label_id:
                    associated_label = page.locator(f"label[for='{label_id}']").count()

                print(f"\n  输入 {i+1}: {tag} type={input_type}")
                print(f"    aria-label: {has_aria_label}")
                print(f"    aria-labelledby: {has_aria_labelledby}")
                print(f"    关联label: {associated_label > 0 if label_id else 'N/A'}")

                # 如果输入可见，应该有某种标签关联
                is_visible = inp.is_visible()
                if is_visible and not has_aria_label and not has_aria_labelledby and associated_label == 0:
                    print(f"    警告: 可视输入缺少无障碍标签")
        else:
            print("\n没有发现表单输入")


# 便捷运行函数
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
