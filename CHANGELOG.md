# CHANGELOG — Kian Trading Intelligence

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with prerelease identifiers during development.

---

## [Unreleased]

### Added — Phase 01: Repository & Engineering Foundation
- Repository identity and remote verification (GitHub: aminbita162-glitch/kian-trading-intelligence)
- Structured monorepo layout (`apps/`, `services/`, `agents/`, `packages/`, `infrastructure/`, `tests/`, `docs/`, `test-house/`)
- Python 3.11+ / FastAPI backend foundation with health endpoint and OpenAPI documentation
- TypeScript 5.6+ / React / Vite frontend foundation with strict type checking
- Shared contracts package (`packages/contracts/`) with Pydantic models for operating modes and order states
- Dependency management with `pyproject.toml` (backend) and `package.json` (frontend)
- Code formatting and linting: Ruff (Python), ESLint + Prettier (TypeScript)
- Unit-test framework: pytest (Python) with passing baseline tests, Vitest (TypeScript)
- CI configuration via GitHub Actions (`.github/workflows/ci.yml`)
- Secret-handling rules: `.gitignore` exclusions, environment file patterns, no-secrets policy
- Architecture documentation (`docs/architecture.md`)
- Proprietary LICENSE file (pending owner/legal review)
- Test house evidence library (`test-house/`) with structured phase directories
- Engineering integrity policy in README.md

### Added — Phase 08: MacBook & iPhone Applications
- Tauri MacBook application shell (`apps/macbook/src-tauri/`) with `tauri.conf.json`, `Cargo.toml`, Rust entry points
- Responsive iPhone PWA (`apps/web/public/manifest.json`, PWA meta tags in `index.html`)
- Onboarding flow with 8-step wizard (`OnboardingStep` enum)
- Trading, mining, and financial dashboard views
- Calendar scheduler view for trading session scheduling
- Secure remote command service (AD-027) with step-up authentication, idempotency, and expiry for 5 high-risk commands
- Notification hub (AD-009) with `NotificationCreateRequest` Pydantic model, preferences, and priority levels
- Connected-account settings with withdrawal prohibition (AD-019)
- Incident and recovery interface (AD-017) with `IncidentCreateRequest` Pydantic model, severity levels, and human-approval gate for critical incidents
- End-to-end simulated workflow (`run_simulated_workflow`) exercising all dashboard areas
- Phase 08 API endpoints in `services/core/app.py`
- Client service module `services/client/__init__.py` with `RemoteCommandService`, `NotificationService`, `IncidentService`
- Frontend client contracts (`client-contracts.ts`, `remote-commands.ts`, `notifications.ts`, `navigation.ts`)
- 11 dashboard view components in `apps/web/src/views/`
- Python tests (`tests/test_client_contracts.py`, ~40 tests) and frontend tests (4 new test files, 91 total)
- Test-house evidence in `test-house/phase-08/evidence.md`

### Added — Phase 09: Security, Resilience, and Scale
- Threat-model review with `ThreatFinding`, `ThreatModelReport`, `SecurityService` — critical/high findings block release (AD-010, AD-022)
- Security scanning with `ScanResult`, `ScanType` (static, dependency, secret, infrastructure, license) (AD-010)
- Tenant-isolation testing with `TenantIsolationTester` — cross-tenant access denied (AD-002, AD-010)
- Risk stress tests with `RiskStressTester` — exposure, daily-loss, concentration, emergency-stop, concurrent authorization (AD-013)
- Financial stress tests with `FinancialStressTester` — double-entry balance, decimal precision, idempotent posting (AD-018)
- Backup restoration with `BackupService` — full/incremental backups, SHA-256 checksums, integrity verification (AD-028)
- Disaster recovery with `DisasterRecoveryState` — 5-phase state machine (DETECT → ASSESS → ISOLATE → RESTORE → VERIFY), human authorization mandatory (AD-017, AD-028)
- Split-brain simulation with `SplitBrainSimulator` — leader/follower roles, quorum detection, partition evidence (AD-016, AD-028)
- Fault injection with `FaultInjector` — 6 fault types (network, latency, crash, disk-full, corruption, timeout) (AD-023)
- Load testing with `LoadTestRunner` — p50/p95/p99 latency, throughput, error rate (AD-016)
- Observability verification with `ObservabilityVerifier`, `ObservabilityMetric`, `MetricType` — structured logs, traces, metrics, SLO compliance (AD-022)
- Cost and token evaluation with `CostEvaluator`, `CostEvaluation` — per-request cost, deterministic-first ratio (AD-025)
- `services.security` package registered in `pyproject.toml`
- Phase 09 API import in `services/core/app.py`, version bumped to `0.9.0`
- 109 new Python tests (`tests/test_security_contracts.py`, `tests/test_security_services.py`) — 933 total
- Test-house evidence in `test-house/phase-09/evidence.md`

