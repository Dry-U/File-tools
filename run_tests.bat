@echo off
chcp 65001 >nul
echo ==========================================
echo 运行测试套件并生成HTML报告
echo ==========================================
echo.

:: 创建报告目录
if not exist reports mkdir reports

:: 运行测试并生成报告
echo 运行所有测试...
python -m pytest tests/ -v --html=reports/test_report.html --self-contained-html

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo 测试全部通过！
    echo 报告位置: reports/test_report.html
    echo ==========================================
) else (
    echo.
    echo ==========================================
    echo 有测试失败，请查看报告
    echo 报告位置: reports/test_report.html
    echo ==========================================
)

echo.
pause
