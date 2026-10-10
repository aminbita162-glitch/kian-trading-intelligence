import type {
  Incident,
  IncidentSeverity,
  IncidentStatus,
  RecoveryAction,
} from "../client-contracts";

export function IncidentRecovery() {
  const mockIncidents: Incident[] = [];

  const severities: IncidentSeverity[] = ["info", "warning", "critical"];
  const statuses: IncidentStatus[] = [
    "active",
    "investigating",
    "mitigated",
    "resolved",
    "acknowledged",
  ];

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Incident & Recovery Status</h2>
        <p className="section__description">
          Incident tracking and recovery coordination. Per AD-017: critical
          failures require SAFE_HALT, reconciliation, and human authorization
          before resumption. Per Section 16: clearly distinguish healthy,
          degraded, and halted operations. Per AD-023: fault injection and
          deterministic verification.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Active Incidents</h3>
        {mockIncidents.length === 0 ? (
          <div className="empty-state">
            <p>
              <span className="badge badge--healthy">No active incidents</span>
            </p>
            <p>
              All systems operational. No critical failures detected. Recovery
              from critical failures requires human authorization (AD-017).
            </p>
          </div>
        ) : (
          <div className="incident-list">
            {mockIncidents.map((inc) => (
              <div
                key={inc.incidentId}
                className={`incident incident--${inc.severity}`}
              >
                <div className="incident__header">
                  <span className={`severity-badge severity--${inc.severity}`}>
                    {inc.severity}
                  </span>
                  <span className={`badge badge--${inc.status}`}>
                    {inc.status}
                  </span>
                </div>
                <div className="incident__title">{inc.title}</div>
                <div className="incident__description">{inc.description}</div>
                <div className="incident__meta">
                  <span>Affected: {inc.affectedComponent}</span>
                  <span>Created: {inc.createdAt}</span>
                  {inc.requiresHumanApproval && (
                    <span className="notice--warning">
                      ⚠ Requires human approval for recovery
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Incident Severity Levels</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Description</th>
              <th>Auto-Recovery</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>info</td>
              <td>Informational — no action required</td>
              <td>N/A</td>
            </tr>
            <tr>
              <td>warning</td>
              <td>Degraded operation — investigation recommended</td>
              <td>Limited</td>
            </tr>
            <tr>
              <td>critical</td>
              <td>Critical failure — SAFE_HALT, reconciliation required</td>
              <td>
                <strong>No</strong> — human authorization required
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3 className="section__title">Recovery Process</h3>
        <div className="recovery-steps">
          <div className="recovery-step">
            <span className="step-number">1</span>
            <span>SAFE_HALT — all new exposure-increasing orders blocked</span>
          </div>
          <div className="recovery-step">
            <span className="step-number">2</span>
            <span>Preserve order and financial evidence</span>
          </div>
          <div className="recovery-step">
            <span className="step-number">3</span>
            <span>Reconciliation — reconcile exchange outcomes</span>
          </div>
          <div className="recovery-step">
            <span className="step-number">4</span>
            <span>Human authorization required for resumption</span>
          </div>
          <div className="recovery-step">
            <span className="step-number">5</span>
            <span>No automatic trading restart after critical failure</span>
          </div>
        </div>
        <p className="section__hint">
          Per Section 05.6: an accepted emergency command is not proof that all
          external orders were cancelled.
        </p>
        <p className="section__hint">
          Severities: {severities.join(", ")} · Statuses: {statuses.join(", ")}
        </p>
      </div>
    </div>
  );
}

export type { RecoveryAction };
