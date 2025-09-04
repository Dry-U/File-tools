# -*- coding: utf-8 -*-
"""专门用于跟踪哈希操作和配置访问的调试脚本"""
import traceback
import sys
import os
import types

# 保存原始的__hash__方法
original_hash = dict.__hash__

def debug_hash(self):
    """调试dict的__hash__方法调用"""
    print(f"\n警告: 尝试哈希字典 {self}")
    print(f"调用堆栈:")
    traceback.print_stack(file=sys.stdout)
    # 引发TypeError以保持原有的行为
    raise TypeError("unhashable type: 'dict'")

# 替换dict的__hash__方法用于调试
dict.__hash__ = debug_hash

# 导入必要的模块
from src.utils.config_loader import ConfigLoader

# 尝试跟踪配置加载器的get方法
old_get = ConfigLoader.get

def debug_get(self, section, key=None, default=None):
    """调试ConfigLoader的get方法"""
    print(f"\n调用ConfigLoader.get(section={section}, key={key}, default={default})")
    print(f"section类型: {type(section)}, key类型: {type(key)}")
    print(f"调用堆栈:")
    traceback.print_stack(file=sys.stdout)
    
    # 如果section或key是dict，记录详细信息
    if isinstance(section, dict):
        print(f"警告: section是字典! 内容: {section}")
    if isinstance(key, dict):
        print(f"警告: key是字典! 内容: {key}")
    
    # 调用原始的get方法
    try:
        return old_get(self, section, key, default)
    except Exception as e:
        print(f"get方法异常: {e}")
        traceback.print_exc(file=sys.stdout)
        return default

# 替换ConfigLoader的get方法
ConfigLoader.get = debug_get

if __name__ == "__main__":
    try:
        print("开始哈希调试...")
        
        # 尝试直接初始化主窗口，但捕获异常以分析问题
        print("\n尝试导入并初始化MainWindow...")
        from src.ui.main_window import MainWindow
        
        # 导入后立即退出，因为我们只关心初始化阶段的哈希调用
        print("\nMainWindow导入成功，开始初始化...")
        
        # 捕获初始化过程中的错误
        try:
            app = MainWindow()
        except Exception as e:
            print(f"\n初始化MainWindow时出错: {e}")
            traceback.print_exc(file=sys.stdout)
            print("\n调试完成")
            sys.exit(1)
            
        print("\nMainWindow初始化成功！")
        print("\n调试完成")
        
    except Exception as e:
        print(f"\n调试过程中出错: {e}")
        traceback.print_exc(file=sys.stdout)
    finally:
        # 恢复原始的__hash__方法
        dict.__hash__ = original_hash
        print("\n调试结束")