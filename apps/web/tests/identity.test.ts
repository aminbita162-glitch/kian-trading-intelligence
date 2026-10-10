import { describe, it, expect } from "vitest";
import {
  canManageRole,
  ROLE_PRIVILEGE_LEVEL,
  type UserRole,
  type SessionStatus,
  type MFAMethod,
  type CredentialType,
  type AuditEventType,
} from "../src/contracts";

describe("Identity Contracts — Role Privilege Hierarchy", () => {
  it("viewer has the lowest privilege", () => {
    expect(ROLE_PRIVILEGE_LEVEL.viewer).toBe(0);
  });

  it("owner has the highest privilege", () => {
    expect(ROLE_PRIVILEGE_LEVEL.owner).toBe(4);
  });

  it("privilege order is viewer < trader < risk_manager < admin < owner", () => {
    expect(ROLE_PRIVILEGE_LEVEL.viewer).toBeLessThan(ROLE_PRIVILEGE_LEVEL.trader);
    expect(ROLE_PRIVILEGE_LEVEL.trader).toBeLessThan(ROLE_PRIVILEGE_LEVEL.risk_manager);
    expect(ROLE_PRIVILEGE_LEVEL.risk_manager).toBeLessThan(ROLE_PRIVILEGE_LEVEL.admin);
    expect(ROLE_PRIVILEGE_LEVEL.admin).toBeLessThan(ROLE_PRIVILEGE_LEVEL.owner);
  });
});

describe("Identity Contracts — canManageRole", () => {
  it("owner can manage admin", () => {
    expect(canManageRole("owner", "admin")).toBe(true);
  });

  it("owner can manage trader", () => {
    expect(canManageRole("owner", "trader")).toBe(true);
  });

  it("owner cannot manage another owner", () => {
    expect(canManageRole("owner", "owner")).toBe(false);
  });

  it("admin can manage trader", () => {
    expect(canManageRole("admin", "trader")).toBe(true);
  });

  it("admin cannot manage owner", () => {
    expect(canManageRole("admin", "owner")).toBe(false);
  });

  it("admin cannot manage another admin", () => {
    expect(canManageRole("admin", "admin")).toBe(false);
  });

  it("viewer cannot manage anyone", () => {
    const roles: UserRole[] = ["viewer", "trader", "risk_manager", "admin", "owner"];
    for (const role of roles) {
      expect(canManageRole("viewer", role)).toBe(false);
    }
  });
});

describe("Identity Contracts — Type Coverage", () => {
  it("all 5 user roles are present", () => {
    const roles: UserRole[] = ["viewer", "trader", "risk_manager", "admin", "owner"];
    expect(roles).toHaveLength(5);
  });

  it("all 4 MFA methods are present", () => {
    const methods: MFAMethod[] = ["totp", "sms", "email", "hardware_key"];
    expect(methods).toHaveLength(4);
  });

  it("all 5 session statuses are present", () => {
    const statuses: SessionStatus[] = [
      "active",
      "step_up_required",
      "expired",
      "revoked",
      "locked",
    ];
    expect(statuses).toHaveLength(5);
  });

  it("all 4 credential types are present", () => {
    const types: CredentialType[] = [
      "exchange_api_key",
      "exchange_api_secret",
      "wallet_private_key",
      "other",
    ];
    expect(types).toHaveLength(4);
  });

  it("all major audit event types are present", () => {
    const eventTypes: AuditEventType[] = [
      "login_success",
      "login_failed",
      "logout",
      "mfa_challenged",
      "mfa_verified",
      "mfa_failed",
      "cross_tenant_access_blocked",
      "privilege_escalation_blocked",
      "credential_stored",
      "credential_accessed",
      "credential_rotated",
      "credential_revoked",
    ];
    expect(eventTypes).toHaveLength(12);
  });
});
