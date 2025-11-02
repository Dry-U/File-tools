#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件"""
import sys
import os

# 修复 torch DLL 加载问题：将 torch lib 目录添加到 PATH
try:
    venv_path = os.path.dirname(sys.executable)
    torch_lib_path = os.path.join(venv_path, 'Lib', 'site-packages', 'torch', 'lib')
    if os.path.exists(torch_lib_path):
        # 添加到 PATH 环境变量
        os.environ['PATH'] = torch_lib_path + os.pathsep + os.environ.get('PATH', '')
        # 如果支持，也添加到 DLL 目录
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(torch_lib_path)
except Exception as e:
    print(f"警告：无法添加 torch DLL 目录：{e}")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

# 导入主窗口模块
from src.ui.main_window import MainWindow

# 确保中文正常显示
def setup_chinese_font_support(app):
    """设置中文字体支持"""
    font_families = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
    
    # 选择系统中可用的字体
    font = QFont()
    for family in font_families:
        font.setFamily(family)
        if font.family() == family:
            app.setFont(font)
            return True
    return False

def main():
    """主函数 - 应用程序入口点"""
    # 创建应用程序实例
    app = QApplication(sys.argv)
    
    # 设置中文字体支持
    setup_chinese_font_support(app)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用程序主循环
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()