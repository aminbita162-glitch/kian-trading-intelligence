"""Evidence and assurance services for Kian Trading Intelligence.

Per E8 (Evidence and Assurance):

Hash-chained decision ledger, per-trade decision dossiers, OpenTelemetry-style
instrumentation (simulated), SLO burn-rate monitoring, living threat model,
CycloneDX SBOM generation, SLSA provenance builder, Sigstore-style signing
(HMAC-SHA256 simulated), API fuzzing, CI badge generation, verifier CLI, and
game-day drill runner.

All classes are thread-safe (threading.Lock) and follow the pattern from
services.strategy_science.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import string
import threading
from datetime import UTC, datetime
from typing import Any

from contracts.evidence import (
    Badge,
    BadgeColor,
    DecisionDossier,
    DossierId,
    DrillId,
    DrillStatus,
    DrillStep,
    FuzzEndpoint,
    FuzzReport,
    FuzzResult,
    FuzzStatus,
    GameDayRecord,
    LedgerEntry,
    LedgerEntryId,
    MetricRecord,
    OTelConfig,
    SBOMComponent,
    SBOMDocument,
    SigningResult,
    SLOAlert,
    SLOAlertLevel,
    SLOBurnRateResult,
    SLODefinition,
    SLORequest,
    SLSABuildInfo,
    SLSAMaterial,
    SLSAProvenance,
    SpanKind,
    SpanRecord,
    ThreatModelEntry,
    ThreatModelEntryId,
    ThreatModelReport,
    ThreatSeverity,
    ThreatStatus,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
)

# ── Decision Ledger ───────────────────────────────────────────────


class DecisionLedger:
    """Hash-chained append-only decision ledger (thread-safe).

    Each entry links to the previous entry's hash, forming a tamper-evident
    chain. Any insertion, deletion, or modification breaks the chain and is
    detectable by verify_chain().

    Attributes:
        _entries: List of ledger entries (in append order).
        _dossiers: Dict of trade_id -> list of entries for that trade.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._dossiers: dict[str, list[LedgerEntry]] = {}
        self._lock = threading.Lock()

    def record_entry(
        self,
        trade_id: str,
        decision_type: str,
        payload: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """Record a new decision entry and return it."""
        with self._lock:
            previous_hash = "genesis"
            if self._entries:
                previous_hash = self._entries[-1].entry_hash
            entry = LedgerEntry(
                entry_id=LedgerEntryId.generate(),
                trade_id=trade_id,
                decision_type=decision_type,
                payload=payload or {},
                previous_hash=previous_hash,
            )
            self._entries.append(entry)
            if trade_id not in self._dossiers:
                self._dossiers[trade_id] = []
            self._dossiers[trade_id].append(entry)
            return entry

    def get_entries(self) -> list[LedgerEntry]:
        """Return all entries (thread-safe copy)."""
        with self._lock:
            return list(self._entries)

    def get_entries_for_trade(self, trade_id: str) -> list[LedgerEntry]:
        """Return all entries for a given trade_id (thread-safe copy)."""
        with self._lock:
            return list(self._dossiers.get(trade_id, []))

    def get_dossiers(self) -> dict[str, list[LedgerEntry]]:
        """Return all dossiers keyed by trade_id (thread-safe copy)."""
        with self._lock:
            return {k: list(v) for k, v in self._dossiers.items()}

    def anchor_external(self, url: str) -> bool:
        """Anchor the current ledger state to an external timestamping service.

        Sets the external_anchor field on the latest entry and returns True
        if successful (simulated — always succeeds if there is at least one
        entry).
        """
        with self._lock:
            if not self._entries:
                return False
            last = self._entries[-1]
            # LedgerEntry is not frozen, so we can set the attribute
            last.external_anchor = url
            return True

    def verify_chain(self) -> bool:
        """Verify the integrity of the hash chain.

        Walks every entry, checking that each entry's previous_hash matches
        the hash of the preceding entry. Returns True only if the entire
        chain is intact.
        """
        with self._lock:
            expected = "genesis"
            for entry in self._entries:
                if entry.previous_hash != expected:
                    return False
                # Recompute the entry hash to detect tampering
                recomputed = entry._compute_hash()
                if recomputed != entry.entry_hash:
                    return False
                expected = entry.entry_hash
            return True

    @property
    def count(self) -> int:
        """Number of entries in the ledger."""
        with self._lock:
            return len(self._entries)

    def reset(self) -> None:
        """Reset the ledger (for testing)."""
        with self._lock:
            self._entries.clear()
            self._dossiers.clear()


# ── Decision Dossier Builder ──────────────────────────────────────


class DecisionDossierBuilder:
    """Builds per-trade decision dossiers from ledger entries.

    Attributes:
        _ledger: The decision ledger to read from.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self, ledger: DecisionLedger) -> None:
        self._ledger = ledger
        self._lock = threading.Lock()

    def build_dossier(self, trade_id: str) -> DecisionDossier | None:
        """Build a decision dossier for a given trade_id.

        Returns a DecisionDossier or None if no entries exist for the trade.
        """
        with self._lock:
            entries = self._ledger.get_entries_for_trade(trade_id)
            if not entries:
                return None
            summary = {
                "trade_id": trade_id,
                "entry_count": len(entries),
                "decision_types": [e.decision_type for e in entries],
                "first_timestamp": entries[0].timestamp.isoformat(),
                "last_timestamp": entries[-1].timestamp.isoformat(),
            }
            return DecisionDossier(
                dossier_id=DossierId.generate(),
                trade_id=trade_id,
                entries=list(entries),
                summary=summary,
            )

    def build_all_dossiers(self) -> list[DecisionDossier]:
        """Build dossiers for all trades in the ledger."""
        with self._lock:
            dossiers: list[Any] = []
            for trade_id, entries in self._ledger.get_dossiers().items():
                if not entries:
                    continue
                summary = {
                    "trade_id": trade_id,
                    "entry_count": len(entries),
                    "decision_types": [e.decision_type for e in entries],
                    "first_timestamp": entries[0].timestamp.isoformat(),
                    "last_timestamp": entries[-1].timestamp.isoformat(),
                }
                dossiers.append(
                    DecisionDossier(
                        dossier_id=DossierId.generate(),
                        trade_id=trade_id,
                        entries=list(entries),
                        summary=summary,
                    ),
                )
            return dossiers


# ── OpenTelemetry-style Instrumentation ───────────────────────────


class OpenTelemetryInstrumentor:
    """OpenTelemetry-style instrumentation setup (simulated, not real OTel SDK).

    Provides span and metric recording. No real OTel SDK is used — this is a
    lightweight simulated instrumentation suitable for evidence collection.

    Attributes:
        _config: OTel configuration.
        _spans: List of recorded spans.
        _metrics: List of recorded metrics.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self, config: OTelConfig | None = None) -> None:
        self._config = config or OTelConfig()
        self._spans: list[SpanRecord] = []
        self._metrics: list[MetricRecord] = []
        self._lock = threading.Lock()

    @property
    def config(self) -> OTelConfig:
        """Return the OTel configuration."""
        return self._config

    def setup(self) -> OTelConfig:
        """Set up instrumentation and return the configuration.

        This is a no-op in the simulated implementation — it simply returns
        the current configuration. In a real deployment this would configure
        exporters, samplers, and resource attributes.
        """
        return self._config

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> SpanRecord:
        """Start a new span and return it (not yet ended)."""
        with self._lock:
            span = SpanRecord(
                span_id=hashlib.sha256(
                    f"{name}{datetime.now(UTC).isoformat()}{len(self._spans)}".encode(),
                ).hexdigest()[:16],
                trace_id=hashlib.sha256(
                    f"trace-{datetime.now(UTC).isoformat()}".encode(),
                ).hexdigest()[:32],
                parent_span_id=parent_span_id,
                name=name,
                kind=kind,
                attributes=attributes or {},
            )
            self._spans.append(span)
            return span

    def end_span(self, span: SpanRecord, status: str = "ok") -> SpanRecord:
        """End a span by setting its end_time and status."""
        with self._lock:
            span.end_time = datetime.now(UTC)
            span.status = status
            return span

    def record_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        status: str = "ok",
    ) -> SpanRecord:
        """Record a complete span (start + end) in one call."""
        span = self.start_span(name, kind=kind, attributes=attributes)
        return self.end_span(span, status=status)

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "1",
        attributes: dict[str, Any] | None = None,
    ) -> MetricRecord:
        """Record a metric value."""
        with self._lock:
            metric = MetricRecord(
                name=name,
                value=value,
                unit=unit,
                attributes=attributes or {},
            )
            self._metrics.append(metric)
            return metric

    def get_spans(self) -> list[SpanRecord]:
        """Return all recorded spans (thread-safe copy)."""
        with self._lock:
            return list(self._spans)

    def get_metrics(self) -> list[MetricRecord]:
        """Return all recorded metrics (thread-safe copy)."""
        with self._lock:
            return list(self._metrics)

    def reset(self) -> None:
        """Reset all recorded spans and metrics (for testing)."""
        with self._lock:
            self._spans.clear()
            self._metrics.clear()


