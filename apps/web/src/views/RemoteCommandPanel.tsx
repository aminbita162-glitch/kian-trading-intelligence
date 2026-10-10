import { useState } from "react";
import type { OperatingMode } from "../contracts";
import type { RemoteCommand, RemoteCommandType } from "../remote-commands";
import {
  requiresStepUp,
  validateRemoteCommand,
  isRemoteCommandExpired,
  REMOTE_COMMAND_CONTRACT_VERSION,
} from "../remote-commands";

interface RemoteCommandPanelProps {
  operatingMode: OperatingMode;
}

export function RemoteCommandPanel({ operatingMode }: RemoteCommandPanelProps) {
  const [commands, setCommands] = useState<RemoteCommand[]>([]);
  const [selectedType, setSelectedType] =
    useState<RemoteCommandType>("emergency_stop");
  const [hasStepUp, setHasStepUp] = useState(false);

  const commandTypes: RemoteCommandType[] = [
    "emergency_stop",
    "start_session",
    "stop_session",
    "cancel_order",
    "update_risk_policy",
    "view_positions",
    "view_ledger",
  ];

  function issueCommand() {
    const needsStepUp = requiresStepUp(selectedType);
    const validation = validateRemoteCommand(
      {
        commandType: selectedType,
        tenantId: "tenant-001",
        userId: "user-001",
        profileId: "profile-001",
        targetResource: "session/all",
        operation: selectedType,
        idempotencyKey: `idem-${Date.now()}`,
        authenticationAssurance: hasStepUp ? "step_up" : "standard",
      },
      hasStepUp,
    );

    if (!validation.valid) {
      const cmd: RemoteCommand = {
        commandId: `cmd-${Date.now()}`,
        commandType: selectedType,
        tenantId: "tenant-001",
        userId: "user-001",
        profileId: "profile-001",
        targetResource: "session/all",
        operation: selectedType,
        authorizationScope: "tenant-scoped",
        contractVersion: REMOTE_COMMAND_CONTRACT_VERSION,
        idempotencyKey: `idem-${Date.now()}`,
        expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        authenticationAssurance: hasStepUp ? "step_up" : "standard",
        status: "denied",
        createdAt: new Date().toISOString(),
        error: validation.reason,
      };
      setCommands((prev) => [cmd, ...prev]);
      return;
    }

    const cmd: RemoteCommand = {
      commandId: `cmd-${Date.now()}`,
      commandType: selectedType,
      tenantId: "tenant-001",
      userId: "user-001",
      profileId: "profile-001",
      targetResource: "session/all",
      operation: selectedType,
      authorizationScope: "tenant-scoped",
      contractVersion: REMOTE_COMMAND_CONTRACT_VERSION,
      idempotencyKey: `idem-${Date.now()}`,
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
      authenticationAssurance: hasStepUp ? "step_up" : "standard",
      status: needsStepUp && !hasStepUp ? "denied" : "completed",
      createdAt: new Date().toISOString(),
      result: needsStepUp
        ? hasStepUp
          ? "Command executed (step-up verified)"
          : "Denied: step-up required"
        : "Command executed (standard auth)",
    };
    setCommands((prev) => [cmd, ...prev]);
  }

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Secure Remote Commands</h2>
        <p className="section__description">
          Typed action contracts with authorization scope, contract version,
          idempotency key, expiry, and authentication assurance. Per AD-027:
          remote commands require typed action contracts, valid authorization,
          expiry, idempotency, and auditable outcomes. Per Section 05.6:
          emergency stop uses a deterministic path independent of LLM
          processing.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Issue Command</h3>
        <div className="form-group">
          <label className="form-label">Command Type</label>
          <select
            className="form-select"
            value={selectedType}
            onChange={(e) =>
              setSelectedType(e.target.value as RemoteCommandType)
            }
          >
            {commandTypes.map((type) => (
              <option key={type} value={type}>
                {type}
                {requiresStepUp(type) ? " (step-up required)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">
            <input
              type="checkbox"
              checked={hasStepUp}
              onChange={(e) => setHasStepUp(e.target.checked)}
            />
            Step-up authentication granted
          </label>
        </div>
        <div className="form-group">
          <span className="badge badge--simulation">
            Operating mode: {operatingMode}
          </span>
          <span className="badge badge--info">
            Contract v{REMOTE_COMMAND_CONTRACT_VERSION}
          </span>
        </div>
        <button className="btn btn--primary" onClick={issueCommand}>
          Issue Command
        </button>
      </div>

      <div className="section">
        <h3 className="section__title">Command History ({commands.length})</h3>
        {commands.length === 0 ? (
          <div className="empty-state">
            <p>No commands issued. Issue a command above to see it here.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Command ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Auth</th>
                <th>Result/Error</th>
                <th>Created</th>
                <th>Expired</th>
              </tr>
            </thead>
            <tbody>
              {commands.map((cmd) => (
                <tr key={cmd.commandId}>
                  <td>{cmd.commandId}</td>
                  <td>{cmd.commandType}</td>
                  <td>
                    <span className={`badge badge--${cmd.status}`}>
                      {cmd.status}
                    </span>
                  </td>
                  <td>{cmd.authenticationAssurance}</td>
                  <td>{cmd.error ?? cmd.result ?? "—"}</td>
                  <td>{cmd.createdAt}</td>
                  <td>
                    {isRemoteCommandExpired(cmd.expiresAt) ? "Yes" : "No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
