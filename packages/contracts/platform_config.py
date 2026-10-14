"""Platform infrastructure configuration — owner decisions locked 2026-10-14.

Implements the "Current (now)" choices from DIRECTIV.txt Section 01
into configuration and adapters without activating LIVE.

Owner decisions (Section 01):
  01.1 Cloud Provider  — Current: Render (agent workloads); Roadmap: AWS.
  01.2 Event Bus       — Current: Redis Streams; Roadmap: AWS SQS/SNS.
  01.3 SLO/RPO/RTO     — Current: 99.0% / ≤15min / ≤60min.
  01.4 Exchange Provs   — Current: Kraken + Bitvavo (MiCA-licensed).
  01.5 Legal Classif.   — Current: EU/German MiCA/GDPR templates.
  01.6 Notifications   — Current: email via SendGrid free tier.

Roadmap items are recorded as constants but are NOT implemented or
activated.  Live trading remains unauthorized (``live_trading_authorized``
is always False per Section 00.3).

This module is a leaf-level configuration module — it must NOT import
from services or simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ──────────────────────────────────────────────────────────────────────────────
# 01.1 — Cloud Provider (OPEN-02)
# ──────────────────────────────────────────────────────────────────────────────


class CloudProvider(StrEnum):
    """Cloud provider for agent workloads and deployment."""

    RENDER = "render"
    AWS = "aws"


#: Current cloud provider (Section 01.1 — "Current (now): Render").
CURRENT_CLOUD_PROVIDER: CloudProvider = CloudProvider.RENDER

#: Roadmap cloud provider (Section 01.1 — "Roadmap: AWS as future production cloud").
ROADMAP_CLOUD_PROVIDER: CloudProvider = CloudProvider.AWS


# ──────────────────────────────────────────────────────────────────────────────
# 01.2 — Event Bus (OPEN-03)
# ──────────────────────────────────────────────────────────────────────────────


class EventBusProvider(StrEnum):
    """Durable event-bus technology."""

    REDIS_STREAMS = "redis_streams"
    AWS_SQS_SNS = "aws_sqs_sns"


#: Current event bus (Section 01.2 — "Current (now): Redis Streams").
CURRENT_EVENT_BUS: EventBusProvider = EventBusProvider.REDIS_STREAMS

#: Roadmap event bus (Section 01.2 — "Roadmap: AWS SQS/SNS as future durable bus").
ROADMAP_EVENT_BUS: EventBusProvider = EventBusProvider.AWS_SQS_SNS


# ──────────────────────────────────────────────────────────────────────────────
# 01.3 — SLO / RPO / RTO (OPEN-05)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SLOTargets:
    """Service-level objective, recovery point and recovery time targets.

    Per Section 01.3:
      Current (test/use):  Availability 99.0%, RPO ≤15 min, RTO ≤60 min.
      Roadmap (high):      Availability 99.9%, RPO ≤1 min, RTO ≤15 min.

    Attributes:
        availability_pct:   Target uptime percentage (e.g. 99.0).
        rpo_minutes:         Maximum acceptable data-loss window in minutes.
        rto_minutes:         Maximum acceptable recovery time in minutes.
        tier:                "current" or "roadmap".
    """

    availability_pct: str
    rpo_minutes: int
    rto_minutes: int
    tier: str


#: Current SLO/RPO/RTO targets (Section 01.3 — "Current (test/use)").
CURRENT_SLO_TARGETS: SLOTargets = SLOTargets(
    availability_pct="99.0",
    rpo_minutes=15,
    rto_minutes=60,
    tier="current",
)

#: Roadmap SLO/RPO/RTO targets (Section 01.3 — "Roadmap (high)").
ROADMAP_SLO_TARGETS: SLOTargets = SLOTargets(
    availability_pct="99.9",
    rpo_minutes=1,
    rto_minutes=15,
    tier="roadmap",
)


# ──────────────────────────────────────────────────────────────────────────────
# 01.4 — Exchange Providers (OPEN-06)
# ──────────────────────────────────────────────────────────────────────────────


class ExchangeProviderName(StrEnum):
    """Approved exchange provider names.

    Per Section 01.4:
      Current: Kraken + Bitvavo (MiCA-licensed).
      Roadmap: Binance + Bybit + OKX + Coinbase with formal contracts.

    No exchange is automatically approved for live use (Section 05.5).
    """

    KRAKEN = "kraken"
    BITVAVO = "bitvavo"
    # Roadmap providers (not activated)
    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    COINBASE = "coinbase"


@dataclass(frozen=True)
class ExchangeProviderConfig:
    """Configuration for a single approved exchange provider.

    Attributes:
        name:           Provider identifier.
        mica_licensed:  Whether the provider holds a MiCA license.
        is_current:     True if this provider is in the "Current (now)" set.
        is_live_authorized: Always False — no live trading is authorized
                             without separate written owner decision.
    """

    name: ExchangeProviderName
    mica_licensed: bool
    is_current: bool
    is_live_authorized: bool = False

    def __post_init__(self) -> None:
        if self.is_live_authorized:
            raise ValueError(
                "is_live_authorized must be False — no live trading is authorized "
                "without separate written owner decision (Section 00.3)."
            )


#: Current approved exchange providers (Section 01.4 — "Current: Kraken + Bitvavo").
CURRENT_EXCHANGE_PROVIDERS: tuple[ExchangeProviderConfig, ...] = (
    ExchangeProviderConfig(
        name=ExchangeProviderName.KRAKEN,
        mica_licensed=True,
        is_current=True,
    ),
    ExchangeProviderConfig(
        name=ExchangeProviderName.BITVAVO,
        mica_licensed=True,
        is_current=True,
    ),
)

#: Roadmap exchange providers (Section 01.4 — recorded only, not implemented).
ROADMAP_EXCHANGE_PROVIDERS: tuple[ExchangeProviderConfig, ...] = (
    ExchangeProviderConfig(
        name=ExchangeProviderName.BINANCE,
        mica_licensed=False,
        is_current=False,
    ),
    ExchangeProviderConfig(
        name=ExchangeProviderName.BYBIT,
        mica_licensed=False,
        is_current=False,
    ),
    ExchangeProviderConfig(
        name=ExchangeProviderName.OKX,
        mica_licensed=False,
        is_current=False,
    ),
    ExchangeProviderConfig(
        name=ExchangeProviderName.COINBASE,
        mica_licensed=False,
        is_current=False,
    ),
)


def get_current_exchange_provider_names() -> list[str]:
    """Return the names of current approved exchange providers."""
    return [str(p.name) for p in CURRENT_EXCHANGE_PROVIDERS]


def is_exchange_provider_current(name: ExchangeProviderName | str) -> bool:
    """Return True if the given provider name is in the current approved set."""
    target = name if isinstance(name, ExchangeProviderName) else ExchangeProviderName(name)
    return any(p.name == target for p in CURRENT_EXCHANGE_PROVIDERS)


# ──────────────────────────────────────────────────────────────────────────────
# 01.5 — Legal Classification (OPEN-08)
# ──────────────────────────────────────────────────────────────────────────────


class LegalJurisdiction(StrEnum):
    """Legal jurisdiction for compliance classification.

    Per Section 01.5: standard EU/German (MiCA/GDPR) templates.
    """

    EU_MICA = "eu_mica"
    GDPR = "gdpr"
    GERMAN_BAFIN = "german_bafin"


@dataclass(frozen=True)
class LegalClassificationConfig:
    """Legal classification and compliance template configuration.

    Per Section 01.5:
      - Use standard EU/German (MiCA/GDPR) templates for compliance package.
      - No external counsel engagement required at this stage.
      - Classification may be updated later.
      - Remain in SIMULATION/PAPER only until formal legal review.

    Attributes:
        jurisdiction:       Primary legal jurisdiction.
        templates:           List of compliance template identifiers.
        counsel_engaged:     Whether external legal counsel has been engaged.
        live_authorized:     Always False — formal legal review required
                             before any live activation.
    """

    jurisdiction: LegalJurisdiction
    templates: tuple[str, ...]
    counsel_engaged: bool
    live_authorized: bool = False

    def __post_init__(self) -> None:
        if self.live_authorized:
            raise ValueError(
                "live_authorized must be False — remain in SIMULATION/PAPER only "
                "until formal legal review (Section 01.5)."
            )


#: Current legal classification config (Section 01.5).
CURRENT_LEGAL_CLASSIFICATION: LegalClassificationConfig = LegalClassificationConfig(
    jurisdiction=LegalJurisdiction.EU_MICA,
    templates=("MiCA", "GDPR", "German_BaFin"),
    counsel_engaged=False,
)


# ──────────────────────────────────────────────────────────────────────────────
# 01.6 — Notification Providers (OPEN-09)
# ──────────────────────────────────────────────────────────────────────────────


class NotificationChannel(StrEnum):
    """Notification delivery channels.

    Per Section 01.6:
      Current:  email via SendGrid free tier.
      Roadmap:  email + Slack + SMS (Twilio) with dual-control.
    """

    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"


@dataclass(frozen=True)
class NotificationProviderConfig:
    """Configuration for a notification delivery provider.

    Attributes:
        channel:       Notification channel type.
        provider:      Provider name (e.g. "sendgrid", "twilio").
        is_current:     True if this provider is in the "Current (now)" set.
        dual_control:   Whether dual-control is required for this provider.
    """

    channel: NotificationChannel
    provider: str
    is_current: bool
    dual_control: bool


#: Current notification provider (Section 01.6 — "Current: email via SendGrid free tier").
CURRENT_NOTIFICATION_PROVIDERS: tuple[NotificationProviderConfig, ...] = (
    NotificationProviderConfig(
        channel=NotificationChannel.EMAIL,
        provider="sendgrid",
        is_current=True,
        dual_control=False,
    ),
)

#: Roadmap notification providers (Section 01.6 — recorded only).
ROADMAP_NOTIFICATION_PROVIDERS: tuple[NotificationProviderConfig, ...] = (
    NotificationProviderConfig(
        channel=NotificationChannel.SLACK,
        provider="slack",
        is_current=False,
        dual_control=True,
    ),
    NotificationProviderConfig(
        channel=NotificationChannel.SMS,
        provider="twilio",
        is_current=False,
        dual_control=True,
    ),
)


# ──────────────────────────────────────────────────────────────────────────────
# Aggregate platform configuration
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlatformConfig:
    """Aggregate platform configuration for all owner decisions (Section 01).

    Collects the "Current (now)" choices for cloud provider, event bus,
    SLO targets, exchange providers, legal classification, and notification
    providers into a single immutable record.

    Roadmap items are NOT included here — they are recorded as separate
    constants but are not part of the active configuration.
    """

    cloud_provider: CloudProvider
    event_bus: EventBusProvider
    slo_targets: SLOTargets
    exchange_providers: tuple[ExchangeProviderConfig, ...]
    legal_classification: LegalClassificationConfig
    notification_providers: tuple[NotificationProviderConfig, ...]
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        if self.live_trading_authorized:
            raise ValueError(
                "live_trading_authorized must be False — "
                "live trading is not authorized (Section 00.3)."
            )


#: Active platform configuration — all "Current (now)" decisions from Section 01.
PLATFORM_CONFIG: PlatformConfig = PlatformConfig(
    cloud_provider=CURRENT_CLOUD_PROVIDER,
    event_bus=CURRENT_EVENT_BUS,
    slo_targets=CURRENT_SLO_TARGETS,
    exchange_providers=CURRENT_EXCHANGE_PROVIDERS,
    legal_classification=CURRENT_LEGAL_CLASSIFICATION,
    notification_providers=CURRENT_NOTIFICATION_PROVIDERS,
)
