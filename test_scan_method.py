#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试扫描方法的脚本，验证 rglob 是否能找到文件
"""
import sys
from pathlib import Path

def test_scan_methods():
    """测试不同的文件扫描方法"""
    test_path = Path("D:\\Garbage\\Career\\Senior\\Thesis")
    
    print(f"测试目录: {test_path}")
    print(f"目录存在: {test_path.exists()}")
    print(f"是目录: {test_path.is_dir()}")
    
    if test_path.exists() and test_path.is_dir():
        # 方法1: 使用 rglob (文件扫描器使用的方法)
        print("\n--- 使用 rglob('*') ---")
        rglob_files = list(test_path.rglob('*'))
        rglob_files = [f for f in rglob_files if f.is_file()]  # 只保留文件
        print(f"rglob 找到文件数: {len(rglob_files)}")
        for f in rglob_files[:5]:  # 显示前5个
            print(f"  {f}")
        
        # 方法2: 使用 glob 
        print("\n--- 使用 glob('**/*') ---")
        glob_files = list(test_path.glob('**/*')) 
        glob_files = [f for f in glob_files if f.is_file()]
        print(f"glob 找到文件数: {len(glob_files)}")
        for f in glob_files[:5]:
            print(f"  {f}")
        
        # 方法3: 使用 os.walk
        print("\n--- 使用 os.walk ---")
        import os
        walk_files = []
        for root, dirs, files in os.walk(test_path):
            for file in files:
                walk_files.append(Path(root) / file)
        print(f"os.walk 找到文件数: {len(walk_files)}")
        for f in walk_files[:5]:
            print(f"  {f}")
        
        # 检查单个文件是否存在
        print("\n--- 验证单个文件 ---")
        sample_file = test_path / "2.计科22101-代拴拴-2204001188-毕业论文(设计)-开题报告.docx"
        print(f"示例文件存在: {sample_file.exists()}")
        if sample_file.exists():
            print(f"示例文件stat: {sample_file.stat()}")

if __name__ == "__main__":
    test_scan_methods()