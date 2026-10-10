import { useState } from "react";
import type {
  OnboardingState,
  OnboardingStep,
  ClientPlatform,
} from "../client-contracts";
import {
  onboardingStepOrder,
  nextOnboardingStep,
  isOnboardingComplete,
} from "../client-contracts";

interface OnboardingProps {
  onComplete: () => void;
  platform: ClientPlatform;
}

export function Onboarding({ onComplete, platform }: OnboardingProps) {
  const [state, setState] = useState<OnboardingState>({
    currentStep: "welcome",
    completedSteps: [],
    mfaEnabled: false,
    accountConnected: false,
  });

  function advance() {
    const next = nextOnboardingStep(state.currentStep);
    if (next === null) {
      setState((prev) => ({
        ...prev,
        currentStep: "complete",
        completedSteps: [...prev.completedSteps, prev.currentStep],
      }));
      onComplete();
      return;
    }
    setState((prev) => ({
      ...prev,
      currentStep: next,
      completedSteps: [...prev.completedSteps, prev.currentStep],
    }));
  }

  const order = onboardingStepOrder();
  const stepIdx = order.indexOf(state.currentStep);
  const progressPct = Math.round((stepIdx / (order.length - 1)) * 100);

  return (
    <div className="view onboarding">
      <div className="onboarding__header">
        <h2 className="section__title">Welcome to Kian Trading Intelligence</h2>
        <p className="section__description">
          Platform: {platform}. This onboarding wizard guides you through
          initial setup: tenant creation, profile configuration, risk policy,
          account connection, and MFA enrollment.
        </p>
      </div>

      <div className="onboarding__progress">
        <div
          className="onboarding__progress-bar"
          style={{ width: `${progressPct}%` }}
        />
        <span className="onboarding__progress-label">{progressPct}%</span>
      </div>

      <div className="onboarding__steps">
        {order.map((step, idx) => (
          <div
            key={step}
            className={`onboarding__step ${
              idx === stepIdx
                ? "onboarding__step--current"
                : idx < stepIdx
                  ? "onboarding__step--done"
                  : ""
            }`}
          >
            <span className="onboarding__step-number">{idx + 1}</span>
            <span className="onboarding__step-label">{step}</span>
          </div>
        ))}
      </div>

      <div className="onboarding__content">
        {state.currentStep === "welcome" && (
          <div>
            <h3>Welcome</h3>
            <p>
              Kian Trading Intelligence is a secure, auditable, cost-aware
              cryptocurrency trading and mining intelligence platform. This
              wizard will guide you through the initial setup process.
            </p>
            <p className="notice notice--info">
              No live trading, real mining, or real financial operations are
              enabled or authorized at this stage.
            </p>
          </div>
        )}
        {state.currentStep === "create_tenant" && (
          <div>
            <h3>Create Tenant</h3>
            <p>
              A tenant is the isolation boundary for your organization
              (AD-002). All users, sessions, and financial records are
              tenant-scoped.
            </p>
          </div>
        )}
        {state.currentStep === "create_profile" && (
          <div>
            <h3>Create Profile</h3>
            <p>
              A trading profile defines your exchange connections, trading
              capital, risk policies, and security preferences (AD-008).
            </p>
          </div>
        )}
        {state.currentStep === "configure_risk" && (
          <div>
            <h3>Configure Risk Policy</h3>
            <p>
              Risk policies enforce hard limits for exposure, daily loss,
              drawdown, concentration, volatility, and liquidity (AD-013).
              The independent Risk & Safety Kernel validates every order
              against your policy.
            </p>
          </div>
        )}
        {state.currentStep === "connect_account" && (
          <div>
            <h3>Connect Exchange Account</h3>
            <p>
              Connect an exchange with scoped API credentials. Withdrawal-
              enabled credentials are prohibited by default (AD-019).
            </p>
          </div>
        )}
        {state.currentStep === "mfa_setup" && (
          <div>
            <h3>Enable MFA</h3>
            <p>
              Multi-factor authentication is required for privileged users
              (AD-026). Sensitive operations require step-up authentication.
            </p>
          </div>
        )}
        {state.currentStep === "review" && (
          <div>
            <h3>Review Configuration</h3>
            <p>
              Review your configuration before completing onboarding. You can
              modify any setting after setup.
            </p>
            <ul>
              <li>Tenant: {state.tenantId ?? "— (will be created)"}</li>
              <li>Profile: {state.profileId ?? "— (will be created)"}</li>
              <li>Risk Policy: {state.riskPolicyId ?? "— (will be configured)"}</li>
              <li>MFA: {state.mfaEnabled ? "Enabled" : "Not yet enabled"}</li>
              <li>
                Account: {state.accountConnected ? "Connected" : "Not yet connected"}
              </li>
            </ul>
          </div>
        )}
        {state.currentStep === "complete" && (
          <div>
            <h3>Setup Complete</h3>
            <p>
              Onboarding complete! You can now access the dashboard. Remember:
              no live trading is authorized until all technical, security,
              legal, and human approval gates pass.
            </p>
          </div>
        )}
      </div>

      <div className="onboarding__actions">
        <button
          className="btn btn--primary"
          onClick={advance}
          disabled={isOnboardingComplete(state)}
        >
          {state.currentStep === "complete" ? "Done" : "Next Step →"}
        </button>
      </div>
    </div>
  );
}

export type { OnboardingStep };
