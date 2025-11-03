#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""主界面模块 - 实现应用程序的主窗口布局和交互逻辑"""
import sys
import os
import platform
from pathlib import Path
import datetime
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTabWidget,
    QPushButton,
    QLabel,
    QStatusBar,
    QAction,
    QMenuBar,
    QMenu,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
    QTreeView,
    QDialog,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QGridLayout,
    QApplication
)
from PyQt5.QtGui import (
    QIcon,
    QFont,
    QStandardItemModel,
    QStandardItem,
    QPixmap
)
from PyQt5.QtCore import (
    Qt,
    QSize,
    QThread,
    pyqtSignal,
    QDateTime,
    QSortFilterProxyModel
)

# 导入项目模块
from src.ui.components import (
    SearchBox,
    SearchResultView,
    SearchResultModel,
    FilePreviewer,
    ProgressIndicator,
    StatusLabel,
    AdvancedFilterWidget,
    ThemeManager,
    IconManager
)
from src.utils.logger import setup_logger, info, debug, error
from src.core.file_scanner import FileScanner
from src.core.search_engine import SearchEngine
from src.core.file_monitor import FileMonitor
from src.core.index_manager import IndexManager
from src.utils.config_loader import ConfigLoader

class ScanThread(QThread):
    """文件扫描线程"""
    progress_updated = pyqtSignal(int)
    scan_completed = pyqtSignal(dict)
    scan_failed = pyqtSignal(str)
    
    def __init__(self, scanner):
        super().__init__()
        self.scanner = scanner
        self.scanner.set_progress_callback(self.update_progress)
        self.running = False
    
    def run(self):
        """运行扫描任务"""
        self.running = True
        try:
            stats = self.scanner.scan_and_index()
            self.scan_completed.emit(stats)
        except Exception as e:
            self.scan_failed.emit(str(e))
        finally:
            self.running = False
    
    def update_progress(self, progress):
        """更新进度"""
        self.progress_updated.emit(progress)
    
    def stop(self):
        """停止扫描"""
        self.scanner.stop_scan()
        self.wait()

class SearchThread(QThread):
    """搜索线程"""
    search_completed = pyqtSignal(list)
    search_failed = pyqtSignal(str)
    
    def __init__(self, search_engine, query, filters=None):
        super().__init__()
        self.search_engine = search_engine
        self.query = query
        self.filters = filters or {}
    
    def run(self):
        """运行搜索任务"""
        try:
            print(f"开始搜索: {self.query}")
            print(f"过滤器: {self.filters}")
            # 修复：将filters作为单个参数传递，而不是展开为关键字参数
            results = self.search_engine.search(self.query, self.filters)
            print(f"搜索完成，找到 {len(results)} 条结果")
            if results:
                print(f"第一条结果: {results[0]}")
            self.search_completed.emit(results)
        except Exception as e:
            print(f"搜索失败: {str(e)}")
            import traceback
            traceback.print_exc()
            self.search_failed.emit(str(e))