# ── SLO Monitor ───────────────────────────────────────────────────


class SLOMonitor:
    """SLO monitoring with burn-rate calculation (thread-safe).

    burn_rate = error_rate / error_budget
    where error_budget = 1 - target_slo_fraction

    When burn_rate > 1.0, the SLO is being consumed faster than allowed
    and an alert is generated.

    Attributes:
        _slos: Dict of slo_name -> SLODefinition.
        _requests: Dict of slo_name -> list of SLORequest.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._slos: dict[str, SLODefinition] = {}
        self._requests: dict[str, list[SLORequest]] = {}
        self._lock = threading.Lock()

    def register_slo(self, slo: SLODefinition) -> None:
        """Register an SLO definition."""
        with self._lock:
            self._slos[slo.name] = slo
            if slo.name not in self._requests:
                self._requests[slo.name] = []

    def record_request(
        self,
        slo_name: str,
        success: bool,
        latency_ms: float = 0.0,
    ) -> SLORequest:
        """Record a request observation for an SLO."""
        with self._lock:
            if slo_name not in self._slos:
                raise ValueError(f"SLO '{slo_name}' is not registered.")
            req = SLORequest(
                slo_name=slo_name,
                success=success,
                latency_ms=latency_ms,
            )
            self._requests[slo_name].append(req)
            return req

    def check_burn_rate(
        self,
        slo_name: str,
        window: int | None = None,
    ) -> SLOBurnRateResult:
        """Calculate the burn rate for an SLO over a given window.

        Args:
            slo_name: SLO name.
            window: Window in seconds (defaults to the SLO's configured window).

        Returns:
            SLOBurnRateResult with error_rate, error_budget, burn_rate, and
            alerting flag.
        """
        with self._lock:
            slo = self._slos.get(slo_name)
            if slo is None:
                raise ValueError(f"SLO '{slo_name}' is not registered.")
            w = window or slo.window
            requests = self._requests.get(slo_name, [])
            # Filter to the window (most recent w seconds)
            now = datetime.now(UTC)
            cutoff = datetime.fromtimestamp(now.timestamp() - w, tz=UTC)
            recent = [r for r in requests if r.timestamp >= cutoff]
            if not recent:
                return SLOBurnRateResult(
                    slo_name=slo_name,
                    error_rate=0.0,
                    error_budget=slo.error_budget,
                    burn_rate=0.0,
                    alerting=False,
                    window_seconds=w,
                )
            error_count = sum(1 for r in recent if not r.success)
            error_rate = error_count / len(recent)
            error_budget = slo.error_budget
            burn_rate = error_rate / error_budget if error_budget > 0 else 0.0
            return SLOBurnRateResult(
                slo_name=slo_name,
                error_rate=error_rate,
                error_budget=error_budget,
                burn_rate=burn_rate,
                alerting=burn_rate > 1.0,
                window_seconds=w,
            )

    def get_alerts(self) -> list[SLOAlert]:
        """Return alerts for all SLOs with burn_rate > 1.0.

        This method does NOT call check_burn_rate (which would re-acquire
        the lock and deadlock). Instead it inlines the burn-rate computation.
        """
        with self._lock:
            alerts: list[SLOAlert] = []
            for name, slo in self._slos.items():
                requests = self._requests.get(name, [])
                now = datetime.now(UTC)
                cutoff = datetime.fromtimestamp(now.timestamp() - slo.window, tz=UTC)
                recent = [r for r in requests if r.timestamp >= cutoff]
                if not recent:
                    continue
                error_count = sum(1 for r in recent if not r.success)
                error_rate = error_count / len(recent)
                error_budget = slo.error_budget
                burn_rate = error_rate / error_budget if error_budget > 0 else 0.0
                _BURN_RATE_ALERT_THRESHOLD = 1.0
                _BURN_RATE_CRITICAL_THRESHOLD = 2.0
                if burn_rate > _BURN_RATE_ALERT_THRESHOLD:
                    level = (
                        SLOAlertLevel.CRITICAL
                        if burn_rate > _BURN_RATE_CRITICAL_THRESHOLD
                        else SLOAlertLevel.WARNING
                    )
                    alerts.append(
                        SLOAlert(
                            slo_name=name,
                            level=level,
                            burn_rate=burn_rate,
                            message=(
                                f"SLO '{name}' burn rate {burn_rate:.2f} "
                                f"exceeds budget (error_rate={error_rate:.4f})"
                            ),
                        ),
                    )
            return alerts

    @property
    def slo_count(self) -> int:
        """Number of registered SLOs."""
        with self._lock:
            return len(self._slos)

    def reset(self) -> None:
        """Reset all SLOs and requests (for testing)."""
        with self._lock:
            self._slos.clear()
            self._requests.clear()


# ── Threat Model Manager ──────────────────────────────────────────


class ThreatModelManager:
    """Living threat model management (thread-safe).

    Maintains a living, continuously-updated threat model. Entries can be
    added, updated, and queried. The full model can be exported as a report.

    Attributes:
        _entries: Dict of entry_id -> ThreatModelEntry.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ThreatModelEntry] = {}
        self._lock = threading.Lock()

    def add_entry(  # noqa: PLR0913, PLR0917
        self,
        component: str,
        threat: str,
        severity: ThreatSeverity = ThreatSeverity.MEDIUM,
        status: ThreatStatus = ThreatStatus.OPEN,
        mitigation: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ThreatModelEntry:
        """Add a new threat model entry."""
        with self._lock:
            if not isinstance(severity, ThreatSeverity):
                severity = ThreatSeverity(severity)
            if not isinstance(status, ThreatStatus):
                status = ThreatStatus(status)
            entry = ThreatModelEntry(
                entry_id=ThreatModelEntryId.generate(),
                component=component,
                threat=threat,
                severity=severity,
                status=status,
                mitigation=mitigation,
                metadata=metadata or {},
            )
            self._entries[str(entry.entry_id)] = entry
            return entry

    def update_entry(
        self,
        entry_id: str,
        *,
        severity: ThreatSeverity | None = None,
        status: ThreatStatus | None = None,
        mitigation: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ThreatModelEntry | None:
        """Update an existing threat model entry.

        Returns the updated entry, or None if the entry was not found.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            if severity is not None:
                entry.severity = (
                    ThreatSeverity(severity)
                    if not isinstance(severity, ThreatSeverity)
                    else severity
                )
            if status is not None:
                entry.status = (
                    ThreatStatus(status) if not isinstance(status, ThreatStatus) else status
                )
            if mitigation is not None:
                entry.mitigation = mitigation
            if metadata is not None:
                entry.metadata = metadata
            entry.updated_at = datetime.now(UTC)
            return entry

    def get_model(self) -> list[ThreatModelEntry]:
        """Return all threat model entries (thread-safe copy)."""
        with self._lock:
            return list(self._entries.values())

    def get_entry(self, entry_id: str) -> ThreatModelEntry | None:
        """Return a single entry by ID."""
        with self._lock:
            return self._entries.get(entry_id)

    def export(self) -> ThreatModelReport:
        """Export the full threat model as a report."""
        with self._lock:
            entries = list(self._entries.values())
            by_severity: dict[str, int] = {}
            by_status: dict[str, int] = {}
            open_count = 0
            for e in entries:
                sev = (
                    e.severity.value if isinstance(e.severity, ThreatSeverity) else str(e.severity)
                )
                by_severity[sev] = by_severity.get(sev, 0) + 1
                st = e.status.value if isinstance(e.status, ThreatStatus) else str(e.status)
                by_status[st] = by_status.get(st, 0) + 1
                if e.status in (ThreatStatus.OPEN, "open"):
                    open_count += 1
            return ThreatModelReport(
                entries=entries,
                total=len(entries),
                open_count=open_count,
                by_severity=by_severity,
                by_status=by_status,
            )

    @property
    def count(self) -> int:
        """Number of threat model entries."""
        with self._lock:
            return len(self._entries)

    def reset(self) -> None:
        """Reset the threat model (for testing)."""
        with self._lock:
            self._entries.clear()


# ── SBOM Generator ────────────────────────────────────────────────


class SBOMGenerator:
    """CycloneDX SBOM generation (thread-safe).

    Generates a Software Bill of Materials in CycloneDX format. Components
    can be added manually or parsed from a pyproject.toml dependencies file.

    Attributes:
        _components: List of SBOM components.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._components: list[SBOMComponent] = []
        self._lock = threading.Lock()

    def add_component(
        self,
        name: str,
        version: str,
        component_type: str = "library",
        purl: str = "",
        supplier: str = "",
    ) -> SBOMComponent:
        """Add a component to the SBOM."""
        with self._lock:
            if not purl:
                purl = f"pkg:pypi/{name}@{version}"
            component = SBOMComponent(
                name=name,
                version=version,
                type=component_type,
                purl=purl,
                bom_ref=f"pkg:pypi/{name}@{version}",
                supplier=supplier,
            )
            self._components.append(component)
            return component

    def from_dependencies(self, pyproject_path: str) -> list[SBOMComponent]:
        """Parse dependencies from a pyproject.toml file.

        Reads the [project.dependencies] and [tool.poetry.dependencies] /
        [tool.poetry.group.*.dependencies] sections and creates SBOMComponents
        for each.
        """
        with self._lock:
            if not os.path.exists(pyproject_path):
                return []
            try:
                import tomllib  # noqa: PLC0415
            except ImportError:
                import tomli as tomllib  # type: ignore[import-not-found,no-redef]  # noqa: PLC0415

            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)

            components: list[SBOMComponent] = []

            # Standard [project.dependencies]
            project = data.get("project", {})
            for dep in project.get("dependencies", []):
                name, version = self._parse_dependency(dep)
                comp = SBOMComponent(
                    name=name,
                    version=version,
                    purl=f"pkg:pypi/{name}@{version}",
                    bom_ref=f"pkg:pypi/{name}@{version}",
                )
                components.append(comp)

            # Poetry [tool.poetry.dependencies]
            tool = data.get("tool", {})
            poetry = tool.get("poetry", {})
            for dep_name, dep_spec in poetry.get("dependencies", {}).items():
                if dep_name == "python":
                    continue
                version = self._parse_poetry_spec(dep_spec)
                comp = SBOMComponent(
                    name=dep_name,
                    version=version,
                    purl=f"pkg:pypi/{dep_name}@{version}",
                    bom_ref=f"pkg:pypi/{dep_name}@{version}",
                )
                components.append(comp)

            self._components.extend(components)
            return components

    @staticmethod
    def _parse_dependency(dep: str) -> tuple[str, str]:
        """Parse a PEP 508 dependency string into (name, version)."""
        dep = dep.strip()
        for sep in (">=", "<=", "==", "~=", ">", "<", "!="):
            if sep in dep:
                parts = dep.split(sep, 1)
                name = parts[0].strip().replace("[", "").replace("]", "")
                version = parts[1].strip().split(",")[0].strip()
                # Strip extras and markers
                version = version.split(";")[0].strip()
                return name, version
        return dep.replace("[", "").replace("]", ""), "0.0.0"

    @staticmethod
    def _parse_poetry_spec(spec: Any) -> str:
        """Parse a poetry dependency specification into a version string."""
        if isinstance(spec, str):
            return spec
        if isinstance(spec, dict):
            version = spec.get("version", "0.0.0")
            if isinstance(version, str):
                for prefix in ("^", "~", ">=", "<=", "=="):
                    if version.startswith(prefix):
                        return version[len(prefix) :]
                return version
        return "0.0.0"

    def generate_sbom(
        self,
        service_name: str = "kian-trading-intelligence",
        service_version: str = "0.1.0",
    ) -> SBOMDocument:
        """Generate a CycloneDX SBOM document from registered components."""
        with self._lock:
            # Always include the application itself as the first component
            app_component = SBOMComponent(
                name=service_name,
                version=service_version,
                type="application",
                purl=f"pkg:pypi/{service_name}@{service_version}",
                bom_ref=f"pkg:pypi/{service_name}@{service_version}",
            )
            all_components = [app_component] + list(self._components)
            return SBOMDocument(
                components=all_components,
                metadata={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "tools": [
                        {
                            "name": "kian-sbom-generator",
                            "version": "1.0.0",
                        },
                    ],
                    "component": {
                        "name": service_name,
                        "version": service_version,
                        "type": "application",
                    },
                },
            )

    def get_components(self) -> list[SBOMComponent]:
        """Return all registered components (thread-safe copy)."""
        with self._lock:
            return list(self._components)

    def reset(self) -> None:
        """Reset the SBOM generator (for testing)."""
        with self._lock:
            self._components.clear()


# ── SLSA Provenance Builder ───────────────────────────────────────


class SLSAProvenanceBuilder:
    """SLSA provenance builder (thread-safe).

    Builds a provenance statement with build info, materials, and a hash.
    The provenance hash covers all fields and is tamper-evident.

    Attributes:
        _build_info: Build information.
        _materials: List of materials.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._build_info: SLSABuildInfo = SLSABuildInfo()
        self._materials: list[SLSAMaterial] = []
        self._lock = threading.Lock()

    def set_build_info(self, build_info: SLSABuildInfo) -> None:
        """Set the build information for the provenance statement."""
        with self._lock:
            self._build_info = build_info

    def add_material(self, uri: str, digest: dict[str, str] | None = None) -> SLSAMaterial:
        """Add a material (input artifact) to the provenance statement."""
        with self._lock:
            material = SLSAMaterial(uri=uri, digest=digest or {})
            self._materials.append(material)
            return material

    def build(
        self,
        subject_uri: str = "",
        subject_digest: dict[str, str] | None = None,
        slsa_level: int = 1,
    ) -> SLSAProvenance:
        """Build the SLSA provenance statement."""
        with self._lock:
            digest_str = json.dumps(subject_digest or {}, sort_keys=True)
            subject: dict[str, str] = {"uri": subject_uri, "digest": digest_str}
            return SLSAProvenance(
                build_info=self._build_info,
                materials=list(self._materials),
                subject=subject,
                slsa_level=slsa_level,
            )

    def verify(self, provenance: SLSAProvenance) -> bool:
        """Verify a provenance statement by recomputing its hash."""
        with self._lock:
            expected_hash = provenance._compute_hash()
            return bool(expected_hash == provenance.provenance_hash)

    def get_materials(self) -> list[SLSAMaterial]:
        """Return all registered materials (thread-safe copy)."""
        with self._lock:
            return list(self._materials)

    def reset(self) -> None:
        """Reset the builder (for testing)."""
        with self._lock:
            self._build_info = SLSABuildInfo()
            self._materials.clear()


# ── Sigstore Signer ───────────────────────────────────────────────


class SigstoreSigner:
    """Sigstore-style signing (HMAC-SHA256 simulated, thread-safe).

    Uses HMAC-SHA256 with a configurable secret key to simulate artifact
    signing. In production this would use the real Sigstore / cosign
    infrastructure with Fulcio certificates and Rekor transparency logs.

    Attributes:
        _secret: HMAC secret key (bytes).
        _lock: Thread lock for concurrent access.
    """

    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret or os.urandom(32)
        self._lock = threading.Lock()

    def sign_artifact(
        self,
        artifact: bytes,
        signer: str = "kian-evidence",
    ) -> SigningResult:
        """Sign an artifact using HMAC-SHA256.

        Args:
            artifact: Raw bytes to sign.
            signer: Signer identity.

        Returns:
            SigningResult with the artifact hash and HMAC signature.
        """
        with self._lock:
            artifact_hash = hashlib.sha256(artifact).hexdigest()
            signature = hmac.new(
                self._secret,
                artifact,
                hashlib.sha256,
            ).hexdigest()
            return SigningResult(
                artifact_hash=artifact_hash,
                signature=signature,
                signer=signer,
                key_id=hashlib.sha256(self._secret).hexdigest()[:16],
            )

    def verify_attestation(
        self,
        artifact: bytes,
        signature: str,
    ) -> VerificationResult:
        """Verify an HMAC-SHA256 signature against an artifact.

        Args:
            artifact: Raw bytes that were signed.
            signature: Hex-encoded HMAC signature to verify.

        Returns:
            VerificationResult indicating whether the signature is valid.
        """
        with self._lock:
            expected = hmac.new(
                self._secret,
                artifact,
                hashlib.sha256,
            ).hexdigest()
            artifact_hash = hashlib.sha256(artifact).hexdigest()
            valid = hmac.compare_digest(expected, signature)
            return VerificationResult(
                valid=valid,
                artifact_hash=artifact_hash,
                message="Signature verified" if valid else "Signature mismatch",
            )

    @property
    def key_id(self) -> str:
        """Return the key identifier (first 16 chars of key hash)."""
        return hashlib.sha256(self._secret).hexdigest()[:16]


# ── API Fuzzer ────────────────────────────────────────────────────


class APIFuzzer:
    """API fuzzing (simulated, thread-safe).

    Registers endpoints and runs simulated fuzz tests by generating random
    inputs for each registered endpoint.

    Attributes:
        _endpoints: Dict of key -> FuzzEndpoint.
        _results: List of fuzz results.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._endpoints: dict[str, FuzzEndpoint] = {}
        self._results: list[FuzzResult] = []
        self._lock = threading.Lock()
        self._rng = random.Random(seed) if seed is not None else random.Random()

    @staticmethod
    def _endpoint_key(method: str, path: str) -> str:
        return f"{method.upper()} {path}"

    def register_endpoint(
        self,
        method: str,
        path: str,
        parameters: dict[str, str] | None = None,
        expected_status: int = 200,
    ) -> FuzzEndpoint:
        """Register an endpoint for fuzzing."""
        with self._lock:
            endpoint = FuzzEndpoint(
                method=method.upper(),
                path=path,
                parameters=parameters or {},
                expected_status=expected_status,
            )
            self._endpoints[self._endpoint_key(method, path)] = endpoint
            return endpoint

    def _generate_fuzz_input(self) -> str:
        """Generate a random fuzz input string."""
        length = self._rng.randint(1, 256)
        chars = string.printable + "\\x00\\xff\\n\\r\\t"
        return "".join(self._rng.choice(chars) for _ in range(length))

    def run_fuzz(
        self,
        iterations_per_endpoint: int = 10,
    ) -> FuzzReport:
        """Run fuzz tests against all registered endpoints.

        Args:
            iterations_per_endpoint: Number of fuzz iterations per endpoint.

        Returns:
            FuzzReport with all results and summary statistics.
        """
        with self._lock:
            _FUZZ_TIMEOUT_PROB = 0.05
            _FUZZ_ERROR_PROB = 0.15
            _FUZZ_ERROR_CODES = [400, 401, 403, 404, 422, 500, 502, 503]
            _FUZZ_SERVER_ERROR_THRESHOLD = 500
            results: list[FuzzResult] = []
            for endpoint in self._endpoints.values():
                for _ in range(iterations_per_endpoint):
                    fuzz_input = self._generate_fuzz_input()
                    # Simulate response — most inputs are OK, some error
                    roll = self._rng.random()
                    if roll < _FUZZ_TIMEOUT_PROB:
                        status = FuzzStatus.TIMEOUT
                        response_status = 0
                        response_body = ""
                    elif roll < _FUZZ_ERROR_PROB:
                        status = FuzzStatus.ERROR
                        response_status = self._rng.choice(_FUZZ_ERROR_CODES)
                        response_body = f"Simulated error for input length {len(fuzz_input)}"
                    else:
                        status = FuzzStatus.OK
                        response_status = endpoint.expected_status
                        response_body = "OK"

                    finding = ""
                    # Flag findings: error on a normally-OK endpoint
                    if (
                        status == FuzzStatus.ERROR
                        and response_status >= _FUZZ_SERVER_ERROR_THRESHOLD
                    ):
                        finding = (
                            f"Server error {response_status} on {endpoint.method} {endpoint.path}"
                        )

                    results.append(
                        FuzzResult(
                            endpoint=endpoint,
                            input=fuzz_input,
                            status=status,
                            response_status=response_status,
                            response_body=response_body,
                            duration_ms=self._rng.uniform(0.1, 100.0),
                            finding=finding,
                        ),
                    )
            self._results.extend(results)
            errors = sum(1 for r in results if r.status == FuzzStatus.ERROR)
            timeouts = sum(1 for r in results if r.status == FuzzStatus.TIMEOUT)
            findings = sum(1 for r in results if r.finding)
            return FuzzReport(
                results=results,
                total=len(results),
                errors=errors,
                timeouts=timeouts,
                findings=findings,
            )

    def get_results(self) -> list[FuzzResult]:
        """Return all fuzz results (thread-safe copy)."""
        with self._lock:
            return list(self._results)

    @property
    def endpoint_count(self) -> int:
        """Number of registered endpoints."""
        with self._lock:
            return len(self._endpoints)

    def reset(self) -> None:
        """Reset the fuzzer (for testing)."""
        with self._lock:
            self._endpoints.clear()
            self._results.clear()
            self._rng = random.Random()


# ── Badge Generator ───────────────────────────────────────────────


class BadgeGenerator:
    """CI badge generation (thread-safe).

    Generates shields.io-style SVG badges for CI status, coverage, tests,
    and other metrics.

    Attributes:
        _badges: Dict of badge_name -> Badge.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._badges: dict[str, Badge] = {}
        self._lock = threading.Lock()

    def generate_badge(
        self,
        label: str,
        message: str,
        color: str = BadgeColor.GREEN,
    ) -> Badge:
        """Generate a single badge.

        Args:
            label: Badge label (left side).
            message: Badge message (right side).
            color: Badge colour (see BadgeColor).

        Returns:
            Badge with rendered SVG.
        """
        with self._lock:
            badge = Badge(label=label, message=message, color=color)
            self._badges[label] = badge
            return badge

    def generate_all_badges(
        self,
        *,
        tests_passing: int = 0,
        tests_total: int = 0,
        coverage: float = 0.0,
        lint_clean: bool = True,
        build_status: str = "passing",
    ) -> dict[str, Badge]:
        """Generate the standard set of CI badges.

        Args:
            tests_passing: Number of passing tests.
            tests_total: Total number of tests.
            coverage: Coverage percentage (0-100).
            lint_clean: Whether linting is clean.
            build_status: Build status string.

        Returns:
            Dict of badge_name -> Badge.
        """
        with self._lock:
            badges: dict[str, Badge] = {}

            # Build status badge
            build_color = BadgeColor.GREEN if build_status == "passing" else BadgeColor.RED
            badges["build"] = Badge(
                label="build",
                message=build_status,
                color=build_color,
            )

            # Tests badge
            if tests_total > 0:
                test_color = BadgeColor.GREEN if tests_passing == tests_total else BadgeColor.YELLOW
                badges["tests"] = Badge(
                    label="tests",
                    message=f"{tests_passing}/{tests_total}",
                    color=test_color,
                )

            # Coverage badge
            _COV_HIGH = 90
            _COV_MID = 70
            _COV_LOW = 50
            if coverage > 0:
                if coverage >= _COV_HIGH:
                    cov_color = BadgeColor.GREEN
                elif coverage >= _COV_MID:
                    cov_color = BadgeColor.YELLOW
                elif coverage >= _COV_LOW:
                    cov_color = BadgeColor.ORANGE
                else:
                    cov_color = BadgeColor.RED
                badges["coverage"] = Badge(
                    label="coverage",
                    message=f"{coverage:.0f}%",
                    color=cov_color,
                )

            # Lint badge
            badges["lint"] = Badge(
                label="lint",
                message="clean" if lint_clean else "errors",
                color=BadgeColor.GREEN if lint_clean else BadgeColor.RED,
            )

            self._badges.update(badges)
            return badges

    def get_badge(self, label: str) -> Badge | None:
        """Return a previously generated badge by label."""
        with self._lock:
            return self._badges.get(label)

    def get_all_badges(self) -> dict[str, Badge]:
        """Return all generated badges (thread-safe copy)."""
        with self._lock:
            return dict(self._badges)

    def reset(self) -> None:
        """Reset the badge generator (for testing)."""
        with self._lock:
            self._badges.clear()


# ── Verifier CLI ──────────────────────────────────────────────────


class VerifierCLI:
    """Verifier CLI for the decision ledger and evidence artifacts (thread-safe).

    Provides verify_ledger, verify_dossier, verify_sbom, and verify_provenance
    operations that return VerificationReports.

    Attributes:
        _ledger: The decision ledger to verify.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self, ledger: DecisionLedger | None = None) -> None:
        self._ledger = ledger
        self._lock = threading.Lock()

    def verify_ledger(self) -> VerificationReport:
        """Verify the integrity of the decision ledger chain."""
        with self._lock:
            if self._ledger is None:
                return VerificationReport(
                    name="ledger",
                    status=VerificationStatus.SKIP,
                    message="No ledger configured",
                )
            ok = self._ledger.verify_chain()
            return VerificationReport(
                name="ledger",
                status=VerificationStatus.PASS if ok else VerificationStatus.FAIL,
                message=(
                    f"Chain intact ({self._ledger.count} entries)"
                    if ok
                    else "Chain tampering detected"
                ),
                details={"entry_count": self._ledger.count},
            )

    def verify_dossier(self, trade_id: str) -> VerificationReport:
        """Verify a dossier for a given trade_id."""
        with self._lock:
            if self._ledger is None:
                return VerificationReport(
                    name=f"dossier:{trade_id}",
                    status=VerificationStatus.SKIP,
                    message="No ledger configured",
                )
            entries = self._ledger.get_entries_for_trade(trade_id)
            if not entries:
                return VerificationReport(
                    name=f"dossier:{trade_id}",
                    status=VerificationStatus.SKIP,
                    message=f"No entries for trade '{trade_id}'",
                )
            # Verify each entry's hash
            all_valid = True
            for entry in entries:
                recomputed = entry._compute_hash()
                if recomputed != entry.entry_hash:
                    all_valid = False
                    break
            return VerificationReport(
                name=f"dossier:{trade_id}",
                status=VerificationStatus.PASS if all_valid else VerificationStatus.FAIL,
                message=(
                    f"Dossier verified ({len(entries)} entries)"
                    if all_valid
                    else "Dossier hash mismatch detected"
                ),
                details={
                    "trade_id": trade_id,
                    "entry_count": len(entries),
                    "entry_hashes": [e.entry_hash[:12] for e in entries],
                },
            )

    def verify_sbom(self, sbom: SBOMDocument) -> VerificationReport:
        """Verify a CycloneDX SBOM document."""
        with self._lock:
            if sbom.bom_format != "CycloneDX":
                return VerificationReport(
                    name="sbom",
                    status=VerificationStatus.FAIL,
                    message=f"Unexpected BOM format: {sbom.bom_format}",
                )
            if not sbom.components:
                return VerificationReport(
                    name="sbom",
                    status=VerificationStatus.FAIL,
                    message="SBOM has no components",
                )
            return VerificationReport(
                name="sbom",
                status=VerificationStatus.PASS,
                message=f"SBOM verified ({len(sbom.components)} components)",
                details={
                    "format": sbom.bom_format,
                    "spec_version": sbom.spec_version,
                    "component_count": len(sbom.components),
                    "serial_number": sbom.serial_number,
                },
            )

    def verify_provenance(self, provenance: SLSAProvenance) -> VerificationReport:
        """Verify a SLSA provenance statement."""
        with self._lock:
            expected_hash = provenance._compute_hash()
            valid = expected_hash == provenance.provenance_hash
            return VerificationReport(
                name="provenance",
                status=VerificationStatus.PASS if valid else VerificationStatus.FAIL,
                message=(
                    f"Provenance verified (SLSA level {provenance.slsa_level})"
                    if valid
                    else "Provenance hash mismatch"
                ),
                details={
                    "provenance_hash": provenance.provenance_hash[:16],
                    "slsa_level": provenance.slsa_level,
                    "material_count": len(provenance.materials),
                },
            )

    def verify_all(
        self,
        sbom: SBOMDocument | None = None,
        provenance: SLSAProvenance | None = None,
    ) -> list[VerificationReport]:
        """Run all available verifications and return a list of reports.

        This method does NOT hold the lock — each sub-verification acquires
        and releases it individually, avoiding deadlock.
        """
        reports: list[VerificationReport] = []
        reports.append(self.verify_ledger())
        if self._ledger is not None:
            for trade_id in self._ledger.get_dossiers():
                reports.append(self.verify_dossier(trade_id))
        if sbom is not None:
            reports.append(self.verify_sbom(sbom))
        if provenance is not None:
            reports.append(self.verify_provenance(provenance))
        return reports


