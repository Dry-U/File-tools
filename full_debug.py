# -*- coding: utf-8 -*-
"""全面调试脚本，用于捕获和分析所有组件的配置获取问题"""
import traceback
import sys
import os
import logging
from src.utils.config_loader import ConfigLoader
from src.core.index_manager import IndexManager
from src.core.search_engine import SearchEngine
from src.core.file_scanner import FileScanner
from src.core.file_monitor import FileMonitor
from src.core.model_manager import ModelManager
from src.ui.main_window import MainWindow

# 配置日志
sys.stdout = open(os.devnull, 'w')
sys.stderr = open('debug.log', 'w')

# 自定义的安全ConfigLoader用于调试
class SafeConfigLoader(ConfigLoader):
    def __init__(self):
        super().__init__()
        print("初始化SafeConfigLoader")
        
    def get(self, section, key=None, default=None):
        print(f"\n调用SafeConfigLoader.get(section={section}, key={key}, default={default})")
        print(f"section类型: {type(section)}")
        print(f"key类型: {type(key)}")
        
        # 安全检查
        try:
            # 检查section是否可哈希
            if not isinstance(section, (str, int)):
                print(f"警告: section {section} 不是可哈希类型！")
                return default
                
            # 检查key是否可哈希
            if key is not None and not isinstance(key, (str, int)):
                print(f"警告: key {key} 不是可哈希类型！")
                return default
                
            # 检查section是否存在
            if section not in self.config:
                print(f"警告: section '{section}' 不存在于配置中")
                return default
                
            # 如果没有key，返回整个section
            if key is None:
                result = self.config[section]
                print(f"返回整个section '{section}': {type(result)}")
                return result
                
            # 检查key是否存在
            if key not in self.config[section]:
                print(f"警告: key '{key}' 不存在于section '{section}' 中")
                return default
                
            # 返回配置值
            result = self.config[section][key]
            print(f"返回 {section}.{key} = {result} ({type(result)})")
            return result
            
        except Exception as e:
            print(f"获取配置时出错: {e}")
            print(f"错误类型: {type(e)}")
            traceback.print_exc(file=sys.stdout)
            return default

if __name__ == "__main__":
    try:
        print("开始全面调试...")
        
        # 1. 初始化安全配置加载器
        print("\n1. 初始化安全配置加载器")
        safe_config = SafeConfigLoader()
        print(f"配置加载器类型: {type(safe_config)}")
        print(f"配置内容: {type(safe_config.config)}, 键: {list(safe_config.config.keys())}")
        
        # 2. 单独测试每个组件的初始化
        print("\n2. 测试各个组件的初始化")
        
        # 2.1 测试IndexManager
        print("\n2.1 测试IndexManager初始化")
        index_manager = IndexManager(safe_config)
        print(f"IndexManager初始化成功: {index_manager}")
        
        # 2.2 测试SearchEngine
        print("\n2.2 测试SearchEngine初始化")
        search_engine = SearchEngine(index_manager, safe_config)
        print(f"SearchEngine初始化成功: {search_engine}")
        
        # 2.3 测试FileScanner
        print("\n2.3 测试FileScanner初始化")
        file_scanner = FileScanner(index_manager, safe_config)
        print(f"FileScanner初始化成功: {file_scanner}")
        
        # 2.4 测试FileMonitor
        print("\n2.4 测试FileMonitor初始化")
        file_monitor = FileMonitor(file_scanner, safe_config)
        print(f"FileMonitor初始化成功: {file_monitor}")
        
        # 2.5 测试ModelManager
        print("\n2.5 测试ModelManager初始化")
        model_manager = ModelManager(safe_config)
        print(f"ModelManager初始化成功: {model_manager}")
        
        print("\n所有组件单独初始化成功！")
        
        # 3. 尝试初始化MainWindow
        print("\n3. 尝试初始化MainWindow (这将初始化所有组件)")
        # 重置配置加载器，因为MainWindow会创建自己的
        original_config = ConfigLoader()
        main_window = MainWindow(original_config)
        print(f"MainWindow初始化成功！")
        
        print("\n全面调试成功完成！")
        
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print(f"错误类型: {type(e)}")
        print("堆栈跟踪:")
        traceback.print_exc(file=sys.stdout)
    finally:
        print("\n调试结束")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__