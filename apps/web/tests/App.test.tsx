import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../src/App";

vi.mock("globalThis.fetch" as never, () => ({
  fetch: vi.fn(() =>
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
}));

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the title", () => {
    render(<App />);
    expect(screen.getByText("Kian Trading Intelligence")).toBeTruthy();
  });

  it("shows operating mode after fetch", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("SIMULATION")).toBeTruthy();
    });
  });

  it("shows live trading as DISABLED", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("DISABLED")).toBeTruthy();
    });
  });
});