### Added — Phase 10: Release Engineering and Controlled Launch
- Final architecture review with `ReviewItem`, `ReviewCategory` (6 categories), `ReviewStatus`, `ArchitectureReviewService` with 5 gates (AD-033)
- Dependency verification with `DependencyRecord`, `DependencyStatus`, `DependencyVerificationService` — 8 pinned standard dependencies (AD-024)
- Release artifact integrity with `ReleaseArtifact`, `ArtifactType` (6 types), `IntegrityStatus`, SHA-256 checksum computation, `ReleaseArtifactService` (AD-024)
- Migration verification with `MigrationRecord`, `MigrationStatus`, `MigrationVerificationService` — applied/reversible/rollback-tested tracking (AD-024)
- Staging deployment with `StagingDeployment`, `DeploymentStatus`, `HealthCheckResult`, `StagingDeploymentService` (AD-024)
- Shadow/canary readiness with `CanaryDeployment`, `CanaryStatus` (5-stage: PENDING→SHADOW→CANARY_10→CANARY_50→CANARY_100→PROMOTED), `CanaryMetrics`, `CanaryService` with auto-abort on bad metrics (AD-024)
- Rollback testing with `RollbackTest`, `RollbackStatus` (PENDING is NOT blocking), `RollbackTestingService` — data integrity + financial-effects-preserved checks (AD-024)
- 8 operational runbooks with `OperationalRunbook`, `RunbookCategory`, `RunbookStep`, `RunbookService` — emergency stop, disaster recovery, split-brain, financial reconciliation, security incident, deployment, rollback, live activation — all with human-approval gates (AD-017, AD-028)
- User documentation with `DocumentationRecord`, `DocType`, `DocumentationService` — 3 user guides (AD-030)
- Administrator documentation — 3 admin guides + API reference + architecture doc + runbooks + release notes + compliance doc (AD-022)
- Release evidence package with `ReleaseEvidencePackage`, `EvidenceRecord`, `EvidenceType` (9 mandatory types), `ReleaseEvidenceService` (AD-032)
- Final readiness report with `FinalReadinessReport`, `ReadinessDecision` (GO/NO_GO/CONDITIONAL_GO), `ReadinessReportService.generate_report()` — 5 Section-23 gates, never sets `live_authorized` (AD-033)
- `services.release` package registered in `pyproject.toml`
- Phase 10 API endpoints in `services/core/app.py`
- 138 new Python tests (`tests/test_release_contracts.py`, `tests/test_release_services.py`) — 1071 total
- Test-house evidence in `test-house/phase-10/evidence.md`

### Security
- No secrets, credentials, or API keys committed to the repository
- `.gitignore` configured to prevent accidental secret commits
- Repository visibility noted as PUBLIC (see addendum A14 — default should be PRIVATE)
- Critical threat-model findings block release (`has_blocking_findings`)
- Disaster recovery requires human authorization before resumption (AD-017)
- Backup restoration verifies SHA-256 checksums (AD-028)
- `generate_report()` never sets `live_authorized` — verified by test
- F-SEC-02 (XOR encryption) and F-SEC-03 (in-memory identity store) remain unresolved release blockers for live operations

---

## [0.1.0-dev] — Not yet released

Prerelease identifier. No stable release has been made. All development is in Phase 01 (Engineering Foundation).

---

## Attribution

**Amin Azimi | AI Architect | End-to-End System Development Business Challenge | Azimi Innovation Lab**
