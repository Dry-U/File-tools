#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI组件模块 - 提供各种界面元素的辅助类和函数"""
import sys
import os
import platform
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QTreeView,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSplitter,
    QComboBox,
    QCheckBox,
    QRadioButton,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QProgressBar,
    QMenu,
    QMenuBar,
    QAction,
    QToolBar,
    QStatusBar,
    QHeaderView
)
from PyQt5.QtGui import (
    QIcon,
    QFont,
    QColor,
    QTextCharFormat,
    QTextCursor,
    QStandardItemModel,
    QStandardItem,
    QPixmap,
    QPainter,
    QPen
)
from PyQt5.QtCore import (
    Qt,
    QSize,
    QModelIndex,
    QThread,
    pyqtSignal,
    QSettings,
    QFile,
    QTextStream,
    QDateTime
)

class SearchBox(QLineEdit):
    """搜索框组件"""
    def __init__(self, parent=None, placeholder="搜索文件内容、名称或路径..."):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)  # 启用清除按钮
        self.setMinimumHeight(30)  # 设置最小高度
        
        # 设置样式
        self.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 15px;
                padding: 5px 10px;
                font-size: 14px;
                background-color: #fff;
            }
            QLineEdit:focus {
                border: 1px solid #4a90e2;
                background-color: #f5f8ff;
            }
        """)

class StatusLabel(QLabel):
    """状态栏标签组件"""
    def __init__(self, parent=None, text="就绪"):
        super().__init__(parent)
        self.setText(text)
        self.setMinimumWidth(200)
        
    def update_status(self, text):
        """更新状态栏文本"""
        self.setText(text)
        
class ProgressIndicator(QProgressBar):
    """进度指示器组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(0)
        self.setVisible(False)  # 默认隐藏
        
    def show_progress(self, value=None):
        """显示进度条"""
        self.setVisible(True)
        if value is not None:
            self.setValue(value)
    
    def hide_progress(self):
        """隐藏进度条"""
        self.setVisible(False)
        self.setValue(0)

class SearchResultModel(QStandardItemModel):
    """搜索结果数据模型"""
    def __init__(self, parent=None):
        super().__init__(0, 4, parent)  # 4列：文件名、路径、匹配度、修改时间
        self.setHorizontalHeaderLabels(["文件名", "路径", "匹配度", "修改时间"])
    
    def add_result(self, file_name, file_path, score, modified_time):
        """添加搜索结果"""
        row_items = [
            QStandardItem(file_name),
            QStandardItem(str(file_path)),
            QStandardItem(f"{score:.2f}%") if score else QStandardItem(""),
            QStandardItem(modified_time.strftime('%Y-%m-%d %H:%M:%S')) if modified_time else QStandardItem("")
        ]
        
        # 设置每个项的对齐方式
        for item in row_items:
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.appendRow(row_items)

