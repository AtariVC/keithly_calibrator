"""Build script: python to_exe.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ENTRY = ROOT / "__main__.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# Data files that must be bundled: (source, dest_inside_bundle)
ADD_DATA: list[tuple[Path, str]] = [
    (ROOT / "gui" / "main_window.ui", "gui"),
    (ROOT / "configs", "configs"),
]


def sep() -> str:
    return ";" if sys.platform == "win32" else ":"


def main() -> None:
    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        str(ENTRY),
        "--name", "keithly-calibrator",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
    ]

    for src, dest in ADD_DATA:
        if not src.exists():
            print(f"[warn] not found, skipping: {src}")
            continue
        cmd += ["--add-data", f"{src}{sep()}{dest}"]

    print("Running PyInstaller:")
    for part in cmd:
        print(" ", part)
    print()

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)

    exe = DIST / ("keithly-calibrator.exe" if sys.platform == "win32" else "keithly-calibrator")
    if exe.exists():
        print(f"\nBuild OK: {exe}")
    else:
        print(f"\nBuild finished but executable not found at expected path: {exe}")


if __name__ == "__main__":
    main()
