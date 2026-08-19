/** Owner gate for the voice portal — secret link, no OAuth.

 * Bookmark once (hash form is safest for base64 keys with '+'):
 *   https://voice.michaelstewman.com/#access=<SAM_PORTAL_ACCESS_KEY>
 * Or query (encode '+' as %2B):
 *   https://voice.michaelstewman.com/?access=<url-encoded-key>
 *
 * The key is stored in localStorage and the URL is cleaned via replaceState
 * (no page refresh). Same candle UX for you; strangers get "Access denied".
 */

const STORAGE_KEY = "sam-portal-access";
const AUTH_STORAGE_KEY = "sam-rm-auth-token";
const URL_PARAM = "access";

/** Base64 keys in ?access= often corrupt '+' into spaces; repair when plausible. */
function normalizeAccessKey(raw: string): string {
  const k = (raw || "").trim();
  if (!k) return "";
  if (k.includes(" ") && !k.includes("+") && /^[A-Za-z0-9+/= ]+$/.test(k)) {
    return k.replace(/ /g, "+");
  }
  return k;
}

export function getPortalAccessKey(): string {
  try {
    const fromLocal = normalizeAccessKey(localStorage.getItem(STORAGE_KEY) || "");
    if (fromLocal) return fromLocal;
    return normalizeAccessKey(sessionStorage.getItem(STORAGE_KEY) || "");
  } catch {
    try {
      return normalizeAccessKey(sessionStorage.getItem(STORAGE_KEY) || "");
    } catch {
      return "";
    }
  }
}

export function setPortalAccessKey(key: string): void {
  try {
    const k = normalizeAccessKey(key);
    if (k) {
      localStorage.setItem(STORAGE_KEY, k);
      try {
        sessionStorage.setItem(STORAGE_KEY, k);
      } catch {
        /* ignore */
      }
    } else {
      localStorage.removeItem(STORAGE_KEY);
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* private mode */
  }
}

export function clearPortalAccessKey(): void {
  setPortalAccessKey("");
}

function readAccessParam(params: URLSearchParams): string {
  return normalizeAccessKey(params.get(URL_PARAM) || "");
}

/** Read access from URL, persist, and strip the param without reloading. */
export function bootstrapPortalAccessFromUrl(): void {
  if (typeof location === "undefined") return;

  // Hash avoids '+' being decoded as space (common with base64 in ?query).
  if (location.hash && location.hash.length > 1) {
    const hashParams = new URLSearchParams(location.hash.replace(/^#/, ""));
    const fromHash = readAccessParam(hashParams);
    if (fromHash) {
      setPortalAccessKey(fromHash);
      history.replaceState(null, "", location.pathname + location.search);
      return;
    }
  }

  const params = new URLSearchParams(location.search);
  const fromQuery = readAccessParam(params);
  if (fromQuery) {
    setPortalAccessKey(fromQuery);
    params.delete(URL_PARAM);
    const qs = params.toString();
    const next = location.pathname + (qs ? `?${qs}` : "") + location.hash;
    history.replaceState(null, "", next);
  }
}

export const PORTAL_ACCESS_HEADER = "X-SAM-Access";

export function getPortalAuthToken(): string {
  try {
    return sessionStorage.getItem(AUTH_STORAGE_KEY) || localStorage.getItem(AUTH_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setPortalAuthToken(token: string): void {
  try {
    if (token) {
      sessionStorage.setItem(AUTH_STORAGE_KEY, token);
      localStorage.setItem(AUTH_STORAGE_KEY, token);
    } else {
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch {
    /* private mode */
  }
}

function decodeBase64UrlJson(blob: string): { token?: string } {
  const normalized = blob.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  return JSON.parse(atob(padded)) as { token?: string };
}

/** Consume rm_api's OAuth hash handoff and remove credentials from the address bar. */
export function consumeOAuthReturn(): "fresh" | "error" | false {
  if (typeof location === "undefined") return false;
  const params = new URLSearchParams(location.search);
  if (params.has("rm_oauth_error")) {
    params.delete("rm_oauth_error");
    const query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? `?${query}` : ""));
    return "error";
  }
  if (!location.hash.startsWith("#rm_auth=")) return false;
  try {
    const payload = decodeBase64UrlJson(decodeURIComponent(location.hash.slice(9)));
    if (!payload.token) throw new Error("missing token");
    setPortalAuthToken(payload.token);
    history.replaceState(null, "", location.pathname + location.search);
    return "fresh";
  } catch {
    setPortalAuthToken("");
    history.replaceState(null, "", location.pathname + location.search);
    return "error";
  }
}

export function rmApiBase(): string {
  const configured = import.meta.env.VITE_RM_API_BASE_URL as string | undefined;
  return (configured || "https://rainmaker-api-waqs.onrender.com").replace(/\/$/, "");
}

export function startGoogleSignIn(): void {
  const appOrigin = location.origin;
  const appReturn = new URL(location.pathname + location.search, appOrigin).toString();
  const url = new URL(rmApiBase() + "/auth/oauth/google/start");
  url.searchParams.set("appOrigin", appOrigin);
  url.searchParams.set("appReturn", appReturn);
  location.assign(url.toString());
}
