# -*- coding: utf-8 -*-
"""调试脚本，用于捕获详细的错误信息和堆栈跟踪"""
import traceback
import sys
from src.utils.config_loader import ConfigLoader
from src.core.index_manager import IndexManager
from src.core.search_engine import SearchEngine

# 自定义的ConfigLoader子类用于调试
class DebugConfigLoader(ConfigLoader):
    def get(self, section, key=None, default=None):
        print(f"\n调用ConfigLoader.get(section={section}, key={key}, default={default})")
        print(f"section类型: {type(section)}")
        print(f"config结构: {type(self.config)}, 键: {list(self.config.keys())[:5]}...")
        
        # 检查section是否为不可哈希类型
        try:
            hash(section)
            print(f"section {section} 是可哈希的")
        except TypeError:
            print(f"警告: section {section} 是不可哈希的！")
            return default
            
        # 检查section是否存在于配置中
        if section not in self.config:
            print(f"section '{section}' 不在配置中")
            return default
            
        # 如果没有指定key，返回整个section
        if key is None:
            print(f"返回整个section '{section}'")
            return self.config[section]
            
        # 检查key是否存在于section中
        if key not in self.config[section]:
            print(f"key '{key}' 不在section '{section}' 中")
            return default
            
        print(f"返回 {section}.{key} = {self.config[section][key]}")
        return self.config[section][key]

if __name__ == "__main__":
    try:
        print("开始调试...")
        # 初始化自定义配置加载器进行详细调试
        print("创建ConfigLoader...")
        config_loader = ConfigLoader()
        print(f"配置加载器类型: {type(config_loader)}")
        print(f"配置内容类型: {type(config_loader.config)}")
        print(f"配置键: {list(config_loader.config.keys())}")
        
        # 测试get方法
        print("\n测试get方法:")
        test_section = 'search'
        test_key = 'text_weight'
        test_value = config_loader.get(test_section, test_key)
        print(f"{test_section}.{test_key} = {test_value}")
        
        # 初始化索引管理器
        print("\n初始化索引管理器...")
        index_manager = IndexManager(config_loader)
        print(f"索引管理器初始化成功: {index_manager}")
        
        # 创建自定义调试配置加载器用于搜索引擎初始化
        print("\n创建DebugConfigLoader用于搜索引擎初始化...")
        debug_config = DebugConfigLoader()
        debug_config.config = config_loader.config  # 复制实际配置
        
        # 初始化搜索引擎
        print("\n初始化搜索引擎...")
        search_engine = SearchEngine(index_manager, debug_config)
        print(f"搜索引擎初始化成功: {search_engine}")
        
        print("\n所有组件初始化成功！")
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print(f"错误类型: {type(e)}")
        print("堆栈跟踪:")
        traceback.print_exc(file=sys.stdout)
    finally:
        print("\n调试结束")