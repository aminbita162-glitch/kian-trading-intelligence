import type {
  ConnectedAccount,
  ExchangeProvider,
  ConnectionStatus,
} from "../client-contracts";

export function ConnectedAccounts() {
  const mockAccounts: ConnectedAccount[] = [
    {
      connectionId: "conn-001",
      tenantId: "tenant-001",
      provider: "simulated",
      label: "Simulated Exchange",
      status: "connected" as ConnectionStatus,
      apiKeyScopes: ["read", "trade"],
      withdrawalEnabled: false,
      connectedAt: "2026-10-01T00:00:00Z",
      lastSyncAt: new Date().toISOString(),
      isSimulation: true,
    },
  ];

  const availableProviders: ExchangeProvider[] = [
    "simulated",
    "binance",
    "coinbase",
    "kraken",
  ];

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Connected Accounts</h2>
        <p className="section__description">
          Exchange connections with scoped API keys. Per AD-005: maintain
          non-custodial boundaries, reconciliation, scoped credentials, and
          manual recovery after critical failures. Per AD-019: withdrawal-
          enabled trading credentials are prohibited by default.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Active Connections</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Connection ID</th>
              <th>Provider</th>
              <th>Label</th>
              <th>Status</th>
              <th>Scopes</th>
              <th>Withdrawal</th>
              <th>Simulation</th>
              <th>Connected</th>
              <th>Last Sync</th>
            </tr>
          </thead>
          <tbody>
            {mockAccounts.map((acc) => (
              <tr key={acc.connectionId}>
                <td>{acc.connectionId}</td>
                <td>{acc.provider}</td>
                <td>{acc.label}</td>
                <td>
                  <span className={`badge badge--${acc.status}`}>
                    {acc.status}
                  </span>
                </td>
                <td>{acc.apiKeyScopes.join(", ")}</td>
                <td>{acc.withdrawalEnabled ? "⚠ Enabled" : "Disabled"}</td>
                <td>{acc.isSimulation ? "✅" : "❌"}</td>
                <td>{acc.connectedAt}</td>
                <td>{acc.lastSyncAt ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3 className="section__title">Available Providers</h3>
        <div className="status-grid">
          {availableProviders.map((provider) => (
            <div key={provider} className="status-card">
              <div className="status-card__label">{provider}</div>
              <div className="status-card__value">
                {provider === "simulated" ? (
                  <span className="badge badge--connected">Connected</span>
                ) : (
                  <span className="badge badge--disconnected">Not Connected</span>
                )}
              </div>
              {provider !== "simulated" && (
                <div className="status-card__hint">
                  Requires explicit approval and KYC verification
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Security Notice</h3>
        <div className="notice notice--warning">
          <p>
            <strong>⚠ Security:</strong> Default trading API credentials must
            NOT permit withdrawals (Section 10.2, AD-019). Withdrawal-enabled
            credentials require explicit authorization and step-up
            authentication.
          </p>
        </div>
      </div>
    </div>
  );
}
