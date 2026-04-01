@echo off
chcp 65001 > nul
echo ====================================
echo   File-Tools 测试运行脚本
echo ====================================
echo.

python "%~dp0run_tests.py" %*

echo.
echo 按任意键退出...
pause > nul
