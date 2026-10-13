---------------------------- MODULE SafeHaltModel ----------------------------
(*
  Formal model of the SAFE_HALT protocol.

  Per E4 (Safety Plane Hardening): formal model of SAFE_HALT checked in CI.

  Invariant: when emergency stop is active, no new exposure-increasing
  (buy) orders are authorized. SAFE_HALT requires reconciliation before
  resuming. The system does not auto-restart after SAFE_HALT — it requires
  explicit human deactivation.
*)

VARIABLES
    emergencyStopActive,
    sessionState,
    (* Was the last buy order authorized? *)
    lastBuyAuthorized

Init ==
    /\ emergencyStopActive = FALSE
    /\ sessionState = "draft"
    /\ lastBuyAuthorized = FALSE

(* Emergency stop activation/deactivation *)
ToggleEmergencyStop ==
    /\ emergencyStopActive' = \~emergencyStopActive
    /\ sessionState' = sessionState
    /\ lastBuyAuthorized' = lastBuyAuthorized

(* Attempt to authorize a buy order *)
AuthorizeBuy ==
    /\ sessionState = "running"
    /\ emergencyStopActive = FALSE
    /\ lastBuyAuthorized' = TRUE
    /\ sessionState' = sessionState
    /\ emergencyStopActive' = emergencyStopActive

(* Emergency stop blocks buy orders *)
BlockBuyOnEmergencyStop ==
    /\ emergencyStopActive = TRUE
    /\ lastBuyAuthorized' = FALSE
    /\ sessionState' = "safe_halt"
    /\ emergencyStopActive' = emergencyStopActive

(* Session enters SAFE_HALT *)
EnterSafeHalt ==
    /\ sessionState \in {"running", "degraded"}
    /\ sessionState' = "safe_halt"
    /\ emergencyStopActive' = TRUE
    /\ lastBuyAuthorized' = FALSE

(* SAFE_HALT requires reconciliation before resuming *)
ResumeFromSafeHalt ==
    /\ sessionState = "safe_halt"
    /\ sessionState' = "reconciling"
    /\ emergencyStopActive' = emergencyStopActive
    /\ lastBuyAuthorized' = FALSE

(* Next step *)
Next ==
    \/ ToggleEmergencyStop
    \/ AuthorizeBuy
    \/ BlockBuyOnEmergencyStop
    \/ EnterSafeHalt
    \/ ResumeFromSafeHalt

(* Invariant: emergency stop blocks buy authorization *)
EmergencyStopBlocksBuyInv ==
    emergencyStopActive = TRUE => lastBuyAuthorized = FALSE

(* Invariant: SAFE_HALT only transitions to reconciling *)
SafeHaltTransitionsInv ==
    sessionState = "safe_halt" => sessionState' = "reconciling"

(* Invariant: no auto-restart — deactivation requires explicit toggle *)
NoAutoRestartInv ==
    sessionState = "safe_halt" => \~(sessionState' \in {"running", "degraded"})

=============================================================================
\* Modification History
\* Last modified Fri Oct 13 2026
