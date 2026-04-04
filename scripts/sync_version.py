#!/usr/bin/env python
"""
版本同步脚本
从 VERSION 文件读取版本号，同步到 pyproject.toml 和 build_nuitka.py

用法:
    python scripts/sync_version.py          # 同步所有
    python scripts/sync_version.py --check   # 检查是否同步
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def read_version():
    """从 VERSION 文件读取版本"""
    version_file = PROJECT_ROOT / "VERSION"
    if not version_file.exists():
        print("ERROR: VERSION file not found")
        sys.exit(1)
    return version_file.read_text().strip()


def update_pyproject(version):
    """更新 pyproject.toml"""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text(encoding='utf-8')
    new_content = re.sub(
        r'^version = "[^"]+"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE
    )
    if content != new_content:
        pyproject.write_text(new_content, encoding='utf-8')
        print(f"Updated pyproject.toml: {version}")
    else:
        print(f"pyproject.toml already has version: {version}")


def update_build_nuitka(version):
    """更新 build_nuitka.py 中的版本号"""
    build_file = PROJECT_ROOT / "build_nuitka.py"
    content = build_file.read_text(encoding='utf-8')

    # 更新 --windows-file-version 和 --windows-product-version (3位版本)
    new_content = re.sub(
        r'--windows-file-version=\d+\.\d+\.\d+(\.\d+)?',
        f'--windows-file-version={version}',
        content
    )
    new_content = re.sub(
        r'--windows-product-version=\d+\.\d+\.\d+(\.\d+)?',
        f'--windows-product-version={version}',
        new_content
    )

    if content != new_content:
        build_file.write_text(new_content, encoding='utf-8')
        print(f"Updated build_nuitka.py: {version}")
    else:
        print(f"build_nuitka.py already has version: {version}")


def update_iss(version):
    """更新 build_inno_setup.iss 中的版本号"""
    iss_file = PROJECT_ROOT / "scripts" / "build_inno_setup.iss"
    if not iss_file.exists():
        print("WARNING: build_inno_setup.iss not found, skipping...")
        return

    content = iss_file.read_text(encoding='utf-8')

    # 更新 #define MyAppVersion
    new_content = re.sub(
        r'#define MyAppVersion "[^"]+"',
        f'#define MyAppVersion "{version}"',
        content
    )

    # 更新 OutputBaseFilename 中的版本号
    new_content = re.sub(
        r'FileTools-[\d.]+-win64-setup',
        f'FileTools-{version}-win64-setup',
        new_content
    )

    if content != new_content:
        iss_file.write_text(new_content, encoding='utf-8')
        print(f"Updated build_inno_setup.iss: {version}")
    else:
        print(f"build_inno_setup.iss already has version: {version}")


def check_sync():
    """检查版本是否同步"""
    version = read_version()
    issues = []

    # 检查 pyproject.toml
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if match := re.search(r'^version = "([^"]+)"', pyproject.read_text(encoding='utf-8'), re.MULTILINE):
        if match.group(1) != version:
            issues.append(f"pyproject.toml: {match.group(1)} != {version}")

    # 检查 build_nuitka.py
    build_file = PROJECT_ROOT / "build_nuitka.py"
    content = build_file.read_text(encoding='utf-8')
    if match := re.search(r'--windows-file-version=(\d+\.\d+\.\d+)', content):
        if match.group(1) != version:
            issues.append(f"build_nuitka.py: {match.group(1)} != {version}")

    # 检查 ISS
    iss_file = PROJECT_ROOT / "scripts" / "build_inno_setup.iss"
    if iss_file.exists():
        content = iss_file.read_text(encoding='utf-8')
        if match := re.search(r'#define MyAppVersion "([^"]+)"', content):
            if match.group(1) != version:
                issues.append(f"build_inno_setup.iss: {match.group(1)} != {version}")

    if issues:
        print("Version sync issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nRun 'python scripts/sync_version.py' to sync versions")
        return False
    else:
        print(f"All versions synced to: {version}")
        return True


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(0 if check_sync() else 1)

    version = read_version()
    print(f"Syncing version to: {version}")

    update_pyproject(version)
    update_build_nuitka(version)
    update_iss(version)

    print("\nVersion sync complete!")


if __name__ == "__main__":
    main()
