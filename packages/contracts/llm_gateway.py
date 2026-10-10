"""LLM gateway and token budget contracts for Kian Trading Intelligence.

Per deliverable 9: validated ML interfaces — LLM outputs must never be
authoritative for prices, balances, order status, or financial permissions.

Per deliverable 10: limited LLM gateway — bounded LLM usage that remains
nonauthoritative for execution.

Per deliverable 11: token budgets — enforce bounded LLM usage, tenant quotas,
and rate limits per AD-025.

Per AD-003 (Hybrid Low-Token Intelligence): routine financial processing
shall use deterministic algorithms and validated quantitative methods.
LLM usage must remain bounded and nonauthoritative for execution.

Per AD-011 (Quantitative and Validated ML Intelligence): LLM outputs must
not directly authorize or execute orders.

Per AD-025 (Cost-Aware Orchestration): enforce bounded LLM usage, tenant
quotas, shared eligible data processing, rate limits, and infrastructure
cost controls without weakening safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import UUID, uuid4


class LLMRequestStatus(StrEnum):
    """Status of an LLM gateway request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    COMPLETED = "completed"
    FAILED = "failed"


class LLMRequestType(StrEnum):
    """Allowed LLM request types per AD-003.

    Only research and analysis types are permitted. LLM outputs must
    never be authoritative for prices, balances, order status, or
    financial permissions (AD-011).
    """

    MARKET_RESEARCH = "market_research"
    STRATEGY_ANALYSIS = "strategy_analysis"
    RISK_SUMMARY = "risk_summary"
    MINING_PROFITABILITY_ANALYSIS = "mining_profitability_analysis"


# Per-AD-003 and AD-011: LLM output may NEVER be used for:
FORBIDDEN_LLM_USES = frozenset(
    {
        "price_authoritative",
        "balance_authoritative",
        "order_status_authoritative",
        "risk_authorization",
        "financial_permission",
        "trade_execution",
    }
)


@dataclass(frozen=True)
class LLMRequestId:
    """Stable identity for an LLM request."""

    value: UUID

    @classmethod
    def generate(cls) -> LLMRequestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TokenBudgetConfig:
    """Token budget configuration per tenant.

    Per deliverable 11: token budgets — bounded LLM usage with
    tenant quotas and rate limits.

    Attributes:
        tenant_id: Tenant scope.
        daily_token_limit: Maximum tokens per day.
        per_request_limit: Maximum tokens per single request.
        requests_per_minute: Rate limit for requests.
    """

    tenant_id: str
    daily_token_limit: int = 10000
    per_request_limit: int = 1000
    requests_per_minute: int = 10

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        MIN_DAILY = 1
        MIN_PER_REQUEST = 1
        MIN_RPM = 1
        if self.daily_token_limit < MIN_DAILY:
            raise ValueError("daily_token_limit must be >= 1.")
        if self.per_request_limit < MIN_PER_REQUEST:
            raise ValueError("per_request_limit must be >= 1.")
        if self.requests_per_minute < MIN_RPM:
            raise ValueError("requests_per_minute must be >= 1.")


@dataclass
class TokenBudget:
    """Per-tenant token budget tracker (deliverable 11).

    Per AD-025: enforce bounded LLM usage, tenant quotas, and rate limits.
    Thread-safe: concurrent agent calls must not overspend the budget.

    Attributes:
        tenant_id: Tenant scope.
        config: Budget configuration.
        tokens_used: Tokens consumed today.
        requests_today: Number of requests today.
        last_reset: UTC timestamp of last daily reset.
        request_timestamps: Timestamps of recent requests for rate limiting.
    """

    tenant_id: str
    config: TokenBudgetConfig
    tokens_used: int = 0
    requests_today: int = 0
    last_reset: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_timestamps: list[datetime] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.last_reset.tzinfo is None:
            raise ValueError("last_reset must be timezone-aware (UTC).")

    def _reset_if_needed(self) -> None:
        """Reset daily counters if 24h have passed."""
        now = datetime.now(UTC)
        if (now - self.last_reset) >= timedelta(days=1):
            self.tokens_used = 0
            self.requests_today = 0
            self.last_reset = now

    def _prune_timestamps(self, now: datetime) -> None:
        """Remove timestamps older than 60 seconds for rate limiting."""
        cutoff = now - timedelta(seconds=60)
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > cutoff]

    def can_spend(self, tokens: int) -> bool:
        """Check if tokens can be spent within budget and rate limits."""
        self._reset_if_needed()
        now = datetime.now(UTC)
        self._prune_timestamps(now)
        if self.tokens_used + tokens > self.config.daily_token_limit:
            return False
        if tokens > self.config.per_request_limit:
            return False
        return len(self.request_timestamps) < self.config.requests_per_minute

    def spend(self, tokens: int) -> bool:
        """Attempt to spend tokens. Returns True if within budget."""
        self._reset_if_needed()
        now = datetime.now(UTC)
        self._prune_timestamps(now)
        if self.tokens_used + tokens > self.config.daily_token_limit:
            return False
        if tokens > self.config.per_request_limit:
            return False
        if len(self.request_timestamps) >= self.config.requests_per_minute:
            return False
        self.tokens_used += tokens
        self.requests_today += 1
        self.request_timestamps.append(now)
        return True

    @property
    def remaining_tokens(self) -> int:
        self._reset_if_needed()
        return max(0, self.config.daily_token_limit - self.tokens_used)

    @property
    def is_exhausted(self) -> bool:
        self._reset_if_needed()
        return self.tokens_used >= self.config.daily_token_limit


