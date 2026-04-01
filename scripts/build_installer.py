#!/usr/bin/env python3
"""
File Tools - NSIS installer build script
Dynamically generates NSIS script and invokes makensis to compile

Usage:
    python scripts/build_installer.py --mode cpu --version 1.0.0
    python scripts/build_installer.py --mode slim
"""

import argparse
import os
import sys
import shutil
import subprocess
from pathlib import Path


def read_version() -> str:
    """Read current version from VERSION file"""
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


def generate_nsis_script(version: str, mode: str, output_dir: str) -> str:
    """Generate NSIS script from template"""
    project_root = Path(__file__).parent.parent
    template_path = project_root / "installer.nsi"
    # Generate script in project root so relative paths (LICENSE, frontend\static\, dist\) resolve correctly
    output_path = project_root / f"installer-{mode}.nsi"

    if not template_path.exists():
        print(f"[ERROR] NSIS template not found: {template_path}")
        sys.exit(1)

    content = template_path.read_text(encoding="utf-8")
    content = content.replace("___VERSION___", version)
    content = content.replace("___MODE___", mode)

    output_path.write_text(content, encoding="utf-8")
    print(f"[OK] NSIS script generated: {output_path}")
    return str(output_path)


def find_nsis() -> str:
    """Find NSIS compiler (makensis)"""
    nsis_paths = [
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
        os.path.expandvars(r"%PROGRAMFILES(x86)%\NSIS\makensis.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\NSIS\makensis.exe"),
    ]

    for path in nsis_paths:
        if os.path.isfile(path):
            return path

    nsis = shutil.which("makensis")
    if nsis:
        return nsis

    return ""


def build_installer(nsis_script: str, version: str, mode: str) -> str:
    """Compile installer with NSIS"""
    nsis_path = find_nsis()
    if not nsis_path:
        print("[ERROR] NSIS (makensis) not found. Install via:")
        print("  Download: https://nsis.sourceforge.io/Download")
        print("  Or: choco install nsis")
        sys.exit(1)

    print(f"[BUILD] Using NSIS: {nsis_path}")
    cmd = [
        nsis_path,
        "/INPUTCHARSET", "UTF8",
        "/OUTPUTCHARSET", "UTF8",
        nsis_script,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] NSIS compile failed:")
        print(result.stderr)
        sys.exit(1)

    # Find generated installer
    project_root = Path(__file__).parent.parent
    pattern = f"filetools_{version}_{mode}_windows_amd64_setup.exe"
    installer_path = project_root / "dist" / pattern

    if installer_path.exists():
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"[OK] Installer: {installer_path} ({size_mb:.1f} MB)")
        return str(installer_path)
    else:
        for f in (project_root / "dist").glob("*_setup.exe"):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"[OK] Installer: {f} ({size_mb:.1f} MB)")
            return str(f)

    print("[WARN] Generated installer not found")
    return ""


def create_portable_archive(version: str, mode: str) -> str:
    """Create portable zip archive"""
    import zipfile

    project_root = Path(__file__).parent.parent
    source_dir = project_root / "dist" / f"FileTools-v{version}-{mode}"

    if not source_dir.exists():
        matches = list((project_root / "dist").glob("FileTools-*"))
        if matches:
            source_dir = matches[0]
        else:
            print(f"[ERROR] Build directory not found")
            return ""

    archive_name = f"filetools_{version}_{mode}_windows_amd64_portable.zip"
    archive_path = project_root / "dist" / archive_name

    print(f"[PACK] Creating portable archive: {archive_name}")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Portable: {archive_path} ({size_mb:.1f} MB)")
    return str(archive_path)


def main():
    parser = argparse.ArgumentParser(description="FileTools Installer Builder")
    parser.add_argument("--mode", choices=["cpu", "gpu", "slim"], default="cpu",
                        help="Build mode (default: cpu)")
    parser.add_argument("--version", default=None,
                        help="Version string (default: read from VERSION file)")
    parser.add_argument("--portable", action="store_true",
                        help="Also create portable zip")
    parser.add_argument("--no-compile", action="store_true",
                        help="Only generate NSIS script, do not compile")

    args = parser.parse_args()

    version = args.version or read_version()
    mode = args.mode

    print(f"\n{'='*50}")
    print(f"File Tools Installer Builder")
    print(f"Version: v{version} | Mode: {mode}")
    print(f"{'='*50}\n")

    # Generate NSIS script
    nsis_script = generate_nsis_script(version, mode, "dist")

    if not args.no_compile:
        build_installer(nsis_script, version, mode)

    if args.portable:
        create_portable_archive(version, mode)

    print("\nDone!")


if __name__ == "__main__":
    main()
