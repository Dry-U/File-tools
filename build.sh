#!/usr/bin/env bash
# ============================================================
# File Tools - Linux/macOS 多版本构建脚本
# 用法: ./build.sh [cpu|gpu|slim] [noupx] [bump] [installer]
# ============================================================

set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$CURRENT_DIR"

# ===== 默认参数 =====
BUILD_MODE="cpu"
USE_UPX="true"
BUMP_VERSION="false"
CREATE_INSTALLER="false"

# ===== 解析参数 =====
while [[ $# -gt 0 ]]; do
    case "$1" in
        cpu|gpu|slim) BUILD_MODE="$1"; shift ;;
        noupx)        USE_UPX="false"; shift ;;
        bump)         BUMP_VERSION="true"; shift ;;
        installer)    CREATE_INSTALLER="true"; shift ;;
        help|-h)      echo "用法: ./build.sh [cpu|gpu|slim] [noupx] [bump] [installer]"; exit 0 ;;
        *)            echo "未知参数: $1"; shift ;;
    esac
done

echo ""
echo "============================================"
echo "  File Tools - Multi-Version Build Script"
echo "============================================"
echo ""

# ===== 版本号管理 =====
APP_VERSION=$(cat VERSION 2>/dev/null || echo "1.0.0")

if [[ "$BUMP_VERSION" == "true" ]]; then
    MAJOR=$(echo "$APP_VERSION" | cut -d. -f1)
    MINOR=$(echo "$APP_VERSION" | cut -d. -f2)
    PATCH=$(echo "$APP_VERSION" | cut -d. -f3)
    NEW_PATCH=$((PATCH + 1))
    APP_VERSION="${MAJOR}.${MINOR}.${NEW_PATCH}"
    echo "$APP_VERSION" > VERSION
    echo "[版本] 递增至: v${APP_VERSION}"
fi

echo "[配置] 版本号:   v${APP_VERSION}"
echo "[配置] 构建模式: ${BUILD_MODE}"
echo "[配置] UPX 压缩: ${USE_UPX}"
echo "[配置] 安装包:   ${CREATE_INSTALLER}"
echo ""

# ===== 选择 Python =====
if [[ -f ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
    echo "[Python] 使用虚拟环境: .venv"
else
    PYTHON="python3"
    echo "[Python] 使用系统 Python"
fi

# ===== 安装构建依赖 =====
echo ""
echo "[1/6] 检查构建依赖..."
$PYTHON -c "import PyInstaller" 2>/dev/null || {
    echo "[安装] PyInstaller..."
    $PYTHON -m pip install pyinstaller
}

# ===== 安装运行时依赖 =====
echo ""
echo "[2/6] 安装运行时依赖..."
$PYTHON -m pip install -e "." --quiet 2>/dev/null

case "$BUILD_MODE" in
    cpu)
        echo "[模式] CPU 版本 - 安装 AI-CPU 依赖..."
        $PYTHON -m pip install -e ".[ai-cpu]" --quiet 2>/dev/null || true
        ;;
    gpu)
        echo "[模式] GPU 版本 - 安装 AI-GPU 依赖..."
        $PYTHON -m pip install -e ".[ai-gpu]" --quiet 2>/dev/null || true
        ;;
    slim)
        echo "[模式] Slim 版本 - 最小化依赖..."
        ;;
esac

# ===== 检查 UPX =====
if [[ "$USE_UPX" == "true" ]]; then
    if ! command -v upx &>/dev/null; then
        echo "[警告] 未找到 UPX，跳过压缩"
        USE_UPX="false"
    else
        echo "[OK] UPX 压缩可用"
    fi
fi

# ===== 清理旧构建 =====
echo ""
echo "[3/6] 清理旧构建..."
rm -rf build dist

# ===== 执行构建 =====
echo ""
echo "[4/6] 开始构建 FileTools v${APP_VERSION} (${BUILD_MODE})..."

export FILETOOLS_VERSION="${APP_VERSION}"
export FILETOOLS_BUILD_MODE="${BUILD_MODE}"

PYINSTALLER_CMD="pyinstaller file-tools.spec --noconfirm --clean"
if [[ "$USE_UPX" == "false" ]]; then
    PYINSTALLER_CMD="$PYINSTALLER_CMD --no-upx"
fi

$PYINSTALLER_CMD

# ===== 构建后处理 =====
echo ""
echo "[5/6] 构建后处理..."

DIST_DIR="dist/FileTools-v${APP_VERSION}-${BUILD_MODE}"
if [[ ! -d "$DIST_DIR" ]]; then
    FOUND=$(find dist -maxdepth 1 -type d -name "FileTools*" | head -1)
    if [[ -n "$FOUND" ]]; then
        DIST_DIR="$FOUND"
    fi
fi

if [[ -d "$DIST_DIR" ]]; then
    mkdir -p "$DIST_DIR/data/logs" "$DIST_DIR/data/cache"

    cat > "$DIST_DIR/VERSION.txt" <<EOF
${APP_VERSION}
Mode: ${BUILD_MODE}
Build: Manual
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Python: $($PYTHON --version 2>&1)
EOF

    cat > "$DIST_DIR/start.sh" <<'LAUNCHER'
#!/usr/bin/env bash
cd "$(dirname "$0")"
./FileTools &
LAUNCHER
    chmod +x "$DIST_DIR/start.sh"

    echo "[OK] 后处理完成"
fi

# ===== 统计大小 =====
echo ""
echo "[6/6] 构建结果统计..."
echo "----------------------------------------"
if [[ -d "$DIST_DIR" ]]; then
    TOTAL_SIZE=$(du -sb "$DIST_DIR" 2>/dev/null | cut -f1 || echo 0)
    TOTAL_MB=$((TOTAL_SIZE / 1048576))
    echo "输出目录: ${DIST_DIR}/"
    echo "总大小:   ~${TOTAL_MB} MB"
fi
echo "----------------------------------------"

# ===== 创建安装包 =====
if [[ "$CREATE_INSTALLER" == "true" ]]; then
    echo ""
    echo "[安装包] 创建 tar.gz 归档..."
    ARCHIVE_NAME="FileTools-${BUILD_MODE}-v${APP_VERSION}-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
    cd dist
    tar -czf "../${ARCHIVE_NAME}.tar.gz" "FileTools-v${APP_VERSION}-${BUILD_MODE}"
    cd ..
    echo "[OK] 安装包: ${ARCHIVE_NAME}.tar.gz"
fi

echo ""
echo "============================================"
echo "  构建完成! v${APP_VERSION} (${BUILD_MODE})"
echo "============================================"
