import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  consumeOAuthReturn,
  getPortalAuthToken,
  startGoogleSignIn,
} from "./portalAccess";

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

describe("portal Google login", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", storage());
    vi.stubGlobal("sessionStorage", storage());
    vi.stubGlobal("history", { replaceState: vi.fn() });
  });

  it("consumes the rm_auth hash and stores the JWT", () => {
    const payload = btoa(JSON.stringify({ token: "rm-jwt" }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    vi.stubGlobal("location", {
      hash: `#rm_auth=${encodeURIComponent(payload)}`,
      search: "",
      pathname: "/",
      origin: "https://voice.michaelstewman.com",
    });
    expect(consumeOAuthReturn()).toBe("fresh");
    expect(getPortalAuthToken()).toBe("rm-jwt");
    expect(history.replaceState).toHaveBeenCalledWith(null, "", "/");
  });

  it("starts OAuth with the portal origin and return path", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", {
      hash: "",
      search: "?welcome=1",
      pathname: "/portal",
      origin: "https://voice.michaelstewman.com",
      assign,
    });
    startGoogleSignIn();
    const target = new URL(assign.mock.calls[0][0]);
    expect(target.pathname).toBe("/auth/oauth/google/start");
    expect(target.searchParams.get("appOrigin")).toBe(
      "https://voice.michaelstewman.com",
    );
    expect(target.searchParams.get("appReturn")).toBe(
      "https://voice.michaelstewman.com/portal?welcome=1",
    );
  });

  it("clears a failed OAuth return without storing a token", () => {
    vi.stubGlobal("location", {
      hash: "",
      search: "?rm_oauth_error=oauth_denied",
      pathname: "/",
      origin: "https://voice.michaelstewman.com",
    });
    expect(consumeOAuthReturn()).toBe("error");
    expect(getPortalAuthToken()).toBe("");
    expect(history.replaceState).toHaveBeenCalledWith(null, "", "/");
  });
});
