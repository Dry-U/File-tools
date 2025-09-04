import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt


def setup_chinese_font_support(app):
    """设置中文字体支持"""
    font_families = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei"]
    
    # 获取应用程序字体
    font = app.font()
    
    # 尝试设置字体
    for family in font_families:
        font.setFamily(family)
        app.setFont(font)
        # 检查是否设置成功（如果字体名称没变，则可能不支持该字体）
        if app.font().family() == family:
            print(f"成功设置中文字体: {family}")
            break


class SimpleMainWindow(QMainWindow):
    """简化版的主窗口，用于测试UI基本功能"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文件工具 - 测试UI")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 添加标签
        label = QLabel("UI测试成功！基本界面组件能够正常加载。")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 18px;")
        layout.addWidget(label)
        
        # 添加额外信息
        info_label = QLabel("这是一个简化版的测试窗口，用于验证PyQt5的基本功能。")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)


if __name__ == "__main__":
    # 创建应用程序实例
    app = QApplication(sys.argv)
    
    # 设置中文字体支持
    setup_chinese_font_support(app)
    
    # 创建并显示主窗口
    window = SimpleMainWindow()
    window.show()
    
    # 运行应用程序主循环
    sys.exit(app.exec_())