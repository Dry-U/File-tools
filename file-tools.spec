# -*- mode: python ; coding: utf-8 -*-
"""
File Tools - PyInstaller 打包配置 (CI/CD 版本)
支持版本号自动注入
"""

import sys
import os
from pathlib import Path

# 获取当前目录
CURRENT_DIR = os.path.abspath(os.path.dirname(SPEC))

# 从环境变量读取版本号，或使用默认值
APP_VERSION = os.environ.get('FILETOOLS_VERSION', '0.1.0')
BUILD_MODE = os.environ.get('FILETOOLS_BUILD_MODE', 'full')

print(f"Building File Tools v{APP_VERSION} in {BUILD_MODE} mode")

# ===== 排除的大型库 =====
EXCLUDES = [
    'pytest', 'unittest', 'test', '_test',
    'pdb', 'pdbv', 'trace', 'tracemalloc',
    'cProfile', 'profile', 'pstats',
    'sphinx', 'pydoc_data',
    'tkinter', 'Tkinter', 'tcl', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'torch.distributions', 'torch.testing', 'torch.hub',
    'torchvision', 'torchaudio',
    'boto3', 'botocore',
    'matplotlib', 'seaborn',
    'jupyter', 'IPython', 'ipykernel', 'ipywidgets',
    'nbformat', 'nbconvert',
    'setuptools', 'pip', 'pkg_resources',
    'debugpy', 'pydevd',
]

if BUILD_MODE == 'slim':
    EXCLUDES.extend([
        'tensorflow',
        'tensorboard',
        'scipy',
    ])

# ===== 隐藏的导入 =====
HIDDEN_IMPORTS = [
    'pywebview',
    'pywebview.window',
    'fastapi',
    'uvicorn',
    'uvicorn.loops',
    'uvicorn.protocols',
    'pydantic',
    'pydantic.core',
    'charset_normalizer',
    'jieba',
    'jieba.posseg',
    'torch',
    'torch.nn',
    'torch.nn.functional',
    'pdfminer',
    'pdfminer.high_level',
    'docx',
    'pptx',
    'markdown',
    'openpyxl',
    'hnswlib',
    'tantivy',
    'yaml',
    'diskcache',
    'simplejson',
    'sortedcontainers',
    'win32com',
    'win32com.client',
    'pythoncom',
]

if BUILD_MODE == 'full':
    HIDDEN_IMPORTS.extend([
        'transformers',
        'transformers.modeling_utils',
        'transformers.tokenization_utils',
        'datasets',
        'pandas',
        'sklearn',
        'sklearn.utils',
        'sklearn.metrics',
    ])

# ===== 收集前端静态文件 =====
def get_static_files():
    """收集前端静态文件"""
    static_files = []
    frontend_static = os.path.join(CURRENT_DIR, 'frontend', 'static')
    if os.path.exists(frontend_static):
        for root, dirs, files in os.walk(frontend_static):
            for file in files:
                src = os.path.join(root, file)
                dest = os.path.join('frontend', 'static', os.path.relpath(root, frontend_static))
                static_files.append((src, dest))
    return static_files

# ===== 获取数据文件 =====
def get_data_files():
    """数据文件配置"""
    datas = get_static_files()

    # 添加默认配置模板
    config_template = os.path.join(CURRENT_DIR, 'config.yaml')
    if os.path.exists(config_template):
        datas.append((config_template, 'templates'))

    # 添加版本号文件
    version_file = os.path.join(CURRENT_DIR, 'VERSION')
    if os.path.exists(version_file):
        datas.append((version_file, '.'))

    return datas

# ===== 分析配置 =====
a = Analysis(
    ['main.py'],
    pathex=[CURRENT_DIR],
    binaries=[],
    datas=get_data_files(),
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

# ===== 过滤二进制文件 =====
def filter_binaries(binaries):
    """过滤大型二进制文件"""
    filtered = []
    excluded_patterns = [
        'test_', '_test',
        'Qt5WebEngine', 'Qt5Qml',
        'libcuda',
        'libnccl',
    ]

    for binary in binaries:
        name = binary[0]
        if not any(pattern in name for pattern in excluded_patterns):
            filtered.append(binary)
        else:
            print(f"[过滤] 排除: {name}")

    return filtered

a.binaries = filter_binaries(a.binaries)

# ===== 创建 PYZ 归档 =====
pyz = PYZ(a.pure, optimize=1)

# ===== 创建可执行文件 =====
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FileTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python3*.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='frontend/static/logo.ico' if os.path.exists('frontend/static/logo.ico') else None,
)

# ===== 收集到目录 =====
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    name=f'FileTools-v{APP_VERSION}'
)

print(f"\n{'='*60}")
print(f"打包完成: FileTools v{APP_VERSION}")
print(f"模式: {BUILD_MODE}")
print(f"{'='*60}\n")
