#!/usr/bin/env python3
"""
File Tools - NSIS 安装包构建脚本
动态生成 NSIS 安装脚本并调用 makensis 编译

用法:
    python scripts/build_installer.py --mode cpu --version 1.0.0
    python scripts/build_installer.py --mode slim
"""

import argparse
import os
import sys
import re
import shutil
import subprocess
from pathlib import Path


def read_version() -> str:
    """读取当前版本号"""
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


def generate_nsis_script(version: str, mode: str, output_dir: str) -> str:
    """从模板生成 NSIS 脚本"""
    project_root = Path(__file__).parent.parent
    template_path = project_root / "installer.nsi"
    output_path = project_root / output_dir / f"installer-{mode}.nsi"

    if not template_path.exists():
        print(f"[错误] 未找到 NSIS 模板: {template_path}")
        sys.exit(1)

    content = template_path.read_text(encoding="utf-8")
    content = content.replace("___VERSION___", version)
    content = content.replace("___MODE___", mode.upper())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"[生成] NSIS 脚本: {output_path}")
    return str(output_path)


def find_nsis() -> str:
    """查找 NSIS 编译器"""
    # 常见安装路径
    nsis_paths = [
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
        os.path.expandvars(r"%PROGRAMFILES(x86)%\NSIS\makensis.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\NSIS\makensis.exe"),
    ]

    for path in nsis_paths:
        if os.path.isfile(path):
            return path

    # 尝试 PATH
    nsis = shutil.which("makensis")
    if nsis:
        return nsis

    return ""


def build_installer(nsis_script: str, version: str, mode: str) -> str:
    """调用 NSIS 编译安装包"""
    nsis_path = find_nsis()
    if not nsis_path:
        print("[错误] 未找到 NSIS (makensis)，请先安装 NSIS:")
        print("  下载地址: https://nsis.sourceforge.io/Download")
        print("  或使用 Chocolatey: choco install nsis")
        sys.exit(1)

    print(f"[编译] 使用 NSIS: {nsis_path}")
    cmd = [
        nsis_path,
        "/INPUTCHARSET", "UTF8",
        "/OUTPUTCHARSET", "UTF8",
        nsis_script,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[错误] NSIS 编译失败:")
        print(result.stderr)
        sys.exit(1)

    # 查找生成的安装包
    project_root = Path(__file__).parent.parent
    pattern = f"FileTools-{mode}-v{version}-Setup.exe"
    installer_path = project_root / "dist" / pattern

    if installer_path.exists():
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"[完成] 安装包: {installer_path} ({size_mb:.1f} MB)")
        return str(installer_path)
    else:
        # 搜索
        for f in (project_root / "dist").glob("*.exe"):
            if "Setup" in f.name:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"[完成] 安装包: {f} ({size_mb:.1f} MB)")
                return str(f)

    print("[警告] 未找到生成的安装包")
    return ""


def create_portable_archive(version: str, mode: str) -> str:
    """创建便携版 zip 归档"""
    import zipfile

    project_root = Path(__file__).parent.parent
    source_dir = project_root / "dist" / f"FileTools-v{version}-{mode}"

    if not source_dir.exists():
        # 尝试查找
        matches = list((project_root / "dist").glob("FileTools-*"))
        if matches:
            source_dir = matches[0]
        else:
            print(f"[错误] 未找到构建目录")
            return ""

    archive_name = f"FileTools-{mode}-v{version}-portable.zip"
    archive_path = project_root / "dist" / archive_name

    print(f"[打包] 创建便携版: {archive_name}")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"[完成] 便携版: {archive_path} ({size_mb:.1f} MB)")
    return str(archive_path)


def main():
    parser = argparse.ArgumentParser(description="File Tools 安装包构建工具")
    parser.add_argument("--mode", choices=["cpu", "gpu", "slim"], default="cpu",
                        help="构建模式 (默认: cpu)")
    parser.add_argument("--version", default=None,
                        help="版本号 (默认从 VERSION 文件读取)")
    parser.add_argument("--portable", action="store_true",
                        help="同时创建便携版 zip")
    parser.add_argument("--no-compile", action="store_true",
                        help="只生成 NSIS 脚本，不编译")

    args = parser.parse_args()

    version = args.version or read_version()
    mode = args.mode

    print(f"\n{'='*50}")
    print(f"File Tools Installer Builder")
    print(f"版本: v{version} | 模式: {mode}")
    print(f"{'='*50}\n")

    # 生成 NSIS 脚本
    nsis_script = generate_nsis_script(version, mode, "dist")

    if not args.no_compile:
        # 编译安装包
        build_installer(nsis_script, version, mode)

    # 创建便携版
    if args.portable:
        create_portable_archive(version, mode)

    print("\n完成!")


if __name__ == "__main__":
    main()
