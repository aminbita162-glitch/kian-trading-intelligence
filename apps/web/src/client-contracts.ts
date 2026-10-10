/**
 * Mining and financial contract types for the client dashboards.
 *
 * These mirror the Python contracts in packages/contracts/mining.py and
 * packages/contracts/ledger.py for the client-side UI.
 *
 * Per Section 16: mining center (deliverable 5), financial center
 * (deliverable 6), connected-account settings (deliverable 10).
 */

// ── Mining Contracts (Phase 07 mirror) ──

export type MiningHardwareStatus =
  | "idle"
  | "running"
  | "throttled"
  | "overheating"
  | "failed"
  | "maintenance"
  | "offline";

export type MiningOperationStatus =
  | "uninitialized"
  | "initializing"
  | "running"
  | "paused"
  | "emergency_stopped"
  | "failed";

export type PoolPayoutScheme = "pps" | "pplns" | "prop" | "solo";

export interface HashRate {
  value: string;
  unit: string;
}

export interface EquipmentSpec {
  equipmentId: string;
  name: string;
  hashRate: HashRate;
  powerConsumptionW: number;
  cost: string;
  usefulLifeYears: number;
  salvageValue: string;
  minTempC: number;
  maxTempC: number;
  efficiencyJPerTh: string;
}

export interface MiningSimulationResult {
  sessionId: string;
  equipmentName: string;
  grossRevenueBtc: string;
  netRevenueBtc: string;
  electricityCost: string;
  electricityCurrency: string;
  depreciationCost: string;
  netProfit: string;
  profitCurrency: string;
  breakEvenBtcPrice: string;
  efficiencyJPerTh: string;
  uncertaintyLow: string;
  uncertaintyHigh: string;
  isSimulation: boolean;
  uptimeHours: number;
}

export interface TelemetryReading {
  equipmentId: string;
  timestamp: string;
  temperatureC: number;
  hashRate: HashRate;
  powerConsumptionW: number;
  status: MiningHardwareStatus;
}

export interface MiningSessionConfig {
  sessionId: string;
  tenantId: string;
  equipmentSpecs: EquipmentSpec[];
  electricityRatePerKwh: string;
  electricityCurrency: string;
  poolName: string;
  poolFeePct: string;
  payoutScheme: PoolPayoutScheme;
  networkDifficulty: string;
  blockReward: string;
  btcPriceUsd: string;
  uptimePct: number;
}

// ── Financial Contracts (Phase 05 mirror) ──

export type AccountType =
  | "asset"
  | "liability"
  | "equity"
  | "trading_balance"
  | "mining_revenue"
  | "fee_account";

export type AccountSide = "debit" | "credit";

export interface FinancialAccount {
  accountId: string;
  tenantId: string;
  asset: string;
  accountType: AccountType;
  balance: string;
  reservedAmount: string;
  availableBalance: string;
}

export interface JournalEntry {
  entryId: string;
  tenantId: string;
  entryType: string;
  timestamp: string;
  description: string;
  lines: JournalLine[];
  isBalanced: boolean;
  isMining: boolean;
}

export interface JournalLine {
  accountId: string;
  asset: string;
  amount: string;
  value: string;
  side: AccountSide;
}

export interface ProfitLoss {
  realizedPnl: string;
  unrealizedPnl: string;
  totalPnl: string;
  currency: string;
  period: string;
}

export interface ProfitThreshold {
  thresholdId: string;
  tenantId: string;
  type: string;
  thresholdValue: string;
  currency: string;
  isActive: boolean;
}

export interface ProfitReservation {
  reservationId: string;
  tenantId: string;
  amount: string;
  currency: string;
  reason: string;
  createdAt: string;
}

export interface WithdrawalRequest {
  requestId: string;
  tenantId: string;
  asset: string;
  amount: string;
  status: string;
  createdAt: string;
  reason: string;
}

// ── Connected Accounts (Section 16, deliverable 10) ──

export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error"
  | "suspended";

export type ExchangeProvider = "simulated" | "binance" | "coinbase" | "kraken";

export interface ConnectedAccount {
  connectionId: string;
  tenantId: string;
  provider: ExchangeProvider;
  label: string;
  status: ConnectionStatus;
  apiKeyScopes: string[];
  withdrawalEnabled: boolean;
  connectedAt: string;
  lastSyncAt?: string;
  isSimulation: boolean;
}

export interface ConnectAccountRequest {
  tenantId: string;
  provider: ExchangeProvider;
  label: string;
  apiKeyScope: string[];
  withdrawalEnabled: boolean;
}

