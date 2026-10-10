# Kian Trading Intelligence — MacBook (Tauri) Application

Per AD-030 (Unified MacBook and iPhone Experience) and AD-031 (Technology
Direction: Tauri for the MacBook application).

## Architecture

The Tauri shell wraps the shared React/TypeScript frontend (`apps/web/`),
providing native macOS window management, CSP enforcement, and platform
integration. The client is NOT a trusted financial execution authority
(Section 03.1) — all execution is cloud-authorized via the FastAPI backend.

## Build

```bash
# Prerequisites: Rust toolchain, Tauri CLI
# cargo install tauri-cli --version "^2"

# Development
cargo tauri dev

# Production build (generates .app and .dmg)
cargo tauri build
```

## Security

- CSP enforces `default-src 'self'` — no external script loading.
- All API communication targets the backend (`http://localhost:8000` in dev).
- No withdrawal-enabled credentials by default (AD-019).
- Emergency stop uses a deterministic path (Section 05.6).

## License

Proprietary — All Rights Reserved — Amin Azimi / Azimi Innovation Lab
