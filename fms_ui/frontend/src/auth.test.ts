import { beforeEach, describe, expect, it } from "vitest";

import { authHeaders, initAuth } from "@/auth";

describe("auth", () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("reads the token from the launch URL, stores it, and strips it", () => {
    window.history.replaceState(null, "", "/?token=secret-token");
    initAuth();
    expect(authHeaders()).toEqual({ "X-FMS-Token": "secret-token" });
    expect(window.location.search).toBe("");
    expect(sessionStorage.getItem("fms.token")).toBe("secret-token");
  });

  it("falls back to sessionStorage when the URL has no token", () => {
    sessionStorage.setItem("fms.token", "stored-token");
    initAuth();
    expect(authHeaders()).toEqual({ "X-FMS-Token": "stored-token" });
  });

  it("returns no header when there is no token", () => {
    initAuth();
    expect(authHeaders()).toEqual({});
  });
});