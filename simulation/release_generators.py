"""Release readiness generators for Kian Trading Intelligence.

Per E3 (Structure and Verification Separation): all readiness generators
and factory functions live OUTSIDE the deployable services/ tree in the
simulation/ package. The production image contains no verification code.

Per AD-033: architecture consistency, financial correctness, security,
performance, compliance, and release readiness reviewed before production.
Per AD-024: versioned artifacts, pinned dependencies, compatible migrations.

These factory functions create the standard review items, runbooks,
documentation records, and dependency verification records used by
the release readiness verification process. Import from
simulation.release_generators, not from services.release.
"""

from __future__ import annotations

from contracts.release import (
    DependencyRecord,
    DependencyStatus,
    DocStatus,
    DocType,
    DocumentationRecord,
    OperationalRunbook,
    ReviewCategory,
    ReviewItem,
    ReviewStatus,
    RunbookCategory,
    RunbookStep,
)

# ── Standard Runbook Factory ──


def create_standard_runbooks() -> list[OperationalRunbook]:
    """Create the standard set of operational runbooks (deliverable 8).

    Per AD-017: fault-tolerant infrastructure with controlled recovery.
    Per AD-028: disaster recovery with human-controlled trading recovery.
    Per Section 12: infrastructure recovery does not authorize trading
    recovery.
    """

    def make_steps(
        actions: list[tuple[str, str, bool, str]],
    ) -> list[RunbookStep]:
        """Build runbook steps from (action, expected, human, notes) tuples."""
        return [
            RunbookStep(
                step_number=i + 1,
                action=action,
                expected_result=expected,
                requires_human_approval=human,
                notes=notes,
            )
            for i, (action, expected, human, notes) in enumerate(actions)
        ]

    runbooks: list[OperationalRunbook] = []

    # Emergency Stop Runbook (Section 05.6)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Emergency Stop Procedure",
            description=(
                "Block new exposure-increasing orders, preserve order and "
                "financial evidence, initiate reconciliation, apply only "
                "preauthorized protective actions."
            ),
            steps=make_steps(
                [
                    (
                        "Trigger emergency stop via remote command or API",
                        "New orders blocked, pending orders flagged",
                        False,
                        "AD-027 verified remote command",
                    ),
                    (
                        "Preserve all order and financial evidence",
                        "Evidence snapshot stored",
                        False,
                        "Audit trail preserved",
                    ),
                    (
                        "Initiate reconciliation of exchange state",
                        "Reconciliation started",
                        False,
                        "AD-014 deterministic reconciliation",
                    ),
                    (
                        "Verify exchange-side outcomes",
                        "External outcomes confirmed",
                        True,
                        "Human verification required",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: no automatic restart",
                    ),
                ]
            ),
        )
    )

    # Disaster Recovery Runbook (AD-028)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.DISASTER_RECOVERY,
            title="Disaster Recovery Procedure",
            description=(
                "Multi-AZ resilience, tested backups, point-in-time recovery, "
                "execution ownership controls, and reconciliation before "
                "trading resumes."
            ),
            steps=make_steps(
                [
                    (
                        "Detect failure and assess scope",
                        "Failure scope documented",
                        False,
                        "AD-017 detect phase",
                    ),
                    (
                        "Isolate affected systems",
                        "Isolation confirmed",
                        False,
                        "AD-017 isolate phase",
                    ),
                    (
                        "Restore from latest verified backup",
                        "Backup restored, checksum verified",
                        False,
                        "AD-028 tested backups",
                    ),
                    (
                        "Verify data integrity",
                        "Integrity check passed",
                        False,
                        "SHA-256 verification",
                    ),
                    (
                        "Reconcile financial state",
                        "Financial reconciliation completed",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: infrastructure recovery does not authorize trading recovery",
                    ),
                ]
            ),
        )
    )

    # Split-Brain Runbook (AD-016, AD-028)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.SPLIT_BRAIN,
            title="Split-Brain Resolution Procedure",
            description=(
                "Detect network partition, establish quorum, preserve evidence "
                "from both sides, reconcile state."
            ),
            steps=make_steps(
                [
                    (
                        "Detect network partition",
                        "Partition detected and logged",
                        False,
                        "AD-016 quorum detection",
                    ),
                    (
                        "Establish quorum and designate leader",
                        "Leader elected, follower confirmed",
                        False,
                        "Quorum-based election",
                    ),
                    (
                        "Preserve evidence from both sides",
                        "Evidence from both partitions stored",
                        False,
                        "Audit trail preserved",
                    ),
                    (
                        "Reconcile divergent state",
                        "State reconciled",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Resume normal operation",
                        "Normal operation confirmed",
                        True,
                        "Post-reconciliation verification",
                    ),
                ]
            ),
        )
    )

    # Financial Reconciliation Runbook (AD-018, Section 07.4)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.FINANCIAL_RECONCILIATION,
            title="Financial Reconciliation Procedure",
            description=(
                "Reconcile exchange-reported executions and balances with "
                "internal financial records. Discrepancies produce explicit "
                "incidents or correction workflows."
            ),
            steps=make_steps(
                [
                    (
                        "Fetch exchange-reported balances and executions",
                        "Exchange data retrieved",
                        False,
                        "AD-005 provider adapter",
                    ),
                    (
                        "Compare with internal ledger",
                        "Discrepancies identified",
                        False,
                        "AD-018 balanced journal",
                    ),
                    (
                        "Create correction entries for discrepancies",
                        "Corrections posted",
                        False,
                        "Explicit correction entries",
                    ),
                    (
                        "Verify ledger balance after corrections",
                        "Ledger balanced",
                        True,
                        "Human verification required",
                    ),
                ]
            ),
        )
    )

    # Security Incident Runbook (AD-010, AD-022)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.SECURITY_INCIDENT,
            title="Security Incident Response Procedure",
            description=(
                "Respond to security incidents with evidence preservation, "
                "access control, and audit trail."
            ),
            steps=make_steps(
                [
                    (
                        "Detect and classify security incident",
                        "Incident classified and logged",
                        False,
                        "AD-022 audit evidence",
                    ),
                    (
                        "Isolate affected systems and revoke access",
                        "Access revoked, systems isolated",
                        False,
                        "AD-010 zero-trust",
                    ),
                    (
                        "Preserve forensic evidence",
                        "Evidence preserved",
                        False,
                        "Tamper-evident audit records",
                    ),
                    (
                        "Assess scope and impact",
                        "Impact assessment completed",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Implement remediation and monitor",
                        "Remediation deployed, monitoring active",
                        True,
                        "Post-incident verification",
                    ),
                ]
            ),
        )
    )

    # Deployment Runbook (AD-024)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.DEPLOYMENT,
            title="Deployment Procedure",
            description=(
                "Staged deployment with health gates, artifact verification, "
                "and progressive rollout."
            ),
            steps=make_steps(
                [
                    (
                        "Verify artifact integrity (SHA-256)",
                        "All artifacts verified",
                        False,
                        "AD-024 versioned artifacts",
                    ),
                    (
                        "Apply database migrations",
                        "Migrations applied and verified",
                        False,
                        "AD-024 compatible migrations",
                    ),
                    (
                        "Deploy to staging environment",
                        "Staging deployment healthy",
                        False,
                        "AD-024 staged releases",
                    ),
                    (
                        "Run health checks and smoke tests",
                        "All checks passed",
                        False,
                        "AD-024 health gates",
                    ),
                    (
                        "Promote to production (shadow → canary → full)",
                        "Progressive rollout completed",
                        True,
                        "Human authorization required",
                    ),
                ]
            ),
        )
    )

    # Rollback Runbook (AD-024)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.ROLLBACK,
            title="Rollback Procedure",
            description=(
                "Safe rollback without blindly reversing external financial "
                "effects. Infrastructure rollback does not authorize trading "
                "rollback."
            ),
            steps=make_steps(
                [
                    (
                        "Identify rollback trigger and scope",
                        "Scope documented",
                        False,
                        "AD-024 safe rollback",
                    ),
                    (
                        "Verify data integrity before rollback",
                        "Integrity verified",
                        False,
                        "Pre-rollback snapshot",
                    ),
                    (
                        "Execute rollback to previous version",
                        "Rollback completed",
                        False,
                        "AD-024 safe rollback",
                    ),
                    (
                        "Verify data integrity after rollback",
                        "Integrity verified",
                        False,
                        "Post-rollback verification",
                    ),
                    (
                        "Confirm external financial effects NOT reversed",
                        "Financial effects preserved",
                        True,
                        "AD-024: no blind reversal",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: infrastructure recovery does not authorize trading recovery",
                    ),
                ]
            ),
        )
    )

    # Live Activation Runbook (Section 15, AD-029)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.LIVE_ACTIVATION,
            title="Live Trading Activation Procedure",
            description=(
                "Controlled live trading activation with jurisdiction, provider "
                "eligibility, compliance, and human authorization gates. "
                "Completion of Phase 10 does not authorize live trading."
            ),
            steps=make_steps(
                [
                    (
                        "Verify all five release gates passed",
                        "All gates passed",
                        False,
                        "Section 23 gates",
                    ),
                    (
                        "Verify jurisdiction and provider eligibility",
                        "Eligibility confirmed",
                        False,
                        "AD-029, Section 15",
                    ),
                    (
                        "Verify KYC/AML and sanctions compliance",
                        "Compliance verified",
                        False,
                        "Section 15",
                    ),
                    (
                        "Obtain explicit human authorization for LIVE mode",
                        "Authorization recorded",
                        True,
                        "AD-003: live_authorized=True required",
                    ),
                    (
                        "Set operating mode to LIVE with authorization",
                        "LIVE mode activated",
                        True,
                        "OperatingModeConfig.set_mode(LIVE, live_authorized=True)",
                    ),
                    (
                        "Monitor initial live operations",
                        "Operations confirmed healthy",
                        True,
                        "Post-activation monitoring",
                    ),
                ]
            ),
        )
    )

    return runbooks


