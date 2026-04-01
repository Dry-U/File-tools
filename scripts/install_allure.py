#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Allure CLI 安装脚本

用法:
    python scripts/install_allure.py        # 安装
    python scripts/install_allure.py --path # 指定安装路径
"""

import argparse
import urllib.request
import zipfile
import shutil
import os
from pathlib import Path


def install_allure(install_dir: str = None):
    """下载并安装 Allure CLI"""

    if install_dir is None:
        # 默认安装到用户目录
        install_dir = os.path.join(os.path.expanduser("~"), ".allure")

    install_dir = Path(install_dir)
    allure_bin = install_dir / "allure" / "bin"
    allure_exe = allure_bin / "allure.bat"

    # 检查是否已安装
    if allure_exe.exists():
        print(f"✅ Allure 已安装在: {install_dir}")
        print(f"   执行: {allure_exe} --version")
        return True

    # 下载 Allure
    version = "2.25.0"
    zip_name = f"allure-{version}.zip"
    url = f"https://github.com/allure-framework/allure2/releases/download/{version}/{zip_name}"

    print(f"正在下载 Allure {version}...")
    print(f"URL: {url}")

    try:
        # 下载
        zip_path = Path(f"{zip_name}")
        urllib.request.urlretrieve(url, zip_path)

        # 解压
        print(f"解压到: {install_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(install_dir)

        # 清理 zip
        zip_path.unlink()

        # 验证安装
        if allure_exe.exists():
            print(f"\n✅ Allure 安装成功!")
            print(f"   安装路径: {install_dir}")
            print(f"\n请将以下路径添加到系统 PATH:")
            print(f"   {allure_bin}")
            print(f"\n或者直接运行:")
            print(f"   {allure_exe} --version")
            return True
        else:
            print("❌ 安装失败: 未找到 allure 可执行文件")
            return False

    except Exception as e:
        print(f"❌ 安装失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Allure CLI 安装脚本")
    parser.add_argument(
        "--path",
        dest="path",
        help="安装路径 (默认: ~/.allure)"
    )
    args = parser.parse_args()

    install_allure(args.path)


if __name__ == "__main__":
    main()
