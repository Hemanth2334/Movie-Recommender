"""STEP 11 - TMDB integration: poster, overview, and where to watch (per country), with a cache.

One request per movie:  GET /movie/{tmdb_id}?append_to_response=watch/providers
The answer (all countries at once) is stored in SQLite for TMDB_CACHE_HOURS, so
changing the country or reloading the page does not call TMDB again.
Watch-provider data comes from JustWatch - the UI must credit JustWatch and TMDB.
"""
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from config import APP_DB, TMDB_API_KEY, TMDB_CACHE_HOURS, TMDB_READ_TOKEN

BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3")
IMG_BASE = "https://image.tmdb.org/t/p/"
# TMDB's names for the availability types -> what we show to the user
OFFER_TYPES = {"flatrate": "Subscription", "free": "Free", "ads": "Free with ads",
               "rent": "Rent", "buy": "Buy"}


class TMDBClient:
    def __init__(self, db_path=APP_DB, ttl_hours=TMDB_CACHE_HOURS):
        if not (TMDB_READ_TOKEN or TMDB_API_KEY):
            print("WARNING: no TMDB_READ_TOKEN or TMDB_API_KEY in backend/.env - posters will be missing")
        self.session = requests.Session()
        if TMDB_READ_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"
        self.session.headers["accept"] = "application/json"
        self.ttl = ttl_hours * 3600
        self.lock = threading.Lock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS tmdb_cache (tmdb_id INTEGER PRIMARY KEY, "
                        "fetched_at REAL, payload TEXT)")
        self.db.commit()

    # ---------------- cache ----------------
    def _cache_get(self, tmdb_id):
        with self.lock:
            row = self.db.execute("SELECT fetched_at, payload FROM tmdb_cache WHERE tmdb_id=?",
                                  (tmdb_id,)).fetchone()
        if row and time.time() - row[0] < self.ttl:
            return json.loads(row[1])
        return None

    def _cache_put(self, tmdb_id, payload):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO tmdb_cache VALUES (?, ?, ?)",
                            (tmdb_id, time.time(), json.dumps(payload)))
            self.db.commit()

    # ---------------- HTTP ----------------
    def _get(self, path, params=None, retries=3):
        params = dict(params or {})
        if TMDB_API_KEY and not TMDB_READ_TOKEN:
            params["api_key"] = TMDB_API_KEY
        for attempt in range(retries):
            r = self.session.get(f"{BASE_URL}{path}", params=params, timeout=10)
            if r.status_code == 429:                       # too many requests -> wait and retry
                time.sleep(float(r.headers.get("Retry-After", 1 + attempt)))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        return None

    def fetch_raw(self, tmdb_id):
        cached = self._cache_get(tmdb_id)
        if cached is not None:
            return cached
        try:
            data = self._get(f"/movie/{tmdb_id}", {"append_to_response": "watch/providers"})
        except requests.RequestException as e:
            print(f"TMDB error for {tmdb_id}: {e}")
            return None
        if data is not None:
            self._cache_put(tmdb_id, data)
        return data

    # ---------------- what the app needs ----------------
    def movie_info(self, tmdb_id, region="US"):
        if tmdb_id is None:
            return {}
        data = self.fetch_raw(int(tmdb_id))
        if not data:
            return {}
        region_data = (data.get("watch/providers") or {}).get("results", {}).get(region.upper(), {})
        providers = {}
        for key, label in OFFER_TYPES.items():
            items = sorted(region_data.get(key, []), key=lambda p: p.get("display_priority", 999))
            if items:
                providers[label] = [{"name": p["provider_name"],
                                     "logo": IMG_BASE + "w92" + p["logo_path"] if p.get("logo_path") else None}
                                    for p in items]
        return {
            "overview": data.get("overview", ""),
            "poster": IMG_BASE + "w342" + data["poster_path"] if data.get("poster_path") else None,
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
            "tmdb_rating": data.get("vote_average"),
            "providers": providers,                       # {"Subscription": [...], "Rent": [...], ...}
            "watch_link": region_data.get("link"),        # TMDB/JustWatch page for this region
        }

    def enrich(self, movies, region="US", workers=8):
        """Add TMDB info to a list of movie dicts (each must have 'tmdbId'), several at a time."""
        with ThreadPoolExecutor(max_workers=workers) as pool:
            infos = list(pool.map(lambda m: self.movie_info(m.get("tmdbId"), region), movies))
        return [{**m, **info} for m, info in zip(movies, infos)]


if __name__ == "__main__":
    # quick manual test:  python tmdb_client.py   (Toy Story = TMDB id 862)
    info = TMDBClient().movie_info(862, "US")
    print(json.dumps(info, indent=2)[:1500])
