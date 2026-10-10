import { describe, it, expect } from "vitest";
import {
  NAVIGATION_ITEMS,
  getNavigationItem,
  type DashboardView,
} from "../src/navigation";

describe("Navigation — Section 16 Product Experience", () => {
  it("has 9 navigation items matching Section 16 deliverables", () => {
    expect(NAVIGATION_ITEMS).toHaveLength(9);
  });

  it("includes overview dashboard", () => {
    const item = getNavigationItem("overview");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Overview");
  });

  it("includes trading center", () => {
    const item = getNavigationItem("trading");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Trading Center");
  });

  it("includes mining center", () => {
    const item = getNavigationItem("mining");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Mining Center");
  });

  it("includes financial center", () => {
    const item = getNavigationItem("financial");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Financial Center");
  });

  it("includes calendar scheduler", () => {
    const item = getNavigationItem("calendar");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Calendar & Sessions");
  });

  it("includes notification hub", () => {
    const item = getNavigationItem("notifications");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Notification Hub");
  });

  it("includes connected accounts", () => {
    const item = getNavigationItem("accounts");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Connected Accounts");
  });

  it("includes security settings", () => {
    const item = getNavigationItem("security");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Security Settings");
  });

  it("includes incident recovery", () => {
    const item = getNavigationItem("incidents");
    expect(item).toBeDefined();
    expect(item?.label).toBe("Incidents & Recovery");
  });

  it("getNavigationItem returns undefined for unknown view", () => {
    const item = getNavigationItem("nonexistent" as DashboardView);
    expect(item).toBeUndefined();
  });

  it("every navigation item has an icon and description", () => {
    for (const item of NAVIGATION_ITEMS) {
      expect(item.icon).toBeTruthy();
      expect(item.description).toBeTruthy();
    }
  });
});
