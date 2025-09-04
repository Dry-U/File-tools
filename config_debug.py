# -*- coding: utf-8 -*-
"""专注于跟踪配置加载和组件初始化的调试脚本"""
import traceback
import sys
import os

# 导入项目模块
from src.utils.config_loader import ConfigLoader

# 创建一个代理类来包装ConfigLoader，跟踪所有的方法调用
class ConfigLoaderProxy:
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.calls = []
    
    def __getattr__(self, name):
        # 获取原始属性
        attr = getattr(self.config_loader, name)
        
        # 如果是方法，包装它以进行跟踪
        if callable(attr) and name != '__class__':
            def wrapped_method(*args, **kwargs):
                print(f"\n调用ConfigLoader.{name}(args={args}, kwargs={kwargs})")
                for i, arg in enumerate(args):
                    print(f"  args[{i}] 类型: {type(arg)}, 值: {arg}")
                for key, value in kwargs.items():
                    print(f"  kwargs[{key}] 类型: {type(value)}, 值: {value}")
                
                # 检查是否有dict类型的参数可能导致哈希问题
                for i, arg in enumerate(args):
                    if isinstance(arg, dict):
                        print(f"  警告: args[{i}] 是dict类型: {arg}")
                for key, value in kwargs.items():
                    if isinstance(value, dict):
                        print(f"  警告: kwargs[{key}] 是dict类型: {value}")
                
                # 记录调用
                call_info = {'method': name, 'args': args, 'kwargs': kwargs}
                self.calls.append(call_info)
                
                try:
                    result = attr(*args, **kwargs)
                    print(f"  返回值类型: {type(result)}")
                    return result
                except Exception as e:
                    print(f"  异常: {e}")
                    traceback.print_exc(file=sys.stdout)
                    return None
            return wrapped_method
        
        return attr

if __name__ == "__main__":
    try:
        print("开始配置调试...")
        
        # 阶段1: 测试ConfigLoader的基本功能
        print("\n阶段1: 测试ConfigLoader的基本功能")
        config_loader = ConfigLoader()
        print(f"配置加载器类型: {type(config_loader)}")
        print(f"配置内容类型: {type(config_loader.config)}")
        print(f"配置键: {list(config_loader.config.keys())}")
        
        # 测试get方法的正常调用
        print("\n测试正常的get方法调用:")
        test_value = config_loader.get('system', 'app_name', '默认应用')
        print(f"获取'system.app_name' = {test_value}")
        
        # 阶段2: 使用代理类跟踪所有方法调用
        print("\n阶段2: 使用代理类跟踪所有方法调用")
        proxy = ConfigLoaderProxy(config_loader)
        
        # 尝试获取配置，模拟组件初始化过程中可能的调用
        print("\n模拟搜索组件配置获取:")
        search_config = proxy.get('search')
        print(f"搜索配置: {search_config}")
        
        # 阶段3: 尝试初始化单个组件并跟踪配置访问
        print("\n阶段3: 尝试初始化单个组件并跟踪配置访问")
        
        print("\n初始化IndexManager...")
        from src.core.index_manager import IndexManager
        index_manager = IndexManager(proxy)
        print(f"IndexManager初始化成功: {index_manager}")
        
        print("\n初始化SearchEngine...")
        from src.core.search_engine import SearchEngine
        search_engine = SearchEngine(index_manager, proxy)
        print(f"SearchEngine初始化成功: {search_engine}")
        
        print("\n初始化FileScanner...")
        from src.core.file_scanner import FileScanner
        file_scanner = FileScanner(proxy, index_manager)
        print(f"FileScanner初始化成功: {file_scanner}")
        
        print("\n初始化FileMonitor...")
        from src.core.file_monitor import FileMonitor
        file_monitor = FileMonitor(proxy, file_scanner)
        print(f"FileMonitor初始化成功: {file_monitor}")
        
        # 阶段4: 最后尝试初始化MainWindow
        print("\n阶段4: 尝试初始化MainWindow")
        try:
            from src.ui.main_window import MainWindow
            print("导入MainWindow成功")
        except Exception as e:
            print(f"导入MainWindow失败: {e}")
            traceback.print_exc(file=sys.stdout)
        
        print("\n调试完成")
        
    except Exception as e:
        print(f"\n调试过程中出错: {e}")
        traceback.print_exc(file=sys.stdout)
    finally:
        print("\n调试结束")