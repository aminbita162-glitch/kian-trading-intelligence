import { useState } from "react";
import type {
  Notification,
  NotificationType,
  NotificationPriority,
  NotificationPreferences,
} from "../notifications";
import {
  sortNotificationsByPriority,
  shouldDeliverNotification,
  priorityRank,
  DEFAULT_PREFERENCES,
} from "../notifications";

export function NotificationHub() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [prefs, setPrefs] = useState<NotificationPreferences>({
    ...DEFAULT_PREFERENCES,
    tenantId: "tenant-001",
    userId: "user-001",
  });

  function addMockNotification(
    type: NotificationType,
    priority: NotificationPriority,
    title: string,
    message: string,
  ) {
    const shouldDeliver = shouldDeliverNotification(type, prefs);
    if (!shouldDeliver) return;

    const notification: Notification = {
      notificationId: `notif-${Date.now()}`,
      tenantId: prefs.tenantId,
      userId: prefs.userId,
      type,
      priority,
      title,
      message,
      status: "unread",
      createdAt: new Date().toISOString(),
    };
    setNotifications((prev) => sortNotificationsByPriority([notification, ...prev]));
  }

  function markAsRead(id: string) {
    setNotifications((prev) =>
      prev.map((n) =>
        n.notificationId === id
          ? { ...n, status: "read", readAt: new Date().toISOString() }
          : n,
      ),
    );
  }

  function dismiss(id: string) {
    setNotifications((prev) =>
      prev.map((n) =>
        n.notificationId === id ? { ...n, status: "dismissed" } : n,
      ),
    );
  }

  function togglePref(key: keyof NotificationPreferences) {
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  const unreadCount = notifications.filter((n) => n.status === "unread").length;
  const sortedNotifications = sortNotificationsByPriority(notifications);

  return (
    <div className="view">
      <div className="section">
        <h2 className="section__title">Notification Hub</h2>
        <p className="section__description">
          Unified notification hub with configurable alerts and auditable
          transaction history. Per AD-009: provide a unified notification hub,
          auditable transaction history, configurable profit alerts, and secure
          iPhone monitoring.
        </p>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card__label">Unread</div>
            <div className="status-card__value">{unreadCount}</div>
          </div>
          <div className="status-card">
            <div className="status-card__label">Total</div>
            <div className="status-card__value">{notifications.length}</div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Generate Test Notification</h3>
        <div className="button-group">
          <button
            className="btn btn--secondary"
            onClick={() =>
              addMockNotification(
                "profit_alert",
                "medium",
                "Profit Alert",
                "Daily profit threshold reached.",
              )
            }
          >
            Profit Alert
          </button>
          <button
            className="btn btn--secondary"
            onClick={() =>
              addMockNotification(
                "risk_threshold_breached",
                "high",
                "Risk Alert",
                "Risk exposure exceeds configured threshold.",
              )
            }
          >
            Risk Alert
          </button>
          <button
            className="btn btn--secondary"
            onClick={() =>
              addMockNotification(
                "emergency_stop_triggered",
                "critical",
                "Emergency Stop",
                "Emergency stop has been triggered. All new orders blocked.",
              )
            }
          >
            Emergency Stop
          </button>
          <button
            className="btn btn--secondary"
            onClick={() =>
              addMockNotification(
                "system_health",
                "low",
                "System Health",
                "All systems nominal.",
              )
            }
          >
            System Health
          </button>
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Notification Preferences</h3>
        <div className="preferences-grid">
          {(
            [
              ["profitAlertsEnabled", "Profit Alerts"],
              ["lossWarningsEnabled", "Loss Warnings"],
              ["orderNotificationsEnabled", "Order Notifications"],
              ["riskAlertsEnabled", "Risk Alerts"],
              ["sessionNotificationsEnabled", "Session Notifications"],
              ["emergencyAlertsEnabled", "Emergency Alerts"],
              ["miningAlertsEnabled", "Mining Alerts"],
              ["systemHealthAlertsEnabled", "System Health"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="preference-toggle">
              <input
                type="checkbox"
                checked={prefs[key] as boolean}
                onChange={() => togglePref(key)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className="section">
        <h3 className="section__title">Notifications ({sortedNotifications.length})</h3>
        {sortedNotifications.length === 0 ? (
          <div className="empty-state">
            <p>No notifications. Generate a test notification above.</p>
          </div>
        ) : (
          <div className="notification-list">
            {sortedNotifications.map((n) => (
              <div
                key={n.notificationId}
                className={`notification notification--${n.priority} notification--${n.status}`}
              >
                <div className="notification__header">
                  <span className="notification__type">{n.type}</span>
                  <span className={`notification__priority priority--${n.priority}`}>
                    {n.priority}
                  </span>
                </div>
                <div className="notification__title">{n.title}</div>
                <div className="notification__message">{n.message}</div>
                <div className="notification__meta">
                  <span>{n.createdAt}</span>
                  {n.status === "unread" && (
                    <button
                      className="btn btn--small"
                      onClick={() => markAsRead(n.notificationId)}
                    >
                      Mark Read
                    </button>
                  )}
                  <button
                    className="btn btn--small"
                    onClick={() => dismiss(n.notificationId)}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export { priorityRank };
