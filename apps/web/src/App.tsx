import { useState, useEffect } from "react";

interface HealthResponse {
  status: string;
  service: string;
  version: string;
  operating_mode: string;
  is_live: boolean;
  timestamp: string;
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("/api/health");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: HealthResponse = await res.json();
        setHealth(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch health");
      }
    }
    fetchHealth();
  }, []);

  return (
    <div className="app">
      <header className="app__header">
        <h1 className="app__title">Kian Trading Intelligence</h1>
        <p className="app__subtitle">
          Secure, auditable, cost-aware cryptocurrency trading and mining intelligence platform
        </p>
      </header>

      <div className="status-grid">
        <div className="status-card">
          <div className="status-card__label">Service Status</div>
          <div className="status-card__value">
            {health ? (
              <span className={`badge badge--${health.operating_mode}`}>
                {health.status}
              </span>
            ) : error ? (
              `Error: ${error}`
            ) : (
              "Connecting..."
            )}
          </div>
        </div>

        <div className="status-card">
          <div className="status-card__label">Operating Mode</div>
          <div className="status-card__value">
            {health ? (
              <span className={`badge badge--${health.operating_mode}`}>
                {health.operating_mode.toUpperCase()}
              </span>
            ) : (
              "—"
            )}
          </div>
        </div>

        <div className="status-card">
          <div className="status-card__label">Version</div>
          <div className="status-card__value">{health?.version ?? "—"}</div>
        </div>

        <div className="status-card">
          <div className="status-card__label">Live Trading</div>
          <div className="status-card__value">
            {health ? (health.is_live ? "ENABLED" : "DISABLED") : "—"}
          </div>
        </div>
      </div>

      <footer style={{ marginTop: "2rem", color: "var(--muted)", fontSize: "0.85rem" }}>
        <p>
          Phase 01 — Engineering Foundation · Proprietary — All Rights Reserved ·
          Amin Azimi / Azimi Innovation Lab
        </p>
      </footer>
    </div>
  );
}