class SearchResultView(QTableView):
    """搜索结果表格视图"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置表格属性
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)
        self.setSortingEnabled(True)
        self.setEditTriggers(QTableView.NoEditTriggers)
        
        # 设置表头
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        
        # 设置样式
        self.setStyleSheet("""
            QTableView {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #fff;
                alternate-background-color: #f5f5f5;
            }
            QTableView::item {
                padding: 5px;
                border-bottom: 1px solid #eee;
            }
            QTableView::item:selected {
                background-color: #4a90e2;
                color: #fff;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 5px;
                border: 1px solid #ccc;
                font-weight: bold;
            }
        """)

class FilePreviewer(QTextEdit):
    """文件预览器组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setAcceptRichText(True)
        self.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #fff;
                padding: 10px;
            }
        """)
        
    def set_content(self, content):
        """设置预览内容"""
        self.clear()
        self.setPlainText(content)
        
    def highlight_text(self, search_text):
        """高亮搜索文本"""
        if not search_text or not self.toPlainText():
            return
        
        cursor = self.textCursor()
        document = self.document()
        
        # 重置所有格式
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        default_format = QTextCharFormat()
        cursor.setCharFormat(default_format)
        
        # 设置高亮格式
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("yellow"))
        
        # 查找并高亮所有匹配项
        cursor = document.find(search_text)
        while not cursor.isNull():
            cursor.mergeCharFormat(highlight_format)
            cursor = document.find(search_text, cursor)
        
        # 移回文档开头
        self.moveCursor(QTextCursor.Start)

class AdvancedFilterWidget(QWidget):
    """高级筛选组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        # 创建布局
        layout = QVBoxLayout(self)
        
        # 创建文件类型筛选组
        file_types_group = QGroupBox("文件类型")
        file_types_layout = QVBoxLayout()
        
        # 文件类型复选框
        self.txt_check = QCheckBox("文本文件 (.txt, .md, .csv)")
        self.doc_check = QCheckBox("文档文件 (.doc, .docx, .pdf)")
        self.xls_check = QCheckBox("电子表格 (.xls, .xlsx)")
        self.img_check = QCheckBox("图像文件 (.jpg, .png, .gif)")
        self.other_check = QCheckBox("其他文件")
        
        # 添加到布局
        for check in [self.txt_check, self.doc_check, self.xls_check, self.img_check, self.other_check]:
            check.setChecked(True)  # 默认全部选中
            file_types_layout.addWidget(check)
        
        file_types_group.setLayout(file_types_layout)
        
        # 创建大小筛选组
        size_group = QGroupBox("文件大小")
        size_layout = QGridLayout()
        
        # 大小输入框
        size_layout.addWidget(QLabel("最小大小 (MB):"), 0, 0)
        self.min_size = QLineEdit()
        self.min_size.setPlaceholderText("0")
        size_layout.addWidget(self.min_size, 0, 1)
        
        size_layout.addWidget(QLabel("最大大小 (MB):"), 1, 0)
        self.max_size = QLineEdit()
        self.max_size.setPlaceholderText("无限制")
        size_layout.addWidget(self.max_size, 1, 1)
        
        size_group.setLayout(size_layout)
        
        # 创建日期筛选组
        date_group = QGroupBox("修改日期")
        date_layout = QGridLayout()
        
        # 日期筛选选项
        self.date_radio = QComboBox()
        self.date_radio.addItems(["任意时间", "过去24小时", "过去7天", "过去30天", "自定义范围"])
        
        date_layout.addWidget(self.date_radio, 0, 0, 1, 2)
        
        date_group.setLayout(date_layout)
        
        # 创建搜索选项组
        search_options_group = QGroupBox("搜索选项")
        search_options_layout = QVBoxLayout()
        
        # 搜索选项复选框
        self.case_sensitive = QCheckBox("区分大小写")
        self.match_whole_word = QCheckBox("匹配整个单词")
        self.search_content = QCheckBox("搜索文件内容")
        self.search_content.setChecked(True)
        
        for check in [self.case_sensitive, self.match_whole_word, self.search_content]:
            search_options_layout.addWidget(check)
        
        search_options_group.setLayout(search_options_layout)
        
        # 添加所有组到主布局
        layout.addWidget(file_types_group)
        layout.addWidget(size_group)
        layout.addWidget(date_group)
        layout.addWidget(search_options_group)
        layout.addStretch()
        
        # 设置样式
        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 10px;
                padding: 5px;
                font-weight: bold;
            }
            QLabel {
                padding: 3px;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
        """)

class ToolTip(QWidget):
    """自定义工具提示组件"""
    def __init__(self, parent=None, text="", x=0, y=0, timeout=2000):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 创建标签
        self.label = QLabel(text, self)
        self.label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 5px;
            border-radius: 4px;
            font-size: 12px;
        """)
        
        # 设置位置和大小
        self.setGeometry(x, y, self.label.sizeHint().width(), self.label.sizeHint().height())
        
        # 设置定时器自动隐藏
        self.timer = QThread.sleep(timeout / 1000)  # 转换为秒
        self.hide()
        
    def show_at(self, x, y, text=None):
        """在指定位置显示工具提示"""
        if text:
            self.label.setText(text)
        
        self.setGeometry(x, y, self.label.sizeHint().width(), self.label.sizeHint().height())
        self.show()
        
        # 启动定时器
        self.timer = QThread.sleep(2)  # 2秒后隐藏
        self.hide()

class ThemeManager:
    """主题管理器"""
    def __init__(self, app):
        self.app = app
        self.current_theme = "light"
        self.themes = {
            "light": self._get_light_theme(),
            "dark": self._get_dark_theme()
        }
    
    def _get_light_theme(self):
        """获取浅色主题样式"""
        return """
            QMainWindow, QWidget {
                background-color: #f0f0f0;
            }
            QLabel {
                color: #333;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QLineEdit, QTextEdit, QTableView {
                background-color: #fff;
                color: #333;
                border: 1px solid #ccc;
            }
        """
    
    def _get_dark_theme(self):
        """获取深色主题样式"""
        return """
            QMainWindow, QWidget {
                background-color: #333;
            }
            QLabel {
                color: #f0f0f0;
            }
            QPushButton {
                background-color: #555;
                color: #f0f0f0;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QLineEdit, QTextEdit, QTableView {
                background-color: #444;
                color: #f0f0f0;
                border: 1px solid #666;
            }
        """
    
    def apply_theme(self, theme_name):
        """应用主题"""
        if theme_name in self.themes:
            self.current_theme = theme_name
            self.app.setStyleSheet(self.themes[theme_name])
        
    def toggle_theme(self):
        """切换主题"""
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.apply_theme(new_theme)
        return new_theme

class IconManager:
    """图标管理器"""
    def __init__(self):
        self.icon_paths = {
            "search": "icons/search.png",
            "folder": "icons/folder.png",
            "file": "icons/file.png",
            "document": "icons/document.png",
            "image": "icons/image.png",
            "audio": "icons/audio.png",
            "video": "icons/video.png",
            "settings": "icons/settings.png",
            "help": "icons/help.png",
            "about": "icons/about.png",
            "refresh": "icons/refresh.png",
            "delete": "icons/delete.png",
            "add": "icons/add.png",
            "edit": "icons/edit.png"
        }
        
        # 确保图标目录存在
        self.ensure_icon_directory()
    
    def ensure_icon_directory(self):
        """确保图标目录存在"""
        for path in self.icon_paths.values():
            icon_dir = Path(path).parent
            if not icon_dir.exists():
                icon_dir.mkdir(parents=True, exist_ok=True)
    
    def get_icon(self, name):
        """获取图标"""
        if name in self.icon_paths:
            icon_path = self.icon_paths[name]
            if Path(icon_path).exists():
                return QIcon(icon_path)
        
        # 如果图标不存在，返回默认图标
        return QIcon()
    
    def set_icon_path(self, name, path):
        """设置图标路径"""
        self.icon_paths[name] = path