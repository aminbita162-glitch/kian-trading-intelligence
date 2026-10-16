"""Phase C contracts — Safety Hardening.

Per DIRECTIV.txt V1.4 Phase C: signed risk authorization tokens activated
on the simulation order path, chaos/PITR evidence contracts, and adversarial
test scope definitions.

Architecture Decisions: AD-036 (signed risk tokens), AD-004 (independent
Risk Kernel), AD-038 (kill plane).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from contracts.risk import RiskAuthorization
from contracts.risk_token import SignedRiskToken


@dataclass(frozen=True)
class SignedAuthorization:
    """A risk authorization paired with its signed token.

    Per Phase C: the simulation order path issues a cryptographically
    signed token (HMAC-SHA256) bound to the exact order parameters when
    an authorization is granted.  The token must be verified and consumed
    before the order is submitted to the exchange.

    Attributes:
        authorization: The underlying risk authorization.
        token: The signed risk token (None if authorization was denied).
    """

    authorization: RiskAuthorization
    token: SignedRiskToken | None

    @property
    def is_authorized(self) -> bool:
        """True if the authorization is approved and a signed token exists."""
        return self.token is not None and self.authorization.status.value == "approved"

    @property
    def token_str(self) -> str:
        """The serialized token string (raises if no token)."""
        if self.token is None:
            raise ValueError("No signed token — authorization was not approved.")
        return self.token.token_str


@dataclass(frozen=True)
class ChaosDrillResult:
    """Result of a chaos drill against the real PostgreSQL instance.

    Per Phase C: execute at least one chaos drill and record the result.
    A chaos drill simulates a failure (connection drop, partial write,
    table corruption) and verifies that the system recovers or fails safe.

    Attributes:
        drill_id: Unique identifier for the drill.
        drill_type: Type of chaos injected.
        started_at: UTC timestamp when the drill started.
        completed_at: UTC timestamp when the drill completed.
        passed: Whether the system behaved correctly under the chaos.
        details: Human-readable description of what happened.
    """

    drill_id: str
    drill_type: str
    started_at: datetime
    completed_at: datetime
    passed: bool
    details: str


@dataclass(frozen=True)
class PitrRestoreResult:
    """Result of a PITR (Point-in-Time Recovery) restore against PostgreSQL.

    Per Phase C: execute at least one PITR restore using synthetic data
    and record the result.  The restore proves that data can be recovered
    to a known-good state after a failure.

    Attributes:
        restore_id: Unique identifier for the restore.
        started_at: UTC timestamp when the restore started.
        completed_at: UTC timestamp when the restore completed.
        passed: Whether the restore succeeded and data integrity was verified.
        rows_before: Number of rows before the simulated failure.
        rows_after: Number of rows after the restore.
        details: Human-readable description of the restore.
    """

    restore_id: str
    started_at: datetime
    completed_at: datetime
    passed: bool
    rows_before: int
    rows_after: int
    details: str
