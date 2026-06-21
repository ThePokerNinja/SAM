/** Owner gate for the voice portal ù secret link, no OAuth.

 * Bookmark once (hash form is safest for base64 keys with '+'):
 *   https://voice.michaelstewman.com/#access=<SAM_PORTAL_ACCESS_KEY>
 * Or query (encode '+' as %2B):
 *   https://voice.michaelstewman.com/?access=<url-encoded-key>
 *
 * The key is stored in localStorage and the URL is cleaned via replaceState
 * (no page refresh). Same candle UX for you; strangers get "Access denied".
 */

const STORAGE_KEY = "sam-portal-access";
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
