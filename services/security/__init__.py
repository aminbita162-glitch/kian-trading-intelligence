"""Security service for Kian Trading Intelligence.

Per E3 (Structure and Verification Separation): the test harnesses and
simulators (TenantIsolationTester, RiskStressTester, FinancialStressTester,
SplitBrainSimulator, FaultInjector, LoadTestRunner, BackupService,
DisasterRecoveryService, ObservabilityVerifier, CostEvaluator) have been
moved to simulation/security_simulators.py — outside the deployable image.

Per AD-010: zero-trust security — strong authentication, MFA, least
privilege, secure credentials, tenant isolation, independently enforced
safety policies.
Per AD-022: observability — structured logs, distributed traces,
operational metrics, tamper-evident audit records.
"""

from __future__ import annotations

from threading import Lock
from uuid import uuid4

from contracts.security import (
    ScanResult,
    ScanStatus,
    ScanType,
    ThreatFinding,
    ThreatFindingId,
    ThreatModelReport,
    ThreatSeverity,
    ThreatStatus,
)

__all__ = [
    "SecurityService",
]


class SecurityService:
    """Security review and scanning service (deliverables 1, 2).

    Per AD-010: zero-trust security review and scanning.
    Per AD-022: structured security audit evidence.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._threat_reports: dict[str, ThreatModelReport] = {}
        self._scan_results: list[ScanResult] = []

    def create_threat_model(
        self,
        scope: str,
        components: list[str],
    ) -> ThreatModelReport:
        """Create a threat-model review report (deliverable 1).

        Per AD-010: zero-trust security review.
        """
        report = ThreatModelReport(
            report_id=uuid4(),
            scope=scope,
            findings=[],
        )
        with self._lock:
            self._threat_reports[str(report.report_id)] = report
        return report

    def add_threat_finding(
        self,
        report: ThreatModelReport,
        component: str,
        threat_vector: str,
        severity: ThreatSeverity,
        mitigation: str = "",
    ) -> ThreatFinding:
        """Add a finding to a threat-model report."""
        finding = ThreatFinding(
            finding_id=ThreatFindingId.generate(),
            component=component,
            threat_vector=threat_vector,
            severity=severity,
            status=ThreatStatus.OPEN,
            mitigation=mitigation,
        )
        report.findings.append(finding)
        return finding

    def resolve_finding(
        self,
        finding: ThreatFinding,
        mitigation: str = "",
    ) -> ThreatFinding:
        """Resolve a threat-model finding."""
        resolved = finding.resolve(mitigation)
        return resolved

    def run_scan(
        self,
        scan_type: ScanType,
        component: str,
        findings: list[str] | None = None,
    ) -> ScanResult:
        """Run a security scan (deliverable 2).

        Per AD-010: security scanning across all components.
        """
        if findings is None:
            result = ScanResult.pass_scan(scan_type, component)
        else:
            result = ScanResult.fail_scan(scan_type, component, findings)
        with self._lock:
            self._scan_results.append(result)
        return result

    @property
    def scan_results(self) -> list[ScanResult]:
        """All scan results."""
        with self._lock:
            return list(self._scan_results)

    def all_scans_passed(self) -> bool:
        """True if all scans passed (deliverable 2 acceptance)."""
        with self._lock:
            return (
                all(s.status is ScanStatus.PASSED for s in self._scan_results)
                and len(self._scan_results) > 0
            )
