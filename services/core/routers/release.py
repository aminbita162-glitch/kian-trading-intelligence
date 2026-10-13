"""Release engineering API router for Kian Trading Intelligence.

Per AD-033: architecture consistency, financial correctness, security,
performance, compliance, and release readiness reviewed before production.
Per AD-024: versioned artifacts, pinned dependencies, compatible migrations.
Per Section 23: five release gates must all pass for a GO decision.
"""

from __future__ import annotations

from fastapi import APIRouter

from services.release import (
    ArchitectureReviewService,
    CanaryService,
    DependencyVerificationService,
    DocumentationService,
    MigrationVerificationService,
    ReadinessReportService,
    ReleaseArtifactService,
    ReleaseEvidenceService,
    RollbackTestingService,
    RunbookService,
    StagingDeploymentService,
)

router = APIRouter(tags=["Release"])

# ── Service singletons ──
_architecture_review_service = ArchitectureReviewService()
_dependency_verification_service = DependencyVerificationService()
_artifact_service = ReleaseArtifactService()
_migration_service = MigrationVerificationService()
_staging_service = StagingDeploymentService()
_canary_service = CanaryService()
_rollback_service = RollbackTestingService()
_runbook_service = RunbookService()
_doc_service = DocumentationService()
_release_evidence_service = ReleaseEvidenceService(release_version="0.10.0")
_readiness_report_service = ReadinessReportService()


# ── Endpoints ──


@router.get("/release/architecture-review")
async def get_architecture_review() -> dict[str, object]:
    """Get the architecture review status (deliverable 1, AD-033).

    Per AD-033: architecture consistency, financial correctness, security,
    performance, compliance, and release readiness reviewed before production.
    """
    items = _architecture_review_service.items
    return {
        "total_items": len(items),
        "blocking": len(_architecture_review_service.blocking_items),
        "warnings": len(_architecture_review_service.warnings),
        "gate_summary": _architecture_review_service.gate_summary,
    }


@router.get("/release/dependencies")
async def get_dependencies() -> dict[str, object]:
    """Get dependency verification status (deliverable 2, AD-024)."""
    deps = _dependency_verification_service.dependencies
    return {
        "total": len(deps),
        "all_pinned": _dependency_verification_service.all_pinned,
        "all_compatible": _dependency_verification_service.all_compatible,
        "blocking": len(_dependency_verification_service.blocking_dependencies),
    }


@router.get("/release/artifacts")
async def get_artifacts() -> dict[str, object]:
    """Get release artifact integrity status (deliverable 3, AD-024)."""
    artifacts = _artifact_service.artifacts
    return {
        "total": len(artifacts),
        "all_verified": _artifact_service.all_verified,
        "blocking": len(_artifact_service.blocking_artifacts),
    }


@router.get("/release/migrations")
async def get_migrations() -> dict[str, object]:
    """Get migration verification status (deliverable 4, AD-024)."""
    migrations = _migration_service.migrations
    return {
        "total": len(migrations),
        "all_applied": _migration_service.all_applied,
        "all_reversible": _migration_service.all_reversible,
        "all_rollback_tested": _migration_service.all_rollback_tested,
        "blocking": len(_migration_service.blocking_migrations),
    }


@router.get("/release/deployment")
async def get_deployment_status() -> dict[str, object]:
    """Get staging deployment status (deliverable 5, AD-024)."""
    deployment = _staging_service.latest_deployment
    if deployment is None:
        return {
            "status": "no_deployment",
            "version": None,
            "healthy": False,
        }
    return {
        "status": deployment.status.value,
        "version": deployment.version,
        "healthy": deployment.all_health_checks_passed,
        "health_checks": len(deployment.health_checks),
        "config_validated": deployment.config_validated,
        "secrets_referenced": deployment.secrets_referenced,
    }


@router.get("/release/canary")
async def get_canary_status() -> dict[str, object]:
    """Get canary deployment status (deliverable 6, AD-024)."""
    canary = _canary_service.latest_canary
    if canary is None:
        return {
            "status": "no_canary",
            "version": None,
        }
    return {
        "status": canary.status.value,
        "version": canary.version,
        "metrics": {
            "error_rate": canary.metrics.error_rate,
            "latency_p95_ms": canary.metrics.latency_p95_ms,
            "latency_p99_ms": canary.metrics.latency_p99_ms,
        }
        if canary.metrics
        else None,
    }


@router.get("/release/rollback")
async def get_rollback_status() -> dict[str, object]:
    """Get rollback test status (deliverable 7, AD-024)."""
    rollbacks = _rollback_service.rollbacks
    return {
        "total": len(rollbacks),
        "all_verified": _rollback_service.all_verified,
        "blocking": len(_rollback_service.blocking_rollbacks),
    }


@router.get("/release/runbooks")
async def get_runbooks() -> dict[str, object]:
    """Get operational runbooks (deliverable 8, AD-017, AD-028)."""
    runbooks = _runbook_service.runbooks
    return {
        "total": len(runbooks),
        "all_have_human_gates": _runbook_service.all_have_human_gates,
        "categories": [r.category.value for r in runbooks],
    }


@router.get("/release/documentation")
async def get_documentation_status() -> dict[str, object]:
    """Get documentation status (deliverables 9, 10, AD-030, AD-022)."""
    docs = _doc_service.docs
    return {
        "total": len(docs),
        "user_docs": len(_doc_service.user_docs),
        "admin_docs": len(_doc_service.admin_docs),
        "blocking": len(_doc_service.blocking_docs),
    }


@router.get("/release/readiness")
async def get_readiness_report() -> dict[str, object]:
    """Get the final readiness report (deliverable 12, AD-033).

    Per Section 17 PHASE 10: Completion does not authorize live trading.
    Per Section 23: Five release gates must all pass for a GO decision.
    """
    report = _readiness_report_service.report
    if report is None:
        return {
            "status": "not_generated",
            "message": "Readiness report has not been generated yet.",
        }
    return {
        "release_version": report.release_version,
        "decision": report.decision.value,
        "all_gates_passed": report.all_gates_passed,
        "is_go": report.is_go,
        "can_activate_live": report.can_activate_live,
        "live_authorized": report.live_authorized,
        "mining_authorized": report.mining_authorized,
        "gates": [
            {
                "gate": g.gate_number,
                "name": g.gate_name,
                "passed": g.passed,
                "evidence_count": g.evidence_count,
            }
            for g in report.gates
        ],
        "blocking_items": report.blocking_items,
        "remaining_risks": report.remaining_risks,
        "generated_at": report.generated_at.isoformat(),
    }
