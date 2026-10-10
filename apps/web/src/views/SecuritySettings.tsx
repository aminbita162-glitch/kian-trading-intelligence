import type {
  MFAMethod,
  SessionStatus,
  DeviceStatus,
  CredentialType,
} from "../contracts";

export function SecuritySettings() {
  const mfaMethods: MFAMethod[] = ["totp", "sms", "email", "hardware_key"];
  const sessionStatuses: SessionStatus[] = [
    "active",
    "step_up_required",
    "expired",
    "revoked",
    "locked",
  ];
  const deviceStatuses: DeviceStatus[] = [
    "pending",
    "trusted",
    "revoked",
    "blocked",
  ];
  const credentialTypes: CredentialType[] = [
    "exchange_api_key",
    "exchange_api_secret",
    "wallet_private_key",
    "other",
  ];

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Security Settings</h2>
        <p className="section__description">
          Multi-factor authentication, session management, device controls, and
          credential vault. Per AD-010: strong authentication, MFA, least
          privilege, secure credentials. Per AD-026: step-up authorization for
          sensitive operations. Per AD-019: non-custodial credential vault.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">MFA Configuration</h3>
        <div className="status-grid">
          {mfaMethods.map((method) => (
            <div key={method} className="status-card">
              <div className="status-card__label">{method.toUpperCase()}</div>
              <div className="status-card__value">
                {method === "totp" ? (
                  <span className="badge badge--simulation">Enabled</span>
                ) : (
                  <span className="badge badge--disconnected">Not Enabled</span>
                )}
              </div>
            </div>
          ))}
        </div>
        <p className="section__hint">
          MFA is required for privileged users (AD-026). Sensitive operations
          require step-up authentication.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Session Statuses</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span className="badge badge--active">active</span></td>
              <td>Session is active and valid</td>
            </tr>
            <tr>
              <td><span className="badge badge--step_up_required">step_up_required</span></td>
              <td>Step-up authentication required for sensitive operations</td>
            </tr>
            <tr>
              <td><span className="badge badge--expired">expired</span></td>
              <td>Session has expired</td>
            </tr>
            <tr>
              <td><span className="badge badge--revoked">revoked</span></td>
              <td>Session has been revoked</td>
            </tr>
            <tr>
              <td><span className="badge badge--locked">locked</span></td>
              <td>Session is locked due to failed attempts</td>
            </tr>
          </tbody>
        </table>
        <p className="section__hint">
          Available session statuses: {sessionStatuses.join(", ")}
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Device Management</h3>
        <div className="status-grid">
          {deviceStatuses.map((status) => (
            <div key={status} className="status-card">
              <div className="status-card__label">{status}</div>
              <div className="status-card__value">
                <span className={`badge badge--${status}`}>{status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Credential Vault</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Credential Type</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {credentialTypes.map((type) => (
              <tr key={type}>
                <td>{type}</td>
                <td>
                  <span className="badge badge--disconnected">
                    No active credentials
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="section__hint">
          Per AD-019: credentials are encrypted, tenant-isolated, and
          access-audited. Withdrawal-enabled credentials are prohibited by
          default.
        </p>
      </div>
    </div>
  );
}