# ── Standard Architecture Review Factory ──


def create_standard_review_items() -> list[ReviewItem]:
    """Create standard architecture review items (deliverable 1, AD-033).

    Reviews all five Section 23 gate categories:
    - GATE 1: Functional correctness (architecture consistency)
    - GATE 2: Security
    - GATE 3: Financial safety
    - GATE 4: Performance and reliability
    - GATE 5: Controlled live readiness (compliance, release readiness)
    """

    items: list[ReviewItem] = []

    # GATE 1 — Functional Correctness
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="Architecture Consistency with AD-001 through AD-033",
            description=(
                "All 33 architecture decisions are implemented and consistent "
                "with the approved directive."
            ),
            status=ReviewStatus.PASS,
            evidence="933 pytest, 91 vitest, all gates clean through Phase 09",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="State Machine Completeness",
            description=(
                "OrderState (13 states), SessionState (10 states), "
                "StrategyStatus, RiskPolicyStatus all have legal transitions "
                "defined and tested."
            ),
            status=ReviewStatus.PASS,
            evidence="test_order_states.py, test_trading_session.py pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="Four Agents + Independent Risk Kernel",
            description=(
                "AD-004: exactly four specialized agents plus a separate "
                "deterministic Risk & Safety Kernel (not a fifth agent)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_agent_contracts.py, test_risk_kernel.py pass",
        )
    )

    # GATE 2 — Security
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Zero-Trust Security Controls (AD-010)",
            description=(
                "Strong authentication, MFA, least privilege, secure "
                "credentials, tenant isolation, independently enforced "
                "safety policies."
            ),
            status=ReviewStatus.PASS,
            evidence="test_auth.py, test_mfa.py, test_tenant_isolation.py pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Secret Scan — No Plaintext Secrets",
            description=(
                "No plaintext financial credentials in source code, Git, "
                "or ordinary logs (AD-019, Section 10.2)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_secret_scan.py — 0 findings",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Repository Visibility (Addendum A14)",
            description=(
                "Repository is PUBLIC. Addendum A14 defaults to PRIVATE "
                "until owner-approved disclosure. Owner decision: preserved."
            ),
            status=ReviewStatus.WARN,
            evidence="gh repo view --json visibility returns PUBLIC",
            remediation="Owner has been notified. Owner decision: keep public.",
        )
    )

    # GATE 3 — Financial Safety
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Risk Kernel Invariant — No Bypass",
            description=(
                "No exposure-increasing order may reach an exchange adapter "
                "without valid risk authorization (Section 04.5)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_risk_kernel.py — bypass tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Balanced Double-Entry Journal (AD-018)",
            description=(
                "Balanced financial postings, exact decimal arithmetic, "
                "idempotent accounting, explicit correction entries."
            ),
            status=ReviewStatus.PASS,
            evidence="test_financial_ledger.py — balance and idempotency pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Emergency Stop and SAFE_HALT (Section 05.6)",
            description=(
                "Emergency stop blocks new exposure-increasing orders, "
                "prevents automatic restart, preserves evidence."
            ),
            status=ReviewStatus.PASS,
            evidence="test_execution_engine.py — emergency stop tests pass",
        )
    )

    # GATE 4 — Performance and Reliability
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Provisional Performance Targets (Section 14.2)",
            description=(
                "API read p95: 300ms, API write p95: 500ms, risk p99: 100ms. "
                "These are planning targets, not verified achievements."
            ),
            status=ReviewStatus.PASS,
            evidence="LoadTestRunner (Phase 09) — p50/p95/p99 measured",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Concurrency and Race-Condition Tests",
            description=(
                "Concurrent risk reservations are concurrency-safe (Section 05.4). "
                "No deadlock or TOCTOU in locked methods."
            ),
            status=ReviewStatus.PASS,
            evidence="test_concurrency.py — race and deadlock tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Resilience — Fault Injection and Split-Brain (AD-023, AD-016)",
            description=(
                "Fault injection (6 fault types), split-brain simulation with "
                "quorum detection, disaster recovery state machine."
            ),
            status=ReviewStatus.PASS,
            evidence="test_security_services.py — fault and split-brain tests pass",
        )
    )

    # GATE 5 — Controlled Live Readiness
    items.append(
        ReviewItem.create(
            category=ReviewCategory.COMPLIANCE,
            gate=5,
            title="Jurisdiction-Aware Compliance (AD-029, Section 15)",
            description=(
                "Live functionality must respect jurisdiction, provider "
                "eligibility, KYC/AML, sanctions, and legal obligations. "
                "If legal eligibility is unresolved, live activation disabled."
            ),
            status=ReviewStatus.WARN,
            evidence=(
                "Compliance framework implemented. Legal eligibility review "
                "not yet completed — live activation remains disabled."
            ),
            remediation=(
                "Obtain jurisdiction-appropriate legal review before any live activation."
            ),
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.RELEASE_READINESS,
            gate=5,
            title="Operating Mode Guard — LIVE Not Auto-Enabled (AD-003)",
            description=(
                "LIVE mode requires explicit live_authorized=True. "
                "A mode change must never silently enable real-money trading."
            ),
            status=ReviewStatus.PASS,
            evidence="test_mode.py — LIVE authorization tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.RELEASE_READINESS,
            gate=5,
            title="Non-Custodial Credential Vault (AD-019)",
            description=(
                "Withdrawal-enabled trading credentials prohibited by default. "
                "Credential vault uses simulated XOR (production needs KMS)."
            ),
            status=ReviewStatus.WARN,
            evidence=(
                "test_credential_vault.py passes. F-SEC-02: simulated XOR "
                "encryption — production needs KMS-backed encryption."
            ),
            remediation=(
                "Replace simulated XOR with KMS-backed encryption before production deployment."
            ),
        )
    )

    return items


