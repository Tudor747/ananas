"""python -m pi_ot_probe.tablet --check works from SSH; GUI needs the Pi desktop."""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="RF Sentinel native touchscreen app")
    parser.add_argument("--check", action="store_true", help="print dependency checks without starting a window")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--size", metavar="WIDTHxHEIGHT", help="window size for desktop previews")
    parser.add_argument("--nodes", type=Path, default=Path(os.environ.get("RF_SENTINEL_NODES", "data/nodes.json")))
    parser.add_argument("--database", type=Path, default=Path("data/tablet.db"))
    parser.add_argument("--reports", type=Path, default=Path("data/tablet-reports"))
    args = parser.parse_args(argv)
    if args.list_tools:
        from dataclasses import asdict
        from .catalog import TOOLS
        print(json.dumps([asdict(t) for t in TOOLS], indent=2))
        return 0
    if args.check:
        from .diagnostics import dependencies
        checks = dependencies(args.nodes)
        print(json.dumps(checks, indent=2))
        return int(any(c["required"] and not c["ok"] for c in checks))
    size = None
    if args.size:
        try:
            width, height = map(int, args.size.lower().split("x"))
            if min(width, height) < 240:
                raise ValueError
            size = width, height
        except ValueError:
            parser.error("--size needs WIDTHxHEIGHT, each at least 240 pixels")
    try:
        import tkinter as tk
    except ImportError:
        print("Install Tk on the Pi: sudo apt install python3-tk", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot open the desktop: {exc}\nRun from the Pi's graphical desktop, or use --check over SSH.", file=sys.stderr)
        return 1
    from .app import TabletApp
    from .backend import TabletBackend
    try:
        backend = TabletBackend(args.nodes, args.database, args.reports)
    except Exception as exc:
        root.destroy()
        print(f"Cannot start tablet: {exc}", file=sys.stderr)
        return 1
    try:
        TabletApp(root, backend, fullscreen=not args.windowed, size=size)
        root.mainloop()
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
