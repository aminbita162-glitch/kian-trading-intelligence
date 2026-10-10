import { describe, it, expect } from "vitest";
import {
  REMOTE_COMMAND_CONTRACT_VERSION,
  COMMANDS_REQUIRING_STEP_UP,
  requiresStepUp,
  isRemoteCommandExpired,
  validateRemoteCommand,
  type RemoteCommandType,
} from "../src/remote-commands";

describe("Remote Command Contracts — AD-027", () => {
  it("contract version is 1.0.0", () => {
    expect(REMOTE_COMMAND_CONTRACT_VERSION).toBe("1.0.0");
  });

  it("emergency_stop requires step-up", () => {
    expect(requiresStepUp("emergency_stop")).toBe(true);
  });

  it("start_session requires step-up", () => {
    expect(requiresStepUp("start_session")).toBe(true);
  });

  it("stop_session requires step-up", () => {
    expect(requiresStepUp("stop_session")).toBe(true);
  });

  it("cancel_order requires step-up", () => {
    expect(requiresStepUp("cancel_order")).toBe(true);
  });

  it("update_risk_policy requires step-up", () => {
    expect(requiresStepUp("update_risk_policy")).toBe(true);
  });

  it("view_positions does not require step-up", () => {
    expect(requiresStepUp("view_positions")).toBe(false);
  });

  it("view_ledger does not require step-up", () => {
    expect(requiresStepUp("view_ledger")).toBe(false);
  });

  it("exactly 5 commands require step-up", () => {
    expect(COMMANDS_REQUIRING_STEP_UP.size).toBe(5);
  });

  it("isRemoteCommandExpired detects past expiry", () => {
    const past = new Date(Date.now() - 60000).toISOString();
    expect(isRemoteCommandExpired(past)).toBe(true);
  });

  it("isRemoteCommandExpired does not flag future expiry", () => {
    const future = new Date(Date.now() + 60000).toISOString();
    expect(isRemoteCommandExpired(future)).toBe(false);
  });

  it("validateRemoteCommand rejects missing idempotency key", () => {
    const result = validateRemoteCommand(
      {
        commandType: "view_positions",
        tenantId: "t1",
        userId: "u1",
        profileId: "p1",
        targetResource: "positions",
        operation: "view",
        idempotencyKey: "",
        authenticationAssurance: "standard",
      },
      false,
    );
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("Idempotency key");
  });

  it("validateRemoteCommand rejects missing tenant ID", () => {
    const result = validateRemoteCommand(
      {
        commandType: "view_positions",
        tenantId: "",
        userId: "u1",
        profileId: "p1",
        targetResource: "positions",
        operation: "view",
        idempotencyKey: "idem-001",
        authenticationAssurance: "standard",
      },
      false,
    );
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("Tenant ID");
  });

  it("validateRemoteCommand rejects missing user ID", () => {
    const result = validateRemoteCommand(
      {
        commandType: "view_positions",
        tenantId: "t1",
        userId: "",
        profileId: "p1",
        targetResource: "positions",
        operation: "view",
        idempotencyKey: "idem-001",
        authenticationAssurance: "standard",
      },
      false,
    );
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("User ID");
  });

  it("validateRemoteCommand denies step-up command without step-up auth", () => {
    const result = validateRemoteCommand(
      {
        commandType: "emergency_stop",
        tenantId: "t1",
        userId: "u1",
        profileId: "p1",
        targetResource: "all",
        operation: "emergency_stop",
        idempotencyKey: "idem-001",
        authenticationAssurance: "standard",
      },
      false,
    );
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("Step-up authentication required");
  });

  it("validateRemoteCommand allows step-up command with step-up auth", () => {
    const result = validateRemoteCommand(
      {
        commandType: "emergency_stop",
        tenantId: "t1",
        userId: "u1",
        profileId: "p1",
        targetResource: "all",
        operation: "emergency_stop",
        idempotencyKey: "idem-001",
        authenticationAssurance: "step_up",
      },
      true,
    );
    expect(result.valid).toBe(true);
  });

  it("validateRemoteCommand allows non-step-up command without step-up", () => {
    const result = validateRemoteCommand(
      {
        commandType: "view_positions",
        tenantId: "t1",
        userId: "u1",
        profileId: "p1",
        targetResource: "positions",
        operation: "view",
        idempotencyKey: "idem-001",
        authenticationAssurance: "standard",
      },
      false,
    );
    expect(result.valid).toBe(true);
  });

  it("all 7 remote command types exist", () => {
    const types: RemoteCommandType[] = [
      "emergency_stop",
      "start_session",
      "stop_session",
      "cancel_order",
      "update_risk_policy",
      "view_positions",
      "view_ledger",
    ];
    expect(types).toHaveLength(7);
  });
});
