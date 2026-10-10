import { describe, it, expect } from "vitest";
import {
  onboardingStepOrder,
  nextOnboardingStep,
  isOnboardingComplete,
  isHealthyState,
  isDegradedState,
  isHaltedState,
  detectPlatform,
  isTauri,
  isPWA,
  type OnboardingStep,
  type SessionState,
} from "../src/client-contracts";

describe("Client Contracts — Onboarding (deliverable 3)", () => {
  it("onboardingStepOrder has 8 steps", () => {
    expect(onboardingStepOrder()).toHaveLength(8);
  });

  it("first step is welcome", () => {
    expect(onboardingStepOrder()[0]).toBe("welcome");
  });

  it("last step is complete", () => {
    const order = onboardingStepOrder();
    expect(order[order.length - 1]).toBe("complete");
  });

  it("nextOnboardingStep from welcome is create_tenant", () => {
    expect(nextOnboardingStep("welcome")).toBe("create_tenant");
  });

  it("nextOnboardingStep from complete is null", () => {
    expect(nextOnboardingStep("complete")).toBeNull();
  });

  it("nextOnboardingStep from review is complete", () => {
    expect(nextOnboardingStep("review")).toBe("complete");
  });

  it("isOnboardingComplete is true when step is complete", () => {
    expect(
      isOnboardingComplete({
        currentStep: "complete",
        completedSteps: [],
        mfaEnabled: false,
        accountConnected: false,
      }),
    ).toBe(true);
  });

  it("isOnboardingComplete is false when not complete", () => {
    expect(
      isOnboardingComplete({
        currentStep: "welcome",
        completedSteps: [],
        mfaEnabled: false,
        accountConnected: false,
      }),
    ).toBe(false);
  });

  it("all onboarding steps are valid", () => {
    const steps: OnboardingStep[] = [
      "welcome",
      "create_tenant",
      "create_profile",
      "configure_risk",
      "connect_account",
      "mfa_setup",
      "review",
      "complete",
    ];
    expect(steps).toHaveLength(8);
  });
});

describe("Client Contracts — Session State Helpers", () => {
  it("isHealthyState: running is healthy", () => {
    expect(isHealthyState("running")).toBe(true);
  });

  it("isHealthyState: completed is healthy", () => {
    expect(isHealthyState("completed")).toBe(true);
  });

  it("isHealthyState: draft is not healthy", () => {
    expect(isHealthyState("draft")).toBe(false);
  });

  it("isDegradedState: degraded is degraded", () => {
    expect(isDegradedState("degraded")).toBe(true);
  });

  it("isDegradedState: reconciling is degraded", () => {
    expect(isDegradedState("reconciling")).toBe(true);
  });

  it("isHaltedState: safe_halt is halted", () => {
    expect(isHaltedState("safe_halt")).toBe(true);
  });

  it("isHaltedState: cancelled is halted", () => {
    expect(isHaltedState("cancelled")).toBe(true);
  });

  it("isHaltedState: running is not halted", () => {
    expect(isHaltedState("running")).toBe(false);
  });

  it("all 10 session states exist", () => {
    const states: SessionState[] = [
      "draft",
      "scheduled",
      "preflight",
      "awaiting_user_approval",
      "running",
      "degraded",
      "safe_halt",
      "reconciling",
      "completed",
      "cancelled",
    ];
    expect(states).toHaveLength(10);
  });
});

describe("Client Contracts — Platform Detection", () => {
  it("detectPlatform returns a valid platform", () => {
    const platform = detectPlatform();
    expect(["macbook", "iphone", "web"]).toContain(platform);
  });

  it("isTauri returns false in test environment", () => {
    expect(isTauri()).toBe(false);
  });

  it("isPWA returns false in test environment", () => {
    expect(isPWA()).toBe(false);
  });
});
