"""
Phase 1: Pull APK from emulator and unzip it.
Run this first. Requires the emulator to be running with the app installed.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import config


def get_apk_path(package: str) -> str:
    """Return on-device APK path for the given package name."""
    result = subprocess.run(
        ["adb", "shell", "pm", "path", package],
        capture_output=True, text=True
    )
    if result.returncode != 0 or "package:" not in result.stdout:
        print(f"✗ App '{package}' not found on device")
        print("  Make sure the emulator is running and the app is installed")
        sys.exit(1)
    return result.stdout.strip().split("package:")[1]


def pull_apk(device_path: str, local_path: Path) -> None:
    """Pull APK from device to local_path."""
    result = subprocess.run(
        ["adb", "pull", device_path, str(local_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"✗ Failed to pull APK: {result.stderr.strip()}")
        sys.exit(1)
    print(f"✓ APK pulled to {local_path}")


def extract_apk(apk_path: Path, extract_dir: Path) -> None:
    """Unzip APK into extract_dir."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk_path, "r") as z:
        z.extractall(extract_dir)
    print(f"✓ APK extracted to {extract_dir}")


def print_asset_tree(extract_dir: Path) -> None:
    """Print a file listing of the assets/ subdirectory."""
    assets_dir = extract_dir / "assets"
    if not assets_dir.exists():
        print("⚠ No assets/ directory found in APK")
        return
    print("\n=== ASSET INVENTORY ===")
    for path in sorted(assets_dir.rglob("*")):
        if path.is_file():
            size = path.stat().st_size
            rel = path.relative_to(extract_dir)
            print(f"  {rel}  ({size:,} bytes)")


def main():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    connected = [l for l in result.stdout.splitlines()[1:] if l.strip() and "offline" not in l]
    if not connected:
        print("✗ No Android emulator/device found")
        print("  Start the emulator and try again: adb devices")
        sys.exit(1)

    device_apk_path = get_apk_path(config.APP_PACKAGE)
    local_apk = Path("paramrut.apk")
    pull_apk(device_apk_path, local_apk)

    extract_dir = Path(config.APK_EXTRACT_DIR)
    extract_apk(local_apk, extract_dir)
    print_asset_tree(extract_dir)
    print(f"\nNext step: run inspect_assets.py")


if __name__ == "__main__":
    main()
