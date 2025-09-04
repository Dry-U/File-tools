#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能文件检索与问答系统 - 主入口文件"""
import sys
import os
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