"""Command-line entry point for the Phase 1 Quick Audit."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from pi_ot_probe.config.logging import configure_logging
from pi_ot_probe.config.settings import Settings
from pi_ot_probe.core.models import Scan, ScanLevel, ScanProfile
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from pi_ot_probe.simulation.scanner import SimulationScanner
from pi_ot_probe.ui.lcd import MockLCD
from pi_ot_probe.ui.screens import scan_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pi-ot-probe", description="Pi-OT Security Probe")
    subparsers = parser.add_subparsers(dest="command")
    audit = subparsers.add_parser("quick-audit", help="run a bounded discovery audit")
    audit.add_argument("--simulation", action="store_true", help="use synthetic devices; sends no packets")
    audit.add_argument("--scenario", choices=("baseline", "changed"), default="changed")
    audit.add_argument("--site", default="DEMO_SITE")
    audit.add_argument("--profile", choices=[p.value for p in ScanProfile], default="industrial")
    audit.add_argument("--database", type=Path, help="override SQLite path")
    audit.add_argument("--no-lcd", action="store_true", help="disable terminal LCD frames")
    audit.add_argument("--json", action="store_true", help="print the final summary as JSON")
    serve = subparsers.add_parser("serve", help="run the authenticated local engineering API")
    serve.add_argument("--database", type=Path, help="override SQLite path")
    serve.add_argument("--host", help="management bind address")
    serve.add_argument("--port", type=int, help="management TCP port")
    return parser


async def run_quick_audit(args: argparse.Namespace, settings: Settings) -> int:
    simulation = bool(args.simulation or settings.simulation_mode)
    if not simulation:
        print(
            "No real scanner is enabled in this foundation. Use --simulation or "
            "set SIMULATION_MODE=true.",
            file=sys.stderr,
        )
        return 2
    database_path = args.database or settings.database_path
    repository = Repository(database_path)
    scanner = SimulationScanner(args.scenario)
    orchestrator = ScanOrchestrator(repository)
    cancellation = CancellationToken()
    lcd = None if args.no_lcd else MockLCD()
    if lcd:
        lcd.display("QUICK AUDIT", "> START")

    def show_progress(progress: object) -> None:
        if lcd:
            completed = getattr(progress, "completed")
            total = getattr(progress, "total")
            lcd.display(*scan_progress(completed, total))

    scan = Scan(
        site=args.site,
        level=ScanLevel.DISCOVERY,
        profile=ScanProfile(args.profile),
        target="simulation://offline-lab",
        simulation=True,
    )
    try:
        outcome = await orchestrator.run(
            scan=scan, scanner=scanner, cancellation=cancellation, on_progress=show_progress
        )
    except asyncio.CancelledError:
        cancellation.cancel()
        raise
    if lcd:
        lcd.display("AUDIT COMPLETE", f"{len(outcome.assets)} DEVICES")
    summary = {
        "scan_id": outcome.scan.id,
        "status": outcome.scan.status.value,
        "site": outcome.scan.site,
        "simulation": True,
        "scenario": args.scenario,
        "assets": len(outcome.assets),
        "database": str(database_path),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"Quick Audit {summary['status']}: {summary['assets']} raw asset records. "
            f"Database: {database_path}"
        )
    return 0 if outcome.scan.status.value == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    if args.command == "quick-audit":
        try:
            return asyncio.run(run_quick_audit(args, settings))
        except KeyboardInterrupt:
            print("Quick Audit cancelled by operator.", file=sys.stderr)
            return 130
    if args.command == "serve":
        if not settings.api_token:
            print("PI_OT_API_TOKEN is required and must contain at least 32 characters.", file=sys.stderr)
            return 2
        from pi_ot_probe.api.server import create_app
        import uvicorn

        repository = Repository(args.database or settings.database_path)
        repository.initialize()
        app = create_app(repository, settings.api_token)
        uvicorn.run(
            app,
            host=args.host or settings.management_host,
            port=args.port or settings.management_port,
        )
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2
