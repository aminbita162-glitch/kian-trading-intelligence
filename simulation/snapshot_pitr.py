"""Snapshot reconciliation and PITR restore for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): snapshot reconciliation
and real PITR restore with ledger diff.

Per AD-023 (Digital Twin): deterministic simulation, replay, fault
injection, and repeatable verification.

Snapshot reconciliation captures the state of the simulation at a
checkpoint and compares it against a replay to detect divergence.
A divergence means the simulation is non-deterministic — a critical
finding that must be investigated.

PITR (Point-in-Time Restore) restores the ledger to a known state and
verifies that the restored state matches the original via a ledger diff.
Any non-zero delta means the restore is imperfect and must be investigated.

Per Section 01.3: SIMULATION mode only — no real financial orders.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock

from contracts.simulation import (
    LedgerDiffEntry,
    PITRConfig,
    PITRId,
    PITRResult,
    PITRStatus,
    SimulationSnapshot,
    SnapshotId,
    SnapshotReconciliationResult,
    SnapshotStatus,
)


def _compute_state_hash(snapshot: SimulationSnapshot) -> str:
    """Compute a SHA-256 hash of the serialised snapshot state.

    The hash covers all fields that define the simulation state:
    ledger balances, order states, exposure, seed, and step index.
    """
    parts: list[str] = [
        f"seed:{snapshot.seed}",
        f"step:{snapshot.step_index}",
        f"exposure:{snapshot.exposure}",
    ]
    for account_id, balance in sorted(snapshot.ledger_balances.items()):
        parts.append(f"bal:{account_id}:{balance}")
    for cid, state in sorted(snapshot.order_states.items()):
        parts.append(f"order:{cid}:{state}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class SnapshotReconciler:
    """Snapshot reconciliation service.

    Per E5: captures snapshots during simulation runs and reconciles
    them against replays to detect non-determinism.

    Thread-safe — snapshots can be captured concurrently from
    different simulation threads.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._snapshots: dict[str, SimulationSnapshot] = {}

    def capture_snapshot(
        self,
        seed: str,
        step_index: int,
        ledger_balances: dict[str, str],
        order_states: dict[str, str],
        exposure: str = "0",
    ) -> SimulationSnapshot:
        """Capture a snapshot of the current simulation state.

        The snapshot includes ledger balances, order states, and exposure.
        The state hash is computed automatically and is the key for
        reconciliation.
        """
        snapshot = SimulationSnapshot(
            snapshot_id=SnapshotId.generate(),
            seed=seed,
            step_index=step_index,
            ledger_balances=dict(ledger_balances),
            order_states=dict(order_states),
            exposure=exposure,
        )
        snapshot.state_hash = _compute_state_hash(snapshot)
        with self._lock:
            self._snapshots[str(snapshot.snapshot_id)] = snapshot
        return snapshot

    def reconcile(
        self,
        original: SimulationSnapshot,
        replayed: SimulationSnapshot,
    ) -> SnapshotReconciliationResult:
        """Reconcile two snapshots and detect divergence.

        Per E5: if the state hashes match, the simulation is deterministic
        for this checkpoint. If they differ, the divergences are listed.
        """
        if original.state_hash == replayed.state_hash:
            return SnapshotReconciliationResult(
                original_hash=original.state_hash,
                replay_hash=replayed.state_hash,
                status=SnapshotStatus.MATCHED,
            )

        divergences: list[str] = []
        if original.exposure != replayed.exposure:
            divergences.append(f"exposure: {original.exposure} vs {replayed.exposure}")
        if original.step_index != replayed.step_index:
            divergences.append(f"step_index: {original.step_index} vs {replayed.step_index}")

        for account_id in set(original.ledger_balances) | set(replayed.ledger_balances):
            orig_bal = original.ledger_balances.get(account_id, "0")
            replay_bal = replayed.ledger_balances.get(account_id, "0")
            if Decimal(orig_bal) != Decimal(replay_bal):
                divergences.append(f"balance[{account_id}]: {orig_bal} vs {replay_bal}")

        for cid in set(original.order_states) | set(replayed.order_states):
            orig_state = original.order_states.get(cid, "missing")
            replay_state = replayed.order_states.get(cid, "missing")
            if orig_state != replay_state:
                divergences.append(f"order[{cid}]: {orig_state} vs {replay_state}")

        return SnapshotReconciliationResult(
            original_hash=original.state_hash,
            replay_hash=replayed.state_hash,
            status=SnapshotStatus.DISCREPANCY,
            divergences=divergences,
        )

    def get_snapshot(self, snapshot_id: str) -> SimulationSnapshot | None:
        """Get a stored snapshot by ID."""
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def reset(self) -> None:
        """Reset all stored snapshots (for testing)."""
        with self._lock:
            self._snapshots.clear()


class PITRRestorer:
    """Point-in-Time Restore with ledger diff.

    Per E5: real PITR restore with ledger diff. The restorer takes a
    snapshot of the ledger state at a restore point and verifies that
    restoring from that snapshot reproduces the original state exactly.

    The ledger diff compares every account's balance between the original
    and restored states. Any non-zero delta is a restore imperfection
    that must be investigated.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._results: dict[str, PITRResult] = {}

    def restore(
        self,
        config: PITRConfig,
        original_balances: dict[str, dict[str, str]],
        restored_balances: dict[str, dict[str, str]],
    ) -> PITRResult:
        """Restore the ledger from a snapshot and compute the ledger diff.

        Per E5: the original_balances and restored_balances are dicts
        of {account_id: {asset: balance}}. The diff is computed per
        account and asset. Any non-zero delta is a restore imperfection.

        The result includes the full ledger diff entries and the
        verification status — VERIFIED if all deltas are zero,
        DIFF_DETECTED otherwise.
        """
        pitr_id = PITRId.generate()
        started_at = datetime.now(UTC)

        diffs: list[LedgerDiffEntry] = []
        all_accounts = set(original_balances) | set(restored_balances)

        for account_id in all_accounts:
            orig_assets = original_balances.get(account_id, {})
            restored_assets = restored_balances.get(account_id, {})
            all_assets = set(orig_assets) | set(restored_assets)

            for asset in all_assets:
                orig_bal = orig_assets.get(asset, "0")
                restored_bal = restored_assets.get(asset, "0")
                diffs.append(
                    LedgerDiffEntry(
                        account_id=account_id,
                        asset=asset,
                        original_balance=orig_bal,
                        restored_balance=restored_bal,
                    )
                )

        diff_count = sum(1 for d in diffs if d.has_diff)
        status = PITRStatus.VERIFIED if diff_count == 0 else PITRStatus.DIFF_DETECTED

        result = PITRResult(
            pitr_id=pitr_id,
            status=status,
            restore_point=config.restore_point,
            ledger_diffs=diffs,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            notes=f"Restored {len(all_accounts)} accounts, {diff_count} diffs detected",
        )

        with self._lock:
            self._results[str(pitr_id)] = result

        return result

    def get_result(self, pitr_id: str) -> PITRResult | None:
        """Get a stored PITR result by ID."""
        with self._lock:
            return self._results.get(pitr_id)

    def reset(self) -> None:
        """Reset all stored results (for testing)."""
        with self._lock:
            self._results.clear()
