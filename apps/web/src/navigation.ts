/**
 * Dashboard view type for navigation between the different product
 * experiences per Section 16 (MacBook and iPhone Product Experience).
 */

export type DashboardView =
  | "overview"
  | "trading"
  | "mining"
  | "financial"
  | "calendar"
  | "notifications"
  | "accounts"
  | "security"
  | "incidents"
  | "onboarding";

export interface NavigationItem {
  id: DashboardView;
  label: string;
  icon: string;
  description: string;
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    id: "overview",
    label: "Overview",
    icon: "📊",
    description: "System overview and status",
  },
  {
    id: "trading",
    label: "Trading Center",
    icon: "📈",
    description: "Active orders, positions, and risk exposure",
  },
  {
    id: "mining",
    label: "Mining Center",
    icon: "⛏️",
    description: "Mining simulation and profitability",
  },
  {
    id: "financial",
    label: "Financial Center",
    icon: "💰",
    description: "Ledger, P&L, and profit policies",
  },
  {
    id: "calendar",
    label: "Calendar & Sessions",
    icon: "📅",
    description: "Trading session scheduling",
  },
  {
    id: "notifications",
    label: "Notification Hub",
    icon: "🔔",
    description: "Alerts and notifications",
  },
  {
    id: "accounts",
    label: "Connected Accounts",
    icon: "🔌",
    description: "Exchange connections",
  },
  {
    id: "security",
    label: "Security Settings",
    icon: "🔐",
    description: "MFA, sessions, and credentials",
  },
  {
    id: "incidents",
    label: "Incidents & Recovery",
    icon: "🚨",
    description: "Incident status and recovery actions",
  },
];

export function getNavigationItem(id: DashboardView): NavigationItem | undefined {
  return NAVIGATION_ITEMS.find((item) => item.id === id);
}
