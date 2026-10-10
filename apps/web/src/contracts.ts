/**
 * Shared contract types for Kian Trading Intelligence.
 *
 * These mirror the Python contracts in packages/contracts/.
 * Architecture Decisions: AD-003, AD-004, AD-014, AD-021.
 */

export type OperatingMode = "simulation" | "paper" | "live";

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

export type OrderSide = "buy" | "sell";

/**
 * Legal order state transitions.
 * Maps each state to the set of states it may legally transition to.
 * Empty set = terminal state.
 */
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

/**
 * Check if a state transition is legal.
 */
export function isLegalTransition(from: OrderState, to: OrderState): boolean {
  return LEGAL_ORDER_TRANSITIONS[from]?.includes(to) ?? false;
}

/**
 * Check if a state is terminal (no outgoing transitions).
 */
export function isTerminalState(state: OrderState): boolean {
  return LEGAL_ORDER_TRANSITIONS[state]?.length === 0;
}

/**
 * Terminal states.
 */
export const TERMINAL_STATES: OrderState[] = ["filled", "cancelled", "rejected", "expired"];

/**
 * Order intent interface (mirrors Python OrderIntent).
 */
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
