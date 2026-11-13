// All calls to the FastAPI backend live here. Vite forwards /api to http://localhost:8000.
// After sign-in the backend gives us a token; we keep it in the browser and send it with every call.
const TOKEN_KEY = "cinematch_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => (token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY));

async function call(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401 && token) {
    setToken(null); // session expired -> back to the sign-in page
    window.dispatchEvent(new Event("cinematch-signed-out"));
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || message;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

const json = (method, body) => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  // accounts
  signup: (name, email, password, legacyUserId) =>
    call("/auth/signup", json("POST", { name, email, password, legacy_user_id: legacyUserId || null })),
  login: (email, password) => call("/auth/login", json("POST", { email, password })),
  logout: () => call("/auth/logout", json("POST")),
  me: () => call("/me"),
  services: () => call("/services"),
  setServices: (services) => call("/me/services", json("PUT", { services })),

  // movies
  onboarding: (region) => call(`/onboarding?n=24&region=${region}`),
  search: (q, region) => call(`/search?q=${encodeURIComponent(q)}&region=${region}`),
  home: (region, onlyMine) => call(`/me/home?region=${region}&only_mine=${onlyMine}`),

  // ratings
  myRatings: (region = "US") => call(`/me/ratings?region=${region}`),
  rate: (movieId, rating) => call("/me/ratings", json("PUT", { movieId, rating })),
  unrate: (movieId) => call(`/me/ratings/${movieId}`, json("DELETE")),

  // My List
  myList: (region = "US") => call(`/me/list?region=${region}`),
  addToList: (movieId) => call(`/me/list/${movieId}`, json("PUT")),
  removeFromList: (movieId) => call(`/me/list/${movieId}`, json("DELETE")),
};
