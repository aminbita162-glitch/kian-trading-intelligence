# Test House — Kian Trading Intelligence

The `test-house/` directory is a durable, human-auditable evidence library for development testing, separate from executable source tests.

## Purpose

Per Addendum A03, this directory preserves structured testing evidence for auditability. It is NOT a replacement for executable test suites or CI artifact storage.

## Structure

```
test-house/
├── README.md           — This file
├── index.md            — Evidence index with run references
├── phase-01/           — Phase 01 evidence
├── security/           — Security test evidence
├── financial-safety/   — Financial safety test evidence
├── performance/         — Performance benchmark evidence
├── reliability/        — Reliability test evidence
└── release-verification/ — Release gate evidence
```

## Evidence Record Format

Each evidence record contains:
- Unique run ID
- ISO-8601 UTC timestamp
- Git commit SHA
- Branch
- Environment
- Tested component/contract
- Exact reproducible command
- Expected result
- Observed result
- PASS/FAIL/BLOCKED/SKIPPED status
- Failure reference (if any)
- Corrective action (if any)

## Policy

- Never check in passwords, API keys, or sensitive data
- Never fabricate test results
- Record skipped tests as SKIPPED with reason
- Preserve historical results; do not overwrite past failures
