"""Scan lifecycle, safety policy, persistence, and audit coordination."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
from time import perf_counter
from typing import Callable

from pi_ot_probe.analysis.risk_engine import RiskEngine
from pi_ot_probe.core.models import Asset, Finding, Scan, ScanLevel, ScanProgress, ScanStatus, utc_now
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken, ScanCancelled, ScanContext, Scanner


ProgressCallback = Callable[[ScanProgress], None]


@dataclass(slots=True)
class ScanOutcome:
    scan: Scan
    assets: list[Asset]
    findings: list[Finding]


class ScanOrchestrator:
    def __init__(self, repository: Repository, risk_engine: RiskEngine | None = None) -> None:
        self.repository = repository
        self.risk_engine = risk_engine or RiskEngine()

    @staticmethod
    def _enforce_safety(context: ScanContext, scanner: Scanner) -> None:
        if context.level > scanner.maximum_level:
            raise ValueError(
                f"scanner {scanner.name!r} supports levels only through "
                f"{scanner.maximum_level.name}"
            )
        if context.level == ScanLevel.ACTIVE_TEST:
            if not context.authorized:
                raise PermissionError("active testing requires explicit authorization")
            try:
                ipaddress.ip_address(context.target)
            except ValueError as exc:
                raise ValueError("active testing requires one explicitly selected host") from exc

    async def run(
        self,
        *,
        scan: Scan,
        scanner: Scanner,
        cancellation: CancellationToken,
        on_progress: ProgressCallback | None = None,
    ) -> ScanOutcome:
        context = ScanContext(scan.site, scan.target, scan.level, scan.profile, scan.authorized)
        self._enforce_safety(context, scanner)
        self.repository.initialize()
        site_id = self.repository.ensure_site(scan.site, utc_now())
        scan.status = ScanStatus.RUNNING
        scan.started_at = utc_now()
        self.repository.create_scan(scan, site_id)
        start = perf_counter()
        assets: list[Asset] = []
        findings: list[Finding] = []
        error: Exception | None = None
        task_cancellation: asyncio.CancelledError | None = None
        try:
            async for progress in scanner.scan(context, cancellation):
                if progress.asset is not None:
                    asset_findings = self.risk_engine.evaluate(progress.asset)
                    asset_id = self.repository.upsert_asset(site_id, progress.asset)
                    self.repository.link_scan_asset(scan.id, asset_id, progress.asset.last_seen)
                    for finding in asset_findings:
                        self.repository.add_finding(scan.id, asset_id, finding)
                    assets.append(progress.asset)
                    findings.extend(asset_findings)
                if on_progress:
                    on_progress(progress)
            observed_at = utc_now()
            artifacts = scanner.artifacts()
            for access_point in artifacts.access_points:
                self.repository.upsert_access_point(site_id, access_point, observed_at)
            for change in artifacts.changes:
                self.repository.add_change(site_id, scan.id, change, observed_at)
            scan.status = ScanStatus.COMPLETED
        except ScanCancelled as exc:
            scan.status = ScanStatus.CANCELLED
            scan.cancelled = True
            scan.error = str(exc)
        except asyncio.CancelledError as exc:
            scan.status = ScanStatus.CANCELLED
            scan.cancelled = True
            scan.error = "scan task cancelled by operator"
            task_cancellation = exc
        except Exception as exc:
            scan.status = ScanStatus.FAILED
            scan.error = str(exc)
            error = exc
        finally:
            scan.finished_at = utc_now()
            scan.assets_found = len(assets)
            scan.findings_found = len(findings)
            self.repository.update_scan(scan)
            duration_ms = round((perf_counter() - start) * 1000)
            self.repository.add_audit_entry(
                timestamp=scan.finished_at,
                user_action="quick_audit",
                scan=scan,
                result=scan.status.value,
                duration_ms=duration_ms,
                errors=scan.error,
            )
        if error:
            raise error
        if task_cancellation:
            raise task_cancellation
        return ScanOutcome(scan, assets, findings)
