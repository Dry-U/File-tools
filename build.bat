@echo off
REM File Tools 构建脚本 (CI/CD 兼容版本)
REM 支持版本号自动管理和多种构建模式

setlocal EnableDelayedExpansion

echo ========================================
echo File Tools - 构建脚本
echo ========================================
echo.

REM 获取当前目录
set "CURRENT_DIR=%~dp0"
cd /d "%CURRENT_DIR%"

REM 解析参数
set "BUILD_MODE=full"
set "USE_UPX=true"
set "BUMP_VERSION=false"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="slim" set "BUILD_MODE=slim" & shift & goto :parse_args
if /i "%~1"=="full" set "BUILD_MODE=full" & shift & goto :parse_args
if /i "%~1"=="noupx" set "USE_UPX=false" & shift & goto :parse_args
if /i "%~1"=="bump" set "BUMP_VERSION=true" & shift & goto :parse_args
shift
goto :parse_args
:args_done

REM 读取/更新版本号
if "%BUMP_VERSION%"=="true" (
    echo [版本] 递增 patch 版本号...
    for /f "tokens=1-3 delims=." %%a in (VERSION) do (
        set /a PATCH=%%c+1
        set "VERSION=%%a.%%b.!PATCH!"
    )
    echo !VERSION! > VERSION
    echo [版本] 新版本: !VERSION!
) else (
    for /f %%i in (VERSION) do set "VERSION=%%i"
)

echo [配置] 版本号: %VERSION%
echo [配置] 构建模式: %BUILD_MODE%
echo [配置] 使用 UPX: %USE_UPX%
echo.

REM 检查虚拟环境
if exist ".venv\Scripts\python.exe" (
    echo [Python] 使用虚拟环境...
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    echo [Python] 使用系统 Python...
    set "PYTHON=python.exe"
)

REM 检查依赖
echo.
echo [1/5] 检查依赖...
%PYTHON% -c "import pyinstaller" 2>nul
if errorlevel 1 (
    echo [安装] PyInstaller...
    %PYTHON% -m pip install pyinstaller
)

REM 检查 UPX
if "%USE_UPX%"=="true" (
    where upx >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 UPX，跳过二进制压缩
        set "USE_UPX=false"
    ) else (
        echo [OK] 找到 UPX
    )
)

REM 清理旧的构建
echo.
echo [2/5] 清理旧构建...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM 设置环境变量
echo.
echo [3/5] 设置构建环境...
set "FILETOOLS_VERSION=%VERSION%"
set "FILETOOLS_BUILD_MODE=%BUILD_MODE%"

REM 构建命令
echo.
echo [4/5] 开始构建 FileTools v%VERSION%...
echo 这可能需要几分钟到几十分钟，请耐心等待...
echo.

set "PYINSTALLER_CMD=pyinstaller file-tools.spec --noconfirm --clean"

if "%USE_UPX%"=="false" (
    set "PYINSTALLER_CMD=%PYINSTALLER_CMD% --upx-dir=NONE"
)

echo [执行] %PYINSTALLER_CMD%
%PYINSTALLER_CMD%

if errorlevel 1 (
    echo.
    echo [错误] 构建失败！
    exit /b 1
)

REM 构建后处理
echo.
echo [5/5] 构建后处理...

set "DIST_DIR=dist\FileTools-v%VERSION%"
if not exist "%DIST_DIR%" (
    REM 尝试找到生成的目录
    for /d %%D in (dist\FileTools*) do (
        set "DIST_DIR=%%D"
        goto :found_dist
    )
)
:found_dist

if exist "%DIST_DIR%" (
    echo [处理] 创建数据目录结构...
    mkdir "%DIST_DIR%\data" 2>nul
    mkdir "%DIST_DIR%\logs" 2>nul

    REM 写入版本信息
    echo %VERSION% > "%DIST_DIR%\VERSION.txt"
    echo Build: Manual >> "%DIST_DIR%\VERSION.txt"
    echo Date: %date% %time% >> "%DIST_DIR%\VERSION.txt"

    REM 复制启动脚本
    echo [处理] 创建启动脚本...
    (
        echo @echo off
        echo REM File Tools v%VERSION% - 启动脚本
        echo.
        echo start "" "%%~dp0FileTools.exe"
    ) > "%DIST_DIR%\启动.bat"
)

REM 显示结果
echo.
echo ========================================
echo 构建完成！
echo ========================================
echo.
echo 版本: v%VERSION%
echo 输出目录: %DIST_DIR%\
echo.
echo 文件大小统计:
echo ----------------------------------------
for %%f in ("%DIST_DIR%\*.exe") do (
    echo 主程序: %%~nxf
    for %%a in ("%%f") do (
        set "size=%%~za"
        echo   大小: !size! 字节 (~!size:~0,-6! MB)
    )
)
echo.
echo 使用说明:
echo 1. 将 %DIST_DIR%\ 目录复制到任意位置
echo 2. 运行 FileTools.exe 或 启动.bat
echo 3. 首次运行会自动创建配置文件和数据目录
echo.

pause
