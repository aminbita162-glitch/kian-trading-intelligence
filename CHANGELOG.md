# CHANGELOG — Kian Trading Intelligence

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with prerelease identifiers during development.

---

## [Unreleased]

### Added — Phase 01: Repository & Engineering Foundation
- Repository identity and remote verification (GitHub: aminbita162-glitch/kian-trading-intelligence)
- Structured monorepo layout (`apps/`, `services/`, `agents/`, `packages/`, `infrastructure/`, `tests/`, `docs/`, `test-house/`)
- Python 3.12+ / FastAPI backend foundation with health endpoint and OpenAPI documentation
- TypeScript 5.6+ / React / Vite frontend foundation with strict type checking
- Shared contracts package (`packages/contracts/`) with Pydantic models for operating modes and order states
- Dependency management with `pyproject.toml` (backend) and `package.json` (frontend)
- Code formatting and linting: Ruff (Python), ESLint + Prettier (TypeScript)
- Unit-test framework: pytest (Python) with passing baseline tests, Vitest (TypeScript)
- CI configuration via GitHub Actions (`.github/workflows/ci.yml`)
- Secret-handling rules: `.gitignore` exclusions, environment file patterns, no-secrets policy
- Architecture documentation (`docs/architecture.md`)
- Proprietary LICENSE file (pending owner/legal review)
- Test house evidence library (`test-house/`) with structured phase directories
- Engineering integrity policy in README.md

### Security
- No secrets, credentials, or API keys committed to the repository
- `.gitignore` configured to prevent accidental secret commits
- Repository visibility noted as PUBLIC (see addendum A14 — default should be PRIVATE)

---

## [0.1.0-dev] — Not yet released

Prerelease identifier. No stable release has been made. All development is in Phase 01 (Engineering Foundation).

---

## Attribution

**Amin Azimi | AI Architect | End-to-End System Development Business Challenge | Azimi Innovation Lab**
