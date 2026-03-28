# -*- mode: python ; coding: utf-8 -*-
"""
File Tools - PyInstaller 打包配置 (多版本支持)
支持 CPU/GPU/Slim 三种打包模式，版本号自动注入
"""

import sys
import os
from pathlib import Path

# 获取当前目录
CURRENT_DIR = os.path.abspath(os.path.dirname(SPEC))

# 从环境变量读取版本号和构建模式
APP_VERSION = os.environ.get('FILETOOLS_VERSION', '1.0.0')
BUILD_MODE = os.environ.get('FILETOOLS_BUILD_MODE', 'cpu')

print(f"\n{'='*60}")
print(f"Building File Tools v{APP_VERSION}")
print(f"Mode: {BUILD_MODE}")
print(f"{'='*60}\n")

# ===== 根据构建模式配置排除库 =====
EXCLUDES = [
    # 测试相关
    'pytest', 'unittest', 'test', '_test',
    'pdb', 'pdbv', 'trace', 'tracemalloc',
    'cProfile', 'profile', 'pstats',
    # 文档相关
    'sphinx', 'pydoc_data',
    # GUI 框架（不需要）
    'tkinter', 'Tkinter', 'tcl', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    # 开发工具
    'debugpy', 'pydevd', 'setuptools', 'pip', 'pkg_resources',
    # 云服务
    'boto3', 'botocore',
    # 可视化
    'matplotlib', 'seaborn',
    # Jupyter
    'jupyter', 'IPython', 'ipykernel', 'ipywidgets',
    'nbformat', 'nbconvert',
    # PyTorch 测试和扩展
    'torch.testing', 'torch.hub',
    'torchvision', 'torchaudio',
]

# Slim 模式额外排除
if BUILD_MODE == 'slim':
    EXCLUDES.extend([
        # AI 模型相关
        'transformers',
        'datasets',
        'pandas',
        'scipy',
        'sklearn',
        'tensorflow',
        'tensorboard',
        'modelscope',
        'langchain',
        # 大型科学计算库
        'numpy.testing',
        'numpy.distutils',
    ])

# CPU/GPU 模式排除一些非必要项
elif BUILD_MODE in ['cpu', 'gpu']:
    EXCLUDES.extend([
        'tensorflow',
        'tensorboard',
    ])

# ===== 根据构建模式配置隐藏导入 =====
HIDDEN_IMPORTS_BASE = [
    # Web 框架
    'pywebview',
    'pywebview.window',
    'fastapi',
    'uvicorn',
    'uvicorn.loops',
    'uvicorn.protocols',
    'uvicorn.lifespan.on',
    # 数据处理
    'pydantic',
    'pydantic.core',
    'charset_normalizer',
    'jieba',
    'jieba.posseg',
    'yaml',
    'diskcache',
    'simplejson',
    'sortedcontainers',
    # Windows 相关
    'win32com',
    'win32com.client',
    'pythoncom',
]

# 文档解析相关（所有模式都需要）
HIDDEN_IMPORTS_PARSER = [
    'pdfminer',
    'pdfminer.high_level',
    'docx',
    'pptx',
    'markdown',
    'openpyxl',
    'six',
]

# 搜索引擎相关（所有模式都需要）
HIDDEN_IMPORTS_SEARCH = [
    'hnswlib',
    'tantivy',
]

# AI 模型相关（仅 CPU/GPU 模式）
HIDDEN_IMPORTS_AI = [
    'torch',
    'torch.nn',
    'torch.nn.functional',
]

if BUILD_MODE in ['cpu', 'gpu']:
    HIDDEN_IMPORTS_AI.extend([
        'transformers',
        'transformers.modeling_utils',
        'transformers.tokenization_utils',
        'sklearn',
        'sklearn.utils',
        'sklearn.metrics',
        'modelscope',
        'addict',
    ])

# 合并所有隐藏导入
HIDDEN_IMPORTS = HIDDEN_IMPORTS_BASE + HIDDEN_IMPORTS_PARSER + HIDDEN_IMPORTS_SEARCH
if BUILD_MODE in ['cpu', 'gpu']:
    HIDDEN_IMPORTS.extend(HIDDEN_IMPORTS_AI)

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

# ===== 过滤二进制文件 =====
def filter_binaries(binaries):
    """过滤大型二进制文件以减小体积"""
    filtered = []
    excluded_patterns = [
        # 测试相关
        'test_', '_test',
        # Qt 相关（如果意外包含）
        'Qt5WebEngine', 'Qt5Qml',
        # CUDA 相关（Slim 模式排除）
        'libcuda', 'libnccl', 'libcudnn',
        # 可选的大型库
        '_caffe',
        '_caffe2',
    ]

    # Slim 模式额外过滤
    if BUILD_MODE == 'slim':
        excluded_patterns.extend([
            'libtorch',
            'libtorch_cpu',
            'libtorch_cuda',
            'torch_cpu',
            'torch_cuda',
            'c10_cuda',
        ])

    for binary in binaries:
        name = binary[0]
        if not any(pattern in name for pattern in excluded_patterns):
            filtered.append(binary)
        else:
            print(f"[过滤] 排除二进制: {name}")

    return filtered

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
    optimize=2,  # 优化级别 2，删除 assert 语句
)

# 过滤二进制文件
a.binaries = filter_binaries(a.binaries)

# ===== 创建 PYZ 归档 =====
pyz = PYZ(a.pure, optimize=2)

# ===== UPX 压缩配置 =====
upx_enabled = True
upx_exclude_list = ['vcruntime140.dll', 'python3*.dll', 'msvcp*.dll']

# ===== 创建可执行文件 =====
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=False,  # 收集所有二进制到 exe
    name='FileTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=upx_enabled,
    upx_exclude=upx_exclude_list,
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
    upx=upx_enabled,
    upx_exclude=upx_exclude_list,
    name=f'FileTools-v{APP_VERSION}-{BUILD_MODE}'
)

# ===== 打印构建信息 =====
print(f"\n{'='*60}")
print(f"打包完成: FileTools v{APP_VERSION}")
print(f"构建模式: {BUILD_MODE}")
if BUILD_MODE == 'slim':
    print("说明: 最小化版本，仅包含文件搜索功能")
elif BUILD_MODE == 'cpu':
    print("说明: CPU 版本，包含完整 AI 功能")
elif BUILD_MODE == 'gpu':
    print("说明: GPU 版本，支持 CUDA 加速")
print(f"{'='*60}\n")
