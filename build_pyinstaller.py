#!/usr/bin/env python
"""
FileTools Backend Builder - PyInstaller 版
支持 Tauri 打包的 Python 后端构建脚本

用法:
    python build_pyinstaller.py          # 构建后端到 src-tauri/bin/
    python build_pyinstaller.py --check  # 仅检查依赖

输出:
    Windows: src-tauri/bin/filetools-backend-x86_64-pc-windows-msvc.exe
    Linux:   src-tauri/bin/filetools-backend-x86_64-unknown-linux-gnu
    macOS:   src-tauri/bin/filetools-backend-x86_64-apple-darwin
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_TAURI_BIN = PROJECT_ROOT / "src-tauri" / "bin"


def clean_dist():
    """清理旧构建"""
    if SRC_TAURI_BIN.exists():
        print("清理旧构建...")
        shutil.rmtree(SRC_TAURI_BIN, ignore_errors=True)
    SRC_TAURI_BIN.mkdir(parents=True, exist_ok=True)


def get_output_name():
    """获取平台对应的输出文件名（Tauri 期望的格式）"""
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Tauri v2 需要带 target triple 的文件名
    # 格式: filetools-backend-{arch}-{vendor}-{os}-{abi}.exe
    arch_map = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }
    arch = arch_map.get(machine, machine)

    if system == "windows":
        return f"filetools_backend-{arch}-pc-windows-msvc.exe"
    elif system == "darwin":
        return f"filetools_backend-{arch}-apple-darwin"
    else:  # linux
        return f"filetools_backend-{arch}-unknown-linux-gnu"


def check_dependencies():
    """检查 Python 依赖是否完整"""
    # 模块名 -> 包名 映射（import 名 vs pip 包名）
    required = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("tantivy", "tantivy"),
        ("hnswlib", "hnswlib"),
        ("jieba", "jieba"),
        ("pypdf", "pypdf"),
        ("pdfplumber", "pdfplumber"),
        ("docx", "python-docx"),  # import docx, pip python-docx
        ("pptx", "python-pptx"),  # import pptx, pip python-pptx
        ("openpyxl", "openpyxl"),
        ("watchdog", "watchdog"),
        ("psutil", "psutil"),
        ("yaml", "pyyaml"),  # import yaml, pip pyyaml
        ("numpy", "numpy"),
        ("pandas", "pandas"),
    ]
    missing = []
    for item in required:
        if isinstance(item, tuple):
            import_name, package_name = item
        else:
            import_name = item
            package_name = item
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print("运行: uv sync 或 pip install -e .")
        return False
    print("依赖检查通过")
    return True


def build_backend():
    """使用 PyInstaller 打包 Python 后端"""
    system = sys.platform.lower()
    is_windows = (
        system == "win32" or system.startswith("cygwin") or system.startswith("msys")
    )
    output_name = get_output_name()
    output_path = SRC_TAURI_BIN / output_name

    # 检查是否已存在（跳过重建）
    if output_path.exists() and output_path.stat().st_size > 100_000_000:  # > 100MB
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"后端文件已存在 ({size_mb:.1f} MB)，跳过构建")
        print(f"如需重新构建，请删除: {output_path}")
        return 0

    print("=" * 60)
    print("Building FileTools Backend with PyInstaller")
    print(f"Platform: {'Windows' if is_windows else 'Linux/macOS'}")
    print(f"Output: {output_path}")
    print("=" * 60)

    # 检查依赖
    if not check_dependencies():
        return 1

    clean_dist()

    # 查找 Python 解释器
    if is_windows:
        python_paths = [
            PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
            Path(sys.executable),  # 当前 Python
        ]
    else:
        python_paths = [
            PROJECT_ROOT / ".venv" / "bin" / "python",
            Path("python3"),
            Path(sys.executable),
        ]

    python = None
    for p in python_paths:
        if p.exists():
            python = str(p)
            break

    if not python:
        print("错误: 找不到 Python 解释器")
        return 1

    print(f"使用 Python: {python}")

    workdir = PROJECT_ROOT / "build" / "pyinstaller"
    workdir.mkdir(parents=True, exist_ok=True)

    # PyInstaller 构建参数
    # PyInstaller 的 --name 只接受基础名称（不含 triple）
    # 输出文件会是 {distpath}/{name}.exe
    pyinstaller_name = output_name.split("-")[0]  # "filetools_backend"

    args = [
        python,
        "-m",
        "PyInstaller",
        "--name",
        pyinstaller_name,  # 只有基础名称
        "--distpath",
        str(SRC_TAURI_BIN),
        "--workpath",
        str(workdir),
        "--specpath",
        str(workdir),
        "--onefile",  # 单文件模式
        "--noconfirm",  # 不确认覆盖
        "--clean",  # 清理临时文件
    ]

    if is_windows:
        args.append("--windowed")  # Windows GUI 模式（无控制台窗口）
    else:
        args.append("--console")  # Linux/macOS 控制台模式

    # 隐藏导入（PyInstaller 自动检测不到的模块）
    hidden_imports = [
        # FastAPI 和 uvicorn
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "pydantic",
        "pydantic.deprecated.decorator",
        # 搜索索引
        "tantivy",
        "hnswlib",
        # 中文分词
        "jieba",
        "jieba.posseg",
        # 文档解析
        "pypdf",
        "pdfplumber",
        "fitz",  # PyMuPDF
        "docx",
        "python_docx",
        "pptx",
        "python_pptx",
        "openpyxl",
        # 系统监控
        "watchdog",
        "psutil",
        # 配置
        "yaml",
        "yaml.cyaml",
        # 机器学习（用于 RAG）
        "sklearn",
        "sklearn.feature_extraction.text",
        # 基础库
        "numpy",
        "pandas",
        # Windows 特定
        "win32api",
        "win32con",
        "win32file",
        "win32process",
        "win32com",
        # 其他
        "PIL",
        "PIL.Image",  # 图片处理
        "requests",  # HTTP 请求
        "aiohttp",  # 异步 HTTP
    ]

    for imp in hidden_imports:
        args.extend(["--hidden-import", imp])

    # 数据文件
    data_files = [
        (str(PROJECT_ROOT / "frontend"), "frontend"),
        (str(PROJECT_ROOT / "config.yaml"), "."),
    ]

    # 添加 data 目录（如果存在）
    data_dir = PROJECT_ROOT / "data"
    if data_dir.exists():
        data_files.append((str(data_dir), "data"))

    for src, dst in data_files:
        if Path(src).exists():
            args.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # 图标
    icon_path = PROJECT_ROOT / "frontend" / "static" / "logo.ico"
    if icon_path.exists():
        args.extend(["--icon", str(icon_path)])

    # 入口文件
    args.append(str(PROJECT_ROOT / "main.py"))

    print(f"\n命令: {' '.join(args)}\n")
    print("开始构建（这可能需要 5-10 分钟）...")

    result = subprocess.run(args, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        # PyInstaller 输出的是基础名称.exe
        # 但我们需要检查 triple 版本（因为 Tauri externalBin 会添加 triple）
        # 实际上 Tauri 会自动添加 triple，所以我们只需要 PyInstaller 输出基础版本
        actual_output = SRC_TAURI_BIN / f"{pyinstaller_name}.exe"

        if actual_output.exists():
            # 重命名为 Tauri 期望的 triple 名称
            triple_name = SRC_TAURI_BIN / output_name
            if not triple_name.exists():
                import shutil as sh

                sh.copy2(actual_output, triple_name)
                actual_output = triple_name

            size_mb = actual_output.stat().st_size / 1024 / 1024
            print(f"\n{'=' * 60}")
            print(f"构建成功!")
            print(f"{'=' * 60}")
            print(f"输出: {actual_output}")
            print(f"大小: {size_mb:.1f} MB")
            return 0
        else:
            print("\n警告: 输出文件未找到")
            print(f"目录内容: {list(SRC_TAURI_BIN.glob('*'))}")
            return 1
    else:
        print(f"\n构建失败，返回码: {result.returncode}")
        return result.returncode


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(0 if check_dependencies() else 1)
    sys.exit(build_backend())
