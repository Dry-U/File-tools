#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试中文分析器"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from backend.core.index_manager import ChineseAnalyzer
    import jieba
    
    print("成功导入jieba和中文分析器")
    
    # 测试jieba分词
    text = "个性化设置"
    tokens = jieba.lcut(text)
    print(f"分词结果: {tokens}")
    
    # 测试中文分析器
    analyzer = ChineseAnalyzer()()
    result = list(analyzer(text))
    print(f"分析器结果: {result}")
    
    print("中文分析器测试成功!")
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()