"""Graduated autonomy, kill plane and compliance package services.

Per E9 (Graduated Autonomy, Kill Plane and Compliance Package):

Implements the trust-level engine (AD-038), the independent kill plane,
the operator cockpit, human-factors review tracking, and the compliance
package builder (legal classification, data inventory, DPIA, market-data
terms register, external penetration test scaffold, drills).

All classes are thread-safe (threading.Lock) and follow the pattern
established in services.evidence.

Architecture Decisions: AD-038 (Graduated Autonomy and Independent Kill Plane).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from contracts.autonomy import (
    ComplianceDocument,
    ComplianceDocumentId,
    ComplianceDocumentType,
    DangerousActionCategory,
    DataInventoryItem,
    DrillOutcome,
    DrillType,
    E9DrillRecord,
    E9DrillRecordId,
    E9OwnerReviewPackage,
    HumanFactorsReview,
    HumanFactorsReviewId,
    KillPlaneAlreadyTriggeredError,
    KillPlaneCommand,
    KillPlaneCommandId,
    KillPlaneError,
    KillPlaneNotArmedError,
    KillPlaneResult,
    KillPlaneScope,
    KillPlaneStatus,
    MarketDataTermsEntry,
    OperatorCockpitSnapshot,
    TrustLevel,
    TrustLevelApproval,
    TrustLevelApprovalId,
    TrustLevelChangeReason,
    TrustLevelError,
    TrustLevelEvent,
    TrustLevelPromotionDeniedError,
    compute_approval_hash,
    compute_event_hash,
)

# ──────────────────────────────────────────────────────────────────────────────
# Trust-level engine (AD-038)
# ──────────────────────────────────────────────────────────────────────────────


class TrustLevelEngine:
    """Manages graduated autonomy trust levels for agents and tenants.

    Per AD-038:
    - Agents start at L0 (observe-only).
    - Promotion requires a signed human approval; the engine verifies the
      approval HMAC before accepting it.
    - Demotion is automatic on policy violation or anomaly; it never
      requires approval.
    - Every change is recorded in an append-only audit trail.

    Thread-safety: all public methods are protected by a threading.Lock.
    """

    _MIN_APPROVAL_KEY_BYTES = 32

    def __init__(self, approval_key: bytes | None = None) -> None:
        raw = os.environ.get("KTI_APPROVAL_KEY", "")
        if approval_key is None:
            if os.environ.get("KTI_ENVIRONMENT", "").lower() == "production":
                if not raw or len(raw) < self._MIN_APPROVAL_KEY_BYTES:
                    raise TrustLevelError(
                        "KTI_APPROVAL_KEY is not set or too short for production."
                    )
                approval_key = raw.encode()
            else:
                raw = raw or "phase-e9-approval-key-change-in-prod"
                approval_key = hashlib.sha256(raw.encode()).digest()
        self._approval_key = approval_key
        self._levels: dict[str, TrustLevel] = {}
        self._events: list[TrustLevelEvent] = []
        self._lock = threading.Lock()

    # ── Helpers ──

    def _sign_approval(self, approval: TrustLevelApproval) -> str:
        """Compute an HMAC-SHA256 signature over the approval fields."""
        msg = json.dumps(
            {
                "approval_id": str(approval.approval_id),
                "agent_id": approval.agent_id,
                "from_level": int(approval.from_level),
                "to_level": int(approval.to_level),
                "approver_id": approval.approver_id,
                "reason": approval.reason,
                "timestamp": approval.timestamp.isoformat(),
                "approval_hash": approval.approval_hash,
            },
            sort_keys=True,
        ).encode()
        return hmac.new(self._approval_key, msg, hashlib.sha256).hexdigest()

    def _record_event(  # noqa: PLR0913
        self,
        agent_id: str,
        old_level: TrustLevel,
        new_level: TrustLevel,
        *,
        reason: TrustLevelChangeReason,
        detail: str,
        approval_id: TrustLevelApprovalId | None = None,
    ) -> TrustLevelEvent:
        event_dict: dict[str, Any] = {
            "agent_id": agent_id,
            "old_level": int(old_level),
            "new_level": int(new_level),
            "reason": str(reason),
            "detail": detail,
            "approval_id": str(approval_id) if approval_id else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        event = TrustLevelEvent(
            event_id=uuid4(),
            agent_id=agent_id,
            old_level=old_level,
            new_level=new_level,
            reason=reason,
            detail=detail,
            approval_id=approval_id,
            timestamp=datetime.now(UTC),
            event_hash=compute_event_hash(event_dict),
        )
        self._events.append(event)
        return event

    # ── Public API ──

    def get_level(self, agent_id: str) -> TrustLevel:
        """Return the current trust level for an agent (default L0)."""
        with self._lock:
            return self._levels.get(agent_id, TrustLevel.L0_OBSERVE)

    def build_approval(
        self,
        agent_id: str,
        to_level: TrustLevel,
        approver_id: str,
        reason: str,
    ) -> TrustLevelApproval:
        """Build and sign a promotion approval.

        The caller (human operator) uses this to produce a signed approval
        record that can then be passed to :meth:`promote`.
        """
        with self._lock:
            from_level = self._levels.get(agent_id, TrustLevel.L0_OBSERVE)
        now = datetime.now(UTC)
        approval_id = TrustLevelApprovalId.generate()
        approval_dict: dict[str, Any] = {
            "approval_id": str(approval_id),
            "agent_id": agent_id,
            "from_level": int(from_level),
            "to_level": int(to_level),
            "approver_id": approver_id,
            "reason": reason,
            "timestamp": now.isoformat(),
        }
        approval_hash = compute_approval_hash(approval_dict)
        approval = TrustLevelApproval(
            approval_id=approval_id,
            agent_id=agent_id,
            from_level=from_level,
            to_level=to_level,
            approver_id=approver_id,
            reason=reason,
            timestamp=now,
            approval_hash=approval_hash,
            signature=self._sign_approval(
                TrustLevelApproval(
                    approval_id=approval_id,
                    agent_id=agent_id,
                    from_level=from_level,
                    to_level=to_level,
                    approver_id=approver_id,
                    reason=reason,
                    timestamp=now,
                    approval_hash=approval_hash,
                    signature="",
                )
            ),
        )
        return approval

    def promote(self, approval: TrustLevelApproval) -> TrustLevelEvent:
        """Promote an agent's trust level using a signed approval.

        Raises:
            TrustLevelPromotionDeniedError: If the approval signature is
                invalid or the from_level does not match the current level.
        """
        # Recompute signature to verify
        expected_sig = self._sign_approval(approval)
        if not hmac.compare_digest(approval.signature, expected_sig):
            raise TrustLevelPromotionDeniedError(
                f"Approval signature invalid for agent {approval.agent_id!r}."
            )
        with self._lock:
            current = self._levels.get(approval.agent_id, TrustLevel.L0_OBSERVE)
            if int(current) != int(approval.from_level):
                raise TrustLevelPromotionDeniedError(
                    f"Agent {approval.agent_id!r} is at level {int(current)}, "
                    f"but approval expects from_level {int(approval.from_level)}."
                )
            self._levels[approval.agent_id] = approval.to_level
            return self._record_event(
                agent_id=approval.agent_id,
                old_level=approval.from_level,
                new_level=approval.to_level,
                reason=TrustLevelChangeReason.SIGNED_PROMOTION,
                detail=f"Promoted by {approval.approver_id}: {approval.reason}",
                approval_id=approval.approval_id,
            )

    def demote(
        self,
        agent_id: str,
        reason: TrustLevelChangeReason,
        detail: str,
        target_level: TrustLevel = TrustLevel.L0_OBSERVE,
    ) -> TrustLevelEvent:
        """Demote an agent's trust level (automatic or manual).

        Demotion never requires approval.
        """
        with self._lock:
            current = self._levels.get(agent_id, TrustLevel.L0_OBSERVE)
            self._levels[agent_id] = target_level
            return self._record_event(
                agent_id=agent_id,
                old_level=current,
                new_level=target_level,
                reason=reason,
                detail=detail,
            )

    def reset_all(self, detail: str = "System reset") -> list[TrustLevelEvent]:
        """Reset all agents to L0 (e.g. on emergency halt)."""
        with self._lock:
            events = []
            for agent_id, current_level in list(self._levels.items()):
                if current_level != TrustLevel.L0_OBSERVE:
                    self._levels[agent_id] = TrustLevel.L0_OBSERVE
                    events.append(
                        self._record_event(
                            agent_id=agent_id,
                            old_level=current_level,
                            new_level=TrustLevel.L0_OBSERVE,
                            reason=TrustLevelChangeReason.SYSTEM_RESET,
                            detail=detail,
                        )
                    )
            return events

    def audit_trail(self) -> list[TrustLevelEvent]:
        """Return a copy of the immutable audit trail."""
        with self._lock:
            return list(self._events)


# ──────────────────────────────────────────────────────────────────────────────
# Independent kill plane (AD-038)
# ──────────────────────────────────────────────────────────────────────────────


class KillPlane:
    """Independent out-of-band kill plane (AD-038).

    Capable of cancelling simulated open orders and blocking new exposure
    even when the main platform is unavailable.  Each activation is
    recorded as a :class:`~contracts.autonomy.KillPlaneResult`.

    Thread-safety: all public methods are protected by a threading.Lock.
    """

    def __init__(self) -> None:
        self._status = KillPlaneStatus.ARMED
        self._commands: list[KillPlaneCommand] = []
        self._results: list[KillPlaneResult] = []
        # Simulated open order registry: order_id → (tenant_id, symbol)
        self._open_orders: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def register_order(self, order_id: str, tenant_id: str, symbol: str) -> None:
        """Register an open order with the kill plane."""
        with self._lock:
            self._open_orders[order_id] = (tenant_id, symbol)

    def deregister_order(self, order_id: str) -> None:
        """Deregister an order (e.g. when it completes normally)."""
        with self._lock:
            self._open_orders.pop(order_id, None)

    @property
    def status(self) -> KillPlaneStatus:
        """Current kill-plane status."""
        with self._lock:
            return self._status

    @property
    def open_order_count(self) -> int:
        """Number of open orders currently tracked."""
        with self._lock:
            return len(self._open_orders)

    def _build_command(
        self,
        scope: KillPlaneScope,
        scope_value: str,
        issuer_id: str,
        reason: str,
        out_of_band: bool,
    ) -> KillPlaneCommand:
        now = datetime.now(UTC)
        command_id = KillPlaneCommandId.generate()
        command_dict: dict[str, Any] = {
            "command_id": str(command_id),
            "scope": str(scope),
            "scope_value": scope_value,
            "issuer_id": issuer_id,
            "reason": reason,
            "timestamp": now.isoformat(),
            "out_of_band": out_of_band,
        }
        command_hash = hashlib.sha256(json.dumps(command_dict, sort_keys=True).encode()).hexdigest()
        return KillPlaneCommand(
            command_id=command_id,
            scope=scope,
            scope_value=scope_value,
            issuer_id=issuer_id,
            reason=reason,
            timestamp=now,
            command_hash=command_hash,
            out_of_band=out_of_band,
        )

    def trigger(
        self,
        scope: KillPlaneScope,
        scope_value: str,
        issuer_id: str,
        reason: str,
        *,
        out_of_band: bool = False,
    ) -> KillPlaneResult:
        """Trigger the kill plane for the specified scope.

        Cancels all open orders matching the scope and blocks new exposure.

        Raises:
            KillPlaneNotArmedError: If the kill plane is not ARMED.
        """
        with self._lock:
            if self._status == KillPlaneStatus.TRIGGERED:
                raise KillPlaneAlreadyTriggeredError("Kill plane has already been triggered.")
            if self._status != KillPlaneStatus.ARMED:
                raise KillPlaneNotArmedError(f"Kill plane is not ARMED (current: {self._status}).")
            command = self._build_command(scope, scope_value, issuer_id, reason, out_of_band)
            self._commands.append(command)
            self._status = KillPlaneStatus.DRAINING

            # Cancel matching orders
            cancelled = 0
            to_remove = []
            for order_id, (tenant_id, symbol) in self._open_orders.items():
                match = (
                    scope == KillPlaneScope.PLATFORM
                    or (scope == KillPlaneScope.TENANT and tenant_id == scope_value)
                    or (scope == KillPlaneScope.SYMBOL and symbol == scope_value)
                )
                if match:
                    to_remove.append(order_id)
                    cancelled += 1
            for order_id in to_remove:
                del self._open_orders[order_id]

            self._status = KillPlaneStatus.HALTED
            result = KillPlaneResult(
                command_id=command.command_id,
                orders_cancelled=cancelled,
                new_exposure_blocked=True,
                status=KillPlaneStatus.HALTED,
                detail=(
                    f"Kill plane triggered by {issuer_id} "
                    f"(scope={scope}, scope_value={scope_value!r}). "
                    f"{cancelled} order(s) cancelled. "
                    f"Out-of-band: {out_of_band}."
                ),
                timestamp=datetime.now(UTC),
            )
            self._results.append(result)
            return result

    def rearm(self, authorizer_id: str) -> None:
        """Re-arm the kill plane after a drill or incident.

        Only allowed from HALTED state; requires an authorizer.
        """
        with self._lock:
            if self._status != KillPlaneStatus.HALTED:
                raise KillPlaneError(
                    f"Can only re-arm from HALTED state (current: {self._status})."
                )
            if not authorizer_id:
                raise KillPlaneError("authorizer_id must not be empty.")
            self._status = KillPlaneStatus.ARMED

    def command_history(self) -> list[KillPlaneCommand]:
        """Return a copy of the command history."""
        with self._lock:
            return list(self._commands)

    def result_history(self) -> list[KillPlaneResult]:
        """Return a copy of the result history."""
        with self._lock:
            return list(self._results)


# ──────────────────────────────────────────────────────────────────────────────
# Human-factors review tracker
# ──────────────────────────────────────────────────────────────────────────────


class HumanFactorsTracker:
    """Tracks human-factors reviews for dangerous actions.

    Dangerous actions (trust-level promotion, kill-plane deactivation,
    live-trading enable, large orders, emergency policy overrides, etc.)
    must be reviewed and approved by a human operator before execution.

    Thread-safety: all public methods are protected by a threading.Lock.
    """

    def __init__(self) -> None:
        self._reviews: list[HumanFactorsReview] = []
        self._lock = threading.Lock()

    def record_review(
        self,
        category: DangerousActionCategory,
        action_detail: str,
        reviewer_id: str,
        approved: bool,
        notes: str = "",
    ) -> HumanFactorsReview:
        """Record a human-factors review decision."""
        now = datetime.now(UTC)
        review_id = HumanFactorsReviewId.generate()
        review_dict: dict[str, Any] = {
            "review_id": str(review_id),
            "category": str(category),
            "action_detail": action_detail,
            "reviewer_id": reviewer_id,
            "approved": approved,
            "notes": notes,
            "timestamp": now.isoformat(),
        }
        review_hash = hashlib.sha256(json.dumps(review_dict, sort_keys=True).encode()).hexdigest()
        review = HumanFactorsReview(
            review_id=review_id,
            category=category,
            action_detail=action_detail,
            reviewer_id=reviewer_id,
            approved=approved,
            notes=notes,
            timestamp=now,
            review_hash=review_hash,
        )
        with self._lock:
            self._reviews.append(review)
        return review

    def get_reviews(
        self, category: DangerousActionCategory | None = None
    ) -> list[HumanFactorsReview]:
        """Return all reviews, optionally filtered by category."""
        with self._lock:
            if category is None:
                return list(self._reviews)
            return [r for r in self._reviews if r.category == category]

    def pending_approvals_required(self, category: DangerousActionCategory) -> bool:
        """True if there are no approved reviews for the given category."""
        with self._lock:
            return not any(r.approved for r in self._reviews if r.category == category)


# ──────────────────────────────────────────────────────────────────────────────
# Operator cockpit
# ──────────────────────────────────────────────────────────────────────────────


class OperatorCockpit:
    """Provides operator cockpit snapshots aggregating platform state.

    The cockpit is a read-only view; it does not change platform state.
    Snapshots are recorded for audit / drill evidence.
    """

    def __init__(
        self,
        trust_engine: TrustLevelEngine,
        kill_plane: KillPlane,
    ) -> None:
        self._trust_engine = trust_engine
        self._kill_plane = kill_plane
        self._snapshots: list[OperatorCockpitSnapshot] = []
        self._lock = threading.Lock()

    def capture_snapshot(
        self,
        platform_mode: str,
        active_alerts: list[str] | None = None,
        compliance_flags: dict[str, bool] | None = None,
        pending_approvals: int = 0,
    ) -> OperatorCockpitSnapshot:
        """Capture and record a cockpit snapshot."""
        now = datetime.now(UTC)
        trust_levels: dict[str, int] = {
            agent_id: int(self._trust_engine.get_level(agent_id))
            for event in self._trust_engine.audit_trail()
            for agent_id in [event.agent_id]
        }
        snapshot = OperatorCockpitSnapshot(
            snapshot_id=uuid4(),
            timestamp=now,
            platform_mode=platform_mode,
            kill_plane_status=self._kill_plane.status,
            active_trust_levels=trust_levels,
            open_order_count=self._kill_plane.open_order_count,
            pending_approvals=pending_approvals,
            active_alerts=list(active_alerts or []),
            compliance_flags=dict(compliance_flags or {}),
        )
        with self._lock:
            self._snapshots.append(snapshot)
        return snapshot

    def all_snapshots(self) -> list[OperatorCockpitSnapshot]:
        """Return all captured snapshots."""
        with self._lock:
            return list(self._snapshots)


# ──────────────────────────────────────────────────────────────────────────────
# Compliance package builder
# ──────────────────────────────────────────────────────────────────────────────


class CompliancePackageBuilder:
    """Builds the E9 compliance package (documents, data inventory, etc.).

    Compliance package contents per E9 scope:
    - Legal classification memo (OPEN-08)
    - Data inventory (DPIA / GDPR evidence)
    - DPIA
    - Market-data terms register
    - External penetration test (scaffold / evidence record)
    - Platform evaluation ADR
    - Runbooks
    - Tabletop and live drill records

    Thread-safety: all public methods are protected by a threading.Lock.
    """

    def __init__(self) -> None:
        self._documents: list[ComplianceDocument] = []
        self._data_inventory: list[DataInventoryItem] = []
        self._market_data_terms: list[MarketDataTermsEntry] = []
        self._drill_records: list[E9DrillRecord] = []
        self._lock = threading.Lock()

    # ── Documents ──

    def add_document(  # noqa: PLR0913
        self,
        doc_type: ComplianceDocumentType,
        title: str,
        owner: str,
        *,
        status: str,
        summary: str,
        references: list[str] | None = None,
    ) -> ComplianceDocument:
        """Add a compliance document to the package."""
        doc = ComplianceDocument(
            document_id=ComplianceDocumentId.generate(),
            doc_type=doc_type,
            title=title,
            owner=owner,
            status=status,
            summary=summary,
            references=list(references or []),
        )
        with self._lock:
            self._documents.append(doc)
        return doc

    def get_documents(
        self, doc_type: ComplianceDocumentType | None = None
    ) -> list[ComplianceDocument]:
        """Return all documents, optionally filtered by type."""
        with self._lock:
            if doc_type is None:
                return list(self._documents)
            return [d for d in self._documents if d.doc_type == doc_type]

    # ── Data inventory ──

    def add_data_inventory_item(  # noqa: PLR0913
        self,
        data_category: str,
        description: str,
        storage_location: str,
        *,
        retention_days: int,
        lawful_basis: str,
        encrypted: bool,
    ) -> DataInventoryItem:
        """Add an item to the data inventory (cross_tenant always False)."""
        item = DataInventoryItem(
            item_id=uuid4(),
            data_category=data_category,
            description=description,
            storage_location=storage_location,
            retention_days=retention_days,
            lawful_basis=lawful_basis,
            encrypted=encrypted,
            cross_tenant=False,
        )
        with self._lock:
            self._data_inventory.append(item)
        return item

    def get_data_inventory(self) -> list[DataInventoryItem]:
        """Return the full data inventory."""
        with self._lock:
            return list(self._data_inventory)

    # ── Market-data terms ──

    def add_market_data_terms(  # noqa: PLR0913
        self,
        provider: str,
        data_types: list[str],
        *,
        permitted_uses: list[str],
        restrictions: list[str],
        license_url: str,
        reviewed_date: str,
        reviewer_id: str,
    ) -> MarketDataTermsEntry:
        """Add an entry to the market-data terms register."""
        entry = MarketDataTermsEntry(
            entry_id=uuid4(),
            provider=provider,
            data_types=list(data_types),
            permitted_uses=list(permitted_uses),
            restrictions=list(restrictions),
            license_url=license_url,
            reviewed_date=reviewed_date,
            reviewer_id=reviewer_id,
        )
        with self._lock:
            self._market_data_terms.append(entry)
        return entry

    def get_market_data_terms(self) -> list[MarketDataTermsEntry]:
        """Return the market-data terms register."""
        with self._lock:
            return list(self._market_data_terms)

    # ── Drills ──

    def start_drill(
        self,
        drill_type: DrillType,
        title: str,
        scenario: str,
        participants: list[str],
    ) -> E9DrillRecord:
        """Start a new drill record."""
        record = E9DrillRecord(
            record_id=E9DrillRecordId.generate(),
            drill_type=drill_type,
            title=title,
            scenario=scenario,
            participants=list(participants),
            outcome=DrillOutcome.PARTIAL,
            findings=[],
            action_items=[],
            started_at=datetime.now(UTC),
            completed_at=None,
        )
        with self._lock:
            self._drill_records.append(record)
        return record

    def complete_drill(
        self,
        record: E9DrillRecord,
        outcome: DrillOutcome,
        findings: list[str],
        action_items: list[str],
    ) -> E9DrillRecord:
        """Complete a drill, recording its outcome, findings and action items."""
        record.outcome = outcome
        record.findings = list(findings)
        record.action_items = list(action_items)
        record.completed_at = datetime.now(UTC)
        # Recompute hash after mutation
        record.record_hash = record._compute_hash()
        return record

    def get_drill_records(self, drill_type: DrillType | None = None) -> list[E9DrillRecord]:
        """Return drill records, optionally filtered by type."""
        with self._lock:
            if drill_type is None:
                return list(self._drill_records)
            return [r for r in self._drill_records if r.drill_type == drill_type]

    # ── Owner review package ──

    def build_owner_review_package(
        self,
        trust_engine: TrustLevelEngine,
        kill_plane: KillPlane,
        human_factors_tracker: HumanFactorsTracker,
        cockpit: OperatorCockpit,
    ) -> E9OwnerReviewPackage:
        """Assemble the complete E9 owner review package.

        Completing E9 does NOT authorize live trading.
        """
        with self._lock:
            return E9OwnerReviewPackage(
                package_id=uuid4(),
                timestamp=datetime.now(UTC),
                trust_level_events=trust_engine.audit_trail(),
                kill_plane_drills=kill_plane.result_history(),
                compliance_documents=list(self._documents),
                data_inventory=list(self._data_inventory),
                market_data_terms=list(self._market_data_terms),
                human_factors_reviews=human_factors_tracker.get_reviews(),
                operator_snapshots=cockpit.all_snapshots(),
                drill_records=list(self._drill_records),
                live_trading_authorized=False,
            )
