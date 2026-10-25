"""Install a native app launcher for the current Pi desktop user."""
import argparse
from pathlib import Path
import subprocess


def desktop_quote(value):
    return '"' + str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--autostart", action="store_true", help="start at graphical desktop login")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    entry = ("[Desktop Entry]\nType=Application\nName=RF Sentinel Tablet\n"
             "Comment=Native touchscreen scanner and device console\n"
             f"Exec=bash {desktop_quote(root / 'run-tablet.sh')}\n"
             "Icon=applications-science\nTerminal=false\nCategories=Utility;\n")
    paths = [Path.home() / ".local/share/applications/rf-sentinel-tablet.desktop"]
    try:
        directory = subprocess.check_output(["xdg-user-dir", "DESKTOP"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        directory = str(Path.home() / "Desktop")
    if directory:
        paths.append(Path(directory) / "rf-sentinel-tablet.desktop")
    if args.autostart:
        paths.append(Path.home() / ".config/autostart/rf-sentinel-tablet.desktop")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry, encoding="utf-8")
        path.chmod(0o755)
        print(f"Installed {path}")


if __name__ == "__main__":
    main()