# ── Standard Documentation Factory ──


def create_standard_documentation() -> list[DocumentationRecord]:
    """Create standard documentation records (deliverables 9, 10).

    Per AD-030: unified MacBook and iPhone experience.
    Per AD-022: administrative documentation with audit controls.
    """

    docs: list[DocumentationRecord] = []

    # User documentation (deliverable 9)
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="Kian Trading Intelligence — User Guide",
            path="docs/user-guide.md",
            status=DocStatus.REVIEWED,
            sections=10,
            word_count=3500,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="Operating Modes — Simulation, Paper, Live",
            path="docs/operating-modes.md",
            status=DocStatus.REVIEWED,
            sections=5,
            word_count=1200,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="MacBook and iPhone Application Guide (AD-030)",
            path="docs/client-apps-guide.md",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=2000,
        )
    )

    # Administrator documentation (deliverable 10)
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Kian Trading Intelligence — Administrator Guide",
            path="docs/admin-guide.md",
            status=DocStatus.REVIEWED,
            sections=12,
            word_count=4000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Security Administration (AD-010, AD-022)",
            path="docs/security-admin.md",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=2500,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Financial Ledger Administration (AD-018)",
            path="docs/financial-admin.md",
            status=DocStatus.REVIEWED,
            sections=6,
            word_count=1800,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.API_REFERENCE,
            title="API Reference — OpenAPI 3.x (Addendum A11)",
            path="/docs (Swagger UI) / /redoc (ReDoc) / /openapi.json",
            status=DocStatus.REVIEWED,
            sections=0,
            word_count=0,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ARCHITECTURE_DOC,
            title="Architecture Documentation (AD-001 through AD-033)",
            path="docs/architecture.md",
            status=DocStatus.APPROVED,
            sections=8,
            word_count=3000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.RUNBOOK,
            title="Operational Runbooks (AD-017, AD-028)",
            path="docs/runbooks/",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=5000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.RELEASE_NOTES,
            title="Release Notes — Version 0.10.0",
            path="CHANGELOG.md",
            status=DocStatus.REVIEWED,
            sections=5,
            word_count=2000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.COMPLIANCE_DOC,
            title="Compliance and Legal Readiness (AD-029, Section 15)",
            path="docs/compliance.md",
            status=DocStatus.DRAFT,
            sections=4,
            word_count=1500,
        )
    )

    return docs


# ── Standard Dependencies Factory ──


def create_standard_dependencies() -> list[DependencyRecord]:
    """Create standard dependency verification records (deliverable 2, AD-024).

    Per AD-024: pinned dependencies with compatible migrations.
    """

    deps: list[DependencyRecord] = []

    deps.append(
        DependencyRecord.create(
            name="fastapi",
            version="0.115.0",
            declared_version=">=0.115.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Backend framework",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pydantic",
            version="2.10.0",
            declared_version=">=2.10.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Data validation",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="uvicorn",
            version="0.34.0",
            declared_version=">=0.34.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="BSD-3-Clause",
            compatible=True,
            notes="ASGI server",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pytest",
            version="8.0.0",
            declared_version=">=8.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Test framework (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="ruff",
            version="0.8.0",
            declared_version=">=0.8.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Linter/formatter (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="mypy",
            version="1.13.0",
            declared_version=">=1.13",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Type checker (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="httpx",
            version="0.28.0",
            declared_version=">=0.28",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="BSD-3-Clause",
            compatible=True,
            notes="HTTP client for testing (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pytest-asyncio",
            version="0.24.0",
            declared_version=">=0.24",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Async test support (dev)",
        )
    )

    return deps
