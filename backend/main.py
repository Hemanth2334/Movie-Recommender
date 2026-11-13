"""STEP 12 - FastAPI backend.

Run (from the backend folder):   uvicorn main:app --reload --port 8000
Interactive docs:                http://localhost:8000/docs
"""
import pickle
import sqlite3
import threading
import time
import uuid

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import APP_DB, DATASET, MODELS_DIR
from tmdb_client import TMDBClient

# ---------------------------------------------------------------- load models once at start-up
MODEL_PATH = MODELS_DIR / f"{DATASET}.pkl"
if not MODEL_PATH.exists():
    raise SystemExit(f"{MODEL_PATH} not found - run data_pipeline.py and train_models.py first")
with open(MODEL_PATH, "rb") as f:
    MODELS = pickle.load(f)
HYBRID = MODELS["hybrid"]
MOVIES = MODELS["movies"].reset_index(drop=True)
POP_COUNTS = MODELS["popularity"].counts            # number of ratings per movie (same order as MOVIES)
MOVIE_POS = {m: i for i, m in enumerate(MOVIES["movieId"])}
tmdb = TMDBClient()

# ---------------------------------------------------------------- tiny user database (SQLite)
db = sqlite3.connect(APP_DB, check_same_thread=False)
db_lock = threading.Lock()
db.executescript("""
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, created_at REAL);
CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, rating REAL, updated_at REAL,
                                    PRIMARY KEY (user_id, movie_id));
""")
db.commit()


def get_user_ratings(user_id):
    with db_lock:
        if db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone() is None:
            raise HTTPException(404, "Unknown user - create one with POST /api/users")
        rows = db.execute("SELECT movie_id, rating FROM ratings WHERE user_id=?", (user_id,)).fetchall()
    return {int(m): float(r) for m, r in rows}


def movie_card(i):
    row = MOVIES.iloc[i]
    return {"movieId": int(row["movieId"]), "title": row["clean_title"],
            "year": None if pd.isna(row["year"]) else int(row["year"]),
            "genres": row["genres"],
            "tmdbId": None if pd.isna(row["tmdbId"]) else int(row["tmdbId"])}


# ---------------------------------------------------------------- the API
app = FastAPI(title="Movie Recommender API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class RatingIn(BaseModel):
    movieId: int
    rating: float = Field(ge=0.5, le=5.0, multiple_of=0.5)


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset": DATASET, "movies": len(MOVIES)}


@app.post("/api/users")
def create_user():
    user_id = uuid.uuid4().hex[:12]
    with db_lock:
        db.execute("INSERT INTO users VALUES (?, ?)", (user_id, time.time()))
        db.commit()
    return {"user_id": user_id}


@app.get("/api/onboarding")
def onboarding(n: int = 24, region: str = "US"):
    """Well-known movies from many genres, for a new user's first ratings."""
    order = np.argsort(-POP_COUNTS)
    picked, genres_used = [], {}
    for i in order:                                   # at most 3 starter movies per main genre
        first_genre = (MOVIES.at[i, "genres"] or "Other").split("|")[0]
        if genres_used.get(first_genre, 0) >= 3:
            continue
        genres_used[first_genre] = genres_used.get(first_genre, 0) + 1
        picked.append(movie_card(i))
        if len(picked) >= n:
            break
    return tmdb.enrich(picked, region)


@app.get("/api/search")
def search(q: str, limit: int = 8, region: str = "US"):
    hits = np.where(MOVIES["title"].str.contains(q, case=False, regex=False).values)[0]
    hits = hits[np.argsort(-POP_COUNTS[hits])][:limit]      # most-rated matches first
    return tmdb.enrich([movie_card(i) for i in hits], region)


@app.put("/api/users/{user_id}/ratings")
def rate(user_id: str, body: RatingIn):
    get_user_ratings(user_id)                         # 404 if the user does not exist
    if body.movieId not in MOVIE_POS:
        raise HTTPException(404, "Unknown movieId")
    with db_lock:
        db.execute("INSERT OR REPLACE INTO ratings VALUES (?, ?, ?, ?)",
                   (user_id, body.movieId, body.rating, time.time()))
        db.commit()
    return {"ok": True, "n_ratings": len(get_user_ratings(user_id))}


@app.delete("/api/users/{user_id}/ratings/{movie_id}")
def unrate(user_id: str, movie_id: int):
    with db_lock:
        db.execute("DELETE FROM ratings WHERE user_id=? AND movie_id=?", (user_id, movie_id))
        db.commit()
    return {"ok": True}


@app.get("/api/users/{user_id}/ratings")
def my_ratings(user_id: str):
    ratings = get_user_ratings(user_id)
    return [{**movie_card(MOVIE_POS[m]), "rating": r} for m, r in ratings.items() if m in MOVIE_POS]


@app.get("/api/users/{user_id}/recommendations")
def recommendations(user_id: str, region: str = "US", per_genre: int = 5, max_genres: int = 6):
    ratings = get_user_ratings(user_id)
    t = time.time()
    groups = HYBRID.recommend_by_genre(ratings, per_genre=per_genre, max_genres=max_genres)
    model_ms = round((time.time() - t) * 1000)
    for g in groups:                                  # add posters + where to watch
        g["movies"] = tmdb.enrich(g["movies"], region)
    return {"n_ratings": len(ratings),
            "weights": {k: round(v, 2) for k, v in HYBRID.weights(len(ratings)).items()},
            "model_ms": model_ms, "region": region.upper(), "groups": groups}
