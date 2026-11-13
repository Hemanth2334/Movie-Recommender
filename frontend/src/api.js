// All calls to the FastAPI backend live here. Vite forwards /api to http://localhost:8000.
async function call(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  createUser: () => call("/users", { method: "POST" }),
  onboarding: (region) => call(`/onboarding?n=24&region=${region}`),
  search: (q, region) => call(`/search?q=${encodeURIComponent(q)}&region=${region}`),
  rate: (userId, movieId, rating) =>
    call(`/users/${userId}/ratings`, { method: "PUT", body: JSON.stringify({ movieId, rating }) }),
  unrate: (userId, movieId) => call(`/users/${userId}/ratings/${movieId}`, { method: "DELETE" }),
  myRatings: (userId) => call(`/users/${userId}/ratings`),
  recommendations: (userId, region) => call(`/users/${userId}/recommendations?region=${region}`),
};
