import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const TUNNEL = "abc123-3000.usw2.devtunnels.ms";

function post(headers: Record<string, string>): Request {
  return new Request("http://localhost:3000/api/local/run", { method: "POST", headers });
}

describe("POST /api/local/run origin check", () => {
  const upstream = vi.fn(async (_url: string, _init?: RequestInit) =>
    Response.json({ running: true }, { status: 202 }),
  );

  beforeEach(() => {
    upstream.mockClear();
    vi.stubEnv("BOARD_API_URL", "http://127.0.0.1:8000");
    vi.stubGlobal("fetch", upstream);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it.each([
    ["another website", { origin: "https://example.com", host: "localhost:3000" }],
    ["a different port on this host", { origin: "http://localhost:4000", host: "localhost:3000" }],
    ["no Origin at all", { host: "localhost:3000" }],
  ])("refuses %s without reaching the local API", async (_name, headers) => {
    const res = await POST(post(headers));
    expect(res.status).toBe(403);
    expect(upstream).not.toHaveBeenCalled();
  });

  it.each([
    ["the page on localhost", { origin: "http://localhost:3000", host: "localhost:3000" }],
    [
      "a forwarded port that sends x-forwarded-host",
      { origin: `https://${TUNNEL}`, host: "localhost:3000", "x-forwarded-host": TUNNEL },
    ],
    ["a forwarded port that rewrites Host", { origin: `https://${TUNNEL}`, host: TUNNEL }],
  ])("proxies %s to the local API", async (_name, headers) => {
    const res = await POST(post(headers));
    expect(res.status).toBe(202);
    expect(upstream).toHaveBeenCalledOnce();
    expect(upstream.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8000/api/local/run");
    expect(upstream.mock.calls[0]?.[1]?.method).toBe("POST");
  });
});