# ── Game-Day Runner ───────────────────────────────────────────────


class GameDayRunner:
    """Game-day drill runner (thread-safe).

    Runs chaos/game-day drills with steps, outcomes, findings, and action
    items. Each drill is tracked from start to completion.

    Attributes:
        _records: Dict of drill_id -> GameDayRecord.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._records: dict[str, GameDayRecord] = {}
        self._lock = threading.Lock()

    def start_drill(
        self,
        name: str,
        scenario: str = "",
    ) -> GameDayRecord:
        """Start a new game-day drill and return the record."""
        with self._lock:
            record = GameDayRecord(
                drill_id=DrillId.generate(),
                name=name,
                scenario=scenario,
                status=DrillStatus.IN_PROGRESS,
            )
            self._records[str(record.drill_id)] = record
            return record

    def record_step(
        self,
        drill_id: str,
        name: str,
        description: str = "",
        outcome: str = "",
        duration_ms: float = 0.0,
    ) -> DrillStep | None:
        """Record a step in an ongoing drill.

        Returns the DrillStep, or None if the drill was not found or is not
        in progress.
        """
        with self._lock:
            record = self._records.get(drill_id)
            if record is None or record.status != DrillStatus.IN_PROGRESS:
                return None
            step = DrillStep(
                step_index=len(record.steps),
                name=name,
                description=description,
                outcome=outcome,
                duration_ms=duration_ms,
            )
            record.steps.append(step)
            return step

    def complete_drill(
        self,
        drill_id: str,
        findings: list[str] | None = None,
        action_items: list[str] | None = None,
    ) -> GameDayRecord | None:
        """Complete a drill, recording findings and action items.

        Returns the completed record, or None if the drill was not found.
        """
        with self._lock:
            record = self._records.get(drill_id)
            if record is None:
                return None
            record.status = DrillStatus.COMPLETED
            record.completed_at = datetime.now(UTC)
            record.findings = findings or []
            record.action_items = action_items or []
            return record

    def get_records(self) -> list[GameDayRecord]:
        """Return all drill records (thread-safe copy)."""
        with self._lock:
            return list(self._records.values())

    def get_drill(self, drill_id: str) -> GameDayRecord | None:
        """Return a single drill record by ID."""
        with self._lock:
            return self._records.get(drill_id)

    @property
    def count(self) -> int:
        """Number of drills."""
        with self._lock:
            return len(self._records)

    def reset(self) -> None:
        """Reset the runner (for testing)."""
        with self._lock:
            self._records.clear()
