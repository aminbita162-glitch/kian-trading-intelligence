import { describe, it, expect } from "vitest";
import {
  isLegalTransition,
  isTerminalState,
  TERMINAL_STATES,
  LEGAL_ORDER_TRANSITIONS,
  type OrderState,
} from "../src/contracts";

describe("Order State Transitions", () => {
  it("created -> validated is legal", () => {
    expect(isLegalTransition("created", "validated")).toBe(true);
  });

  it("created -> submitted is illegal (must go through risk_approved)", () => {
    expect(isLegalTransition("created", "submitted")).toBe(false);
  });

  it("risk_approved -> submission_pending is legal", () => {
    expect(isLegalTransition("risk_approved", "submission_pending")).toBe(true);
  });

  it("filled is terminal", () => {
    expect(isTerminalState("filled")).toBe(true);
  });

  it("cancelled is terminal", () => {
    expect(isTerminalState("cancelled")).toBe(true);
  });

  it("created is not terminal", () => {
    expect(isTerminalState("created")).toBe(false);
  });

  it("terminal states have empty transition arrays", () => {
    for (const state of TERMINAL_STATES) {
      expect(LEGAL_ORDER_TRANSITIONS[state]).toEqual([]);
    }
  });

  it("safe_halt -> reconciliation_required is legal", () => {
    expect(isLegalTransition("safe_halt", "reconciliation_required")).toBe(true);
  });

  it("unknown_outcome -> reconciliation_required is legal", () => {
    expect(isLegalTransition("unknown_outcome", "reconciliation_required")).toBe(true);
  });

  it("all 13 states are present", () => {
    const allStates = Object.keys(LEGAL_ORDER_TRANSITIONS);
    expect(allStates).toHaveLength(13);
  });

  it("no state can transition to created", () => {
    for (const state of Object.keys(LEGAL_ORDER_TRANSITIONS) as OrderState[]) {
      expect(LEGAL_ORDER_TRANSITIONS[state]).not.toContain("created");
    }
  });
});
