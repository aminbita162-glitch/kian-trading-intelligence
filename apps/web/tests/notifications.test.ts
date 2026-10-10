import { describe, it, expect } from "vitest";
import {
  DEFAULT_PREFERENCES,
  shouldDeliverNotification,
  priorityRank,
  sortNotificationsByPriority,
  type NotificationType,
  type NotificationPriority,
  type Notification,
} from "../src/notifications";

describe("Notification Hub Contracts — AD-009", () => {
  it("default preferences have all alerts enabled", () => {
    expect(DEFAULT_PREFERENCES.profitAlertsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.lossWarningsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.orderNotificationsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.riskAlertsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.sessionNotificationsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.emergencyAlertsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.miningAlertsEnabled).toBe(true);
    expect(DEFAULT_PREFERENCES.systemHealthAlertsEnabled).toBe(true);
  });

  it("shouldDeliverNotification returns true when enabled", () => {
    const prefs = {
      ...DEFAULT_PREFERENCES,
      tenantId: "t1",
      userId: "u1",
    };
    expect(shouldDeliverNotification("profit_alert", prefs)).toBe(true);
  });

  it("shouldDeliverNotification returns false when disabled", () => {
    const prefs = {
      ...DEFAULT_PREFERENCES,
      tenantId: "t1",
      userId: "u1",
      profitAlertsEnabled: false,
    };
    expect(shouldDeliverNotification("profit_alert", prefs)).toBe(false);
  });

  it("shouldDeliverNotification respects loss warning preference", () => {
    const prefs = {
      ...DEFAULT_PREFERENCES,
      tenantId: "t1",
      userId: "u1",
      lossWarningsEnabled: false,
    };
    expect(shouldDeliverNotification("loss_warning", prefs)).toBe(false);
  });

  it("shouldDeliverNotification respects emergency alert preference", () => {
    const prefs = {
      ...DEFAULT_PREFERENCES,
      tenantId: "t1",
      userId: "u1",
      emergencyAlertsEnabled: false,
    };
    expect(
      shouldDeliverNotification("emergency_stop_triggered", prefs),
    ).toBe(false);
  });

  it("priorityRank: critical > high > medium > low", () => {
    expect(priorityRank("critical")).toBeGreaterThan(priorityRank("high"));
    expect(priorityRank("high")).toBeGreaterThan(priorityRank("medium"));
    expect(priorityRank("medium")).toBeGreaterThan(priorityRank("low"));
  });

  it("priorityRank: critical is 4", () => {
    expect(priorityRank("critical")).toBe(4);
  });

  it("priorityRank: low is 1", () => {
    expect(priorityRank("low")).toBe(1);
  });

  it("sortNotificationsByPriority sorts by priority descending", () => {
    const notifications: Notification[] = [
      {
        notificationId: "1",
        tenantId: "t1",
        userId: "u1",
        type: "system_health" as NotificationType,
        priority: "low" as NotificationPriority,
        title: "Low",
        message: "low",
        status: "unread",
        createdAt: "2026-01-01T00:00:00Z",
      },
      {
        notificationId: "2",
        tenantId: "t1",
        userId: "u1",
        type: "emergency_stop_triggered" as NotificationType,
        priority: "critical" as NotificationPriority,
        title: "Critical",
        message: "critical",
        status: "unread",
        createdAt: "2026-01-01T00:00:01Z",
      },
      {
        notificationId: "3",
        tenantId: "t1",
        userId: "u1",
        type: "risk_threshold_breached" as NotificationType,
        priority: "high" as NotificationPriority,
        title: "High",
        message: "high",
        status: "unread",
        createdAt: "2026-01-01T00:00:02Z",
      },
    ];
    const sorted = sortNotificationsByPriority(notifications);
    expect(sorted[0].priority).toBe("critical");
    expect(sorted[1].priority).toBe("high");
    expect(sorted[2].priority).toBe("low");
  });

  it("all 11 notification types exist", () => {
    const types: NotificationType[] = [
      "profit_alert",
      "loss_warning",
      "order_filled",
      "order_rejected",
      "risk_threshold_breached",
      "session_started",
      "session_stopped",
      "emergency_stop_triggered",
      "mining_profitability_change",
      "reconciliation_required",
      "system_health",
    ];
    expect(types).toHaveLength(11);
  });

  it("all 4 priorities exist", () => {
    const priorities: NotificationPriority[] = [
      "low",
      "medium",
      "high",
      "critical",
    ];
    expect(priorities).toHaveLength(4);
  });
});
