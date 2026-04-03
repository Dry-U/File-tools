#!/usr/bin/env python
"""
Nuitka Build Script for FileTools
使用 Nuitka 将 Python 代码编译为 C，再编译为独立可执行文件
配合 Inno Setup 生成原生 Windows 安装包

用法:
    python build_nuitka.py [mode]
    mode: slim (默认), cpu, gpu
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"


def get_python_executable():
    """获取正确的 Python 解释器路径"""
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def install_nuitka():
    """安装 Nuitka"""
    python = get_python_executable()
    try:
        import nuitka
        try:
            print(f"Nuitka version: {nuitka.__version__}")
        except AttributeError:
            result = subprocess.run([python, "-m", "nuitka", "--version"], capture_output=True, text=True)
            print(f"Nuitka version: {result.stdout.split()[1]}")
    except ImportError:
        print("Installing Nuitka...")
        try:
            subprocess.check_call(["uv", "pip", "install", "nuitka"])
        except FileNotFoundError:
            subprocess.check_call([python, "-m", "pip", "install", "nuitka"])


def get_build_args(mode):
    """获取 Nuitka 构建参数 (Nuitka 4.x 语法)"""
    python = get_python_executable()
    args = [
        python, "-m", "nuitka",
        "--mode=standalone",           # 独立可执行文件
        "--follow-imports",            # 跟随所有导入
        f"--output-dir={DIST_DIR}",
        "--assume-yes-for-downloads",
        # 体积优化
        "--lto=yes",                          # 启用 LTO 优化
        "--include-windows-runtime-dlls=no",   # 不包含 Windows Runtime DLL
        # Windows 特定
        "--windows-console-mode=disable",   # 禁用控制台窗口
        "--windows-icon-from-ico=frontend/static/logo.ico" if (PROJECT_ROOT / "frontend/static/logo.ico").exists() else None,
    ]

    # 过滤 None 值
    args = [a for a in args if a]

    # Windows 版本信息
    args.extend([
        "--windows-company-name=FileTools",
        "--windows-product-name=FileTools",
        "--windows-file-version=1.0.0",
        "--windows-product-version=1.0.0",
        "--windows-file-description=智能文件检索与问答系统",
    ])

    # 模式特定排除 (Nuitka 4.x 使用 --nofollow-import-to)
    if mode == "slim":
        nofollow_modules = [
            "torch",
            "transformers",
            "fastembed",
            "modelscope",
            "datasets",
            "pandas",
            "numpy",
            "scipy",
            "sklearn",
            "pymupdf",
            "pdfplumber",
            "pytesseract",
            "pycryptodome",
            "cryptography",
        ]
    elif mode == "cpu":
        nofollow_modules = [
            "torch.cuda",
            "torch.distributed",
            "torch.distributions",
            "torch.testing",
            "torch.backends.cudnn",
        ]
    elif mode == "gpu":
        nofollow_modules = [
            "torch.backends.cudnn",
        ]
    else:
        nofollow_modules = []

    for mod in nofollow_modules:
        args.append(f"--nofollow-import-to={mod}")

    # 入口文件
    args.append(str(PROJECT_ROOT / "main.py"))

    return args


def clean_dist():
    """清理旧构建"""
    import time
    if DIST_DIR.exists():
        print("Cleaning old build...")
        try:
            shutil.rmtree(DIST_DIR)
        except PermissionError:
            # 文件被占用，跳过清理
            print("Warning: Some files are locked, skipping clean...")


def analyze_output(mode):
    """分析构建产物"""
    if not DIST_DIR.exists():
        return

    print("\n=== Build Output Analysis ===")

    # 查找输出 - Nuitka 输出为 main.dist
    main_dir = DIST_DIR / "main.dist"
    if not main_dir.exists():
        for dist_folder in DIST_DIR.glob("*.dist"):
            main_dir = dist_folder
            break

    if main_dir.exists() and main_dir.is_dir():
        total_size = sum(
            f.stat().st_size
            for f in main_dir.rglob("*")
            if f.is_file()
        )
        file_count = sum(1 for _ in main_dir.rglob("*") if _.is_file())

        print(f"\nExecutable: {main_dir.name}")
        print(f"  Directory size: {total_size / 1024 / 1024:.2f} MB")
        print(f"  File count: {file_count}")

        print("\n  Largest files:")
        files = sorted(
            [(f, f.stat().st_size) for f in main_dir.rglob("*") if f.is_file()],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        for f, size in files:
            print(f"    {size / 1024 / 1024:.2f} MB - {f.name} ({f.parent.name}/)")

    print()


def build(mode="slim"):
    """执行构建"""
    print(f"\n{'='*60}")
    print(f"Building FileTools with Nuitka (Mode: {mode})")
    print(f"{'='*60}\n")

    install_nuitka()
    clean_dist()

    args = get_build_args(mode)
    print(f"Command: {' '.join(args)}\n")

    env = os.environ.copy()
    env["FILETOOLS_BUILD_MODE"] = mode

    result = subprocess.run(args, env=env, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"\n{'='*60}")
        print(f"Build successful! (Mode: {mode})")
        print(f"{'='*60}")
        analyze_output(mode)
    else:
        print(f"\nBuild failed with code {result.returncode}")
        return result.returncode

    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "slim"
    mode = mode.lower()

    if mode not in ["slim", "cpu", "gpu"]:
        print(f"Unknown mode: {mode}")
        print("Usage: python build_nuitka.py [slim|cpu|gpu]")
        sys.exit(1)

    sys.exit(build(mode))
