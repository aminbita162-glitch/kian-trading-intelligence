"""Tests for E8 — Evidence, Observability and Supply Chain.

Per E8 (Evidence, Observability and Supply Chain) and AD-037
(Tamper-Evident Decision Ledger):

Hash-chained decision ledger with external anchoring and verifier CLI;
decision dossiers; full OpenTelemetry (simulated); SLOs with burn-rate
alerts; IaC with policy scanning; CodeQL/Semgrep/gitleaks/Dependabot
(CycloneDX SBOM; Sigstore signing; SLSA provenance; API fuzzing; living
threat model (STRIDE + agent-specific); CI-generated badges; game-day
records.

Acceptance: Audit chain detects any single-byte edit; supply-chain targets
met; game-day records exist.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from contracts.evidence import (
    BadgeColor,
    DrillStatus,
    LedgerEntry,
    LedgerEntryId,
    OTelConfig,
    SLOAlertLevel,
    SLODefinition,
    SLSABuildInfo,
    SpanKind,
    ThreatSeverity,
    ThreatStatus,
    VerificationStatus,
)
from services.evidence import (
    APIFuzzer,
    BadgeGenerator,
    DecisionDossierBuilder,
    DecisionLedger,
    GameDayRunner,
    OpenTelemetryInstrumentor,
    SBOMGenerator,
    SigstoreSigner,
    SLOMonitor,
    SLSAProvenanceBuilder,
    ThreatModelManager,
    VerifierCLI,
)

# ── Decision Ledger ───────────────────────────────────────────────


class TestDecisionLedger:
    """Hash-chained append-only decision ledger (AD-037)."""

    def test_record_entry_returns_entry(self) -> None:
        ledger = DecisionLedger()
        entry = ledger.record_entry("trade-1", "entry", {"side": "buy"})
        assert entry.trade_id == "trade-1"
        assert entry.decision_type == "entry"
        assert entry.entry_hash != ""
        assert ledger.count == 1

    def test_chain_links_correctly(self) -> None:
        ledger = DecisionLedger()
        e1 = ledger.record_entry("trade-1", "entry", {"side": "buy"})
        e2 = ledger.record_entry("trade-1", "exit", {"price": "50000"})
        e3 = ledger.record_entry("trade-2", "entry", {"side": "sell"})
        assert e1.previous_hash == "genesis"
        assert e2.previous_hash == e1.entry_hash
        assert e3.previous_hash == e2.entry_hash

    def test_verify_chain_valid(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        assert ledger.verify_chain() is True

    def test_verify_chain_detects_tamper(self) -> None:
        ledger = DecisionLedger()
        e1 = ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        # Tamper: modify the first entry's payload
        e1.payload = {"side": "sell"}
        assert ledger.verify_chain() is False

    def test_verify_chain_detects_hash_tamper(self) -> None:
        ledger = DecisionLedger()
        e1 = ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        # Tamper: modify the entry hash directly
        e1.entry_hash = "tampered"
        assert ledger.verify_chain() is False

    def test_empty_chain_verifies(self) -> None:
        ledger = DecisionLedger()
        assert ledger.verify_chain() is True

    def test_external_anchor(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        assert ledger.anchor_external("https://anchor.example/123") is True
        entries = ledger.get_entries()
        assert entries[-1].external_anchor == "https://anchor.example/123"

    def test_external_anchor_empty_ledger(self) -> None:
        ledger = DecisionLedger()
        assert ledger.anchor_external("https://anchor.example/123") is False

    def test_get_entries_for_trade(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        ledger.record_entry("trade-2", "entry", {"side": "sell"})
        trade1 = ledger.get_entries_for_trade("trade-1")
        trade2 = ledger.get_entries_for_trade("trade-2")
        assert len(trade1) == 2
        assert len(trade2) == 1
        assert trade1[0].trade_id == "trade-1"

    def test_reset(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry")
        ledger.reset()
        assert ledger.count == 0


# ── Decision Dossier ──────────────────────────────────────────────


class TestDecisionDossier:
    """Per-trade decision dossiers (AD-037)."""

    def test_build_dossier(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        builder = DecisionDossierBuilder(ledger)
        dossier = builder.build_dossier("trade-1")
        assert dossier is not None
        assert dossier.trade_id == "trade-1"
        assert len(dossier.entries) == 2
        assert dossier.dossier_hash != ""

    def test_build_dossier_no_entries(self) -> None:
        ledger = DecisionLedger()
        builder = DecisionDossierBuilder(ledger)
        dossier = builder.build_dossier("nonexistent")
        assert dossier is None

    def test_build_all_dossiers(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-2", "entry", {"side": "sell"})
        builder = DecisionDossierBuilder(ledger)
        dossiers = builder.build_all_dossiers()
        assert len(dossiers) == 2


# ── OpenTelemetry ─────────────────────────────────────────────────


class TestOpenTelemetry:
    """Full OpenTelemetry-style instrumentation (simulated)."""

    def test_setup_returns_config(self) -> None:
        otel = OpenTelemetryInstrumentor()
        config = otel.setup()
        assert config.service_name == "kian-trading-intelligence"
        assert config.enabled is True

    def test_record_span(self) -> None:
        otel = OpenTelemetryInstrumentor()
        span = otel.record_span("test-span", kind=SpanKind.SERVER)
        assert span.name == "test-span"
        assert span.kind == SpanKind.SERVER
        assert span.end_time is not None
        assert span.status == "ok"
        assert len(otel.get_spans()) == 1

    def test_start_end_span(self) -> None:
        otel = OpenTelemetryInstrumentor()
        span = otel.start_span("test-span", kind=SpanKind.CLIENT)
        assert span.end_time is None
        otel.end_span(span, status="error")
        assert span.end_time is not None
        assert span.status == "error"

    def test_record_metric(self) -> None:
        otel = OpenTelemetryInstrumentor()
        metric = otel.record_metric("requests", 42.0, unit="1")
        assert metric.name == "requests"
        assert metric.value == 42.0
        assert len(otel.get_metrics()) == 1

    def test_custom_config(self) -> None:
        config = OTelConfig(service_name="custom", sampling_rate=0.5)
        otel = OpenTelemetryInstrumentor(config)
        assert otel.config.service_name == "custom"
        assert otel.config.sampling_rate == 0.5

    def test_reset(self) -> None:
        otel = OpenTelemetryInstrumentor()
        otel.record_span("test")
        otel.record_metric("m", 1.0)
        otel.reset()
        assert len(otel.get_spans()) == 0
        assert len(otel.get_metrics()) == 0


# ── SLO Monitor ───────────────────────────────────────────────────


class TestSLOMonitor:
    """SLO monitoring with burn-rate alerts."""

    def test_register_slo(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(name="api-availability", target=0.999)
        monitor.register_slo(slo)
        assert monitor.slo_count == 1

    def test_record_request_and_check_burn_rate(self) -> None:
        monitor = SLOMonitor()
        monitor.register_slo(SLODefinition(name="api-availability", target=0.99))
        # Record 100 successful requests
        for _ in range(100):
            monitor.record_request("api-availability", success=True)
        result = monitor.check_burn_rate("api-availability")
        assert result.error_rate == 0.0
        assert result.burn_rate == 0.0
        assert result.alerting is False

    def test_burn_rate_alerting(self) -> None:
        monitor = SLOMonitor()
        monitor.register_slo(SLODefinition(name="api-availability", target=0.99))
        # 10% error rate, SLO is 99%, error_budget is 1%
        # burn_rate = 0.1 / 0.01 = 10.0 > 1.0 → alerting
        for _ in range(90):
            monitor.record_request("api-availability", success=True)
        for _ in range(10):
            monitor.record_request("api-availability", success=False)
        result = monitor.check_burn_rate("api-availability")
        assert result.error_rate == pytest.approx(0.1)
        assert result.burn_rate > 1.0
        assert result.alerting is True

    def test_get_alerts(self) -> None:
        monitor = SLOMonitor()
        monitor.register_slo(SLODefinition(name="api-availability", target=0.99))
        for _ in range(50):
            monitor.record_request("api-availability", success=False)
        alerts = monitor.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].slo_name == "api-availability"
        assert alerts[0].level in (SLOAlertLevel.WARNING, SLOAlertLevel.CRITICAL)

    def test_no_alerts_when_healthy(self) -> None:
        monitor = SLOMonitor()
        monitor.register_slo(SLODefinition(name="api-availability", target=0.99))
        for _ in range(100):
            monitor.record_request("api-availability", success=True)
        alerts = monitor.get_alerts()
        assert len(alerts) == 0

    def test_record_request_unregistered_slo(self) -> None:
        monitor = SLOMonitor()
        with pytest.raises(ValueError, match="not registered"):
            monitor.record_request("unknown-slo", success=True)

    def test_check_burn_rate_unregistered(self) -> None:
        monitor = SLOMonitor()
        with pytest.raises(ValueError, match="not registered"):
            monitor.check_burn_rate("unknown-slo")

    def test_reset(self) -> None:
        monitor = SLOMonitor()
        monitor.register_slo(SLODefinition(name="api", target=0.99))
        monitor.record_request("api", success=True)
        monitor.reset()
        assert monitor.slo_count == 0


# ── Threat Model ──────────────────────────────────────────────────


class TestThreatModel:
    """Living threat model (STRIDE + agent-specific)."""

    def test_add_entry(self) -> None:
        mgr = ThreatModelManager()
        entry = mgr.add_entry(
            component="Risk Kernel",
            threat="Spoofed risk authorization token",
            severity=ThreatSeverity.HIGH,
        )
        assert entry.component == "Risk Kernel"
        assert entry.severity == ThreatSeverity.HIGH
        assert mgr.count == 1

    def test_update_entry(self) -> None:
        mgr = ThreatModelManager()
        entry = mgr.add_entry(
            component="Exchange Adapter",
            threat="Man-in-the-middle attack",
            severity=ThreatSeverity.HIGH,
        )
        updated = mgr.update_entry(
            str(entry.entry_id),
            status=ThreatStatus.MITIGATED,
            mitigation="TLS 1.3 with cert pinning",
        )
        assert updated is not None
        assert updated.status == ThreatStatus.MITIGATED
        assert updated.mitigation == "TLS 1.3 with cert pinning"

    def test_update_entry_not_found(self) -> None:
        mgr = ThreatModelManager()
        result = mgr.update_entry("nonexistent", status=ThreatStatus.MITIGATED)
        assert result is None

    def test_export_report(self) -> None:
        mgr = ThreatModelManager()
        mgr.add_entry("API", "SQL injection", severity=ThreatSeverity.CRITICAL)
        mgr.add_entry("Auth", "Credential leak", severity=ThreatSeverity.MEDIUM)
        report = mgr.export()
        assert report.total == 2
        assert report.open_count == 2
        assert "critical" in report.by_severity
        assert "medium" in report.by_severity

    def test_get_model(self) -> None:
        mgr = ThreatModelManager()
        mgr.add_entry("API", "SQL injection")
        mgr.add_entry("Auth", "Credential leak")
        model = mgr.get_model()
        assert len(model) == 2

    def test_reset(self) -> None:
        mgr = ThreatModelManager()
        mgr.add_entry("API", "SQL injection")
        mgr.reset()
        assert mgr.count == 0


# ── SBOM Generator ────────────────────────────────────────────────


class TestSBOMGenerator:
    """CycloneDX SBOM generation."""

    def test_add_component(self) -> None:
        gen = SBOMGenerator()
        comp = gen.add_component("pytest", "8.0.0")
        assert comp.name == "pytest"
        assert comp.version == "8.0.0"
        assert "pypi" in comp.purl

    def test_generate_sbom(self) -> None:
        gen = SBOMGenerator()
        gen.add_component("fastapi", "0.115.0")
        gen.add_component("pydantic", "2.10.0")
        sbom = gen.generate_sbom()
        assert sbom.bom_format == "CycloneDX"
        assert len(sbom.components) == 3  # app + 2 deps
        assert sbom.components[0].type == "application"
        assert sbom.components[1].type == "library"

    def test_sbom_to_dict(self) -> None:
        gen = SBOMGenerator()
        gen.add_component("fastapi", "0.115.0")
        sbom = gen.generate_sbom()
        d = sbom.to_dict()
        assert d["bomFormat"] == "CycloneDX"
        assert len(d["components"]) == 2

    def test_from_dependencies(self) -> None:
        gen = SBOMGenerator()
        comps = gen.from_dependencies("pyproject.toml")
        assert len(comps) > 0
        names = [c.name for c in comps]
        assert "fastapi" in names or any("fastapi" in n for n in names)

    def test_from_dependencies_missing_file(self) -> None:
        gen = SBOMGenerator()
        comps = gen.from_dependencies("/nonexistent/path.toml")
        assert len(comps) == 0

    def test_reset(self) -> None:
        gen = SBOMGenerator()
        gen.add_component("test", "1.0")
        gen.reset()
        assert len(gen.get_components()) == 0


# ── SLSA Provenance ───────────────────────────────────────────────


class TestSLSAProvenance:
    """SLSA provenance builder."""

    def test_build_provenance(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(
            SLSABuildInfo(
                builder_id="github-actions",
                build_type="github-actions",
                source_uri="https://github.com/aminbita162-glitch/kian-trading-intelligence",
                source_branch="main",
                source_commit="abc123",
            ),
        )
        builder.add_material(
            "pkg:pypi/kian-trading-intelligence@0.10.0",
            {"sha256": "abc123"},
        )
        provenance = builder.build(
            subject_uri="pkg:pypi/kian-trading-intelligence@0.10.0",
            subject_digest={"sha256": "def456"},
            slsa_level=2,
        )
        assert provenance.slsa_level == 2
        assert provenance.provenance_hash != ""
        assert len(provenance.materials) == 1

    def test_verify_provenance(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(SLSABuildInfo(builder_id="test"))
        builder.add_material("pkg:source", {"sha256": "aaa"})
        provenance = builder.build(subject_uri="pkg:app")
        assert builder.verify(provenance) is True

    def test_provenance_detects_tamper(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(SLSABuildInfo(builder_id="test"))
        builder.add_material("pkg:source", {"sha256": "aaa"})
        provenance = builder.build(subject_uri="pkg:app")
        # Tamper with the provenance hash
        provenance.provenance_hash = "tampered"
        assert builder.verify(provenance) is False

    def test_reset(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.add_material("pkg:source")
        builder.reset()
        assert len(builder.get_materials()) == 0


# ── Sigstore Signer ───────────────────────────────────────────────


class TestSigstoreSigner:
    """Sigstore-style signing (HMAC-SHA256 simulated)."""

    def test_sign_and_verify(self) -> None:
        signer = SigstoreSigner(secret=b"test-secret-key")
        artifact = b"important artifact content"
        result = signer.sign_artifact(artifact)
        assert result.artifact_hash != ""
        assert result.signature != ""
        verification = signer.verify_attestation(artifact, result.signature)
        assert verification.valid is True

    def test_verify_wrong_artifact(self) -> None:
        signer = SigstoreSigner(secret=b"test-secret-key")
        result = signer.sign_artifact(b"original artifact")
        verification = signer.verify_attestation(b"tampered artifact", result.signature)
        assert verification.valid is False

    def test_verify_wrong_signature(self) -> None:
        signer = SigstoreSigner(secret=b"test-secret-key")
        verification = signer.verify_attestation(b"artifact", "wrong-signature")
        assert verification.valid is False

    def test_key_id(self) -> None:
        signer = SigstoreSigner(secret=b"test-secret-key")
        assert len(signer.key_id) == 16

    def test_default_secret(self) -> None:
        signer = SigstoreSigner()
        result = signer.sign_artifact(b"test")
        assert result.signature != ""


# ── API Fuzzer ────────────────────────────────────────────────────


class TestAPIFuzzer:
    """API fuzzing."""

    def test_register_endpoint(self) -> None:
        fuzzer = APIFuzzer(seed=42)
        ep = fuzzer.register_endpoint("GET", "/api/v1/trades")
        assert ep.method == "GET"
        assert ep.path == "/api/v1/trades"
        assert fuzzer.endpoint_count == 1

    def test_run_fuzz(self) -> None:
        fuzzer = APIFuzzer(seed=42)
        fuzzer.register_endpoint("GET", "/api/v1/trades")
        fuzzer.register_endpoint("POST", "/api/v1/orders")
        report = fuzzer.run_fuzz(iterations_per_endpoint=20)
        assert report.total == 40
        assert (
            report.errors + report.timeouts + (report.total - report.errors - report.timeouts)
            == report.total
        )

    def test_fuzz_results_stored(self) -> None:
        fuzzer = APIFuzzer(seed=42)
        fuzzer.register_endpoint("GET", "/api/v1/health")
        fuzzer.run_fuzz(iterations_per_endpoint=5)
        assert len(fuzzer.get_results()) == 5

    def test_fuzz_deterministic_with_seed(self) -> None:
        fuzzer1 = APIFuzzer(seed=42)
        fuzzer2 = APIFuzzer(seed=42)
        fuzzer1.register_endpoint("GET", "/api/v1/health")
        fuzzer2.register_endpoint("GET", "/api/v1/health")
        r1 = fuzzer1.run_fuzz(iterations_per_endpoint=10)
        r2 = fuzzer2.run_fuzz(iterations_per_endpoint=10)
        assert r1.total == r2.total
        assert r1.errors == r2.errors

    def test_reset(self) -> None:
        fuzzer = APIFuzzer(seed=42)
        fuzzer.register_endpoint("GET", "/api/v1/health")
        fuzzer.run_fuzz(iterations_per_endpoint=5)
        fuzzer.reset()
        assert fuzzer.endpoint_count == 0
        assert len(fuzzer.get_results()) == 0


# ── Badge Generator ──────────────────────────────────────────────


class TestBadgeGenerator:
    """CI badge generation."""

    def test_generate_badge(self) -> None:
        gen = BadgeGenerator()
        badge = gen.generate_badge("tests", "100/100")
        assert badge.label == "tests"
        assert badge.message == "100/100"
        assert badge.color == BadgeColor.GREEN
        assert "<svg" in badge.svg

    def test_generate_all_badges(self) -> None:
        gen = BadgeGenerator()
        badges = gen.generate_all_badges(
            tests_passing=100,
            tests_total=100,
            coverage=95.0,
            lint_clean=True,
            build_status="passing",
        )
        assert "build" in badges
        assert "tests" in badges
        assert "coverage" in badges
        assert "lint" in badges
        assert badges["build"].color == BadgeColor.GREEN
        assert badges["coverage"].color == BadgeColor.GREEN

    def test_failing_build_badge(self) -> None:
        gen = BadgeGenerator()
        badges = gen.generate_all_badges(build_status="failing")
        assert badges["build"].color == BadgeColor.RED

    def test_partial_tests_badge(self) -> None:
        gen = BadgeGenerator()
        badges = gen.generate_all_badges(
            tests_passing=90,
            tests_total=100,
        )
        assert badges["tests"].color == BadgeColor.YELLOW

    def test_coverage_color_thresholds(self) -> None:
        gen = BadgeGenerator()
        badges = gen.generate_all_badges(coverage=95.0)
        assert badges["coverage"].color == BadgeColor.GREEN
        badges = gen.generate_all_badges(coverage=75.0)
        assert badges["coverage"].color == BadgeColor.YELLOW
        badges = gen.generate_all_badges(coverage=55.0)
        assert badges["coverage"].color == BadgeColor.ORANGE
        badges = gen.generate_all_badges(coverage=30.0)
        assert badges["coverage"].color == BadgeColor.RED

    def test_reset(self) -> None:
        gen = BadgeGenerator()
        gen.generate_badge("test", "ok")
        gen.reset()
        assert gen.get_badge("test") is None


# ── Verifier CLI ──────────────────────────────────────────────────


class TestVerifierCLI:
    """Verifier CLI for decision ledger and evidence artifacts."""

    def test_verify_ledger_pass(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        verifier = VerifierCLI(ledger=ledger)
        report = verifier.verify_ledger()
        assert report.status == VerificationStatus.PASS
        assert "Chain intact" in report.message

    def test_verify_ledger_fail(self) -> None:
        ledger = DecisionLedger()
        e1 = ledger.record_entry("trade-1", "entry", {"side": "buy"})
        ledger.record_entry("trade-1", "exit", {"price": "50000"})
        e1.payload = {"tampered": True}
        verifier = VerifierCLI(ledger=ledger)
        report = verifier.verify_ledger()
        assert report.status == VerificationStatus.FAIL

    def test_verify_ledger_no_ledger(self) -> None:
        verifier = VerifierCLI()
        report = verifier.verify_ledger()
        assert report.status == VerificationStatus.SKIP

    def test_verify_dossier(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry", {"side": "buy"})
        verifier = VerifierCLI(ledger=ledger)
        report = verifier.verify_dossier("trade-1")
        assert report.status == VerificationStatus.PASS

    def test_verify_dossier_not_found(self) -> None:
        ledger = DecisionLedger()
        verifier = VerifierCLI(ledger=ledger)
        report = verifier.verify_dossier("nonexistent")
        assert report.status == VerificationStatus.SKIP

    def test_verify_sbom(self) -> None:
        gen = SBOMGenerator()
        gen.add_component("fastapi", "0.115.0")
        sbom = gen.generate_sbom()
        verifier = VerifierCLI()
        report = verifier.verify_sbom(sbom)
        assert report.status == VerificationStatus.PASS
        assert "CycloneDX" in report.message or "verified" in report.message

    def test_verify_sbom_empty(self) -> None:
        gen = SBOMGenerator()
        sbom = gen.generate_sbom()
        verifier = VerifierCLI()
        report = verifier.verify_sbom(sbom)
        # The app component is always included, so it should pass
        assert report.status == VerificationStatus.PASS

    def test_verify_provenance(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(SLSABuildInfo(builder_id="test"))
        provenance = builder.build(subject_uri="pkg:app")
        verifier = VerifierCLI()
        report = verifier.verify_provenance(provenance)
        assert report.status == VerificationStatus.PASS

    def test_verify_provenance_tampered(self) -> None:
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(SLSABuildInfo(builder_id="test"))
        provenance = builder.build(subject_uri="pkg:app")
        provenance.provenance_hash = "tampered"
        verifier = VerifierCLI()
        report = verifier.verify_provenance(provenance)
        assert report.status == VerificationStatus.FAIL

    def test_verify_all(self) -> None:
        ledger = DecisionLedger()
        ledger.record_entry("trade-1", "entry")
        gen = SBOMGenerator()
        gen.add_component("fastapi", "0.115.0")
        sbom = gen.generate_sbom()
        builder = SLSAProvenanceBuilder()
        builder.set_build_info(SLSABuildInfo())
        provenance = builder.build()
        verifier = VerifierCLI(ledger=ledger)
        reports = verifier.verify_all(sbom=sbom, provenance=provenance)
        assert len(reports) >= 3
        statuses = [r.status for r in reports]
        assert VerificationStatus.FAIL not in statuses


# ── Game-Day Runner ───────────────────────────────────────────────


class TestGameDayRunner:
    """Game-day records and drills."""

    def test_start_drill(self) -> None:
        runner = GameDayRunner()
        record = runner.start_drill("Kill Plane Drill", "Test independent kill plane")
        assert record.name == "Kill Plane Drill"
        assert record.status == DrillStatus.IN_PROGRESS
        assert runner.count == 1

    def test_record_step(self) -> None:
        runner = GameDayRunner()
        record = runner.start_drill("Chaos Drill", "Inject latency")
        step = runner.record_step(
            str(record.drill_id),
            "Inject 500ms latency",
            "Added artificial delay",
            "PASS",
        )
        assert step is not None
        assert step.name == "Inject 500ms latency"
        assert step.outcome == "PASS"

    def test_record_step_not_found(self) -> None:
        runner = GameDayRunner()
        step = runner.record_step("nonexistent", "test")
        assert step is None

    def test_complete_drill(self) -> None:
        runner = GameDayRunner()
        record = runner.start_drill("Game Day", "Full scenario")
        runner.record_step(str(record.drill_id), "Step 1", outcome="PASS")
        completed = runner.complete_drill(
            str(record.drill_id),
            findings=["Latency spike detected"],
            action_items=["Add auto-scaling"],
        )
        assert completed is not None
        assert completed.status == DrillStatus.COMPLETED
        assert completed.completed_at is not None
        assert len(completed.findings) == 1
        assert len(completed.action_items) == 1

    def test_complete_drill_not_found(self) -> None:
        runner = GameDayRunner()
        result = runner.complete_drill("nonexistent")
        assert result is None

    def test_get_records(self) -> None:
        runner = GameDayRunner()
        runner.start_drill("Drill 1")
        runner.start_drill("Drill 2")
        records = runner.get_records()
        assert len(records) == 2

    def test_reset(self) -> None:
        runner = GameDayRunner()
        runner.start_drill("Test")
        runner.reset()
        assert runner.count == 0


# ── LedgerEntry contract ───────────────────────────────────────────


class TestLedgerEntryContract:
    """Direct contract tests for LedgerEntry."""

    def test_entry_hash_computed(self) -> None:
        entry = LedgerEntry(
            entry_id=LedgerEntryId.generate(),
            trade_id="trade-1",
            decision_type="entry",
            payload={"side": "buy"},
        )
        assert entry.entry_hash != ""
        assert len(entry.entry_hash) == 64  # SHA-256 hex

    def test_entry_empty_trade_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="trade_id"):
            LedgerEntry(
                entry_id=LedgerEntryId.generate(),
                trade_id="",
                decision_type="entry",
            )

    def test_entry_empty_decision_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="decision_type"):
            LedgerEntry(
                entry_id=LedgerEntryId.generate(),
                trade_id="trade-1",
                decision_type="",
            )

    def test_entry_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            LedgerEntry(
                entry_id=LedgerEntryId.generate(),
                trade_id="trade-1",
                decision_type="entry",
                timestamp=datetime(2024, 1, 1),  # noqa: DTZ001
            )


# ── SLODefinition contract ────────────────────────────────────────


class TestSLODefinitionContract:
    """Direct contract tests for SLODefinition."""

    def test_valid_slo(self) -> None:
        slo = SLODefinition(name="api", target=0.999)
        assert slo.error_budget == pytest.approx(0.001)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            SLODefinition(name="", target=0.99)

    def test_target_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="target"):
            SLODefinition(name="api", target=0.0)
        with pytest.raises(ValueError, match="target"):
            SLODefinition(name="api", target=1.0)
