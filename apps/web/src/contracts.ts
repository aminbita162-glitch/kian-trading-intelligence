/**
 * Shared contract types for Kian Trading Intelligence.
 *
 * These mirror the Python contracts in packages/contracts/.
 * Architecture Decisions: AD-003, AD-004, AD-014, AD-021,
 * AD-002 (Multi-Tenant), AD-010 (Zero-Trust), AD-026 (Step-Up Auth).
 */

// ── Operating Mode (AD-003) ──

export type OperatingMode = "simulation" | "paper" | "live";

// ── Order State (AD-014) ──

export type OrderState =
  | "created"
  | "validated"
  | "risk_approved"
  | "submission_pending"
  | "submitted"
  | "partially_filled"
  | "filled"
  | "cancelled"
  | "rejected"
  | "expired"
  | "unknown_outcome"
  | "reconciliation_required"
  | "safe_halt";

export type OrderSide = "buy" | "sell";

/** Legal order state transitions. */
export const LEGAL_ORDER_TRANSITIONS: Record<OrderState, OrderState[]> = {
  created: ["validated", "rejected", "cancelled"],
  validated: ["risk_approved", "rejected", "cancelled"],
  risk_approved: ["submission_pending", "cancelled", "expired"],
  submission_pending: ["submitted", "rejected", "expired", "safe_halt"],
  submitted: [
    "partially_filled",
    "filled",
    "cancelled",
    "rejected",
    "expired",
    "unknown_outcome",
    "safe_halt",
  ],
  partially_filled: [
    "filled",
    "cancelled",
    "unknown_outcome",
    "reconciliation_required",
    "safe_halt",
  ],
  filled: [],
  cancelled: [],
  rejected: [],
  expired: [],
  unknown_outcome: ["reconciliation_required", "safe_halt"],
  reconciliation_required: ["filled", "partially_filled", "cancelled", "safe_halt"],
  safe_halt: ["reconciliation_required"],
};

export function isLegalTransition(from: OrderState, to: OrderState): boolean {
  return LEGAL_ORDER_TRANSITIONS[from]?.includes(to) ?? false;
}

export function isTerminalState(state: OrderState): boolean {
  return LEGAL_ORDER_TRANSITIONS[state]?.length === 0;
}

export const TERMINAL_STATES: OrderState[] = ["filled", "cancelled", "rejected", "expired"];

export interface OrderIntent {
  intentId: string;
  tenantId: string;
  profileId: string;
  symbol: string;
  side: OrderSide;
  quantity: string;
  createdAt: string;
  state: OrderState;
  idempotencyKey?: string;
}

// ── Session State (Section 06.2) ──

export type SessionState =
  | "draft"
  | "scheduled"
  | "preflight"
  | "awaiting_user_approval"
  | "running"
  | "degraded"
  | "safe_halt"
  | "reconciling"
  | "completed"
  | "cancelled";

// ── Identity & Security (Phase 02) ──

export type UserRole = "viewer" | "trader" | "risk_manager" | "admin" | "owner";

export type MFAMethod = "totp" | "sms" | "email" | "hardware_key";

export type SessionStatus = "active" | "step_up_required" | "expired" | "revoked" | "locked";

export type DeviceStatus = "pending" | "trusted" | "revoked" | "blocked";

export type CredentialType =
  | "exchange_api_key"
  | "exchange_api_secret"
  | "wallet_private_key"
  | "other";

export type AuditEventType =
  | "login_success"
  | "login_failed"
  | "logout"
  | "session_expired"
  | "session_revoked"
  | "mfa_challenged"
  | "mfa_verified"
  | "mfa_failed"
  | "mfa_enabled"
  | "mfa_disabled"
  | "step_up_granted"
  | "step_up_denied"
  | "device_trusted"
  | "device_revoked"
  | "device_blocked"
  | "credential_stored"
  | "credential_accessed"
  | "credential_rotated"
  | "credential_revoked"
  | "cross_tenant_access_blocked"
  | "privilege_escalation_blocked"
  | "tenant_created"
  | "user_created"
  | "user_suspended"
  | "user_reactivated";

/** Privilege level for each role (lower = less privileged). */
export const ROLE_PRIVILEGE_LEVEL: Record<UserRole, number> = {
  viewer: 0,
  trader: 1,
  risk_manager: 2,
  admin: 3,
  owner: 4,
};

/** Check if an actor role can manage a target role (strictly higher privilege required). */
export function canManageRole(actor: UserRole, target: UserRole): boolean {
  return ROLE_PRIVILEGE_LEVEL[actor] > ROLE_PRIVILEGE_LEVEL[target];
}

export interface Tenant {
  tenantId: string;
  name: string;
  isActive: boolean;
}

export interface User {
  userId: string;
  tenantId: string;
  email: string;
  role: UserRole;
  isActive: boolean;
  mfaEnabled: boolean;
}

export interface AuthSession {
  sessionId: string;
  tenantId: string;
  userId: string;
  status: SessionStatus;
  hasStepUp: boolean;
  isExpired: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
  tenantId: string;
  deviceFingerprint?: string;
}

export interface LoginResponse {
  sessionId: string;
  userId: string;
  tenantId: string;
  email: string;
  role: UserRole;
  mfaRequired: boolean;
}
