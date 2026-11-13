"""STEP 11 - TMDB integration: poster, backdrop, trailer, overview and where to watch, with a cache.

One request per movie:  GET /movie/{tmdb_id}?append_to_response=watch/providers,videos
The answer (all countries at once) is stored in SQLite for TMDB_CACHE_HOURS, so
changing the country or reloading the page does not call TMDB again.
Watch-provider data comes from JustWatch - the UI must credit JustWatch and TMDB.

CineMatch upgrade: every provider gets a `link`. TMDB's free API does not give a
direct link to the movie inside each service (that needs JustWatch's paid API),
so the link opens that service's own SEARCH for the movie title. Services without
a known search page fall back to a web search for "<title> <year> <service>".
"""
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

import requests

from config import APP_DB, TMDB_API_KEY, TMDB_CACHE_HOURS, TMDB_READ_TOKEN

BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3")
IMG_BASE = os.getenv("TMDB_IMG_BASE", "https://image.tmdb.org/t/p/")
# TMDB's names for the availability types -> what we show to the user
OFFER_TYPES = {"flatrate": "Subscription", "free": "Free", "ads": "Free with ads",
               "rent": "Rent", "buy": "Buy"}
STREAM_TYPES = ("Subscription", "Free", "Free with ads")   # watchable without buying

# ---------------------------------------------------------------- provider search links
# Matched by the START of TMDB's provider name (lower-case). {q} = the movie title, URL-encoded.
# If a link stops working, change it here - this is the only place.
SEARCH_URLS = [
    ("netflix", "https://www.netflix.com/search?q={q}"),
    ("amazon prime video", "https://www.amazon.com/s?k={q}&i=instant-video"),   # US Amazon only
    ("amazon video", "https://www.amazon.com/s?k={q}&i=instant-video"),
    ("apple tv", "https://tv.apple.com/search?term={q}"),
    ("youtube", "https://www.youtube.com/results?search_query={q}+full+movie"),
    ("google play movies", "https://play.google.com/store/search?q={q}&c=movies"),
    ("hulu", "https://www.hulu.com/search?q={q}"),
    ("tubi", "https://tubitv.com/search/{q}"),
]
US_ONLY = ("amazon",)       # Amazon links above are for amazon.com; other countries use the web search

# The services a user can pick under "My services" (key, display name, TMDB name prefixes)
SERVICES = [
    ("netflix", "Netflix", ("netflix",)),
    ("prime", "Prime Video", ("amazon prime video",)),
    ("disney", "Disney+", ("disney plus", "disney+")),
    ("max", "Max", ("max", "hbo max")),
    ("hulu", "Hulu", ("hulu",)),
    ("appletv", "Apple TV+", ("apple tv plus", "apple tv+")),
    ("peacock", "Peacock", ("peacock",)),
    ("paramount", "Paramount+", ("paramount plus", "paramount+")),
    ("hotstar", "JioHotstar", ("jiohotstar", "jio hotstar", "hotstar")),
]
SERVICE_PREFIXES = {key: prefixes for key, _, prefixes in SERVICES}


def provider_link(provider_name, title, year, region):
    name = provider_name.lower()
    q = quote_plus(title)
    for prefix, url in SEARCH_URLS:
        if name.startswith(prefix):
            if any(name.startswith(p) for p in US_ONLY) and region.upper() != "US":
                break
            return url.format(q=q)
    return "https://www.google.com/search?q=" + quote_plus(f"{title} {year or ''} watch on {provider_name}")


def provider_matches(provider_name, service_keys):
    name = provider_name.lower()
    return any(name.startswith(p) for key in service_keys for p in SERVICE_PREFIXES.get(key, ()))


def streamable_on(info, service_keys):
    """True if the movie can be watched on one of the user's services, or for free."""
    providers = info.get("providers") or {}
    if providers.get("Free") or providers.get("Free with ads"):
        return True
    return any(provider_matches(p["name"], service_keys) for p in providers.get("Subscription", []))


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
        # v2 table: the cached answer now also holds trailers (videos)
        self.db.execute("CREATE TABLE IF NOT EXISTS tmdb_cache_v2 (tmdb_id INTEGER PRIMARY KEY, "
                        "fetched_at REAL, payload TEXT)")
        self.db.commit()

    # ---------------- cache ----------------
    def _cache_get(self, tmdb_id):
        with self.lock:
            row = self.db.execute("SELECT fetched_at, payload FROM tmdb_cache_v2 WHERE tmdb_id=?",
                                  (tmdb_id,)).fetchone()
        if row and time.time() - row[0] < self.ttl:
            return json.loads(row[1])
        return None

    def _cache_put(self, tmdb_id, payload):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO tmdb_cache_v2 VALUES (?, ?, ?)",
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
            data = self._get(f"/movie/{tmdb_id}", {"append_to_response": "watch/providers,videos"})
        except requests.RequestException as e:
            print(f"TMDB error for {tmdb_id}: {e}")
            return None
        if data is not None:
            self._cache_put(tmdb_id, data)
        return data

    # ---------------- what the app needs ----------------
    @staticmethod
    def _trailer_key(data):
        videos = [v for v in (data.get("videos") or {}).get("results", [])
                  if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")]
        videos.sort(key=lambda v: (v.get("type") != "Trailer", not v.get("official", False)))
        return videos[0]["key"] if videos else None

    def movie_info(self, tmdb_id, region="US", title=None, year=None):
        if tmdb_id is None:
            return {}
        data = self.fetch_raw(int(tmdb_id))
        if not data:
            return {}
        title = title or data.get("title", "")
        region_data = (data.get("watch/providers") or {}).get("results", {}).get(region.upper(), {})
        providers = {}
        for key, label in OFFER_TYPES.items():
            items = sorted(region_data.get(key, []), key=lambda p: p.get("display_priority", 999))
            if items:
                providers[label] = [{"name": p["provider_name"],
                                     "logo": IMG_BASE + "w92" + p["logo_path"] if p.get("logo_path") else None,
                                     "link": provider_link(p["provider_name"], title, year, region)}
                                    for p in items]
        return {
            "overview": data.get("overview", ""),
            "tagline": data.get("tagline", ""),
            "poster": IMG_BASE + "w342" + data["poster_path"] if data.get("poster_path") else None,
            "backdrop": IMG_BASE + "w1280" + data["backdrop_path"] if data.get("backdrop_path") else None,
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
            "tmdb_rating": data.get("vote_average"),
            "trailer": self._trailer_key(data),          # YouTube video id, or None
            "providers": providers,                       # {"Subscription": [...], "Rent": [...], ...}
            "watch_link": region_data.get("link"),        # TMDB/JustWatch page for this region
        }

    def enrich(self, movies, region="US", workers=8):
        """Add TMDB info to a list of movie dicts (each must have 'tmdbId'), several at a time."""
        with ThreadPoolExecutor(max_workers=workers) as pool:
            infos = list(pool.map(lambda m: self.movie_info(m.get("tmdbId"), region,
                                                            m.get("title"), m.get("year")), movies))
        return [{**m, **info} for m, info in zip(movies, infos)]


if __name__ == "__main__":
    # quick manual test:  python tmdb_client.py   (Toy Story = TMDB id 862)
    info = TMDBClient().movie_info(862, "US", "Toy Story", 1995)
    print(json.dumps(info, indent=2)[:2000])
