import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "@/lib/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function errorResponse(status: number, code: string): Response {
  return jsonResponse(status, {
    error: { code, message: "nope", requestId: "req-1", details: {} },
  });
}

describe("apiClient", () => {
  beforeEach(() => {
    document.cookie = "nql_csrf=csrf-value";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends cookies and omits a CSRF header on safe methods", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.get("/api/v1/industries");

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).has("x-csrf-token")).toBe(false);
  });

  it("attaches the double-submit CSRF token to mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.post("/api/v1/auth/logout", {}, { skipRefresh: true });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get("x-csrf-token")).toBe("csrf-value");
  });

  it("refreshes once and retries after a 401", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse(401, "unauthenticated"))
      .mockResolvedValueOnce(jsonResponse(200, {})) // the refresh call
      .mockResolvedValueOnce(jsonResponse(200, { id: "u1" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiClient.get("/api/v1/auth/me")).resolves.toEqual({ id: "u1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/api/v1/auth/refresh");
  });

  it("shares one refresh across concurrent 401s so the token family is not rotated twice", async () => {
    let refreshCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/auth/refresh")) {
          refreshCalls += 1;
          return jsonResponse(200, {});
        }
        // Fails until a refresh has happened, then succeeds.
        return refreshCalls === 0 ? errorResponse(401, "unauthenticated") : jsonResponse(200, {});
      }),
    );

    await Promise.all([
      apiClient.get("/api/v1/industries"),
      apiClient.get("/api/v1/auth/me"),
      apiClient.get("/ready"),
    ]);

    expect(refreshCalls).toBe(1);
  });

  it("does not attempt a refresh when the caller opted out", async () => {
    const fetchMock = vi.fn().mockResolvedValue(errorResponse(401, "invalid_credentials"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiClient.post("/api/v1/auth/login", {}, { skipRefresh: true }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces the backend error code and request id", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorResponse(403, "forbidden")));

    let error: unknown;
    try {
      await apiClient.get("/api/v1/diagnostics");
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiError);
    // Narrowed by the assertion above; asserted explicitly so the rest type-checks.
    if (!(error instanceof ApiError)) throw new Error("unreachable");
    expect(error.code).toBe("forbidden");
    expect(error.requestId).toBe("req-1");
    expect(error.isForbidden).toBe(true);
    expect(error.isRetryable).toBe(false);
  });
});
