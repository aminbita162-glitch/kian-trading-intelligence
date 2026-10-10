import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import App from "../src/App";

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              status: "healthy",
              service: "kian-trading-intelligence",
              version: "0.1.0",
              operating_mode: "simulation",
              is_live: false,
              timestamp: "2025-01-01T00:00:00Z",
            }),
        }),
      ) as unknown as typeof fetch,
    );
  });

  it("renders the title", async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByText("Kian Trading Intelligence")).toBeTruthy();
  });

  it("shows operating mode after fetch", async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getAllByText("SIMULATION").length).toBeGreaterThan(0);
    });
  });

  it("shows live trading as DISABLED", async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText("DISABLED")).toBeTruthy();
    });
  });
});
