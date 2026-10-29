"""Package tablet updates and node A source; exclude data, firmware binaries and venvs."""
from pathlib import Path
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    paths = [root / name for name in (
        "pyproject.toml", "run-tablet.sh", "scripts/setup-tablet.sh",
        "scripts/install-tablet-desktop.py", "scripts/build-tablet-update.py",
        "docs/tablet-app.md", "docs/wifi-bwifikiller-parity.md",
        "README.md", "docs/usage.md", "BWifiKiller/README.md",
        "tests/test_tablet.py", "tests/test_peripherals.py", "tests/test_sentinel_firmware.py",
        "firmware/src/node_a.cpp", "docs/development.md", "docs/sentinel-integration.md",
        "firmware/platformio.ini", "firmware/build_identity.py", "firmware/README.md",
        "firmware/src/node_b.cpp", "firmware/src/node_c.cpp",
        "BWifiKiller/platformio.ini", "BWifiKiller/include/app_config.h",
        "BWifiKiller/include/wifi_observation.h", "BWifiKiller/src/sentinel_main.cpp", "BWifiKiller/LICENSE",
        "BWifiKiller/src/wifiscan.cpp", "BWifiKiller/src/wifi_channel_scan.cpp", "BWifiKiller/src/wifi_radar.cpp",
        "src/pi_ot_probe/collectors/wifi.py", "tests/test_wifi_views.py",
        "tests/test_gpio_navigation.py", "tests/test_tablet_results.py", "tests/web/test_wifi_and_reports.py",
        "tests/conftest.py", "docs/scan-results-audit.md",
    )]
    paths.extend(sorted((root / "firmware/include").glob("*.h")))
    paths.extend(sorted((root / "src/pi_ot_probe/tablet").glob("*.py")))
    paths.extend(sorted((root / "src/pi_ot_probe/peripherals").glob("*.py")))
    destination = root / "dist/rf-sentinel-tablet-update.tar.gz"
    destination.parent.mkdir(exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        for path in paths:
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    with tarfile.open(destination, "r:gz") as archive:
        assert len(archive.getmembers()) == len(paths)
        for member, path in zip(archive.getmembers(), paths):
            assert member.isfile() and not member.name.startswith("/") and ".." not in Path(member.name).parts
            assert archive.extractfile(member).read() == path.read_bytes()
    print(f"Created {destination} ({len(paths)} files, {destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
