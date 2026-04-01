#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试运行脚本 - 支持 Allure 报告

用法:
    python scripts/run_tests.py              # 运行所有测试
    python scripts/run_tests.py unit         # 仅运行单元测试
    python scripts/run_tests.py integration  # 仅运行集成测试
    python scripts/run_tests.py e2e          # 仅运行 E2E 测试
    python scripts/run_tests.py --allure     # 运行测试并生成 Allure 报告
    python scripts/run_tests.py --open       # 运行测试并打开 Allure 报告
"""

import argparse
import subprocess
import sys
import os
import shutil
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS = REPORTS_DIR / "allure-results"
ALLURE_REPORT = REPORTS_DIR / "allure-report"

# Allure 安装路径
ALLURE_PATH = Path.home() / ".allure" / "allure-2.25.0" / "bin" / "allure.bat"


def ensure_reports_dir():
    """确保报告目录存在"""
    REPORTS_DIR.mkdir(exist_ok=True)
    ALLURE_RESULTS.mkdir(exist_ok=True, parents=True)


def is_allure_installed():
    """检查 Allure 是否已安装"""
    return ALLURE_PATH.exists()


def run_pytest(args: list, description: str) -> int:
    """运行 pytest 并返回结果"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")

    cmd = ["python", "-m", "pytest"] + args
    print(f"执行命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def generate_allure_report(open_browser: bool = False):
    """生成 Allure 报告"""
    print(f"\n{'='*60}")
    print(f"  生成 Allure 报告")
    print(f"{'='*60}\n")

    if not is_allure_installed():
        print("错误: Allure CLI 未安装")
        print(f"请运行: python scripts/install_allure.py")
        return 1

    if not ALLURE_RESULTS.exists() or not list(ALLURE_RESULTS.glob("*")):
        print("错误: 未找到 Allure 测试结果")
        print("请先运行测试: python scripts/run_tests.py --allure")
        return 1

    # 复制历史数据
    history_dest = ALLURE_RESULTS / "history"
    if ALLURE_REPORT.exists():
        history_src = ALLURE_REPORT / "history"
        if history_src.exists():
            shutil.copytree(history_src, history_dest, dirs_exist_ok=True)

    # 生成报告
    cmd = [str(ALLURE_PATH), "generate", str(ALLURE_RESULTS), "-o", str(ALLURE_REPORT), "--clean"]
    print(f"执行: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"\n成功: Allure 报告已生成")
        print(f"   路径: {ALLURE_REPORT}")

        if open_browser:
            print("正在打开浏览器...")
            subprocess.Popen([str(ALLURE_PATH), "open", str(ALLURE_REPORT)])
        return 0
    else:
        print("错误: 生成 Allure 报告失败")
        return 1


def run_tests(categories: list = None, use_allure: bool = False, open_report: bool = False):
    """运行测试"""
    ensure_reports_dir()

    # 构建 pytest 参数
    args = [
        "-v",
        "--tb=short"
    ]

    # 如果使用 Allure，添加相关参数
    if use_allure:
        args.extend(["--alluredir", str(ALLURE_RESULTS)])

    # 添加标准报告参数
    args.extend([
        "--html=reports/test_report.html",
        "--self-contained-html",
        "--cov=backend",
        "--cov-report=html:reports/coverage",
        "--cov-report=term-missing",
    ])

    # 按分类运行
    if categories:
        for cat in categories:
            if cat == "unit":
                run_pytest(args + ["-m", "unit"], "单元测试")
            elif cat == "integration":
                run_pytest(args + ["-m", "integration"], "集成测试")
            elif cat == "e2e":
                run_pytest(args + ["-m", "e2e"], "端到端测试")
            elif cat == "performance":
                run_pytest(args + ["-m", "performance"], "性能测试")
    else:
        # 运行所有测试
        run_pytest(args, "所有测试")

    # 生成 Allure 报告
    if use_allure or open_report:
        generate_allure_report(open_browser=open_report)


def main():
    parser = argparse.ArgumentParser(
        description="测试运行脚本 - 支持 Allure 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "categories",
        nargs="*",
        choices=["unit", "integration", "e2e", "performance"],
        help="测试分类 (可选)"
    )
    parser.add_argument(
        "--allure",
        action="store_true",
        help="生成 Allure 报告"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="打开 Allure 报告"
    )

    args = parser.parse_args()

    run_tests(
        categories=args.categories,
        use_allure=args.allure,
        open_report=args.open
    )


if __name__ == "__main__":
    main()
