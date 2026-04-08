#!/usr/bin/env python
"""FileTools Backend Builder - 检查模式（不重新构建）"""
import sys
from pathlib import Path

SRC_TAURI_BIN = Path(__file__).parent.resolve() / "src-tauri" / "bin"
expected_file = SRC_TAURI_BIN / "filetools-backend-x86_64-pc-windows-msvc.exe"

if expected_file.exists():
    print(f"后端文件已存在: {expected_file}")
    print(f"大小: {expected_file.stat().st_size / 1024 / 1024:.1f} MB")
    sys.exit(0)
else:
    print(f"错误: 找不到 {expected_file}")
    print("请先运行: python build_pyinstaller.py")
    sys.exit(1)
