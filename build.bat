@echo off
REM ============================================================
REM File Tools - 多版本构建脚本
REM 支持模式: cpu / gpu / slim
REM 用法: build.bat [cpu|gpu|slim] [noupx] [bump] [installer]
REM 示例: build.bat cpu          - 构建 CPU 版本
REM        build.bat slim noupx  - 构建 Slim 版本(不压缩)
REM        build.bat gpu bump    - 构建 GPU 版本并递增版本号
REM        build.bat cpu installer - 构建并创建安装包
REM ============================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================
echo   File Tools - Multi-Version Build Script
echo ============================================
echo.

set "CURRENT_DIR=%~dp0"
cd /d "%CURRENT_DIR%"

REM ===== 默认参数 =====
set "BUILD_MODE=cpu"
set "USE_UPX=true"
set "BUMP_VERSION=false"
set "CREATE_INSTALLER=false"

REM ===== 解析参数 =====
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="cpu" set "BUILD_MODE=cpu" & shift & goto :parse_args
if /i "%~1"=="gpu" set "BUILD_MODE=gpu" & shift & goto :parse_args
if /i "%~1"=="slim" set "BUILD_MODE=slim" & shift & goto :parse_args
if /i "%~1"=="noupx" set "USE_UPX=false" & shift & goto :parse_args
if /i "%~1"=="bump" set "BUMP_VERSION=true" & shift & goto :parse_args
if /i "%~1"=="installer" set "CREATE_INSTALLER=true" & shift & goto :parse_args
if /i "%~1"=="help" goto :usage
if /i "%~1"=="-h" goto :usage
echo [警告] 未知参数: %~1
shift
goto :parse_args

:args_done

REM ===== 版本号管理 =====
if "%BUMP_VERSION%"=="true" (
    echo [版本] 递增 patch 版本号...
    for /f "tokens=1-3 delims=." %%a in (VERSION) do (
        set /a PATCH=%%c+1
        set "APP_VERSION=%%a.%%b.!PATCH!"
    )
    echo !APP_VERSION! > VERSION
    echo [版本] 新版本: !APP_VERSION!
) else (
    for /f "usebackq" %%i in ("VERSION") do set "APP_VERSION=%%i"
)

echo [配置] 版本号:   v%APP_VERSION%
echo [配置] 构建模式: %BUILD_MODE%
echo [配置] UPX 压缩: %USE_UPX%
echo [配置] 安装包:   %CREATE_INSTALLER%
echo.

REM ===== 选择虚拟环境 =====
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [Python] 使用虚拟环境: .venv
) else (
    set "PYTHON=python.exe"
    echo [Python] 使用系统 Python
)

REM ===== 安装构建依赖 =====
echo.
echo [1/6] 检查构建依赖...
%PYTHON% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [安装] PyInstaller...
    %PYTHON% -m pip install pyinstaller
)

REM ===== 根据构建模式安装运行时依赖 =====
echo.
echo [2/6] 安装运行时依赖...
%PYTHON% -m pip install -e "." 2>nul

if /i "%BUILD_MODE%"=="cpu" (
    echo [模式] CPU 版本 - 安装 AI-CPU 依赖...
    %PYTHON% -m pip install -e ".[ai-cpu]" 2>nul
)
if /i "%BUILD_MODE%"=="gpu" (
    echo [模式] GPU 版本 - 安装 AI-GPU 依赖...
    %PYTHON% -m pip install -e ".[ai-gpu]" 2>nul
)
if /i "%BUILD_MODE%"=="slim" (
    echo [模式] Slim 版本 - 最小化依赖，跳过 AI 库...
)

REM ===== 检查 UPX =====
if "%USE_UPX%"=="true" (
    where upx >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 UPX，跳过二进制压缩
        set "USE_UPX=false"
    ) else (
        echo [OK] UPX 压缩可用
    )
)

REM ===== 清理旧构建 =====
echo.
echo [3/6] 清理旧构建...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM ===== 执行构建 =====
echo.
echo [4/6] 开始构建 FileTools v%APP_VERSION% (%BUILD_MODE%)...
echo.

set "FILETOOLS_VERSION=%APP_VERSION%"
set "FILETOOLS_BUILD_MODE=%BUILD_MODE%"

