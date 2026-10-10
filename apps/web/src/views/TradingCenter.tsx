import { useState } from "react";
import type { OperatingMode } from "../contracts";
import {
  isHealthyState,
  isDegradedState,
  isHaltedState,
  type OpenOrderSummary,
  type PositionSummary,
  type RiskExposureSummary,
  type SessionState,
} from "../client-contracts";

interface TradingCenterProps {
  operatingMode: OperatingMode;
}

export function TradingCenter({ operatingMode }: TradingCenterProps) {
  const [_mode] = useState<OperatingMode>(operatingMode);

  const mockOrders: OpenOrderSummary[] = [];
  const mockPositions: PositionSummary[] = [];
  const mockRisk: RiskExposureSummary = {
    totalExposure: "0",
    maxExposure: "100000",
    dailyLoss: "0",
    maxDailyLoss: "5000",
    drawdown: "0",
    maxDrawdown: "10000",
    exposurePct: "0.00",
  };

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Trading Center</h2>
        <p className="section__description">
          Active orders, positions, and risk exposure. Per Section 16:
          clearly distinguish submitted and filled orders; realized and
          unrealized P&L; available and reserved capital.
        </p>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Operating Mode</div>
            <div className="status-card__value">
              <span className={`badge badge--${_mode}`}>{_mode.toUpperCase()}</span>
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Open Orders</div>
            <div className="status-card__value">{mockOrders.length}</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Open Positions</div>
            <div className="status-card__value">{mockPositions.length}</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Exposure</div>
            <div className="status-card__value">
              {mockRisk.exposurePct}%
            </div>
            <div className="status-card__hint">
              Max: {mockRisk.maxExposure} USDT
            </div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Open Orders</h3>
        {mockOrders.length === 0 ? (
          <div className="empty-state">
            <p>No open orders. All order submissions require risk
              authorization from the independent Risk & Safety Kernel
              (AD-004 invariant).</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>State</th>
                <th>Filled</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {mockOrders.map((order) => (
                <tr key={order.orderId}>
                  <td>{order.orderId}</td>
                  <td>{order.symbol}</td>
                  <td>{order.side}</td>
                  <td>{order.quantity}</td>
                  <td>
                    <span className={`badge badge--${order.state}`}>
                      {order.state}
                    </span>
                  </td>
                  <td>{order.filledQuantity}</td>
                  <td>{order.createdAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h3 className="section__title">Risk Exposure Summary</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Current</th>
              <th>Limit</th>
              <th>Utilization</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Total Exposure</td>
              <td>{mockRisk.totalExposure} USDT</td>
              <td>{mockRisk.maxExposure} USDT</td>
              <td>{mockRisk.exposurePct}%</td>
            </tr>
            <tr>
              <td>Daily Loss</td>
              <td>{mockRisk.dailyLoss} USDT</td>
              <td>{mockRisk.maxDailyLoss} USDT</td>
              <td>—</td>
            </tr>
            <tr>
              <td>Drawdown</td>
              <td>{mockRisk.drawdown} USDT</td>
              <td>{mockRisk.maxDrawdown} USDT</td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3 className="section__title">Session State Guide</h3>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Healthy States</div>
            <div className="status-card__value">running, completed</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Degraded States</div>
            <div className="status-card__value">degraded, reconciling</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Halted States</div>
            <div className="status-card__value">safe_halt, cancelled</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export { isHealthyState, isDegradedState, isHaltedState };
export type { SessionState };
