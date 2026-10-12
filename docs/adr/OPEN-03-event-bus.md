# ADR-OPEN-03: Durable Event-Bus Selection

## Status
PROPOSED — Owner approval required before implementation.

## Context
The data plane requires a durable event bus for asynchronous processing (Section 03).
The current architecture lists "event bus (selected via ADR)" without a final decision.
This is a prerequisite for E2 (Durable Core) transactional outbox/inbox.

## Decision
[REQUIRES OWNER DECISION]

Options under consideration:
- PostgreSQL LISTEN/NOTIFY (simple, no additional infrastructure, limited throughput)
- Redis Streams (already in stack as cache, moderate durability)
- Kafka (high throughput, additional infrastructure complexity)
- NATS / RabbitMQ (lightweight, good for smaller scale)

## Consequences
- Affects throughput, durability guarantees, operational complexity, and cost.
- Transactional outbox pattern requires compatibility with the chosen bus.

## Alternatives Considered
- No event bus (synchronous only — limits scalability)
- Multiple buses per concern (higher complexity)

## Compliance
Interacts with: Section 03 (Data Plane), AD-016 (Event-driven architecture),
AD-014 (Deterministic execution), E2 (Durable Core — transactional outbox/inbox).

## Owner Approval
- [ ] Owner-signed approval required before implementation.
