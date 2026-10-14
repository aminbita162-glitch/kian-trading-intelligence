---------------------------- MODULE OrderModel ----------------------------
(*
  Formal model of the order state machine for Kian Trading Intelligence.

  Per E4 (Safety Plane Hardening): formal model of order lifecycle
  checked in CI.

  Invariant: order state transitions follow LEGAL_ORDER_TRANSITIONS.
  Terminal states have no outgoing transitions. No state transitions
  to CREATED.
*)

CONSTANTS
    (* The set of all order states *)
    States

VARIABLES
    (* Current state of the order *)
    state

Init ==
    /\ state = "CREATED"

Next ==
    /\ state = "CREATED"        /\ state' = "VALIDATED"
    \/ state = "CREATED"        /\ state' = "REJECTED"
    \/ state = "CREATED"        /\ state' = "CANCELLED"
    \/ state = "VALIDATED"      /\ state' = "RISK_APPROVED"
    \/ state = "VALIDATED"      /\ state' = "REJECTED"
    \/ state = "RISK_APPROVED"  /\ state' = "SUBMISSION_PENDING"
    \/ state = "RISK_APPROVED"  /\ state' = "CANCELLED"
    \/ state = "RISK_APPROVED"  /\ state' = "REJECTED"
    \/ state = "SUBMISSION_PENDING" /\ state' = "SUBMITTED"
    \/ state = "SUBMISSION_PENDING" /\ state' = "CANCELLED"
    \/ state = "SUBMISSION_PENDING" /\ state' = "EXPIRED"
    \/ state = "SUBMITTED"      /\ state' = "PARTIALLY_FILLED"
    \/ state = "SUBMITTED"      /\ state' = "FILLED"
    \/ state = "SUBMITTED"      /\ state' = "CANCELLED"
    \/ state = "SUBMITTED"      /\ state' = "REJECTED"
    \/ state = "SUBMITTED"      /\ state' = "EXPIRED"
    \/ state = "SUBMITTED"      /\ state' = "UNKNOWN_OUTCOME"
    \/ state = "SUBMITTED"      /\ state' = "RECONCILIATION_REQUIRED"
    \/ state = "SUBMITTED"      /\ state' = "SAFE_HALT"
    \/ state = "PARTIALLY_FILLED" /\ state' = "FILLED"
    \/ state = "PARTIALLY_FILLED" /\ state' = "CANCELLED"
    \/ state = "PARTIALLY_FILLED" /\ state' = "UNKNOWN_OUTCOME"
    \/ state = "PARTIALLY_FILLED" /\ state' = "RECONCILIATION_REQUIRED"
    \/ state = "PARTIALLY_FILLED" /\ state' = "SAFE_HALT"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "FILLED"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "CANCELLED"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "REJECTED"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "EXPIRED"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "RECONCILIATION_REQUIRED"
    \/ state = "UNKNOWN_OUTCOME" /\ state' = "SAFE_HALT"
    \/ state = "RECONCILIATION_REQUIRED" /\ state' = "FILLED"
    \/ state = "RECONCILIATION_REQUIRED" /\ state' = "CANCELLED"
    \/ state = "RECONCILIATION_REQUIRED" /\ state' = "REJECTED"
    \/ state = "RECONCILIATION_REQUIRED" /\ state' = "SAFE_HALT"

(* Terminal states have no outgoing transitions *)
IsTerminal(s) ==
    s \in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}

(* No state transitions to CREATED *)
NoTransitionToCreated ==
    state' # "CREATED"

(* Invariant: terminal states stay terminal *)
TerminalInv ==
    /\ IsTerminal(state) => state' = state

(* Invariant: CREATED is never a target *)
CreatedNeverTargetInv ==
    state' # "CREATED"

=============================================================================
\* Modification History
\* Last modified Fri Oct 13 2026
