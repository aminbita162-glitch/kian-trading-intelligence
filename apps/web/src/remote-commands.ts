/**
 * Remote command contracts for Kian Trading Intelligence.
 *
 * Per Section 10.4 (Remote Action Contracts): sensitive commands require
 * actor identity; tenant and profile; target resource; operation; authorization
 * scope; contract version; idempotency key; expiry; authentication assurance.
 *
 * Per AD-027 (Verified Remote Commands): remote commands require typed action
 * contracts, valid authorization, expiry, idempotency, and auditable outcomes.
 *
 * Per Section 05.6 (Emergency Stop): remote emergency stop must use a
 * deterministic path independent of LLM processing.
 */

import type { OperatingMode } from "./contracts";

// ── Remote Command Types (AD-027, Section 10.4) ──

export type RemoteCommandType =
  | "emergency_stop"
  | "start_session"
  | "stop_session"
  | "cancel_order"
  | "update_risk_policy"
  | "view_positions"
  | "view_ledger";

export type RemoteCommandStatus =
  | "pending"
  | "authorized"
  | "executing"
  | "completed"
  | "denied"
  | "expired"
  | "failed";

export interface RemoteCommand {
  commandId: string;
  commandType: RemoteCommandType;
  tenantId: string;
  userId: string;
  profileId: string;
  targetResource: string;
  operation: string;
  authorizationScope: string;
  contractVersion: string;
  idempotencyKey: string;
  expiresAt: string;
  authenticationAssurance: "standard" | "step_up";
  status: RemoteCommandStatus;
  createdAt: string;
  result?: string;
  error?: string;
}

export interface RemoteCommandRequest {
  commandType: RemoteCommandType;
  tenantId: string;
  userId: string;
  profileId: string;
  targetResource: string;
  operation: string;
  idempotencyKey: string;
  authenticationAssurance: "standard" | "step_up";
}

export interface RemoteCommandResponse {
  commandId: string;
  status: RemoteCommandStatus;
  message: string;
  executedAt: string;
}

// ── Emergency Stop (Section 05.6) ──

export interface EmergencyStopRequest {
  tenantId: string;
  userId: string;
  reason: string;
  idempotencyKey: string;
}

export interface EmergencyStopResponse {
  accepted: boolean;
  timestamp: string;
  message: string;
  operatingMode: OperatingMode;
  pendingOrdersBlocked: boolean;
}

// ── Validation ──

export const REMOTE_COMMAND_CONTRACT_VERSION = "1.0.0";

export const COMMANDS_REQUIRING_STEP_UP: ReadonlySet<RemoteCommandType> =
  new Set([
    "emergency_stop",
    "start_session",
    "stop_session",
    "cancel_order",
    "update_risk_policy",
  ]);

export function requiresStepUp(commandType: RemoteCommandType): boolean {
  return COMMANDS_REQUIRING_STEP_UP.has(commandType);
}

export function isRemoteCommandExpired(expiresAt: string): boolean {
  return new Date(expiresAt).getTime() < Date.now();
}

export function validateRemoteCommand(
  req: RemoteCommandRequest,
  hasStepUp: boolean,
): { valid: boolean; reason?: string } {
  if (!req.idempotencyKey || req.idempotencyKey.length === 0) {
    return { valid: false, reason: "Idempotency key is required" };
  }
  if (!req.tenantId || req.tenantId.length === 0) {
    return { valid: false, reason: "Tenant ID is required" };
  }
  if (!req.userId || req.userId.length === 0) {
    return { valid: false, reason: "User ID is required" };
  }
  if (requiresStepUp(req.commandType) && !hasStepUp) {
    return {
      valid: false,
      reason: "Step-up authentication required for this command",
    };
  }
  return { valid: true };
}
