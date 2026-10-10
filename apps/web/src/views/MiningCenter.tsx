import type { OperatingMode } from "../contracts";
import type {
  MiningHardwareStatus,
  MiningOperationStatus,
  MiningSimulationResult,
  TelemetryReading,
} from "../client-contracts";

interface MiningCenterProps {
  operatingMode: OperatingMode;
}

export function MiningCenter({ operatingMode }: MiningCenterProps) {
  const isSimulation = operatingMode === "simulation";

  const mockSimulation: MiningSimulationResult = {
    sessionId: "sim-0001",
    equipmentName: "Antminer S19 Pro (simulated)",
    grossRevenueBtc: "0.00123456",
    netRevenueBtc: "0.00112345",
    electricityCost: "3.45",
    electricityCurrency: "USD",
    depreciationCost: "1.20",
    netProfit: "45.80",
    profitCurrency: "USD",
    breakEvenBtcPrice: "28000",
    efficiencyJPerTh: "29.5",
    uncertaintyLow: "38.93",
    uncertaintyHigh: "52.67",
    isSimulation: true,
    uptimeHours: 24,
  };

  const mockTelemetry: TelemetryReading = {
    equipmentId: "eq-001",
    timestamp: new Date().toISOString(),
    temperatureC: 65,
    hashRate: { value: "110", unit: "TH/s" },
    powerConsumptionW: 3250,
    status: "running" as MiningHardwareStatus,
  };

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Mining Center</h2>
        <p className="section__description">
          Mining profitability simulation, hardware telemetry, and pool
          coordination. Per AD-015: simulation only; real hardware and pool
          integration require explicit approval and safety controls. The
          MacBook is a control interface, not the assumed mining hardware
          (Section 09.2).
        </p>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Mining Status</div>
            <div className="status-card__value">
              <span className="badge badge--simulation">
                {isSimulation ? "SIMULATION" : "ACTIVE"}
              </span>
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Hardware Status</div>
            <div className="status-card__value">{mockTelemetry.status}</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Temperature</div>
            <div className="status-card__value">
              {mockTelemetry.temperatureC}°C
            </div>
            <div className="status-card__hint">Safe range: 20–75°C</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Hash Rate</div>
            <div className="status-card__value">
              {mockTelemetry.hashRate.value} {mockTelemetry.hashRate.unit}
            </div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Profitability Simulation</h3>
        <table className="table">
          <tbody>
            <tr>
              <td>Equipment</td>
              <td>{mockSimulation.equipmentName}</td>
            </tr>
            <tr>
              <td>Gross Revenue (BTC)</td>
              <td>{mockSimulation.grossRevenueBtc}</td>
            </tr>
            <tr>
              <td>Net Revenue (BTC)</td>
              <td>{mockSimulation.netRevenueBtc}</td>
            </tr>
            <tr>
              <td>Electricity Cost</td>
              <td>
                {mockSimulation.electricityCost} {mockSimulation.electricityCurrency}
              </td>
            </tr>
            <tr>
              <td>Depreciation Cost</td>
              <td>{mockSimulation.depreciationCost}</td>
            </tr>
            <tr>
              <td>Net Profit (USD/day)</td>
              <td>
                <strong>{mockSimulation.netProfit}</strong>
              </td>
            </tr>
            <tr>
              <td>Break-even BTC Price</td>
              <td>${mockSimulation.breakEvenBtcPrice}</td>
            </tr>
            <tr>
              <td>Efficiency</td>
              <td>{mockSimulation.efficiencyJPerTh} J/TH</td>
            </tr>
            <tr>
              <td>Uncertainty Range</td>
              <td>
                {mockSimulation.uncertaintyLow} – {mockSimulation.uncertaintyHigh}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="section__hint">
          ⚠ This is a deterministic simulation (AD-023). No physical mining
          operations are active.
        </p>
      </div>

      <div className="section">
        <h3 className="section__title">Hardware Telemetry</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Equipment ID</th>
              <th>Temperature</th>
              <th>Hash Rate</th>
              <th>Power (W)</th>
              <th>Status</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{mockTelemetry.equipmentId}</td>
              <td>{mockTelemetry.temperatureC}°C</td>
              <td>
                {mockTelemetry.hashRate.value} {mockTelemetry.hashRate.unit}
              </td>
              <td>{mockTelemetry.powerConsumptionW}</td>
              <td>
                <span className="badge badge--running">
                  {mockTelemetry.status}
                </span>
              </td>
              <td>{mockTelemetry.timestamp}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3 className="section__title">Operation Status</h3>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Operation Status</div>
            <div className="status-card__value">
              <span className="badge badge--simulation">uninitialized</span>
            </div>
            <div className="status-card__hint">
              MiningOperationStatus: {("uninitialized" as MiningOperationStatus)}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Uptime</div>
            <div className="status-card__value">
              {mockSimulation.uptimeHours} hours
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
