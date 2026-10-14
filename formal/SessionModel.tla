---------------------------- MODULE SessionModel ----------------------------
(*
  Formal model of the trading session state machine.

  Per E4 (Safety Plane Hardening): formal model of session lifecycle
  checked in CI.

  Invariant: session transitions follow LEGAL_SESSION_TRANSITIONS.
  SAFE_HALT can only transition to RECONCILING. COMPLETED and CANCELLED
  are terminal.
*)

VARIABLES
    state

Init ==
    /\ state = "draft"

Next ==
    /\ state = "draft"                  /\ state' = "scheduled"
    \/ state = "draft"                  /\ state' = "cancelled"
    \/ state = "scheduled"              /\ state' = "preflight"
    \/ state = "scheduled"              /\ state' = "cancelled"
    \/ state = "preflight"              /\ state' = "awaiting_user_approval"
    \/ state = "preflight"              /\ state' = "cancelled"
    \/ state = "preflight"              /\ state' = "safe_halt"
    \/ state = "awaiting_user_approval" /\ state' = "running"
    \/ state = "awaiting_user_approval" /\ state' = "cancelled"
    \/ state = "awaiting_user_approval" /\ state' = "safe_halt"
    \/ state = "running"                /\ state' = "degraded"
    \/ state = "running"                /\ state' = "safe_halt"
    \/ state = "running"                /\ state' = "reconciling"
    \/ state = "running"                /\ state' = "completed"
    \/ state = "degraded"                /\ state' = "running"
    \/ state = "degraded"                /\ state' = "safe_halt"
    \/ state = "degraded"                /\ state' = "reconciling"
    \/ state = "degraded"                /\ state' = "completed"
    \/ state = "safe_halt"              /\ state' = "reconciling"
    \/ state = "reconciling"            /\ state' = "running"
    \/ state = "reconciling"            /\ state' = "completed"
    \/ state = "reconciling"            /\ state' = "safe_halt"

(* Terminal states *)
IsTerminal(s) ==
    s \in {"completed", "cancelled"}

(* SAFE_HALT can only go to RECONCILING *)
SafeHaltConstraint ==
    state = "safe_halt" => state' = "reconciling"

(* Invariant: terminal states stay terminal *)
TerminalInv ==
    /\ IsTerminal(state) => state' = state

(* Invariant: SAFE_HALT only transitions to reconciling *)
SafeHaltInv ==
    state = "safe_halt" => state' = "reconciling"

=============================================================================
\* Modification History
\* Last modified Fri Oct 13 2026