set "PYINSTALLER_CMD=pyinstaller file-tools.spec --noconfirm --clean"
if "%USE_UPX%"=="false" (
    set "PYINSTALLER_CMD=%PYINSTALLER_CMD% --no-upx"
)

%PYINSTALLER_CMD%

if errorlevel 1 (
    echo.
    echo [错误] 构建失败！
    pause
    exit /b 1
)

REM ===== 构建后处理 =====
echo.
echo [5/6] 构建后处理...

set "DIST_DIR=dist\FileTools-v%APP_VERSION%-%BUILD_MODE%"
if not exist "%DIST_DIR%" (
    for /d %%D in (dist\FileTools*) do (
        set "DIST_DIR=%%D"
        goto :found_dist
    )
)
:found_dist

if exist "%DIST_DIR%" (
    REM 创建必要目录
    mkdir "%DIST_DIR%\data" 2>nul
    mkdir "%DIST_DIR%\data\logs" 2>nul
    mkdir "%DIST_DIR%\data\cache" 2>nul

    REM 写入版本信息
    > "%DIST_DIR%\VERSION.txt" (
        echo %APP_VERSION%
        echo Mode: %BUILD_MODE%
        echo Build: Manual
        echo Date: %date% %time%
        echo Python: 
    )
    %PYTHON% --version >> "%DIST_DIR%\VERSION.txt" 2>&1

    REM 创建启动脚本
    > "%DIST_DIR%\start.bat" (
        echo @echo off
        echo REM File Tools v%APP_VERSION% (%BUILD_MODE%) - Launcher
        echo cd /d "%%~dp0"
        echo start "" "FileTools.exe"
    )

    REM 创建卸载信息
    > "%DIST_DIR%\uninstall.bat" (
        echo @echo off
        echo echo 正在卸载 File Tools v%APP_VERSION%...
        echo rmdir /s /q "%%~dp0data" 2^>nul
        echo del /f /q "%%~dp0config.yaml" 2^>nul
        echo echo 卸载完成（用户数据已清理，程序文件请手动删除）
        echo pause
    )

    echo [OK] 后处理完成
)

REM ===== 统计大小 =====
echo.
echo [6/6] 构建结果统计...
echo ----------------------------------------
set "TOTAL_SIZE=0"
for /r "%DIST_DIR%" %%f in (*) do (
    set /a TOTAL_SIZE+=%%~zf
)
echo 输出目录: %DIST_DIR%\
echo 总大小:   %TOTAL_SIZE% 字节
set /a "TOTAL_MB=%TOTAL_SIZE% / 1048576"
echo           ~%TOTAL_MB% MB
echo ----------------------------------------

REM ===== 创建安装包 =====
if "%CREATE_INSTALLER%"=="true" (
    echo.
    echo [安装包] 开始创建 NSIS 安装程序...
    if exist ".venv\Scripts\python.exe" (
        %PYTHON% scripts/build_installer.py --mode %BUILD_MODE% --version %APP_VERSION%
    ) else (
        python scripts/build_installer.py --mode %BUILD_MODE% --version %APP_VERSION%
    )
)

echo.
echo ============================================
echo   构建完成！ v%APP_VERSION% (%BUILD_MODE%)
echo ============================================
echo.
echo 输出: %DIST_DIR%\
echo.
pause
goto :eof

:usage
echo.
echo 用法: build.bat [模式] [选项]
echo.
echo 模式:
echo   cpu   - CPU 版本 (默认，含完整 AI 功能)
echo   gpu   - GPU 版本 (支持 CUDA 加速)
echo   slim  - Slim 版本 (仅文件搜索，体积最小)
echo.
echo 选项:
echo   noupx       - 禁用 UPX 压缩 (构建更快)
echo   bump        - 递增版本号
echo   installer   - 构建 NSIS 安装包
echo   help        - 显示此帮助
echo.
echo 示例:
echo   build.bat cpu              - 构建 CPU 版本
echo   build.bat slim noupx       - 构建 Slim 版本(无压缩)
echo   build.bat gpu bump         - GPU 版本 + 递增版本
echo   build.bat cpu installer    - CPU 版本 + 安装包
echo.
pause
goto :eof