@dataclass
class LLMRequest:
    """An LLM gateway request.

    Per deliverable 10: the LLM gateway is bounded and nonauthoritative.
    All requests must specify a type that is in LLMRequestType and must
    NOT be in FORBIDDEN_LLM_USES.

    Attributes:
        request_id: Stable unique identifier.
        tenant_id: Tenant scope.
        request_type: Type of LLM request (must be in LLMRequestType).
        prompt: Input prompt text.
        estimated_tokens: Estimated token count for the request.
        status: Request status.
        created_at: UTC creation timestamp.
        response: LLM response text (empty until completed).
        tokens_used: Actual tokens consumed.
    """

    request_id: LLMRequestId
    tenant_id: str
    request_type: LLMRequestType
    prompt: str
    estimated_tokens: int = 0
    status: LLMRequestStatus = LLMRequestStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    response: str = ""
    tokens_used: int = 0

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.prompt:
            raise ValueError("prompt must not be empty.")
        if self.estimated_tokens < 0:
            raise ValueError("estimated_tokens must be non-negative.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")


@dataclass
class LLMResponse:
    """Nonauthoritative LLM response.

    Per AD-011: LLM outputs must NEVER be authoritative for prices,
    balances, order status, or financial permissions. The response
    is advisory only.

    Attributes:
        request_id: Linked request.
        text: Response text.
        tokens_used: Tokens consumed.
        is_authoritative: Always False per AD-011.
        timestamp: UTC response timestamp.
    """

    request_id: LLMRequestId
    text: str
    tokens_used: int = 0
    is_authoritative: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.is_authoritative:
            raise ValueError("LLM responses must NOT be authoritative per AD-011.")


class TokenBudgetExceededError(Exception):
    """Raised when a token budget is exceeded."""


class LLMGatewayError(Exception):
    """Base exception for LLM gateway errors."""


class LLMGateway:
    """Bounded LLM gateway (deliverable 10).

    Per AD-003: LLM usage must remain bounded and nonauthoritative.
    Per AD-011: LLM outputs must not directly authorize or execute orders.
    Per AD-025: enforce bounded LLM usage, tenant quotas, and rate limits.

    The gateway is thread-safe: concurrent agent calls must not overspend
    the token budget.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._budgets: dict[str, TokenBudget] = {}
        self._requests: dict[str, LLMRequest] = {}

    def configure_budget(self, config: TokenBudgetConfig) -> TokenBudget:
        """Configure or update a tenant's token budget."""
        with self._lock:
            budget = TokenBudget(tenant_id=config.tenant_id, config=config)
            self._budgets[config.tenant_id] = budget
            return budget

    def _get_budget_locked(self, tenant_id: str) -> TokenBudget:
        """Get the token budget for a tenant. Caller must hold self._lock."""
        budget = self._budgets.get(tenant_id)
        if budget is None:
            config = TokenBudgetConfig(tenant_id=tenant_id)
            budget = TokenBudget(tenant_id=tenant_id, config=config)
            self._budgets[tenant_id] = budget
        return budget

    def get_budget(self, tenant_id: str) -> TokenBudget:
        """Get the token budget for a tenant."""
        with self._lock:
            return self._get_budget_locked(tenant_id)

    def submit_request(self, request: LLMRequest) -> LLMResponse:
        """Submit a request to the LLM gateway.

        Per deliverable 10: the gateway is bounded and nonauthoritative.
        Per deliverable 11: token budgets are enforced.

        Returns an LLMResponse with is_authoritative=False.
        Raises TokenBudgetExceededError if the budget is exhausted.
        """
        with self._lock:
            budget = self._get_budget_locked(request.tenant_id)

            tokens = request.estimated_tokens
            MIN_TOKENS = 1
            tokens = max(tokens, MIN_TOKENS)

            if not budget.can_spend(tokens):
                request.status = LLMRequestStatus.DENIED
                self._requests[str(request.request_id)] = request
                raise TokenBudgetExceededError(
                    f"Token budget exceeded for tenant {request.tenant_id} "
                    f"(requested {tokens}, remaining {budget.remaining_tokens})."
                )

            # Simulate LLM response (deterministic, nonauthoritative)
            if not budget.spend(tokens):
                request.status = LLMRequestStatus.DENIED
                self._requests[str(request.request_id)] = request
                raise TokenBudgetExceededError(
                    f"Token budget exceeded for tenant {request.tenant_id}."
                )

            request.status = LLMRequestStatus.COMPLETED
            request.tokens_used = tokens
            self._requests[str(request.request_id)] = request

            response_text = self._simulate_response(request)

            return LLMResponse(
                request_id=request.request_id,
                text=response_text,
                tokens_used=tokens,
                is_authoritative=False,
            )

    def _simulate_response(self, request: LLMRequest) -> str:
        """Simulate a deterministic LLM response (nonauthoritative).

        Per AD-003: in SIMULATION mode, the LLM gateway produces
        deterministic responses. No real API call is made.
        """
        return (
            f"[SIMULATED] Research summary for {request.request_type.value}: "
            f"Analysis based on provided context. "
            f"This is advisory only — NOT authoritative for execution."
        )

    def get_request(self, request_id: str) -> LLMRequest:
        """Get a request by ID."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise LLMGatewayError(f"Request {request_id} not found.")
            return req

    def get_remaining_tokens(self, tenant_id: str) -> int:
        """Get remaining tokens for a tenant."""
        with self._lock:
            budget = self._get_budget_locked(tenant_id)
            return budget.remaining_tokens

    def reset(self) -> None:
        """Reset all gateway state (for testing)."""
        with self._lock:
            self._budgets.clear()
            self._requests.clear()
