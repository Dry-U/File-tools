#!/usr/bin/env python
"""FileTools Backend Builder - 检查模式（不重新构建）"""

import sys
from pathlib import Path

SRC_TAURI_BIN = Path(__file__).parent.resolve() / "src-tauri" / "bin"
expected_candidates = [
    # 当前主命名（下划线）
    SRC_TAURI_BIN / "filetools_backend-x86_64-pc-windows-msvc.exe",
    SRC_TAURI_BIN / "filetools_backend.exe",
]

for expected_file in expected_candidates:
    if expected_file.exists():
        print(f"后端文件已存在: {expected_file}")
        print(f"大小: {expected_file.stat().st_size / 1024 / 1024:.1f} MB")
        sys.exit(0)

print("错误: 找不到后端构建产物")
print("已检查候选文件:")
for candidate in expected_candidates:
    print(f"  - {candidate}")
print("请先运行: python build_pyinstaller.py")
sys.exit(1)
