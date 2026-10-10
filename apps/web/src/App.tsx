import { useState, useEffect, useCallback } from "react";
import type { DashboardView } from "./navigation";
import { NAVIGATION_ITEMS } from "./navigation";
import type { OperatingMode } from "./contracts";
import type { ClientPlatform } from "./client-contracts";
import { detectPlatform, isTauri, isPWA } from "./client-contracts";
import { OverviewDashboard } from "./views/OverviewDashboard";
import { TradingCenter } from "./views/TradingCenter";
import { MiningCenter } from "./views/MiningCenter";
import { FinancialCenter } from "./views/FinancialCenter";
import { CalendarScheduler } from "./views/CalendarScheduler";
import { NotificationHub } from "./views/NotificationHub";
import { ConnectedAccounts } from "./views/ConnectedAccounts";
import { SecuritySettings } from "./views/SecuritySettings";
import { IncidentRecovery } from "./views/IncidentRecovery";
import { Onboarding } from "./views/Onboarding";
import { RemoteCommandPanel } from "./views/RemoteCommandPanel";

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
  const [activeView, setActiveView] = useState<DashboardView>("overview");
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [platform] = useState<ClientPlatform>(() => detectPlatform());
  const [isNativeTauri] = useState(() => isTauri());
  const [isInstalledPWA] = useState(() => isPWA());

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

  const handleViewChange = useCallback((view: DashboardView) => {
    setActiveView(view);
  }, []);

  const handleOnboardingComplete = useCallback(() => {
    setShowOnboarding(false);
    setActiveView("overview");
  }, []);

  if (showOnboarding) {
    return (
      <Onboarding
        onComplete={handleOnboardingComplete}
        platform={platform}
      />
    );
  }

  const operatingMode: OperatingMode = health
    ? (health.operating_mode as OperatingMode)
    : "simulation";

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-row">
          <div>
            <h1 className="app__title">Kian Trading Intelligence</h1>
            <p className="app__subtitle">
              Secure, auditable, cost-aware cryptocurrency trading and mining intelligence platform
            </p>
          </div>
          <div className="app__header-status">
            <span className={`badge badge--${operatingMode}`}>
              {operatingMode.toUpperCase()}
            </span>
            {health ? (
              <span className="app__version">v{health.version}</span>
            ) : error ? (
              <span className="app__error">⚠ {error}</span>
            ) : null}
            <span className="app__platform">{platform}</span>
            {isNativeTauri && <span className="app__platform-tag">Tauri</span>}
            {isInstalledPWA && <span className="app__platform-tag">PWA</span>}
          </div>
        </div>
        <nav className="app__nav">
          {NAVIGATION_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-btn ${activeView === item.id ? "nav-btn--active" : ""}`}
              onClick={() => handleViewChange(item.id)}
              title={item.description}
            >
              <span className="nav-btn__icon">{item.icon}</span>
              <span className="nav-btn__label">{item.label}</span>
            </button>
          ))}
        </nav>
      </header>

      <main className="app__main">
        {activeView === "overview" && (
          <OverviewDashboard
            health={health}
            error={error}
            onStartOnboarding={() => setShowOnboarding(true)}
          />
        )}
        {activeView === "trading" && <TradingCenter operatingMode={operatingMode} />}
        {activeView === "mining" && <MiningCenter operatingMode={operatingMode} />}
        {activeView === "financial" && <FinancialCenter />}
        {activeView === "calendar" && <CalendarScheduler />}
        {activeView === "notifications" && <NotificationHub />}
        {activeView === "accounts" && <ConnectedAccounts />}
        {activeView === "security" && <SecuritySettings />}
        {activeView === "incidents" && <IncidentRecovery />}
        {activeView === "onboarding" && (
          <RemoteCommandPanel operatingMode={operatingMode} />
        )}
      </main>

      <footer className="app__footer">
        <p>
          Phase 08 — MacBook & iPhone Applications · Proprietary — All Rights Reserved ·
          Amin Azimi / Azimi Innovation Lab
        </p>
        <p className="app__footer-disclaimer">
          No live trading, real mining, or real financial operations are enabled or authorized.
          {health?.is_live ? " ⚠ LIVE MODE ACTIVE" : " · Simulation mode active"}
        </p>
      </footer>
    </div>
  );
}
