---------------------------- MODULE ReservationModel ----------------------------
(*
  Formal model of the risk reservation lifecycle.

  Per E4 (Safety Plane Hardening): formal model of reservation lifecycle
  checked in CI.

  Invariant: a reservation transitions ACTIVE -> {RELEASED, EXPIRED, CONSUMED}.
  A CONSUMED reservation cannot be released. An EXPIRED reservation cannot
  be consumed. A RELEASED reservation cannot be re-consumed.
*)

VARIABLES
    state

Init ==
    /\ state = "ACTIVE"

Next ==
    /\ state = "ACTIVE"   /\ state' = "RELEASED"
    \/ state = "ACTIVE"   /\ state' = "EXPIRED"
    \/ state = "ACTIVE"   /\ state' = "CONSUMED"

(* Terminal states *)
IsTerminal(s) ==
    s \in {"RELEASED", "EXPIRED", "CONSUMED"}

(* Invariant: terminal states stay terminal *)
TerminalInv ==
    /\ IsTerminal(state) => state' = state

(* Invariant: only ACTIVE can transition *)
OnlyActiveTransitions ==
    state # "ACTIVE" => state' = state

=============================================================================
\* Modification History
\* Last modified Fri Oct 13 2026
