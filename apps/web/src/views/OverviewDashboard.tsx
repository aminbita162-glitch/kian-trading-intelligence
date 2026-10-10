import { useState } from "react";
import {
  isHealthyState,
  isDegradedState,
  isHaltedState,
  type ClientPlatform,
} from "../client-contracts";
import { onboardingStepOrder } from "../client-contracts";

interface HealthData {
  status: string;
  service: string;
  version: string;
  operating_mode: string;
  is_live: boolean;
  timestamp: string;
}

interface OverviewDashboardProps {
  health: HealthData | null;
  error: string | null;
  onStartOnboarding: () => void;
}

export function OverviewDashboard({
  health,
  error,
  onStartOnboarding,
}: OverviewDashboardProps) {
  const [onboardingStep] = useState(0);

  const onboardingSteps = onboardingStepOrder();
  const onboardingProgress = Math.round(
    (onboardingStep / (onboardingSteps.length - 1)) * 100,
  );

  return (
    <div className="view">
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

      <div className="section">
        <h2 className="section__title">Platform Overview</h2>
        <p className="section__description">
          Kian Trading Intelligence provides a unified dashboard for trading,
          mining, financial management, and operational safety. The MacBook
          application runs as a Tauri native app; the iPhone experience is a
          responsive PWA. All clients are monitoring and configuration
          interfaces — not financial execution authorities (Section 03.1).
        </p>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Active Sessions</div>
            <div className="status-card__value">0</div>
            <div className="status-card__hint">No active trading sessions</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Risk Exposure</div>
            <div className="status-card__value">0.00%</div>
            <div className="status-card__hint">of max exposure</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">System Health</div>
            <div className="status-card__value">
              <span className="badge badge--healthy">HEALTHY</span>
            </div>
            <div className="status-card__hint">All systems nominal</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Onboarding</div>
            <div className="status-card__value">{onboardingProgress}%</div>
            <button
              className="btn btn--primary"
              onClick={onStartOnboarding}
            >
              Start Onboarding
            </button>
          </div>
        </div>
      </div>

      <div className="section">
        <h2 className="section__title">Operating Mode Distinction</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Mode</th>
              <th>Description</th>
              <th>Real Money</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>SIMULATION</td>
              <td>Historical or synthetic data</td>
              <td>No</td>
              <td>
                {health?.operating_mode === "simulation" ? "✅" : "—"}
              </td>
            </tr>
            <tr>
              <td>PAPER</td>
              <td>Simulated trading with approved data</td>
              <td>No</td>
              <td>{health?.operating_mode === "paper" ? "✅" : "—"}</td>
            </tr>
            <tr>
              <td>LIVE</td>
              <td>Real financial execution (gated)</td>
              <td>Yes (after all gates)</td>
              <td>{health?.operating_mode === "live" ? "✅" : "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Re-export for testing
export { isHealthyState, isDegradedState, isHaltedState };
export type { ClientPlatform };
