# ADR-OPEN-09: Notification Delivery Providers

## Status
PROPOSED — Owner approval required before implementation.

## Context
The platform includes a unified notification hub (AD-009, Phase 08). Delivery providers
for push notifications, email, and SMS have not been finalized. The current implementation
is in-memory (simulation-grade) and does not send real notifications.

## Decision
[REQUIRES OWNER DECISION]

Items to define:
- Push notification provider (APNs for iOS, web push for PWA)
- Email delivery provider (SendGrid, Postmark, SES, others)
- SMS provider (Twilio, Vonage, others) — if needed
- Webhook / integration delivery (Slack, Discord, others) — if needed
- Tenant-scoped delivery preferences and rate limits

## Consequences
- Provider selection affects cost, reliability, and regional availability.
- Push notification delivery may require Apple Developer Program license (Addendum A12).
- All notification delivery must be auditable (AD-009, AD-022).

## Alternatives Considered
- Single provider for all channels (simpler, less redundancy)
- Multi-provider per channel (higher resilience, higher complexity)

## Compliance
Interacts with: AD-009 (Unified notification hub), AD-022 (Observability), AD-030
(MacBook and iPhone experience), Addendum A12 (Apple Developer Program).

## Owner Approval
- [ ] Owner-signed approval required before implementation.
