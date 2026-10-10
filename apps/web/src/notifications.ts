/**
 * Notification hub contracts for Kian Trading Intelligence.
 *
 * Per AD-009 (Notifications and Mobile Monitoring): provide a unified
 * notification hub, auditable transaction history, configurable profit
 * alerts, and secure iPhone monitoring.
 *
 * Per Section 16 (MacBook and iPhone Product Experience): notification hub
 * is deliverable 7.
 */

// ── Notification Types ──

export type NotificationType =
  | "profit_alert"
  | "loss_warning"
  | "order_filled"
  | "order_rejected"
  | "risk_threshold_breached"
  | "session_started"
  | "session_stopped"
  | "emergency_stop_triggered"
  | "mining_profitability_change"
  | "reconciliation_required"
  | "system_health";

export type NotificationPriority = "low" | "medium" | "high" | "critical";

export type NotificationStatus = "unread" | "read" | "dismissed" | "archived";

export interface Notification {
  notificationId: string;
  tenantId: string;
  userId: string;
  type: NotificationType;
  priority: NotificationPriority;
  title: string;
  message: string;
  status: NotificationStatus;
  createdAt: string;
  readAt?: string;
  relatedEntityType?: string;
  relatedEntityId?: string;
}

// ── Notification Preferences ──

export interface NotificationPreferences {
  tenantId: string;
  userId: string;
  profitAlertsEnabled: boolean;
  profitAlertThreshold?: string;
  lossWarningsEnabled: boolean;
  lossWarningThreshold?: string;
  orderNotificationsEnabled: boolean;
  riskAlertsEnabled: boolean;
  sessionNotificationsEnabled: boolean;
  emergencyAlertsEnabled: boolean;
  miningAlertsEnabled: boolean;
  systemHealthAlertsEnabled: boolean;
  quietHoursStart?: string;
  quietHoursEnd?: string;
}

// ── Audit Trail (AD-009, AD-022) ──

export interface NotificationAuditEntry {
  auditId: string;
  notificationId: string;
  action: "created" | "read" | "dismissed" | "archived";
  timestamp: string;
  userId: string;
}

export const DEFAULT_PREFERENCES: Omit<
  NotificationPreferences,
  "tenantId" | "userId"
> = {
  profitAlertsEnabled: true,
  lossWarningsEnabled: true,
  orderNotificationsEnabled: true,
  riskAlertsEnabled: true,
  sessionNotificationsEnabled: true,
  emergencyAlertsEnabled: true,
  miningAlertsEnabled: true,
  systemHealthAlertsEnabled: true,
};

export function shouldDeliverNotification(
  type: NotificationType,
  prefs: NotificationPreferences,
): boolean {
  switch (type) {
    case "profit_alert":
      return prefs.profitAlertsEnabled;
    case "loss_warning":
      return prefs.lossWarningsEnabled;
    case "order_filled":
    case "order_rejected":
      return prefs.orderNotificationsEnabled;
    case "risk_threshold_breached":
      return prefs.riskAlertsEnabled;
    case "session_started":
    case "session_stopped":
      return prefs.sessionNotificationsEnabled;
    case "emergency_stop_triggered":
      return prefs.emergencyAlertsEnabled;
    case "mining_profitability_change":
      return prefs.miningAlertsEnabled;
    case "system_health":
      return prefs.systemHealthAlertsEnabled;
    case "reconciliation_required":
      return prefs.riskAlertsEnabled;
    default:
      return true;
  }
}

export function priorityRank(priority: NotificationPriority): number {
  const ranks: Record<NotificationPriority, number> = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };
  return ranks[priority];
}

export function sortNotificationsByPriority(
  notifications: Notification[],
): Notification[] {
  return [...notifications].sort(
    (a, b) => priorityRank(b.priority) - priorityRank(a.priority),
  );
}
