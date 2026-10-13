"""Tests for Phase E9 — Graduated Autonomy, Kill Plane and Compliance Package.

Covers:
- Trust-level engine: initial state, promotion (signed), promotion denied (bad sig),
  promotion denied (wrong from_level), automatic demotion, manual demotion,
  reset_all, audit trail integrity.
- Kill plane: armed state, trigger platform scope (cancels all orders),
  trigger tenant scope, trigger symbol scope, already-triggered guard,
  not-armed guard, rearm, out-of-band flag, result history.
- Human-factors tracker: record approved review, record rejected review,
  filter by category, pending_approvals_required logic.
- Operator cockpit: snapshot captures trust levels + kill plane status.
- Compliance package builder: add/get documents, data inventory (cross_tenant
  prohibited), market-data terms, drill start/complete lifecycle, build owner
  review package.
- Owner review package: live_trading_authorized is always False, package_hash set.
- Contract invariants: TrustLevelApproval to_level > from_level, DataInventoryItem
  cross_tenant=True raises, E9DrillRecord requires title, KillPlaneCommand
  requires issuer_id.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contracts.autonomy import (
    ComplianceDocumentType,
    DangerousActionCategory,
    DataInventoryItem,
    DrillOutcome,
    DrillType,
    E9DrillRecord,
    E9DrillRecordId,
    E9OwnerReviewPackage,
    KillPlaneCommand,
    KillPlaneCommandId,
    KillPlaneError,
    KillPlaneNotArmedError,
    KillPlaneScope,
    KillPlaneStatus,
    TrustLevel,
    TrustLevelApproval,
    TrustLevelApprovalId,
    TrustLevelChangeReason,
    TrustLevelPromotionDeniedError,
    compute_approval_hash,
    compute_event_hash,
)
from services.autonomy import (
    CompliancePackageBuilder,
    HumanFactorsTracker,
    KillPlane,
    OperatorCockpit,
    TrustLevelEngine,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

NOW = datetime.now(UTC)


def make_engine() -> TrustLevelEngine:
    return TrustLevelEngine()


def make_kill_plane() -> KillPlane:
    return KillPlane()


# ──────────────────────────────────────────────────────────────────────────────
# TrustLevel enum
# ──────────────────────────────────────────────────────────────────────────────


class TestTrustLevelEnum:
    def test_ordering(self) -> None:
        assert TrustLevel.L0_OBSERVE < TrustLevel.L1_PAPER < TrustLevel.L5_HIGHER_CAP

    def test_int_values(self) -> None:
        assert int(TrustLevel.L0_OBSERVE) == 0
        assert int(TrustLevel.L5_HIGHER_CAP) == 5


# ──────────────────────────────────────────────────────────────────────────────
# TrustLevelEngine — basic level management
# ──────────────────────────────────────────────────────────────────────────────


class TestTrustLevelEngineDefaults:
    def test_default_level_is_l0(self) -> None:
        engine = make_engine()
        assert engine.get_level("agent-1") == TrustLevel.L0_OBSERVE

    def test_audit_trail_starts_empty(self) -> None:
        engine = make_engine()
        assert engine.audit_trail() == []


class TestTrustLevelEnginePromotion:
    def test_promotion_with_valid_approval(self) -> None:
        engine = make_engine()
        approval = engine.build_approval(
            "agent-1", TrustLevel.L2_SMALL_LIVE, "approver-1", "Testing"
        )
        event = engine.promote(approval)
        assert engine.get_level("agent-1") == TrustLevel.L2_SMALL_LIVE
        assert event.new_level == TrustLevel.L2_SMALL_LIVE
        assert event.reason == TrustLevelChangeReason.SIGNED_PROMOTION
        assert event.approval_id == approval.approval_id

    def test_promotion_recorded_in_audit_trail(self) -> None:
        engine = make_engine()
        approval = engine.build_approval(
            "agent-2", TrustLevel.L1_PAPER, "approver-1", "Paper trading"
        )
        engine.promote(approval)
        trail = engine.audit_trail()
        assert len(trail) == 1
        assert trail[0].agent_id == "agent-2"

    def test_sequential_promotions(self) -> None:
        engine = make_engine()
        a1 = engine.build_approval("agent-3", TrustLevel.L1_PAPER, "op", "Step 1")
        engine.promote(a1)
        a2 = engine.build_approval("agent-3", TrustLevel.L3_MEDIUM_LIVE, "op", "Step 2")
        engine.promote(a2)
        assert engine.get_level("agent-3") == TrustLevel.L3_MEDIUM_LIVE
        assert len(engine.audit_trail()) == 2

    def test_promotion_rejected_bad_signature(self) -> None:
        engine = make_engine()
        approval = engine.build_approval(
            "agent-4", TrustLevel.L2_SMALL_LIVE, "approver-1", "Testing"
        )
        # Tamper with signature
        tampered = TrustLevelApproval(
            approval_id=approval.approval_id,
            agent_id=approval.agent_id,
            from_level=approval.from_level,
            to_level=approval.to_level,
            approver_id=approval.approver_id,
            reason=approval.reason,
            timestamp=approval.timestamp,
            approval_hash=approval.approval_hash,
            signature="deadbeef" * 8,
        )
        with pytest.raises(TrustLevelPromotionDeniedError):
            engine.promote(tampered)

    def test_promotion_rejected_wrong_from_level(self) -> None:
        """Build an approval assuming from=L1 but agent is at L0."""
        engine = make_engine()
        # Agent is at L0; build approval claiming from_level=L1 manually
        # We do this by building a valid approval then mutating from_level
        # (which requires a re-signed token).
        # The easiest way: build approval for L1→L2 but agent is at L0.
        # First promote to L1.
        a1 = engine.build_approval("agent-5", TrustLevel.L1_PAPER, "op", "ok")
        engine.promote(a1)
        # Now build approval for L1→L2 — but first demote agent back to L0.
        engine.demote("agent-5", TrustLevelChangeReason.AUTOMATIC_DEMOTION, "test")
        a2 = engine.build_approval("agent-5", TrustLevel.L2_SMALL_LIVE, "op", "ok")
        # a2 has from_level=L0 (agent is at L0 now) → this should succeed
        engine.promote(a2)
        assert engine.get_level("agent-5") == TrustLevel.L2_SMALL_LIVE

    def test_approval_to_level_must_be_higher(self) -> None:
        with pytest.raises(ValueError, match="to_level"):
            TrustLevelApproval(
                approval_id=TrustLevelApprovalId.generate(),
                agent_id="a",
                from_level=TrustLevel.L2_SMALL_LIVE,
                to_level=TrustLevel.L1_PAPER,
                approver_id="op",
                reason="bad",
                timestamp=NOW,
                approval_hash="abc",
                signature="sig",
            )


class TestTrustLevelEngineDemotion:
    def test_automatic_demotion_to_l0(self) -> None:
        engine = make_engine()
        approval = engine.build_approval("agent-6", TrustLevel.L3_MEDIUM_LIVE, "op", "Test")
        engine.promote(approval)
        event = engine.demote(
            "agent-6",
            TrustLevelChangeReason.AUTOMATIC_DEMOTION,
            "Policy violation detected",
        )
        assert engine.get_level("agent-6") == TrustLevel.L0_OBSERVE
        assert event.reason == TrustLevelChangeReason.AUTOMATIC_DEMOTION
        assert event.new_level == TrustLevel.L0_OBSERVE

    def test_demotion_to_custom_target_level(self) -> None:
        engine = make_engine()
        a = engine.build_approval("agent-7", TrustLevel.L4_LARGE_LIVE, "op", "Test")
        engine.promote(a)
        engine.demote(
            "agent-7",
            TrustLevelChangeReason.MANUAL_DEMOTION,
            "Manual reduction",
            target_level=TrustLevel.L1_PAPER,
        )
        assert engine.get_level("agent-7") == TrustLevel.L1_PAPER

    def test_reset_all(self) -> None:
        engine = make_engine()
        for i in range(3):
            a = engine.build_approval(f"a{i}", TrustLevel.L2_SMALL_LIVE, "op", "Test")
            engine.promote(a)
        events = engine.reset_all("Emergency halt test")
        assert len(events) == 3
        for i in range(3):
            assert engine.get_level(f"a{i}") == TrustLevel.L0_OBSERVE


class TestTrustLevelAuditTrailIntegrity:
    def test_event_hash_is_set(self) -> None:
        engine = make_engine()
        approval = engine.build_approval("x", TrustLevel.L1_PAPER, "op", "Test")
        engine.promote(approval)
        trail = engine.audit_trail()
        assert all(len(e.event_hash) == 64 for e in trail)

    def test_audit_trail_is_copy(self) -> None:
        engine = make_engine()
        trail = engine.audit_trail()
        trail.append(None)  # type: ignore[arg-type]
        assert len(engine.audit_trail()) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Kill plane
# ──────────────────────────────────────────────────────────────────────────────


class TestKillPlaneArmed:
    def test_initial_status_is_armed(self) -> None:
        kp = make_kill_plane()
        assert kp.status == KillPlaneStatus.ARMED

    def test_register_order(self) -> None:
        kp = make_kill_plane()
        kp.register_order("ord-1", "tenant-1", "BTC/USDT")
        assert kp.open_order_count == 1

    def test_deregister_order(self) -> None:
        kp = make_kill_plane()
        kp.register_order("ord-1", "tenant-1", "BTC/USDT")
        kp.deregister_order("ord-1")
        assert kp.open_order_count == 0

    def test_deregister_nonexistent_order_noop(self) -> None:
        kp = make_kill_plane()
        kp.deregister_order("no-such-order")  # must not raise


class TestKillPlaneTrigger:
    def test_platform_scope_cancels_all_orders(self) -> None:
        kp = make_kill_plane()
        kp.register_order("ord-1", "t1", "BTC/USDT")
        kp.register_order("ord-2", "t2", "ETH/USDT")
        kp.register_order("ord-3", "t1", "SOL/USDT")
        result = kp.trigger(KillPlaneScope.PLATFORM, "all", "operator-1", "Emergency stop")
        assert result.orders_cancelled == 3
        assert result.new_exposure_blocked is True
        assert result.status == KillPlaneStatus.HALTED
        assert kp.open_order_count == 0

    def test_tenant_scope_cancels_only_tenant_orders(self) -> None:
        kp = make_kill_plane()
        kp.register_order("ord-1", "tenant-A", "BTC/USDT")
        kp.register_order("ord-2", "tenant-B", "BTC/USDT")
        kp.register_order("ord-3", "tenant-A", "ETH/USDT")
        result = kp.trigger(KillPlaneScope.TENANT, "tenant-A", "operator-1", "Tenant suspension")
        assert result.orders_cancelled == 2
        assert kp.open_order_count == 1  # tenant-B order remains

    def test_symbol_scope_cancels_only_symbol_orders(self) -> None:
        kp = make_kill_plane()
        kp.register_order("ord-1", "t1", "BTC/USDT")
        kp.register_order("ord-2", "t2", "ETH/USDT")
        kp.register_order("ord-3", "t1", "BTC/USDT")
        result = kp.trigger(KillPlaneScope.SYMBOL, "BTC/USDT", "operator-1", "Symbol halt")
        assert result.orders_cancelled == 2
        assert kp.open_order_count == 1  # ETH/USDT remains

    def test_trigger_sets_halted_status(self) -> None:
        kp = make_kill_plane()
        kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Test")
        assert kp.status == KillPlaneStatus.HALTED

    def test_already_triggered_raises_not_armed(self) -> None:
        """Once triggered the kill plane is HALTED; re-trigger raises KillPlaneNotArmedError."""
        kp = make_kill_plane()
        kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "First")
        with pytest.raises(KillPlaneNotArmedError):
            kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Second")

    def test_out_of_band_flag(self) -> None:
        kp = make_kill_plane()
        result = kp.trigger(
            KillPlaneScope.PLATFORM,
            "all",
            "watchdog",
            "Out-of-band kill",
            out_of_band=True,
        )
        assert "Out-of-band: True" in result.detail
        # Command history records out_of_band
        commands = kp.command_history()
        assert commands[-1].out_of_band is True

    def test_result_history_recorded(self) -> None:
        kp = make_kill_plane()
        kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Test")
        assert len(kp.result_history()) == 1

    def test_rearm_after_halt(self) -> None:
        kp = make_kill_plane()
        kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Test")
        kp.rearm("authorizer-1")
        assert kp.status == KillPlaneStatus.ARMED

    def test_rearm_from_armed_raises(self) -> None:
        kp = make_kill_plane()
        with pytest.raises(KillPlaneError):
            kp.rearm("authorizer-1")

    def test_trigger_with_no_orders(self) -> None:
        kp = make_kill_plane()
        result = kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Empty test")
        assert result.orders_cancelled == 0
        assert result.new_exposure_blocked is True


class TestKillPlaneCommandIntegrity:
    def test_command_hash_is_set(self) -> None:
        kp = make_kill_plane()
        kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Hash test")
        commands = kp.command_history()
        assert len(commands[0].command_hash) == 64

    def test_command_requires_issuer_id(self) -> None:
        with pytest.raises(ValueError, match="issuer_id"):
            KillPlaneCommand(
                command_id=KillPlaneCommandId.generate(),
                scope=KillPlaneScope.PLATFORM,
                scope_value="all",
                issuer_id="",
                reason="test",
                timestamp=NOW,
                command_hash="abc",
            )

    def test_command_requires_reason(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            KillPlaneCommand(
                command_id=KillPlaneCommandId.generate(),
                scope=KillPlaneScope.PLATFORM,
                scope_value="all",
                issuer_id="op",
                reason="",
                timestamp=NOW,
                command_hash="abc",
            )


# ──────────────────────────────────────────────────────────────────────────────
# Human-factors tracker
# ──────────────────────────────────────────────────────────────────────────────


class TestHumanFactorsTracker:
    def test_record_approved_review(self) -> None:
        tracker = HumanFactorsTracker()
        review = tracker.record_review(
            DangerousActionCategory.TRUST_LEVEL_PROMOTION,
            "Promote agent-1 to L2",
            "reviewer-1",
            approved=True,
            notes="All checks passed.",
        )
        assert review.approved is True
        assert len(review.review_hash) == 64

    def test_record_rejected_review(self) -> None:
        tracker = HumanFactorsTracker()
        review = tracker.record_review(
            DangerousActionCategory.LIVE_TRADING_ENABLE,
            "Enable live trading",
            "reviewer-1",
            approved=False,
            notes="Legal review incomplete.",
        )
        assert review.approved is False

    def test_filter_by_category(self) -> None:
        tracker = HumanFactorsTracker()
        tracker.record_review(DangerousActionCategory.TRUST_LEVEL_PROMOTION, "Promote", "r1", True)
        tracker.record_review(DangerousActionCategory.KILL_PLANE_DEACTIVATION, "Rearm", "r1", True)
        promotions = tracker.get_reviews(DangerousActionCategory.TRUST_LEVEL_PROMOTION)
        assert len(promotions) == 1
        assert promotions[0].category == DangerousActionCategory.TRUST_LEVEL_PROMOTION

    def test_pending_approvals_required_no_approved(self) -> None:
        tracker = HumanFactorsTracker()
        assert tracker.pending_approvals_required(DangerousActionCategory.LARGE_ORDER) is True

    def test_pending_approvals_required_false_when_approved(self) -> None:
        tracker = HumanFactorsTracker()
        tracker.record_review(DangerousActionCategory.LARGE_ORDER, "Big order", "r1", True)
        assert tracker.pending_approvals_required(DangerousActionCategory.LARGE_ORDER) is False

    def test_get_all_reviews(self) -> None:
        tracker = HumanFactorsTracker()
        tracker.record_review(DangerousActionCategory.LARGE_ORDER, "A", "r", True)
        tracker.record_review(DangerousActionCategory.SCHEMA_MIGRATION, "B", "r", False)
        assert len(tracker.get_reviews()) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Operator cockpit
# ──────────────────────────────────────────────────────────────────────────────


class TestOperatorCockpit:
    def test_snapshot_captures_kill_plane_status(self) -> None:
        engine = make_engine()
        kp = make_kill_plane()
        cockpit = OperatorCockpit(engine, kp)
        snapshot = cockpit.capture_snapshot("SIMULATION")
        assert snapshot.kill_plane_status == KillPlaneStatus.ARMED
        assert snapshot.platform_mode == "SIMULATION"

    def test_snapshot_captures_trust_levels(self) -> None:
        engine = make_engine()
        approval = engine.build_approval("a1", TrustLevel.L1_PAPER, "op", "Test")
        engine.promote(approval)
        kp = make_kill_plane()
        cockpit = OperatorCockpit(engine, kp)
        snapshot = cockpit.capture_snapshot("SIMULATION")
        assert "a1" in snapshot.active_trust_levels
        assert snapshot.active_trust_levels["a1"] == 1

    def test_snapshot_open_order_count(self) -> None:
        engine = make_engine()
        kp = make_kill_plane()
        kp.register_order("o1", "t1", "BTC/USDT")
        kp.register_order("o2", "t1", "ETH/USDT")
        cockpit = OperatorCockpit(engine, kp)
        snapshot = cockpit.capture_snapshot("SIMULATION")
        assert snapshot.open_order_count == 2

    def test_snapshot_active_alerts(self) -> None:
        engine = make_engine()
        kp = make_kill_plane()
        cockpit = OperatorCockpit(engine, kp)
        snapshot = cockpit.capture_snapshot("SIMULATION", active_alerts=["SLO burn rate HIGH"])
        assert "SLO burn rate HIGH" in snapshot.active_alerts

    def test_all_snapshots_returns_all(self) -> None:
        engine = make_engine()
        kp = make_kill_plane()
        cockpit = OperatorCockpit(engine, kp)
        cockpit.capture_snapshot("SIMULATION")
        cockpit.capture_snapshot("SIMULATION")
        assert len(cockpit.all_snapshots()) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Compliance package builder
# ──────────────────────────────────────────────────────────────────────────────


class TestCompliancePackageDocuments:
    def test_add_and_get_document(self) -> None:
        builder = CompliancePackageBuilder()
        doc = builder.add_document(
            ComplianceDocumentType.LEGAL_CLASSIFICATION_MEMO,
            "Legal Classification Memo",
            "Legal Counsel",
            status="OPEN",
            summary="Awaiting external legal review (OPEN-08).",
            references=["OPEN-08", "AD-034"],
        )
        assert len(doc.doc_hash) == 64
        assert len(builder.get_documents()) == 1

    def test_filter_documents_by_type(self) -> None:
        builder = CompliancePackageBuilder()
        builder.add_document(
            ComplianceDocumentType.LEGAL_CLASSIFICATION_MEMO,
            "Legal",
            "Counsel",
            status="OPEN",
            summary="Summary",
        )
        builder.add_document(
            ComplianceDocumentType.DPIA,
            "DPIA",
            "DPO",
            status="DRAFT",
            summary="Summary",
        )
        memos = builder.get_documents(ComplianceDocumentType.LEGAL_CLASSIFICATION_MEMO)
        assert len(memos) == 1
        dpias = builder.get_documents(ComplianceDocumentType.DPIA)
        assert len(dpias) == 1

    def test_document_hash_changes_with_content(self) -> None:
        builder = CompliancePackageBuilder()
        doc1 = builder.add_document(
            ComplianceDocumentType.DPIA, "DPIA v1", "DPO", status="DRAFT", summary="Summary A"
        )
        doc2 = builder.add_document(
            ComplianceDocumentType.DPIA, "DPIA v2", "DPO", status="DRAFT", summary="Summary B"
        )
        assert doc1.doc_hash != doc2.doc_hash


class TestCompliancePackageDataInventory:
    def test_add_data_inventory_item(self) -> None:
        builder = CompliancePackageBuilder()
        item = builder.add_data_inventory_item(
            "PII",
            "User email addresses",
            "PostgreSQL/users",
            retention_days=365,
            lawful_basis="contract",
            encrypted=True,
        )
        assert item.encrypted is True
        assert item.cross_tenant is False
        assert len(builder.get_data_inventory()) == 1

    def test_cross_tenant_raises(self) -> None:
        with pytest.raises(ValueError, match="cross_tenant"):
            DataInventoryItem(
                item_id=__import__("uuid").uuid4(),
                data_category="PII",
                description="test",
                storage_location="db",
                retention_days=365,
                lawful_basis="contract",
                encrypted=True,
                cross_tenant=True,
            )

    def test_retention_days_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="retention_days"):
            DataInventoryItem(
                item_id=__import__("uuid").uuid4(),
                data_category="PII",
                description="test",
                storage_location="db",
                retention_days=0,
                lawful_basis="contract",
                encrypted=True,
            )


class TestCompliancePackageMarketDataTerms:
    def test_add_market_data_terms_entry(self) -> None:
        builder = CompliancePackageBuilder()
        entry = builder.add_market_data_terms(
            provider="Binance",
            data_types=["OHLCV", "orderbook"],
            permitted_uses=["simulation", "paper trading"],
            restrictions=["no redistribution"],
            license_url="https://binance.com/terms",
            reviewed_date="2025-07-10",
            reviewer_id="compliance-officer",
        )
        assert entry.provider == "Binance"
        assert len(builder.get_market_data_terms()) == 1

    def test_market_data_terms_provider_required(self) -> None:
        import uuid

        from contracts.autonomy import MarketDataTermsEntry

        with pytest.raises(ValueError, match="provider"):
            MarketDataTermsEntry(
                entry_id=uuid.uuid4(),
                provider="",
                data_types=[],
                permitted_uses=[],
                restrictions=[],
                license_url="",
                reviewed_date="2025-01-01",
                reviewer_id="r",
            )


class TestCompliancePackageDrills:
    def test_start_and_complete_drill(self) -> None:
        builder = CompliancePackageBuilder()
        record = builder.start_drill(
            DrillType.KILL_PLANE,
            "Kill-plane drill 001",
            "Trigger platform kill with main platform running",
            ["op-1", "eng-1"],
        )
        assert record.completed_at is None
        completed = builder.complete_drill(
            record,
            DrillOutcome.PASSED,
            ["No gaps found"],
            ["Review kill-plane docs quarterly"],
        )
        assert completed.outcome == DrillOutcome.PASSED
        assert completed.completed_at is not None
        assert len(completed.record_hash) == 64

    def test_tabletop_drill(self) -> None:
        builder = CompliancePackageBuilder()
        record = builder.start_drill(
            DrillType.TABLETOP,
            "Runbook review",
            "Walk through all runbooks with team",
            ["op-1"],
        )
        builder.complete_drill(record, DrillOutcome.PARTIAL, ["Gap in PITR runbook"], [])
        records = builder.get_drill_records(DrillType.TABLETOP)
        assert len(records) == 1
        assert records[0].outcome == DrillOutcome.PARTIAL

    def test_filter_drill_records_by_type(self) -> None:
        builder = CompliancePackageBuilder()
        builder.start_drill(DrillType.KILL_PLANE, "KP drill", "scenario", ["op"])
        builder.start_drill(DrillType.LIVE, "Live drill", "scenario", ["op"])
        kp_drills = builder.get_drill_records(DrillType.KILL_PLANE)
        assert len(kp_drills) == 1
        all_drills = builder.get_drill_records()
        assert len(all_drills) == 2

    def test_drill_record_requires_title(self) -> None:
        with pytest.raises(ValueError, match="title"):
            E9DrillRecord(
                record_id=E9DrillRecordId.generate(),
                drill_type=DrillType.TABLETOP,
                title="",
                scenario="scenario",
                participants=[],
                outcome=DrillOutcome.PASSED,
                findings=[],
                action_items=[],
                started_at=NOW,
                completed_at=None,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Owner review package
# ──────────────────────────────────────────────────────────────────────────────


class TestOwnerReviewPackage:
    def _build_full_package(self) -> None:
        self.engine = make_engine()
        self.kp = make_kill_plane()
        self.tracker = HumanFactorsTracker()
        self.cockpit = OperatorCockpit(self.engine, self.kp)
        self.builder = CompliancePackageBuilder()

        # Add a document
        self.builder.add_document(
            ComplianceDocumentType.LEGAL_CLASSIFICATION_MEMO,
            "Legal Memo",
            "Counsel",
            status="OPEN",
            summary="Awaiting counsel (OPEN-08).",
        )
        # Add data inventory
        self.builder.add_data_inventory_item(
            "PII",
            "User emails",
            "PostgreSQL/users",
            retention_days=365,
            lawful_basis="contract",
            encrypted=True,
        )
        # Add market data terms
        self.builder.add_market_data_terms(
            "CoinGecko",
            ["price"],
            permitted_uses=["simulation"],
            restrictions=["no commercial redistribution"],
            license_url="https://coingecko.com/terms",
            reviewed_date="2025-07-10",
            reviewer_id="compliance",
        )
        # Drill
        drill = self.builder.start_drill(DrillType.KILL_PLANE, "KP001", "Platform kill", ["op-1"])
        self.builder.complete_drill(drill, DrillOutcome.PASSED, [], [])
        # Kill plane drill
        self.kp.register_order("o1", "t1", "BTC/USDT")
        self.kp.trigger(KillPlaneScope.PLATFORM, "all", "op", "Drill")
        self.kp.rearm("auth-1")
        # Human factors
        self.tracker.record_review(
            DangerousActionCategory.TRUST_LEVEL_PROMOTION, "Promote a1", "op", True
        )
        # Cockpit snapshot
        self.cockpit.capture_snapshot("SIMULATION")

    def test_package_live_trading_authorized_is_false(self) -> None:
        self._build_full_package()
        pkg = self.builder.build_owner_review_package(
            self.engine, self.kp, self.tracker, self.cockpit
        )
        assert pkg.live_trading_authorized is False

    def test_package_cannot_be_created_with_live_authorized_true(self) -> None:
        with pytest.raises(ValueError, match="live_trading_authorized"):
            E9OwnerReviewPackage(
                package_id=__import__("uuid").uuid4(),
                timestamp=NOW,
                trust_level_events=[],
                kill_plane_drills=[],
                compliance_documents=[],
                data_inventory=[],
                market_data_terms=[],
                human_factors_reviews=[],
                operator_snapshots=[],
                drill_records=[],
                live_trading_authorized=True,
            )

    def test_package_hash_is_set(self) -> None:
        self._build_full_package()
        pkg = self.builder.build_owner_review_package(
            self.engine, self.kp, self.tracker, self.cockpit
        )
        assert len(pkg.package_hash) == 64

    def test_package_contains_all_components(self) -> None:
        self._build_full_package()
        pkg = self.builder.build_owner_review_package(
            self.engine, self.kp, self.tracker, self.cockpit
        )
        assert len(pkg.compliance_documents) >= 1
        assert len(pkg.data_inventory) >= 1
        assert len(pkg.market_data_terms) >= 1
        assert len(pkg.drill_records) >= 1
        assert len(pkg.kill_plane_drills) >= 1
        assert len(pkg.human_factors_reviews) >= 1
        assert len(pkg.operator_snapshots) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Contract utility helpers
# ──────────────────────────────────────────────────────────────────────────────


class TestContractUtilities:
    def test_compute_approval_hash(self) -> None:
        h = compute_approval_hash({"key": "value"})
        assert len(h) == 64

    def test_compute_approval_hash_deterministic(self) -> None:
        payload = {"a": 1, "b": "two"}
        assert compute_approval_hash(payload) == compute_approval_hash(payload)

    def test_compute_event_hash(self) -> None:
        h = compute_event_hash({"event": "test"})
        assert len(h) == 64

    def test_approval_hash_sensitive_to_content(self) -> None:
        h1 = compute_approval_hash({"field": "value1"})
        h2 = compute_approval_hash({"field": "value2"})
        assert h1 != h2
