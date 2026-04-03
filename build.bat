@echo off
REM ============================================================
REM File Tools - Nuitka 构建脚本
REM 使用 Nuitka 将 Python 编译为 C，再编译为独立可执行文件
REM 支持模式: slim / cpu / gpu
REM 用法: build_nuitka.bat [slim|cpu|gpu] [installer] [clean]
REM 示例: build_nuitka.bat slim        - 构建 Slim 版本
REM        build_nuitka.bat cpu        - 构建 CPU 版本
REM        build_nuitka.bat gpu        - 构建 GPU 版本
REM        build_nuitka.bat cpu installer - 构建并创建安装包
REM ============================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================
echo   File Tools - Nuitka Build Script
echo ============================================
echo.

set "CURRENT_DIR=%~dp0"
cd /d "%CURRENT_DIR%"

REM ===== 默认参数 =====
set "BUILD_MODE=slim"
set "CREATE_INSTALLER=false"
set "CLEAN_BUILD=false"
set "BUILD_TOOL=nuitka"

REM ===== 解析参数 =====
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="slim" set "BUILD_MODE=slim" & shift & goto :parse_args
if /i "%~1"=="cpu" set "BUILD_MODE=cpu" & shift & goto :parse_args
if /i "%~1"=="gpu" set "BUILD_MODE=gpu" & shift & goto :parse_args
if /i "%~1"=="installer" set "CREATE_INSTALLER=true" & shift & goto :parse_args
if /i "%~1"=="clean" set "CLEAN_BUILD=true" & shift & goto :parse_args
if /i "%~1"=="help" goto :usage
if /i "%~1"=="-h" goto :usage
echo [警告] 未知参数: %~1
shift
goto :parse_args

:args_done

REM ===== 读取版本号 =====
if exist "VERSION" (
    for /f "usebackq" %%i in ("VERSION") do set "APP_VERSION=%%i"
) else (
    set "APP_VERSION=1.0.0"
)

echo [配置] 版本号:   v%APP_VERSION%
echo [配置] 构建模式: %BUILD_MODE%
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
echo [1/5] 检查构建依赖...

%PYTHON% -c "import nuitka" 2>nul
if errorlevel 1 (
    echo [安装] Nuitka...
    %PYTHON% -m pip install nuitka
)

REM ===== 清理旧构建 =====
echo.
echo [2/5] 清理旧构建...
if "%CLEAN_BUILD%"=="true" (
    if exist "dist" rmdir /s /q "dist"
    echo [OK] 已清理 dist 目录
)

REM ===== 执行 Nuitka 构建 =====
echo.
echo [3/5] 开始 Nuitka 编译 (Mode: %BUILD_MODE%)...
echo.

set "FILETOOLS_VERSION=%APP_VERSION%"
set "FILETOOLS_BUILD_MODE=%BUILD_MODE%"
set "PYTHONPATH=%CD%"

REM 调用 Python 构建脚本
%PYTHON% scripts\build_nuitka.py %BUILD_MODE%

if errorlevel 1 (
    echo.
    echo [错误] Nuitka 构建失败！
    pause
    exit /b 1
)

REM ===== 构建后处理 =====
echo.
echo [4/5] 构建后处理...

set "DIST_DIR=dist\main.dist"
if not exist "%DIST_DIR%" (
    for /d %%D in (dist\main*) do (
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
    mkdir "%DIST_DIR%\data\tantivy_index" 2>nul
    mkdir "%DIST_DIR%\data\hnsw_index" 2>nul

    REM 写入版本信息
    > "%DIST_DIR%\VERSION.txt" (
        echo %APP_VERSION%
        echo Mode: %BUILD_MODE%
        echo Builder: Nuitka
        echo Date: %date% %time%
    )

    REM 创建启动脚本
    > "%DIST_DIR%\start.bat" (
        echo @echo off
        echo cd /d "%%~dp0"
        echo start "" main.exe
    )

    echo [OK] 后处理完成
)

REM ===== 创建安装包 =====
if "%CREATE_INSTALLER%"=="true" (
    echo.
    echo [5/5] 创建 Inno Setup 安装包...

    REM 检查 Inno Setup
    where iscc >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 Inno Setup，尝试默认路径...
        if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
            set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        ) else (
            echo [错误] 请安装 Inno Setup 6: https://jrsoftware.org/isdl.php
            goto :skip_installer
        )
    ) else (
        set "ISCC=iscc"
    )

    mkdir dist\installer 2>nul
    "%ISCC%" scripts\build_inno_setup.iss

    if errorlevel 1 (
        echo [错误] 安装包创建失败！
    ) else (
        echo [OK] 安装包已创建: dist\installer\FileTools-%APP_VERSION%-win64-setup.exe
    )
)
:skip_installer

REM ===== 统计大小 =====
echo.
echo ===== 构建结果统计 =====
echo ----------------------------------------
set "TOTAL_SIZE=0"
set "FILE_COUNT=0"
for /r "%DIST_DIR%" %%f in (*) do (
    set /a TOTAL_SIZE+=%%~zf
    set /a FILE_COUNT+=1
)
echo 输出目录: %DIST_DIR%\
set /a "TOTAL_MB=%TOTAL_SIZE% / 1048576"
echo 总大小:   ~%TOTAL_MB% MB
echo 文件数量: %FILE_COUNT%
echo ----------------------------------------

REM ===== 显示最大文件 =====
echo.
echo [分析] 体积最大的文件 (Top 10):
powershell -command "Get-ChildItem -Path '%DIST_DIR%' -Recurse -File | Sort-Object Length -Descending | Select-Object -First 10 @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}}, FullName | Format-Table -AutoSize"

echo.
echo ============================================
echo   构建完成！ v%APP_VERSION% (%BUILD_MODE%)
echo ============================================
echo.
if "%CREATE_INSTALLER%"=="true" (
    echo 安装包: dist\installer\FileTools-%APP_VERSION%-win64-setup.exe
    echo.
)
echo 输出: %DIST_DIR%\
echo.
pause
goto :eof

:usage
echo.
echo 用法: build_nuitka.bat [模式] [选项]
echo.
echo 模式:
echo   slim  - Slim 版本 (仅文件搜索，体积最小) [默认]
echo   cpu   - CPU 版本 (含完整 AI 功能)
echo   gpu   - GPU 版本 (支持 CUDA 加速)
echo.
echo 选项:
echo   installer   - 构建 Inno Setup 安装包
echo   clean       - 清理旧构建
echo   help        - 显示此帮助
echo.
echo 示例:
echo   build_nuitka.bat slim         - 构建 Slim 版本
echo   build_nuitka.bat cpu installer - 构建 CPU 版本 + 安装包
echo   build_nuitka.bat gpu clean    - 清理并构建 GPU 版本
echo.
pause
goto :eof
