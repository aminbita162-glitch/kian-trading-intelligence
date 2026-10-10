import type {
  FinancialAccount,
  JournalEntry,
  ProfitLoss,
  ProfitThreshold,
  ProfitReservation,
  WithdrawalRequest,
} from "../client-contracts";

export function FinancialCenter() {
  const mockAccounts: FinancialAccount[] = [
    {
      accountId: "acc-001",
      tenantId: "tenant-001",
      asset: "USDT",
      accountType: "trading_balance",
      balance: "100000.00",
      reservedAmount: "0.00",
      availableBalance: "100000.00",
    },
    {
      accountId: "acc-002",
      tenantId: "tenant-001",
      asset: "BTC",
      accountType: "trading_balance",
      balance: "0.50000000",
      reservedAmount: "0.00000000",
      availableBalance: "0.50000000",
    },
  ];

  const mockPnl: ProfitLoss = {
    realizedPnl: "0.00",
    unrealizedPnl: "0.00",
    totalPnl: "0.00",
    currency: "USDT",
    period: "all-time",
  };

  const mockThresholds: ProfitThreshold[] = [];
  const mockReservations: ProfitReservation[] = [];
  const mockWithdrawals: WithdrawalRequest[] = [];
  const mockJournal: JournalEntry[] = [];

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Financial Center</h2>
        <p className="section__description">
          Financial ledger, P&L reporting, profit policies, and withdrawal
          requests. Per Section 16: distinguish realized and unrealized P&L;
          available and reserved capital. Per AD-018: balanced journal
          postings with exact decimal arithmetic.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Profit & Loss Summary</h3>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Realized P&L</div>
            <div className="status-card__value">
              {mockPnl.realizedPnl} {mockPnl.currency}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Unrealized P&L</div>
            <div className="status-card__value">
              {mockPnl.unrealizedPnl} {mockPnl.currency}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Total P&L</div>
            <div className="status-card__value">
              {mockPnl.totalPnl} {mockPnl.currency}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Period</div>
            <div className="status-card__value">{mockPnl.period}</div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Accounts</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Account ID</th>
              <th>Asset</th>
              <th>Type</th>
              <th>Balance</th>
              <th>Reserved</th>
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            {mockAccounts.map((account) => (
              <tr key={account.accountId}>
                <td>{account.accountId}</td>
                <td>{account.asset}</td>
                <td>{account.accountType}</td>
                <td>{account.balance}</td>
                <td>{account.reservedAmount}</td>
                <td>{account.availableBalance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3 className="section__title">Profit Thresholds</h3>
        {mockThresholds.length === 0 ? (
          <div className="empty-state">
            <p>No profit thresholds configured. Profit thresholds trigger
              alerts when realized P&L crosses configured levels (AD-007).</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Threshold</th>
                <th>Currency</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {mockThresholds.map((t) => (
                <tr key={t.thresholdId}>
                  <td>{t.thresholdId}</td>
                  <td>{t.type}</td>
                  <td>{t.thresholdValue}</td>
                  <td>{t.currency}</td>
                  <td>{t.isActive ? "✅" : "❌"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Profit Reservations</h3>
        {mockReservations.length === 0 ? (
          <div className="empty-state">
            <p>No profit reservations. Profit reservation is NOT a withdrawal
              (Section 07.3).</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Amount</th>
                <th>Reason</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {mockReservations.map((r) => (
                <tr key={r.reservationId}>
                  <td>{r.reservationId}</td>
                  <td>{r.amount} {r.currency}</td>
                  <td>{r.reason}</td>
                  <td>{r.createdAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Withdrawal Requests</h3>
        {mockWithdrawals.length === 0 ? (
          <div className="empty-state">
            <p>No withdrawal requests. Actual withdrawals require separate
              authorization and provider/legal eligibility (Section 07.3,
              AD-019). Default trading API credentials must not permit
              withdrawals.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Asset</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {mockWithdrawals.map((w) => (
                <tr key={w.requestId}>
                  <td>{w.requestId}</td>
                  <td>{w.asset}</td>
                  <td>{w.amount}</td>
                  <td>{w.status}</td>
                  <td>{w.createdAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Journal Entries</h3>
        {mockJournal.length === 0 ? (
          <div className="empty-state">
            <p>No journal entries. All financial postings use balanced
              double-entry bookkeeping with exact decimal arithmetic
              (AD-018).</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Entry ID</th>
                <th>Type</th>
                <th>Description</th>
                <th>Balanced</th>
                <th>Mining</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {mockJournal.map((e) => (
                <tr key={e.entryId}>
                  <td>{e.entryId}</td>
                  <td>{e.entryType}</td>
                  <td>{e.description}</td>
                  <td>{e.isBalanced ? "✅" : "❌"}</td>
                  <td>{e.isMining ? "Yes" : "No"}</td>
                  <td>{e.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
