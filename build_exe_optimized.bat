@echo off
REM File Tools 优化构建脚本
REM 支持多种构建模式：完整版、精简版、单文件/单目录

setlocal EnableDelayedExpansion

echo ========================================
echo File Tools - 优化构建脚本
echo ========================================
echo.

REM 获取当前目录
set "CURRENT_DIR=%~dp0"
cd /d "%CURRENT_DIR%"

REM 解析参数
set "BUILD_MODE=full"
set "BUILD_TYPE=onedir"
set "USE_UPX=true"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="slim" set "BUILD_MODE=slim" & shift & goto :parse_args
if /i "%~1"=="full" set "BUILD_MODE=full" & shift & goto :parse_args
if /i "%~1"=="onefile" set "BUILD_TYPE=onefile" & shift & goto :parse_args
if /i "%~1"=="onedir" set "BUILD_TYPE=onedir" & shift & goto :parse_args
if /i "%~1"=="noupx" set "USE_UPX=false" & shift & goto :parse_args
shift
goto :parse_args
:args_done

echo 构建模式: %BUILD_MODE%
echo 构建类型: %BUILD_TYPE%
echo 使用 UPX: %USE_UPX%
echo.

REM 检查虚拟环境
if exist ".venv\Scripts\python.exe" (
    echo 使用虚拟环境...
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    echo 使用系统 Python...
    set "PYTHON=python.exe"
)

REM 安装/检查依赖
echo.
echo [1/5] 检查依赖...
%PYTHON% -c "import pyinstaller" 2>nul
if errorlevel 1 (
    echo 安装 PyInstaller...
    %PYTHON% -m pip install pyinstaller
)

REM 检查 UPX
if "%USE_UPX%"=="true" (
    where upx >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 UPX，将不进行二进制压缩
        echo [提示] 从 https://github.com/upx/upx/releases 下载 UPX 并添加到 PATH
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
set "FILETOOLS_BUILD_MODE=%BUILD_MODE%"

REM 选择 spec 文件
if "%BUILD_MODE%"=="slim" (
    set "SPEC_FILE=file-tools-optimized.spec"
    echo 使用精简模式（排除 tensorflow 等）
) else (
    set "SPEC_FILE=file-tools-optimized.spec"
    echo 使用完整模式
)

REM 构建命令
echo.
echo [4/5] 开始构建...
echo 这可能需要几分钟到几十分钟，请耐心等待...
echo.

set "PYINSTALLER_CMD=pyinstaller %SPEC_FILE% --noconfirm"

if "%USE_UPX%"=="false" (
    set "PYINSTALLER_CMD=%PYINSTALLER_CMD% --upx-dir=NONE"
)

echo 执行: %PYINSTALLER_CMD%
%PYINSTALLER_CMD%

if errorlevel 1 (
    echo.
    echo [错误] 构建失败！
    exit /b 1
)

REM 构建后处理
echo.
echo [5/5] 构建后处理...

REM 创建便携版目录结构
set "DIST_DIR=dist\FileTools"
if not exist "%DIST_DIR%" set "DIST_DIR=dist\FileTools"

if exist "%DIST_DIR%" (
    echo 创建数据目录结构...
    mkdir "%DIST_DIR%\data" 2>nul
    mkdir "%DIST_DIR%\logs" 2>nul

    REM 复制启动脚本
    echo 创建启动脚本...
    (
        echo @echo off
        echo REM File Tools - 便携式启动脚本
        echo.
        echo REM 设置用户数据目录为应用目录（便携模式）
        echo set "FILETOOLS_PORTABLE=1"
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
echo 输出目录: dist\FileTools\
echo.
echo 文件大小统计:
echo ----------------------------------------
for %%f in ("dist\FileTools\*.exe") do (
    echo 主程序: %%~nxf
    for %%a in ("%%f") do (
        set "size=%%~za"
        echo   大小: !size! 字节
    )
)
echo.
if exist "dist\FileTools\_internal" (
    for /f "usebackq" %%a in (`dir /s /-c "dist\FileTools\_internal" 2^>nul ^| findstr "文件(夹)"`) do (
        echo 总计: %%a
    )
)
echo.
echo 使用说明:
echo 1. 将 dist\FileTools\ 目录复制到任意位置
if "%BUILD_TYPE%"=="onefile" (
    echo 2. 直接运行 FileTools.exe（单文件模式）
) else (
    echo 2. 运行 FileTools.exe 或 启动.bat
)
echo 3. 首次运行会自动创建配置文件和数据目录
echo.
echo 配置文件位置:
echo   - Windows: %%APPDATA%%\FileTools\
echo   - 便携模式: 应用目录\data\
echo.

pause
