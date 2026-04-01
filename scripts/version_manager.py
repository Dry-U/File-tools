#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
版本号管理工具
自动更新小版本号 (x.x.y 中的 y)
"""

import os
import re
from pathlib import Path

VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def read_version():
    """读取当前版本号"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "0.1.0"


def parse_version(version_str):
    """解析版本号为 major, minor, patch"""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_str)
    if not match:
        return 0, 1, 0
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_patch_version(version_str):
    """递增 patch 版本号"""
    major, minor, patch = parse_version(version_str)
    patch += 1
    return f"{major}.{minor}.{patch}"


def bump_minor_version(version_str):
    """递增 minor 版本号"""
    major, minor, _ = parse_version(version_str)
    minor += 1
    return f"{major}.{minor}.0"


def write_version(version):
    """写入版本号"""
    VERSION_FILE.write_text(version)
    print(f"版本号已更新: {version}")


def get_version_for_ci():
    """为 CI 获取版本号（自动递增 patch）"""
    current = read_version()

    # 如果是 tag 触发，使用 tag 的版本号
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/tags/v'):
        return ref.replace('refs/tags/v', '')

    # 否则递增 patch 版本
    new_version = bump_patch_version(current)
    write_version(new_version)
    return new_version


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='版本号管理工具')
    parser.add_argument('command', choices=['get', 'bump', 'bump-minor', 'ci'])

    args = parser.parse_args()

    if args.command == 'get':
        print(read_version())
    elif args.command == 'bump':
        new_ver = bump_patch_version(read_version())
        write_version(new_ver)
    elif args.command == 'bump-minor':
        new_ver = bump_minor_version(read_version())
        write_version(new_ver)
    elif args.command == 'ci':
        print(get_version_for_ci())