// ── Calendar & Session (Section 16, deliverable 7) ──

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

export interface TradingSession {
  sessionId: string;
  tenantId: string;
  profileId: string;
  strategyVersionId: string;
  exchange: string;
  instruments: string[];
  capitalAllocation: string;
  riskPolicyId: string;
  state: SessionState;
  startCondition: string;
  stopCondition: string;
  timezone: string;
  createdAt: string;
  scheduledStart?: string;
  scheduledEnd?: string;
  completedAt?: string;
}

export interface CalendarEvent {
  eventId: string;
  tenantId: string;
  sessionId: string;
  title: string;
  startTime: string;
  endTime: string;
  state: SessionState;
  timezone: string;
}

// ── Incident & Recovery (Section 16, deliverable 11) ──

export type IncidentSeverity = "info" | "warning" | "critical";

export type IncidentStatus =
  | "active"
  | "investigating"
  | "mitigated"
  | "resolved"
  | "acknowledged";

export interface Incident {
  incidentId: string;
  tenantId: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  title: string;
  description: string;
  createdAt: string;
  resolvedAt?: string;
  affectedComponent: string;
  recoveryActions: string[];
  requiresHumanApproval: boolean;
}

export interface RecoveryAction {
  actionId: string;
  incidentId: string;
  actionType: string;
  description: string;
  status: "pending" | "approved" | "executing" | "completed" | "failed";
  requiresApproval: boolean;
  executedAt?: string;
  result?: string;
}

// ── Onboarding (Section 16, deliverable 3) ──

export type OnboardingStep =
  | "welcome"
  | "create_tenant"
  | "create_profile"
  | "configure_risk"
  | "connect_account"
  | "mfa_setup"
  | "review"
  | "complete";

export interface OnboardingState {
  tenantId?: string;
  profileId?: string;
  email?: string;
  currentStep: OnboardingStep;
  completedSteps: OnboardingStep[];
  riskPolicyId?: string;
  mfaEnabled: boolean;
  accountConnected: boolean;
}

export function onboardingStepOrder(): OnboardingStep[] {
  return [
    "welcome",
    "create_tenant",
    "create_profile",
    "configure_risk",
    "connect_account",
    "mfa_setup",
    "review",
    "complete",
  ];
}

export function isOnboardingComplete(state: OnboardingState): boolean {
  return state.currentStep === "complete";
}

export function nextOnboardingStep(
  current: OnboardingStep,
): OnboardingStep | null {
  const order = onboardingStepOrder();
  const idx = order.indexOf(current);
  if (idx === -1 || idx === order.length - 1) return null;
  return order[idx + 1];
}

// ── Trading Dashboard (Section 16, deliverable 4) ──

export interface TradingDashboardData {
  operatingMode: string;
  isLive: boolean;
  activeSessions: TradingSession[];
  openOrders: OpenOrderSummary[];
  positions: PositionSummary[];
  riskExposure: RiskExposureSummary;
}

export interface OpenOrderSummary {
  orderId: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
  state: string;
  filledQuantity: string;
  createdAt: string;
}

export interface PositionSummary {
  symbol: string;
  side: "long" | "short";
  quantity: string;
  avgEntryPrice: string;
  currentPrice: string;
  unrealizedPnl: string;
}

export interface RiskExposureSummary {
  totalExposure: string;
  maxExposure: string;
  dailyLoss: string;
  maxDailyLoss: string;
  drawdown: string;
  maxDrawdown: string;
  exposurePct: string;
}

export function isHealthyState(state: SessionState): boolean {
  return state === "running" || state === "completed";
}

export function isDegradedState(state: SessionState): boolean {
  return state === "degraded" || state === "reconciling";
}

export function isHaltedState(state: SessionState): boolean {
  return state === "safe_halt" || state === "cancelled";
}

// ── PWA / Tauri Platform Detection ──

export type ClientPlatform = "macbook" | "iphone" | "web";

export function detectPlatform(): ClientPlatform {
  if (typeof window === "undefined") return "web";
  const ua = window.navigator.userAgent.toLowerCase();
  if (ua.includes("iphone") || ua.includes("ipad")) return "iphone";
  if (ua.includes("mac")) return "macbook";
  return "web";
}

export function isTauri(): boolean {
  return (
    typeof window !== "undefined" && "__TAURI__" in window
  );
}

export function isPWA(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(display-mode: standalone)").matches
  );
}
