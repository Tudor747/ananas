"""python -m pi_ot_probe.tablet --check works from SSH; GUI needs the Pi desktop."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import queue
import threading


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
        args.database.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
            handlers=[logging.StreamHandler(), RotatingFileHandler(
                args.database.with_suffix(".log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
        )
    except Exception as exc:
        root.destroy()
        print(f"Cannot start tablet: {exc}", file=sys.stderr)
        return 1
    # Paint before opening the database or starting USB workers. Keep Tk responsive
    # even when an attached device or slow SD card delays backend initialization.
    root.title("RF Sentinel")
    root.configure(bg="#0c1420")
    root.geometry(f"{size[0]}x{size[1]}" if size else "480x320")
    root.attributes("-fullscreen", not args.windowed)
    loading = tk.Label(root, text="Starting tablet...\nPreparing saved ESP connections",
                       bg="#0c1420", fg="#4ee3b3", font=("DejaVu Sans", 14), wraplength=260)
    loading.pack(expand=True, fill="both")
    root.report_callback_exception = lambda kind, value, trace: logging.getLogger(__name__).error(
        "Tk callback failed", exc_info=(kind, value, trace))
    ready = queue.Queue()
    backend = window = None
    abandoned = threading.Event()

    def initialize():
        try:
            instance = TabletBackend(args.nodes, args.database, args.reports)
            ready.put(instance)
            if abandoned.is_set():
                instance.close()
        except Exception as exc:
            logging.exception("Tablet backend startup failed")
            ready.put(exc)

    def finish_startup():
        nonlocal backend, window
        try:
            result = ready.get_nowait()
        except queue.Empty:
            root.after(50, finish_startup)
            return
        if isinstance(result, Exception):
            loading.configure(text=f"Startup failed:\n{result}\nSee data/tablet.log", fg="#ffb5a5")
            return
        backend = result
        try:
            window = TabletApp(root, backend, fullscreen=not args.windowed, size=size)
        except Exception as exc:
            logging.exception("Tablet window startup failed")
            for child in root.winfo_children():
                if child is not loading:
                    child.destroy()
            loading.configure(text=f"Window startup failed:\n{exc}\nSee data/tablet.log", fg="#ffb5a5")
        else:
            loading.destroy()

    threading.Thread(target=initialize, name="tablet-startup", daemon=True).start()
    root.after(50, finish_startup)
    try:
        root.mainloop()
    finally:
        abandoned.set()
        try:
            if window is not None:
                window.close_power_switch()
                window.close_gpio()
        finally:
            if backend is None:
                try:
                    result = ready.get_nowait()
                    backend = result if not isinstance(result, Exception) else None
                except queue.Empty:
                    pass
            if backend is not None:
                backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
