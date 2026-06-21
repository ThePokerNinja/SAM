/** Owner gate for the voice portal � secret link, no OAuth.

 * Bookmark once: https://voice.michaelstewman.com/?access=<SAM_PORTAL_ACCESS_KEY>
 * The key is stored in localStorage and the URL is cleaned via replaceState
 * (no page refresh). Same candle UX for you; strangers get "Access denied".
 */

const STORAGE_KEY = "sam-portal-access";
const URL_PARAM = "access";

export function getPortalAccessKey(): string {
  try {
    return (localStorage.getItem(STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function setPortalAccessKey(key: string): void {
  try {
    const k = (key || "").trim();
    if (k) localStorage.setItem(STORAGE_KEY, k);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode */
  }
}

export function clearPortalAccessKey(): void {
  setPortalAccessKey("");
}

/** Read ?access= from the URL, persist, and strip the param without reloading. */
export function bootstrapPortalAccessFromUrl(): void {
  if (typeof location === "undefined") return;
  const params = new URLSearchParams(location.search);
  const fromUrl = (params.get(URL_PARAM) || "").trim();
  if (fromUrl) {
    setPortalAccessKey(fromUrl);
    params.delete(URL_PARAM);
    const qs = params.toString();
    const next = location.pathname + (qs ? `?${qs}` : "") + location.hash;
    history.replaceState(null, "", next);
  }
}

export const PORTAL_ACCESS_HEADER = "X-SAM-Access";
