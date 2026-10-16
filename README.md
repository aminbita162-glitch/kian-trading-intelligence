# Kian Trading Intelligence

> **A secure, auditable, cost-aware cryptocurrency trading and mining intelligence platform** combining deterministic execution, validated quantitative intelligence, specialized agents, and human-controlled operational authority.

---

**Amin Azimi · AI Architect · End-to-End System Development Business Challenge · Azimi Innovation Lab**

[![Phase](https://img.shields.io/badge/Elevation-E0%E2%80%93E10%20%2B%20A%E2%80%93D%20COMPLETE-blue)]()
[![Status](https://img.shields.io/badge/Status-SIMULATION-orange)]()
[![License](https://img.shields.io/badge/License-Proprietary-red)]()
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6%2B-3178c6)]()
[![Directive](https://img.shields.io/badge/Directive-V1.4-purple)]()

---

## Project Status — Single Source of Truth

The canonical project status is maintained in `status.yaml` (introduced in E0).
All public claims in this README, CHANGELOG, and architecture docs trace to `status.yaml`
or are explicitly labeled PLANNED.

**Directive version**: V1.4 (Post-E10 Elevation Plan A–D: Real Infrastructure and Locked Ideas)
**Software version**: 0.20.0
**Operating mode**: SIMULATION (LIVE not authorized)
**Repository visibility**: PUBLIC (owner-decided per Addendum A14)

### Elevation Phase Status (E0–E10)

| Phase | Name | Status |
|-------|------|--------|
| **E0** | Truth Reset and Governance Repair | ✅ COMPLETE |
| **E1** | Security Blocker Removal | ✅ COMPLETE |
| **E2** | Durable Core | ✅ COMPLETE |
| **E3** | Structure and Verification Separation | ✅ COMPLETE |
| **E4** | Safety Plane Hardening | ✅ COMPLETE |
| **E5** | Simulation and Truth Infrastructure | ✅ COMPLETE |
| **E6** | Agent Runtime and Evaluation | ✅ COMPLETE |
| **E7** | Strategy Science | ✅ COMPLETE |
| **E8** | Evidence, Observability and Supply Chain | ✅ COMPLETE |
| **E9** | Graduated Autonomy, Kill Plane and Compliance Package | ✅ COMPLETE |
| **E10** | Commercial Monetization, Payment Tiers and Market Readiness | ✅ COMPLETE |

### Post-E10 Elevation Phases (A–D)

| Phase | Name | Status |
|-------|------|--------|
| **Phase A** | Real Infrastructure (PostgreSQL + Redis Streams) | ✅ COMPLETE |
| **Phase B** | Operational Locked Ideas (Token Budget Governor, Decision Replay, Schema-First Bus) | ✅ COMPLETE |
| **Phase C** | Safety Hardening (Signed Risk Tokens, Chaos/PITR, Adversarial Tests) | ✅ COMPLETE |
| **Phase D** | Final Truth Reset and Status Update | ✅ COMPLETE |

### Prior Phase Status (01–10 — all COMPLETE, merged to main)

| Phase | Name | Status |
|-------|------|--------|
| 01 | Repository & Engineering Foundation | COMPLETE |
| 02 | Identity & Multi-Tenant Security | COMPLETE |
| 03 | Market Data Foundation | COMPLETE |
| 04 | Risk Kernel & Trading Execution | COMPLETE |
| 05 | Financial Ledger & Profit Policies | COMPLETE |
| 06 | Four-Agent Intelligence | COMPLETE |
| 07 | Mining Simulation & Safety | COMPLETE |
| 08 | MacBook & iPhone Applications | COMPLETE |
| 09 | Security, Resilience & Scale | COMPLETE |
| 10 | Release Engineering & Controlled Launch | COMPLETE |

### Security Findings

| Finding | Description | Status |
|---------|-------------|--------|
| F-SEC-01 | Repository is PUBLIC (should be PRIVATE per A14) | RESOLVED — owner-decided to keep PUBLIC |
| F-SEC-02 | XOR encryption in credential vault | RESOLVED — AES-256-GCM envelope encryption (merged, PR #12) |
| F-SEC-03 | In-memory identity store | RESOLVED — SQLAlchemy persistent store (merged, PR #12) |

> **Production readiness**: This project is in SIMULATION mode. No live trading, real mining,
> or real financial operations are enabled or authorized. The platform is a simulation-grade
> scaffold being elevated to production-candidate via E-phases. See `status.yaml` for the
> complete and canonical status.

---

## Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        MB[MacBook App<br/>Tauri]
        IP[iPhone PWA<br/>Responsive]
    end

    subgraph "Cloud Control Plane"
        ID[Identity & Tenant Management]
        SC[Session & Calendar Scheduling]
        CM[Compliance & Eligibility]
    end

    subgraph "Cloud Execution Plane"
        MD[Market Data Processing]
        RK[Risk & Safety Kernel<br/>Deterministic]
        EX[Exchange Adapters]
        FL[Financial Ledger]
    end

    subgraph "Four Specialized Agents"
        A1[Market Intelligence Agent]
        A2[Strategy & Portfolio Agent]
        A3[Execution & Supervisor Agent]
        A4[Mining Operations Agent]
    end

    subgraph "Data Plane"
        PG[(PostgreSQL)]
        RD[(Redis Cache)]
        EB[Event Bus]
    end

    MB --> ID
    IP --> ID
    ID --> SC
    SC --> CM
    CM --> MD
    MD --> A1
    A1 --> A2
    A2 --> RK
    RK --> EX
    EX --> FL
    A3 --> EX
    A4 --> MD
    RK -.->|No exposure-increasing order<br/>bypasses this| EX
    PG --> FL
    RD --> MD
    EB --> MD
```

### Four Agents + Independent Risk Kernel

| Agent | Responsibility | Prohibited |
|-------|---------------|------------|
| **Market Intelligence** | Market observations, feature computation, bounded research summaries | Direct trade execution |
| **Strategy & Portfolio** | Strategy evaluation, portfolio analysis, position proposals | Risk override or self-authorized execution |
| **Execution & Supervisor** | Order lifecycle coordination, exchange adapter orchestration, reconciliation | Bypassing independent risk authorization |
| **Mining Operations** | Mining simulation, profitability assessment, pool/hardware coordination | Unrestricted trading-account access |
| **Risk & Safety Kernel** *(not an agent)* | Deterministic safety validation — tenant, session, capital, exposure, compliance checks | N/A — no order may bypass this |

> **Invariant**: No exposure-increasing order may reach an exchange adapter without valid risk authorization from the independent deterministic Risk & Safety Kernel.

---

## Operating Modes

| Mode | Description | Real Money | Status |
|------|-------------|------------|--------|
| **SIMULATION** | Historical or synthetic data without real financial orders | No | ACTIVE |
| **PAPER** | Simulated trading using approved market data or sandbox environments | No | PLANNED |
| **LIVE** | Real financial execution through explicitly authorized providers | Yes | PLANNED (not authorized) |

> A mode change must never silently enable real-money trading. All interfaces, records, and audit events must clearly identify the active mode.

---

## Technology Stack

| Layer | Technology | Status |
|-------|-----------|--------|
| Backend | Python 3.11+, FastAPI | REAL |
| Interfaces | React, TypeScript 5.6+ | REAL |
| MacBook App | Tauri | REAL (shell) |
| iPhone | Responsive PWA | REAL |
| Database | PostgreSQL | REAL |
| Cache | Redis | REAL |
| Observability | OpenTelemetry | REAL |
| Deployment | Render | PLANNED (configured as target; not yet deployed) |
| CI/CD | GitHub Actions | REAL |

---

## Repository Structure

```
kian-trading-intelligence/
├── apps/              # Client applications (web, Tauri)
├── services/         # Backend services
├── agents/           # Specialized AI agents
├── packages/         # Shared contracts and libraries
├── infrastructure/   # Infrastructure configuration
├── tests/            # Integration and end-to-end tests
├── docs/             # Architecture and design documents
├── docs/adr/         # ADR templates for open decisions
├── test-house/       # Durable evidence library
├── .github/workflows/ # CI pipelines
├── DIRECTIV.txt      # Master engineering directive (V1.4)
├── status.yaml       # Single source of truth for project status
├── LICENSE           # Proprietary (all rights reserved)
├── README.md         # This file
└── CHANGELOG.md      # Release history
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 22+
- PostgreSQL 16+ (for later phases)
- Git

### Backend Setup

```bash
cd services/core
python -m venv .venv
source .venv/bin/activate
pip install -e "../../packages/contracts"
pip install -e ".[dev]"
pytest
```

### Frontend Setup

```bash
cd apps/web
npm install
npm run dev
```

### Running Tests

```bash
# Python tests
pytest

# TypeScript tests
cd apps/web && npm test
```

---

## Engineering Integrity Policy

This project enforces an honest, evidence-based engineering standard:

1. **No fabricated evidence**: Test results, benchmarks, deployment claims, and Git evidence must reflect actual execution.
2. **No production-readiness claims** without passing explicit release gates.
3. **No false features**: Only implemented and verified features are advertised.
4. **No hidden limitations**: Known limits and gaps are documented.
5. **No guaranteed returns**: No strategy may be represented as guaranteed profitable.
6. **No real-money operations** without all technical, security, legal, and human approval gates passing.

---

## Governance and Directive Lineage

| Version | Description | Status |
|---------|-------------|--------|
| V1.0 | Original master engineering directive | Superseded |
| V1.1 | Owner-approved addendum — governance and project presentation | Superseded |
| V1.2 | Elevation and market completion — AD-034 through AD-040, E0 through E10 | Superseded |
| V1.3 | Post-E10 completion and market readiness — residual task scope | Superseded |
| V1.4 | Post-E10 elevation plan A-D — real infrastructure (PostgreSQL + Redis Streams) and locked ideas | Active |

The full directive is preserved in `DIRECTIV.txt`. The project status single source of
truth is `status.yaml`. ADR templates for open decisions are in `docs/adr/`.

---

## Third-Party Notices

This project uses third-party open-source components. Their licenses are respected:

- **Python** — PSF License
- **FastAPI** — MIT License
- **Pydantic** — MIT License
- **pytest** — MIT License
- **Ruff** — MIT License
- **React** — MIT License
- **TypeScript** — Apache 2.0 License
- **Vite** — MIT License
- **Vitest** — MIT License
- **ESLint** — MIT License
- **Prettier** — MIT License

Third-party components retain their original licenses; this project's proprietary license does not override them.

---

## Links

- **Repository**: [github.com/aminbita162-glitch/kian-trading-intelligence](https://github.com/aminbita162-glitch/kian-trading-intelligence)
- **Master Directive**: `DIRECTIV.txt` (V1.4, preserved in repository root)
- **Status**: `status.yaml` (single source of truth)

---

## AUTHOR

> **Amin Azimi**
> AI Architect
> End-to-End System Development Business Challenge
> Azimi Innovation Lab
>
> **Project**: Kian Trading Intelligence
> **Master Engineering Directive**: V1.4 — Post-E10 Elevation Plan A-D: Real Infrastructure and Locked Ideas
> **Current software version**: 0.20.0 (Post-E10 — residual task 02.4: Final README and Status Truth Reset)
>
> Kian Trading Intelligence is a secure, auditable, cost-aware cryptocurrency trading and mining intelligence platform. It combines deterministic execution, validated quantitative intelligence, four specialized AI agents, and an independent deterministic Risk & Safety Kernel to provide human-controlled operational authority over trading and mining activities. The platform is designed for multi-tenant cloud operation with support for MacBook desktop and iPhone mobile interfaces.
>
> What this project **IS**: A principled engineering effort to build a trading intelligence platform with safety-first architecture, auditable financial operations, tenant isolation, and human-gated execution. It supports simulation, paper trading, and controlled live execution modes with mandatory risk authorization.
>
> What this project **IS NOT**: It is not a get-rich-quick scheme, a guaranteed-profit system, an autonomous trading bot, or a replacement for human financial judgment. No strategy may be represented as guaranteed profitable. No LLM output directly authorizes or executes orders.
>
> What it **DOES**: It provides market intelligence, strategy evaluation, risk management, financial ledger accounting, mining profitability simulation, and controlled trading execution — all with deterministic safety controls and human oversight.
>
> What it **INTENDS TO DO**: Progress through elevation phases E0 through E10, from truth reset and governance repair to commercial monetization and market readiness, with explicit human approval gates at each milestone. Live trading requires all technical, security, legal, and human approval gates to pass.
>
> **Disclaimers**: No guaranteed returns. No unsupported real-trading claims. This repository does not authorize third-party use. Project maturity and regulatory status are accurately represented. No live trading, real mining, or real financial operations are enabled or authorized at this stage.

---

*Proprietary — All Rights Reserved — Amin Azimi / Azimi Innovation Lab*
