# Phase E8 — Evidence, Observability and Supply Chain

**Branch:** `phase/e8-evidence-observability-supply-chain`
**Commit:** `da1af716a43b47ee85e78948dc4bc63b07095b21`
**Date:** 2025-07-10
**AD Refs:** AD-037 (Tamper-Evident Decision Ledger)

---

## Scope

Phase E8 delivers the full evidence, observability and supply-chain layer for
Kian Trading Intelligence. All work landed in a single commit on top of the
phase/e7-strategy-science tree; no Phase E9+ work was performed.

---

## Deliverables

### Contracts (`packages/contracts/evidence.py`)

| Contract | Purpose |
|---|---|
| `LedgerEntry` / `LedgerEntryId` | Frozen hash-chained ledger entry (SHA-256, genesis sentinel) |
| `DecisionDossier` / `DossierId` | Per-trade dossier with aggregate hash |
| `OTelConfig` / `OTelSpan` / `OTelMetric` / `SpanKind` | OTel-style telemetry types |
| `SLODefinition` / `SLOBurnRateResult` / `SLOAlert` / `SLOAlertLevel` | SLO definitions and burn-rate alert types |
| `ThreatModelEntry` / `ThreatModelReport` / `ThreatSeverity` / `ThreatStatus` | STRIDE threat model types |
| `SBOMComponent` / `SBOM` | CycloneDX SBOM component and document |
| `SLSABuildInfo` / `SLSAMaterial` / `SLSAProvenance` | SLSA provenance statement (levels 1-4) |
| `SigningResult` / `VerificationResult` | Sigstore-style artifact signing results |
| `FuzzEndpoint` / `FuzzResult` / `FuzzReport` / `FuzzStatus` | API fuzzer types |
| `Badge` / `BadgeColor` | CI badge (SVG) with color thresholds |
| `VerificationReport` / `VerificationStatus` | Unified verifier report |
| `DrillRecord` / `DrillStep` / `DrillId` / `DrillStatus` | Game-day drill records |

### Service (`services/evidence/__init__.py`)

| Class | Responsibility |
|---|---|
| `DecisionLedger` | Append-only hash-chained ledger; `verify_chain()` detects any single-byte tamper; external anchoring |
| `DecisionDossierBuilder` | Builds per-trade dossiers from ledger; aggregate dossier hash |
| `OpenTelemetryInstrumentor` | Simulated OTel spans and metrics; `start_span`/`end_span`/`record_metric` |
| `SLOMonitor` | Register SLOs; record requests; `check_burn_rate()`; `get_alerts()` with WARNING/CRITICAL levels |
| `ThreatModelManager` | Add/update threat entries; `export()` report by severity |
| `SBOMGenerator` | Add components; `generate_sbom()` → CycloneDX JSON; `from_dependencies()` autodiscovery from `pyproject.toml` |
| `SLSAProvenanceBuilder` | Build SLSA provenance with materials; `verify()` for tamper detection |
| `SigstoreSigner` | HMAC-SHA256 artifact signing; `verify_attestation()` |
| `APIFuzzer` | Deterministic seeded fuzzer; edge-case and long-input generation; `run_fuzz()` report |
| `BadgeGenerator` | SVG badge generation; color thresholds for coverage (≥90% green, ≥70% yellow, ≥50% orange, <50% red) |
| `VerifierCLI` | Unified CLI-style verifier for ledger, dossier, SBOM and provenance; `verify_all()` |
| `GameDayRunner` | Start drills, record steps, complete with findings and action items |

---

## Quality Gate Results

| Gate | Result |
|---|---|
| `ruff check services/evidence/__init__.py tests/test_e8_evidence.py` | ✅ All checks passed |
| `ruff format --check services/evidence/__init__.py tests/test_e8_evidence.py` | ✅ 2 files already formatted |
| `mypy packages/ services/evidence/ tests/test_e8_evidence.py` | ✅ No errors |
| `pytest tests/test_e8_evidence.py` | ✅ 83 passed in 0.62s |
| `pytest` (full suite) | ✅ 1646 passed, 12 skipped in 16.04s |

---

## Fixes Applied in This Session

| File | Location | Error | Fix |
|---|---|---|---|
| `services/evidence/__init__.py` | Line 1020 | `ruff E501` — line too long (102 > 100) | Wrapped `if` condition into multi-line form |
| `services/evidence/__init__.py` | Line 676 | `mypy [no-redef]` — `tomllib` already defined; `type: ignore[import-not-found]` didn't cover `[no-redef]` | Extended comment to `type: ignore[import-not-found,no-redef]` |
| `services/evidence/__init__.py` | Line 826 (arg-type) | `mypy [arg-type]` — `subject` passed `dict[str, str\|dict]`; `SLSAProvenance.subject` requires `dict[str, str]` | Added `import json` at module top; serialize `subject_digest` to JSON string |
| `services/evidence/__init__.py` | Line 838 | `mypy [no-any-return]` — `str.__eq__` returns `bool` but inferred as `Any` | Wrapped return with `bool()` |
| `tests/test_e8_evidence.py` | 19 lines | `mypy [unused-ignore]` — stale `type: ignore` comments | Removed all 19 comments |

---

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| Audit chain detects any single-byte edit | ✅ `test_verify_chain_detects_tamper` + `test_verify_chain_detects_hash_tamper` |
| Supply-chain targets met (SBOM, SLSA, signing) | ✅ `TestSBOMGenerator`, `TestSLSAProvenance`, `TestSigstoreSigner` |
| Game-day records exist | ✅ `TestGameDayRunner` (7 tests covering start, step, complete, findings) |
| Zero new ruff/mypy errors | ✅ Confirmed |
| Full test suite green | ✅ 1646 passed |

---

## Remote Verification

```
Branch:  phase/e8-evidence-observability-supply-chain
SHA:     da1af716a43b47ee85e78948dc4bc63b07095b21
Remote:  origin/phase/e8-evidence-observability-supply-chain  ← matched
CI:      triggered on push (branch matches phase/* pattern in ci.yml)
```

---

## Hard Stop

Phase E8 is complete. **NEXT PHASE NOT AUTHORIZED.**
