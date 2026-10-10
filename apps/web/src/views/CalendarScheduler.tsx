import type {
  TradingSession,
  CalendarEvent,
  SessionState,
} from "../client-contracts";

export function CalendarScheduler() {
  const mockSessions: TradingSession[] = [];
  const mockEvents: CalendarEvent[] = [];

  const sessionStates: SessionState[] = [
    "draft",
    "scheduled",
    "preflight",
    "awaiting_user_approval",
    "running",
    "degraded",
    "safe_halt",
    "reconciling",
    "completed",
    "cancelled",
  ];

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Calendar & Session Scheduler</h2>
        <p className="section__description">
          Trading session scheduling with explicit timezone handling. Per
          Section 06.1: every session must specify tenant and profile;
          strategy version; exchange and instruments; capital allocation;
          risk policy; start and stop conditions; preflight requirements;
          end-of-session position policy.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Session State Machine</h3>
        <div className="state-flow">
          {sessionStates.map((state, idx) => (
            <span key={state} className="state-pill">
              <span className={`badge badge--${state}`}>{state}</span>
              {idx < sessionStates.length - 1 && (
                <span className="state-arrow">→</span>
              )}
            </span>
          ))}
        </div>
        <p className="section__hint">
          Critical failures require reconciliation and human approval before
          resumption (Section 06.3).
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Scheduled Sessions</h3>
        {mockSessions.length === 0 ? (
          <div className="empty-state">
            <p>No scheduled sessions. Every session requires authorization
              and preflight checks before execution.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Session ID</th>
                <th>Strategy</th>
                <th>Exchange</th>
                <th>Capital</th>
                <th>State</th>
                <th>Scheduled Start</th>
                <th>Scheduled End</th>
              </tr>
            </thead>
            <tbody>
              {mockSessions.map((s) => (
                <tr key={s.sessionId}>
                  <td>{s.sessionId}</td>
                  <td>{s.strategyVersionId}</td>
                  <td>{s.exchange}</td>
                  <td>{s.capitalAllocation}</td>
                  <td>
                    <span className={`badge badge--${s.state}`}>{s.state}</span>
                  </td>
                  <td>{s.scheduledStart ?? "—"}</td>
                  <td>{s.scheduledEnd ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Calendar Events</h3>
        {mockEvents.length === 0 ? (
          <div className="empty-state">
            <p>No calendar events. Sessions appear here when scheduled.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Title</th>
                <th>Start</th>
                <th>End</th>
                <th>State</th>
                <th>Timezone</th>
              </tr>
            </thead>
            <tbody>
              {mockEvents.map((e) => (
                <tr key={e.eventId}>
                  <td>{e.eventId}</td>
                  <td>{e.title}</td>
                  <td>{e.startTime}</td>
                  <td>{e.endTime}</td>
                  <td>
                    <span className={`badge badge--${e.state}`}>{e.state}</span>
                  </td>
                  <td>{e.timezone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
