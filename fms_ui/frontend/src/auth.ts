const STORAGE_KEY = "fms.token";

let token: string | null = null;

export function initAuth(): void {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("token");
  if (fromUrl) {
    token = fromUrl;
    try {
      sessionStorage.setItem(STORAGE_KEY, fromUrl);
    } catch {
      // Private-browsing modes may block storage; the in-memory token still works.
    }
    url.searchParams.delete("token");
    window.history.replaceState(null, "", url.toString());
    return;
  }
  try {
    token = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    token = null;
  }
}

export function authHeaders(): Record<string, string> {
  return token ? { "X-FMS-Token": token } : {};
}