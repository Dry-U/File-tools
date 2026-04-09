#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Allure 报告管理脚本

用法:
    python scripts/allure_report.py generate  # 生成报告
    python scripts/allure_report.py open       # 生成并打开报告
    python scripts/allure_report.py clean      # 清理报告
    python scripts/allure_report.py history    # 查看历史趋势
"""

import argparse
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS = REPORTS_DIR / "allure-results"
ALLURE_REPORT = REPORTS_DIR / "allure-report"
ALLURE_HISTORY = ALLURE_RESULTS / "history"


def check_allure():
    """检查 allure 是否安装"""
    result = subprocess.run(["allure", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("错误: Allure 命令行工具未安装")
        print("\n安装方式:")
        print("  Windows: scoop install allure")
        print("  macOS:   brew install allure")
        print("  Linux:   sudo apt install allure")
        return False
    print(f"Allure 版本: {result.stdout.strip()}")
    return True


def generate_report(open_browser: bool = False):
    """生成 Allure 报告"""
    if not check_allure():
        return 1

    if not ALLURE_RESULTS.exists() or not list(ALLURE_RESULTS.glob("*")):
        print(f"错误: 未找到测试结果目录 {ALLURE_RESULTS}")
        print("请先运行测试: python scripts/run_tests.py")
        return 1

    # 复制历史数据
    history_source = ALLURE_REPORT / "history" if ALLURE_REPORT.exists() else None
    if history_source and history_source.exists():
        shutil.copytree(history_source, ALLURE_HISTORY, dirs_exist_ok=True)

    print(f"\n生成 Allure 报告...")
    cmd = [
        "allure",
        "generate",
        str(ALLURE_RESULTS),
        "-o",
        str(ALLURE_REPORT),
        "--clean",
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"\n✅ 报告已生成: {ALLURE_REPORT}")
        if open_browser:
            print("正在打开浏览器...")
            subprocess.Popen(["allure", "open", str(ALLURE_REPORT)])
        return 0
    else:
        print("生成报告失败")
        return 1


def clean_reports():
    """清理报告"""
    if ALLURE_REPORT.exists():
        shutil.rmtree(ALLURE_REPORT)
        print(f"已清理: {ALLURE_REPORT}")

    if ALLURE_RESULTS.exists():
        shutil.rmtree(ALLURE_RESULTS)
        print(f"已清理: {ALLURE_RESULTS}")

    print("\n✅ 所有报告已清理")


def serve_report():
    """本地服务方式查看报告"""
    if not check_allure():
        return 1

    if not ALLURE_REPORT.exists():
        print("报告不存在，正在生成...")
        generate_report(open_browser=False)

    print(f"\n启动 Allure 本地服务...")
    print(f"访问地址: http://localhost:4040\n")
    subprocess.run(["allure", "serve", str(ALLURE_RESULTS)])


def main():
    parser = argparse.ArgumentParser(
        description="Allure 报告管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # generate 命令
    gen_parser = subparsers.add_parser("generate", help="生成 Allure 报告")
    gen_parser.add_argument("--open", action="store_true", help="生成后打开浏览器")

    # open 命令
    subparsers.add_parser("open", help="打开 Allure 报告")

    # clean 命令
    subparsers.add_parser("clean", help="清理所有报告")

    # serve 命令
    subparsers.add_parser("serve", help="本地服务方式查看报告")

    args = parser.parse_args()

    if args.command == "generate":
        return generate_report(open_browser=args.open)
    elif args.command == "open":
        return generate_report(open_browser=True)
    elif args.command == "clean":
        clean_reports()
        return 0
    elif args.command == "serve":
        return serve_report()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    exit(main())