class MainWindow(QMainWindow):
    """应用程序主窗口"""
    def __init__(self):
        super().__init__()
        # 初始化配置和日志
        try:
            self.config_loader = ConfigLoader()
            # 不直接存储config字典，始终通过config_loader访问配置
            self.logger = setup_logger(config=self.config_loader)
            
            # 初始化核心组件 - 确保所有组件都接收ConfigLoader对象
            self.index_manager = IndexManager(self.config_loader)
            self.search_engine = SearchEngine(self.index_manager, self.config_loader)  # 正确顺序：index_manager, config_loader
            self.file_scanner = FileScanner(self.config_loader, None, self.index_manager)  # 正确顺序：config_loader, document_parser(None), index_manager
            self.file_monitor = FileMonitor(self.config_loader, self.index_manager)  # 正确参数：config_loader, index_manager
            
            # 初始化UI组件
            try:
                self.theme_manager = ThemeManager(self)
                self.icon_manager = IconManager()
                # 应用配置的主题 - 通过config_loader获取配置
                theme_name = self.config_loader.get('interface', 'theme', 'light')
                self.theme_manager.apply_theme(theme_name)
                self.logger.info(f"已应用主题: {theme_name}")
            except Exception as e:
                self.logger.warning(f"初始化UI组件失败: {str(e)}，使用默认设置")
            
            # 设置中文字体
            self.set_font()
            
            # 初始化UI
            self.init_ui()
            
            # 启动文件监控（如果启用）
            if self.config_loader.get('monitor', 'enabled', False):
                self.start_monitoring()
        except Exception as e:
            # 全局异常捕获，确保程序不会崩溃
            error_message = f"程序初始化失败: {str(e)}"
            print(error_message)
            # 显示错误信息并退出
            QMessageBox.critical(None, "初始化失败", error_message)
            sys.exit(1)
    
    def set_font(self):
        """设置中文字体支持"""
        font_families = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
        
        # 选择系统中可用的字体
        font = QFont()
        for family in font_families:
            font.setFamily(family)
            if font.family() == family:
                break
        
        # 设置全局字体
        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            app.setFont(font)
    
    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口标题和大小
        app_name = self.config_loader.get('system', 'app_name', '智能文件检索与问答系统')
        self.setWindowTitle(app_name)
        self.resize(1200, 800)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 创建搜索栏区域
        search_layout = QHBoxLayout()
        
        # 搜索框
        self.search_box = SearchBox(self)
        self.search_box.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_box)
        
        # 搜索按钮
        self.search_button = QPushButton("搜索")
        self.search_button.setMinimumWidth(80)
        self.search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_button)
        
        # 高级筛选按钮
        self.filter_button = QPushButton("高级筛选")
        self.filter_button.setMinimumWidth(100)
        self.filter_button.clicked.connect(self.toggle_advanced_filter)
        search_layout.addWidget(self.filter_button)
        
        # 索引按钮
        self.index_button = QPushButton("重建索引")
        self.index_button.setMinimumWidth(100)
        self.index_button.clicked.connect(self.rebuild_index)
        search_layout.addWidget(self.index_button)
        
        # 添加搜索栏到主布局
        main_layout.addLayout(search_layout)
        
        # 创建分割器
        self.splitter = QSplitter(Qt.Vertical)  # type: ignore[attr-defined]
        
        # 创建搜索结果区域
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        
        # 搜索结果标题
        self.results_label = QLabel("搜索结果")
        results_layout.addWidget(self.results_label)
        
        # 搜索结果表格
        self.results_model = SearchResultModel(self)
        self.results_view = SearchResultView(self)
        self.results_view.setModel(self.results_model)
        self.results_view.clicked.connect(self.on_result_clicked)
        results_layout.addWidget(self.results_view)
        
        # 添加到分割器
        self.splitter.addWidget(results_widget)
        
        # 创建预览区域
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        # 预览标题
        self.preview_label = QLabel("文件预览")
        preview_layout.addWidget(self.preview_label)
        
        # 文件预览器
        self.previewer = FilePreviewer(self)
        preview_layout.addWidget(self.previewer)
        
        # 添加到分割器
        self.splitter.addWidget(preview_widget)
        
        # 设置分割器比例
        self.splitter.setSizes([500, 300])
        
        # 添加分割器到主布局
        main_layout.addWidget(self.splitter)
        
        # 创建高级筛选面板（默认隐藏）
        self.advanced_filter_widget = AdvancedFilterWidget(self)
        self.advanced_filter_widget.setVisible(False)
        main_layout.addWidget(self.advanced_filter_widget)
        
        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 添加状态栏组件
        self.status_label = StatusLabel(self)
        self.progress_indicator = ProgressIndicator(self)
        
        self.status_bar.addWidget(self.status_label)
        self.status_bar.addPermanentWidget(self.progress_indicator)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 应用主题
        theme = self.config_loader.get('interface', 'theme', 'light')
        self.theme_manager.apply_theme(theme)
    
    def create_menu_bar(self):
        """创建菜单栏"""
        # 创建菜单栏
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")  # type: ignore[union-attr]
        
        # 打开文件操作
        open_action = QAction("打开文件", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)  # type: ignore[union-attr]
        
        # 打开目录操作
        open_dir_action = QAction("打开目录", self)
        open_dir_action.setShortcut("Ctrl+D")
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)  # type: ignore[union-attr]
        
        # 导出搜索结果
        export_action = QAction("导出搜索结果", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)  # type: ignore[union-attr]
        
        # 分隔符
        file_menu.addSeparator()  # type: ignore[union-attr]
        
        # 退出操作
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)  # type: ignore[arg-type]
        file_menu.addAction(exit_action)  # type: ignore[union-attr]
        
        # 搜索菜单
        search_menu = menu_bar.addMenu("搜索")  # type: ignore[union-attr]
        
        # 重建索引操作
        rebuild_index_action = QAction("重建索引", self)
        rebuild_index_action.setShortcut("Ctrl+R")
        rebuild_index_action.triggered.connect(self.rebuild_index)
        search_menu.addAction(rebuild_index_action)  # type: ignore[union-attr]
        
        # 清除缓存操作
        clear_cache_action = QAction("清除缓存", self)
        clear_cache_action.setShortcut("Ctrl+L")
        clear_cache_action.triggered.connect(self.clear_cache)
        search_menu.addAction(clear_cache_action)  # type: ignore[union-attr]
        
        # 视图菜单
        view_menu = menu_bar.addMenu("视图")  # type: ignore[union-attr]
        
        # 切换主题操作
        theme_action = QAction("切换主题", self)
        theme_action.setShortcut("Ctrl+T")
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)  # type: ignore[union-attr]
        
        # 高级筛选操作
        filter_action = QAction("高级筛选", self)
        filter_action.setShortcut("Ctrl+F")
        filter_action.triggered.connect(self.toggle_advanced_filter)
        view_menu.addAction(filter_action)  # type: ignore[union-attr]
        
        # 设置菜单
        settings_menu = menu_bar.addMenu("设置")  # type: ignore[union-attr]
        
        # AI接口配置操作
        ai_config_action = QAction("AI接口配置", self)
        ai_config_action.triggered.connect(self.show_ai_config_dialog)
        settings_menu.addAction(ai_config_action)  # type: ignore[union-attr]
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")  # type: ignore[union-attr]
        
        # 使用帮助操作
        help_action = QAction("使用帮助", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)  # type: ignore[union-attr]
        
        # 关于操作
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)  # type: ignore[union-attr]
    
    def toggle_advanced_filter(self):
        """切换高级筛选面板的显示状态"""
        self.advanced_filter_widget.setVisible(not self.advanced_filter_widget.isVisible())
    
    def perform_search(self):
        """执行搜索操作"""
        query = self.search_box.text().strip()
        if not query:
            self.status_label.update_status("请输入搜索关键词")
            return
        
        print(f"准备搜索: {query}")
        
        # 更新状态栏
        self.status_label.update_status(f"正在搜索: {query}")
        
        # 获取筛选条件
        filters = self.get_filter_options()
        
        # 禁用搜索按钮
        self.search_button.setEnabled(False)
        self.search_button.setText("搜索中...")
        
        # 清空结果
        self.results_model.clear()
        self.results_model.setHorizontalHeaderLabels(["文件名", "路径", "匹配度", "修改时间"])
        
        # 在新线程中执行搜索
        self.search_thread = SearchThread(self.search_engine, query, filters)
        self.search_thread.search_completed.connect(self.on_search_completed)
        self.search_thread.search_failed.connect(self.on_search_failed)
        print("启动搜索线程")
        self.search_thread.start()
    
    def get_filter_options(self):
        """获取筛选选项"""
        # 获取高级筛选面板中的筛选条件
        afw = self.advanced_filter_widget
        
        # 文件类型筛选
        file_types = []
        if afw.txt_check.isChecked():
            file_types.extend([".txt", ".md", ".csv"])
        if afw.doc_check.isChecked():
            file_types.extend([".doc", ".docx", ".pdf"])
        if afw.xls_check.isChecked():
            file_types.extend([".xls", ".xlsx"])
        if afw.code_check.isChecked():
            file_types.extend([".py", ".js", ".java", ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".php", ".rb", ".swift"])
        if afw.img_check.isChecked():
            file_types.extend([".jpg", ".png", ".gif"])
        
        # 文件大小筛选
        min_size = None
        max_size = None
        try:
            if afw.min_size.text().strip():
                min_size = float(afw.min_size.text()) * 1024 * 1024  # 转换为字节
        except ValueError:
            pass
        
        try:
            if afw.max_size.text().strip():
                max_size = float(afw.max_size.text()) * 1024 * 1024  # 转换为字节
        except ValueError:
            pass
        
        # 搜索选项
        case_sensitive = afw.case_sensitive.isChecked()
        match_whole_word = afw.match_whole_word.isChecked()
        search_content = afw.search_content.isChecked()
        
        # 注意：只有当file_types不为空时才传递，否则不过滤
        filters = {
            "case_sensitive": case_sensitive,
            "match_whole_word": match_whole_word,
            "search_content": search_content
        }
        
        # 只添加非空None的过滤条件
        if file_types:
            filters["file_types"] = file_types  # type: ignore[assignment]
        if min_size is not None:
            filters["min_size"] = min_size  # type: ignore[assignment]
        if max_size is not None:
            filters["max_size"] = max_size  # type: ignore[assignment]
            
        return filters
    
    def on_search_completed(self, results):
        """搜索完成回调"""
        print(f"搜索完成回调，结果数: {len(results)}")
        
        # 启用搜索按钮
        self.search_button.setEnabled(True)
        self.search_button.setText("搜索")
        
        # 更新状态栏
        self.status_label.update_status(f"找到 {len(results)} 个结果")
        
        if len(results) == 0:
            # 显示提示信息
            QMessageBox.information(self, "搜索结果", "未找到匹配的文件。\n\n请尝试：\n1. 检查关键词拼写\n2. 使用不同的关键词\n3. 先点击'重建索引'扫描文件")
            return
        
        # 显示搜索结果
        for result in results:
            try:
                file_path = Path(result["path"])
                file_name = file_path.name
                score = result.get("score", 0) * 100  # 转换为百分比
                
                # 获取文件修改时间
                try:
                    modified_time = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
                except Exception:
                    modified_time = None
                
                # 添加到结果模型
                self.results_model.add_result(file_name, str(file_path), score, modified_time)
            except Exception as e:
                print(f"处理结果失败: {str(e)}")
                continue
    
    def on_search_failed(self, error_msg):
        """搜索失败回调"""
        # 启用搜索按钮
        self.search_button.setEnabled(True)
        self.search_button.setText("搜索")
        
        # 更新状态栏
        self.status_label.update_status(f"搜索失败: {error_msg}")
        
        # 显示错误消息
        QMessageBox.critical(self, "搜索错误", f"搜索过程中发生错误:\n{error_msg}")
    
    def on_result_clicked(self, index):
        """搜索结果点击回调"""
        # 获取选中的行
        row = index.row()
        
        # 获取文件路径
        path_index = self.results_model.index(row, 1)
        file_path = self.results_model.data(path_index)
        
        # 预览文件
        self.preview_file(file_path)
    
    def preview_file(self, file_path):
        """预览文件内容"""
        try:
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            # 读取最大预览大小配置
            max_preview_size = self.config_loader.get('interface', 'max_preview_size', 5 * 1024 * 1024)  # 默认5MB
            
            # 检查文件大小
            if file_size > max_preview_size:
                self.previewer.set_content(f"文件过大（{file_size/1024/1024:.2f}MB），无法预览")
                return
            
            # 获取文件扩展名
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # 根据文件类型进行预览
            if file_ext in ['.txt', '.md', '.csv', '.json', '.xml', '.py', '.js', '.html', '.css']:
                # 文本文件预览
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.previewer.set_content(content)
                
                # 高亮搜索文本
                search_text = self.search_box.text().strip()
                if search_text:
                    self.previewer.highlight_text(search_text)
            else:
                # 非文本文件提示
                self.previewer.set_content(f"不支持的文件类型（{file_ext}），无法预览内容")
            
            # 更新预览标签
            self.preview_label.setText(f"文件预览: {os.path.basename(file_path)}")
            
        except Exception as e:
            self.previewer.set_content(f"预览文件时发生错误:\n{str(e)}")
            self.logger.error(f"预览文件失败: {file_path}", exc_info=True)
    
    def rebuild_index(self):
        """重建索引"""
        # 询问用户是否确认重建索引
        reply = QMessageBox.question(
            self,
            "确认重建索引",
            "重建索引将重新扫描所有文件，可能需要较长时间。\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 创建进度对话框
        progress_dialog = QProgressDialog("正在重建索引...", "取消", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModal)  # type: ignore[attr-defined]
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        # 禁用索引按钮
        self.index_button.setEnabled(False)
        self.index_button.setText("重建中...")
        
        # 更新状态栏
        self.status_label.update_status("正在重建索引...")
        
        # 创建扫描线程
        self.scan_thread = ScanThread(self.file_scanner)
        self.scan_thread.progress_updated.connect(progress_dialog.setValue)
        self.scan_thread.progress_updated.connect(self.progress_indicator.setValue)
        self.scan_thread.scan_completed.connect(lambda stats: self.on_scan_completed(stats, progress_dialog))
        self.scan_thread.scan_failed.connect(lambda msg: self.on_scan_failed(msg, progress_dialog))
        
        # 连接取消按钮信号
        progress_dialog.canceled.connect(self.scan_thread.stop)
        
        # 启动扫描
        self.scan_thread.start()
    
    def on_scan_completed(self, stats, progress_dialog):
        """扫描完成回调"""
        # 关闭进度对话框
        progress_dialog.close()
        
        # 启用索引按钮
        self.index_button.setEnabled(True)
        self.index_button.setText("重建索引")
        
        # 隐藏进度指示器
        self.progress_indicator.hide_progress()
        
        # 更新状态栏
        files_scanned = stats.get('files_scanned', 0)
        files_indexed = stats.get('files_indexed', 0)
        self.status_label.update_status(f"索引重建完成: 扫描 {files_scanned} 个文件，索引 {files_indexed} 个文件")
        
        # 显示完成消息
        QMessageBox.information(
            self,
            "索引重建完成",
            f"索引重建已完成！\n\n"\
            f"扫描文件数: {files_scanned}\n"\
            f"索引文件数: {files_indexed}\n"\
            f"耗时: {stats.get('time_taken', 0):.2f} 秒"
        )
    
    def on_scan_failed(self, error_msg, progress_dialog):
        """扫描失败回调"""
        # 关闭进度对话框
        progress_dialog.close()
        
        # 启用索引按钮
        self.index_button.setEnabled(True)
        self.index_button.setText("重建索引")
        
        # 隐藏进度指示器
        self.progress_indicator.hide_progress()
        
        # 更新状态栏
        self.status_label.update_status(f"索引重建失败: {error_msg}")
        
        # 显示错误消息
        QMessageBox.critical(self, "索引重建失败", f"重建索引过程中发生错误:\n{error_msg}")
    
    def start_monitoring(self):
        """启动文件监控"""
        try:
            self.file_monitor.start_monitoring()
            self.status_label.update_status("文件监控已启动")
            self.logger.info("文件监控已启动")
        except Exception as e:
            self.status_label.update_status(f"文件监控启动失败: {str(e)}")
            self.logger.error(f"文件监控启动失败", exc_info=True)
    
    def stop_monitoring(self):
        """停止文件监控"""
        try:
            self.file_monitor.stop_monitoring()
            self.status_label.update_status("文件监控已停止")
            self.logger.info("文件监控已停止")
        except Exception as e:
            self.logger.error(f"文件监控停止失败", exc_info=True)
    
    def toggle_theme(self):
        """切换主题"""
        new_theme = self.theme_manager.toggle_theme()
        self.status_label.update_status(f"已切换到 {new_theme} 主题")
        
        # 保存主题设置
        self.config['interface']['theme'] = new_theme
        self.config_loader.save()
    
    def open_file(self):
        """打开文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开文件",
            str(Path.home()),
            "所有文件 (*);;文本文件 (*.txt *.md);;PDF文件 (*.pdf);;Office文件 (*.doc *.docx *.xls *.xlsx *.ppt *.pptx)"
        )
        
        if file_path:
            try:
                # 预览文件
                self.preview_file(file_path)
                
                # 尝试使用系统默认程序打开文件
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    os.system(f'open "{file_path}"')
                else:  # Linux
                    os.system(f'xdg-open "{file_path}"')
            except Exception as e:
                QMessageBox.critical(self, "打开文件失败", f"无法打开文件:\n{str(e)}")
    
    def open_directory(self):
        """打开目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "打开目录",
            str(Path.home())
        )
        
        if dir_path:
            try:
                # 尝试使用系统默认程序打开目录
                if platform.system() == 'Windows':
                    os.startfile(dir_path)
                elif platform.system() == 'Darwin':  # macOS
                    os.system(f'open "{dir_path}"')
                else:  # Linux
                    os.system(f'xdg-open "{dir_path}"')
            except Exception as e:
                QMessageBox.critical(self, "打开目录失败", f"无法打开目录:\n{str(e)}")
    
    def export_results(self):
        """导出搜索结果"""
        if self.results_model.rowCount() == 0:
            QMessageBox.information(self, "导出结果", "没有搜索结果可供导出")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出搜索结果",
            str(Path.home() / f"搜索结果_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
            "CSV文件 (*.csv);;文本文件 (*.txt)"
        )
        
        if file_path:
            try:
                # 根据文件扩展名选择格式
                is_csv = file_path.lower().endswith('.csv')
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    # 写入标题行
                    headers = ["文件名", "路径", "匹配度", "修改时间"]
                    if is_csv:
                        f.write(",".join(f"\"{header}\"" for header in headers) + "\n")
                    else:
                        f.write("\t".join(headers) + "\n")
                    
                    # 写入数据行
                    for row in range(self.results_model.rowCount()):
                        row_data = []
                        for col in range(self.results_model.columnCount()):
                            index = self.results_model.index(row, col)
                            value = self.results_model.data(index)
                            
                            # 处理包含特殊字符的值
                            if isinstance(value, str):
                                if is_csv:
                                    # CSV格式需要转义引号和逗号
                                    value = value.replace('"', '""')  # 转义引号
                                    row_data.append(f"\"{value}\"")
                                else:
                                    row_data.append(value)
                            else:
                                row_data.append(str(value))
                        
                        # 写入一行数据
                        if is_csv:
                            f.write(",".join(row_data) + "\n")
                        else:
                            f.write("\t".join(row_data) + "\n")
                
                self.status_label.update_status(f"已导出 {self.results_model.rowCount()} 条结果到 {file_path}")
                QMessageBox.information(self, "导出成功", f"搜索结果已成功导出到:\n{file_path}")
            except Exception as e:
                self.status_label.update_status(f"导出结果失败: {str(e)}")
                QMessageBox.critical(self, "导出失败", f"导出搜索结果时发生错误:\n{str(e)}")
    
    def clear_cache(self):
        """清除缓存"""
        # 询问用户是否确认清除缓存
        reply = QMessageBox.question(
            self,
            "确认清除缓存",
            "清除缓存将删除所有临时文件和搜索缓存。\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            # 清除搜索缓存
            self.search_engine.clear_cache()  # type: ignore[attr-defined]
            
            # 清除临时文件目录
            temp_dir = Path(self.config_loader.get('system', 'temp_dir', './data/temp'))
            if temp_dir.exists():
                for file_path in temp_dir.glob('*'):
                    if file_path.is_file():
                        file_path.unlink()
            
            self.status_label.update_status("缓存已清除")
            QMessageBox.information(self, "清除成功", "缓存已成功清除")
        except Exception as e:
            self.status_label.update_status(f"清除缓存失败: {str(e)}")
            QMessageBox.critical(self, "清除失败", f"清除缓存时发生错误:\n{str(e)}")
    
    def show_help(self):
        """显示帮助信息"""
        QMessageBox.information(
            self,
            "使用帮助",
            "智能文件检索与问答系统\n\n"\
            "功能说明:\n"\
            "1. 在搜索框中输入关键词进行文件搜索\n"\
            "2. 点击搜索结果可在下方预览文件内容\n"\
            "3. 使用高级筛选可根据文件类型、大小等条件过滤结果\n"\
            "4. 点击'重建索引'可重新扫描文件并创建索引\n"\
            "\n"\
            "快捷键:\n"\
            "Ctrl+O - 打开文件\n"\
            "Ctrl+D - 打开目录\n"\
            "Ctrl+E - 导出搜索结果\n"\
            "Ctrl+R - 重建索引\n"\
            "Ctrl+L - 清除缓存\n"\
            "Ctrl+T - 切换主题\n"\
            "Ctrl+F - 高级筛选\n"\
            "Ctrl+Q - 退出程序"
        )
    
    def show_about(self):
        """显示关于信息"""
        app_name = self.config_loader.get('system', 'app_name', '智能文件检索与问答系统')
        app_version = self.config_loader.get('system', 'version', '1.0.0')
        
        QMessageBox.about(
            self,
            "关于",
            f"{app_name}\n"
            f"版本: {app_version}\n"
            "\n"
            "智能文件检索与问答系统\n"
            "基于Python的本地文件智能管理工具\n"
            "\n"
            "© 2023 版权所有"
        )
        
    def show_ai_config_dialog(self):
        """显示AI接口配置对话框"""
        dialog = AIConfigDialog(self.config_loader, self)
        if dialog.exec_() == QDialog.Accepted:
            # 保存配置
            self.config_loader.save()
            # 更新状态
            self.status_label.update_status("AI接口配置已更新")
            # 重新初始化ModelManager以应用新配置
            try:
                from src.core.model_manager import ModelManager
                self.model_manager = ModelManager(self.config_loader)
                self.logger.info("模型管理器已重新初始化")
            except Exception as e:
                self.logger.error(f"重新初始化模型管理器失败: {e}")
                QMessageBox.critical(self, "错误", f"重新初始化模型管理器失败: {str(e)}")
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        # 停止文件监控
        self.stop_monitoring()
        
        # 关闭索引管理器
        self.index_manager.close()
        
        # 接受关闭事件
        event.accept()

class AIConfigDialog(QDialog):
    """AI接口配置对话框"""
    def __init__(self, config_loader, parent=None):
        super().__init__(parent)
        self.config_loader = config_loader
        self.setWindowTitle("AI接口配置")
        self.resize(500, 300)
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建设置组
        settings_group = QGroupBox("AI接口设置")
        settings_layout = QFormLayout()
        
        # 启用AI模型复选框
        self.enable_checkbox = QCheckBox()
        self.enable_checkbox.setChecked(self.config_loader.get('model', 'enabled', False))
        settings_layout.addRow("启用AI模型:", self.enable_checkbox)
        
        # AI接口类型下拉框
        self.interface_combo = QComboBox()
        self.interface_combo.addItems(["local", "wsl", "api"])
        current_interface = self.config_loader.get('model', 'interface_type', 'local')
        if current_interface in ["local", "wsl", "api"]:
            self.interface_combo.setCurrentText(current_interface)
        settings_layout.addRow("接口类型:", self.interface_combo)
        
        # API URL输入框
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setText(self.config_loader.get('model', 'api_url', 'http://localhost:8000/v1/completions'))
        settings_layout.addRow("API URL:", self.api_url_edit)
        
        # API密钥输入框
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setText(self.config_loader.get('model', 'api_key', ''))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        settings_layout.addRow("API密钥:", self.api_key_edit)
        
        # 嵌入模型输入框
        self.embedding_model_edit = QLineEdit()
        self.embedding_model_edit.setText(self.config_loader.get('model', 'embedding_model', 'all-MiniLM-L6-v2'))
        settings_layout.addRow("嵌入模型:", self.embedding_model_edit)
        
        # 最大令牌数输入框
        self.max_tokens_edit = QLineEdit()
        self.max_tokens_edit.setText(str(self.config_loader.get('model', 'max_tokens', 2048)))
        settings_layout.addRow("最大令牌数:", self.max_tokens_edit)
        
        # 温度参数输入框
        self.temperature_edit = QLineEdit()
        self.temperature_edit.setText(str(self.config_loader.get('model', 'temperature', 0.7)))
        settings_layout.addRow("温度参数:", self.temperature_edit)
        
        # 将设置布局添加到设置组
        settings_group.setLayout(settings_layout)
        
        # 创建按钮区域
        button_layout = QHBoxLayout()
        
        # 保存按钮
        save_button = QPushButton("保存")
        save_button.clicked.connect(self.accept)
        
        # 取消按钮
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        
        # 添加按钮到按钮布局
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        
        # 添加设置组和按钮区域到主布局
        main_layout.addWidget(settings_group)
        main_layout.addLayout(button_layout)
    
    def accept(self):
        """接受对话框，保存配置"""
        # 验证并保存数值设置
        try:
            max_tokens = int(self.max_tokens_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "最大令牌数必须是整数")
            return
        
        try:
            temperature = float(self.temperature_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "温度参数必须是数字")
            return
        
        # 保存配置
        self.config_loader.set('model', 'enabled', self.enable_checkbox.isChecked())
        self.config_loader.set('model', 'interface_type', self.interface_combo.currentText())
        self.config_loader.set('model', 'api_url', self.api_url_edit.text())
        self.config_loader.set('model', 'api_key', self.api_key_edit.text())
        self.config_loader.set('model', 'embedding_model', self.embedding_model_edit.text())
        self.config_loader.set('model', 'max_tokens', max_tokens)
        self.config_loader.set('model', 'temperature', temperature)
        
        super().accept()