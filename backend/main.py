"""STEP 12 - FastAPI backend for CineMatch.

Run (from the backend folder):   uvicorn main:app --reload --port 8000
Interactive docs:                http://localhost:8000/docs

Accounts: email + password. Passwords are never stored: we store a salted
PBKDF2-SHA256 hash. Logging in gives the browser a random session token, sent back
as "Authorization: Bearer <token>" on every request. Only a hash of the token is stored.
"""
import hashlib
import hmac
import json
import pickle
import re
import secrets
import sqlite3
import threading
import time

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import APP_DB, DATASET, MODELS_DIR
from tmdb_client import SERVICES, TMDBClient, streamable_on
from user_cf import row_normalise

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
# movie-to-movie similarity from "who watched what" (for "Because you liked X")
ITEM_VECS = row_normalise(MODELS["user_cf"].M.T.tocsr())
SERVICE_KEYS = {key for key, _, _ in SERVICES}
tmdb = TMDBClient()

SESSION_DAYS = 30
PBKDF2_ROUNDS = 200_000
STREAM_POOL = 300            # how many top candidates to check when "only what I can stream" is on

# ---------------------------------------------------------------- database (SQLite)
db = sqlite3.connect(APP_DB, check_same_thread=False)
db_lock = threading.Lock()
db.executescript("""
CREATE TABLE IF NOT EXISTS accounts (user_id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT,
                                     pw_hash TEXT, salt TEXT, services TEXT DEFAULT '[]', created_at REAL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, rating REAL, updated_at REAL,
                                    PRIMARY KEY (user_id, movie_id));
CREATE TABLE IF NOT EXISTS my_list (user_id TEXT, movie_id INTEGER, added_at REAL,
                                    PRIMARY KEY (user_id, movie_id));
""")
db.commit()


def sql(query, args=(), commit=False):
    with db_lock:
        rows = db.execute(query, args).fetchall()
        if commit:
            db.commit()
    return rows


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS).hex()


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    sql("INSERT INTO sessions VALUES (?, ?, ?)", (hash_token(token), user_id, time.time()), commit=True)
    return token


def public_user(row):
    user_id, email, name, services = row
    return {"user_id": user_id, "email": email, "name": name, "services": json.loads(services or "[]")}


def current_user(authorization: str = Header(default="")):
    """Every protected endpoint asks for this: it turns the Bearer token into the user."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Please sign in")
    rows = sql("SELECT a.user_id, a.email, a.name, a.services, s.created_at FROM sessions s "
               "JOIN accounts a ON a.user_id = s.user_id WHERE s.token_hash=?", (hash_token(token),))
    if not rows or time.time() - rows[0][4] > SESSION_DAYS * 86400:
        raise HTTPException(401, "Session expired - please sign in again")
    return public_user(rows[0][:4])


def user_ratings(user_id):
    return {int(m): float(r) for m, r in sql("SELECT movie_id, rating FROM ratings WHERE user_id=?", (user_id,))}


def user_list(user_id):
    return [int(m) for (m,) in sql("SELECT movie_id FROM my_list WHERE user_id=? ORDER BY added_at DESC", (user_id,))]


def movie_card(i):
    row = MOVIES.iloc[i]
    return {"movieId": int(row["movieId"]), "title": row["clean_title"],
            "year": None if pd.isna(row["year"]) else int(row["year"]),
            "genres": row["genres"],
            "tmdbId": None if pd.isna(row["tmdbId"]) else int(row["tmdbId"])}


# ---------------------------------------------------------------- "Because you liked X"
def liked_seeds(ratings, n=2):
    """The user's favourite movies (rating >= 4), best-rated and best-known first."""
    liked = [m for m, r in ratings.items() if r >= 4 and m in MOVIE_POS]
    liked.sort(key=lambda m: (-ratings[m], -POP_COUNTS[MOVIE_POS[m]]))
    return liked[:n]


def similar_to(movie_id, exclude, allowed=None, n=10):
    """60% "people who watched it also watched" + 40% "similar genres/tags/era" (content model)."""
    seed = MOVIE_POS[movie_id]
    co_watch = np.asarray((ITEM_VECS @ ITEM_VECS[seed].T).todense()).ravel()
    content = HYBRID.content.similarity(np.arange(len(MOVIES)), [seed]).ravel()
    sims = 0.6 * co_watch / max(co_watch.max(), 1e-9) + 0.4 * content
    series = HYBRID.series()
    sims[series == series[seed]] = -1                  # skip sequels of the movie itself
    sims[POP_COUNTS < 5] = -1
    for m in exclude:
        if m in MOVIE_POS:
            sims[MOVIE_POS[m]] = -1
    if allowed is not None:
        sims[~np.isin(MOVIES["movieId"].values, list(allowed))] = -1
    picked, seen_series = [], set()
    for i in np.argsort(-sims):
        if sims[i] <= 0 or len(picked) == n:
            break
        if series[i] in seen_series:                    # one film per franchise
            continue
        seen_series.add(series[i])
        picked.append(movie_card(i))
    return picked


def explain(cards, ratings):
    """Add 'because': the title of the user's liked movie most similar to each recommendation."""
    liked = [m for m, r in ratings.items() if r >= 4 and m in MOVIE_POS]
    if not liked or not cards:
        return cards
    S = (ITEM_VECS[[MOVIE_POS[c["movieId"]] for c in cards]] @ ITEM_VECS[[MOVIE_POS[m] for m in liked]].T).toarray()
    for c, row in zip(cards, S):
        if row.max() > 0.05:
            c["because"] = MOVIES.at[MOVIE_POS[liked[int(row.argmax())]], "clean_title"]
    return cards


def streamable_ids(ratings, services, region):
    """Movie ids among the user's top candidates that they can watch on their services (or free)."""
    scores = HYBRID.scores(ratings)
    order = np.argsort(-scores)[:STREAM_POOL]
    order = [i for i in order if np.isfinite(scores[i])]
    popular = [i for i in np.argsort(-POP_COUNTS)[:100]]
    idx = list(dict.fromkeys(order + popular))
    cards = tmdb.enrich([movie_card(i) for i in idx], region, workers=16)
    return {c["movieId"] for c in cards if streamable_on(c, services)}


# ---------------------------------------------------------------- the API
app = FastAPI(title="CineMatch API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=200)
    legacy_user_id: str | None = None      # ratings made before accounts existed, in this browser


class LoginIn(BaseModel):
    email: str
    password: str


class ServicesIn(BaseModel):
    services: list[str]


class RatingIn(BaseModel):
    movieId: int
    rating: float = Field(ge=0.5, le=5.0, multiple_of=0.5)


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset": DATASET, "movies": len(MOVIES)}


@app.get("/api/services")
def services():
    return [{"key": k, "name": n} for k, n, _ in SERVICES]


# ---------- accounts ----------
@app.post("/api/auth/signup")
def signup(body: SignupIn):
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Please enter a valid email address")
    if sql("SELECT 1 FROM accounts WHERE email=?", (email,)):
        raise HTTPException(409, "An account with this email already exists - sign in instead")
    user_id, salt = secrets.token_hex(8), secrets.token_hex(16)
    sql("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, '[]', ?)",
        (user_id, email, body.name.strip(), hash_password(body.password, salt), salt, time.time()), commit=True)
    if body.legacy_user_id and not sql("SELECT 1 FROM accounts WHERE user_id=?", (body.legacy_user_id,)):
        sql("UPDATE ratings SET user_id=? WHERE user_id=?", (user_id, body.legacy_user_id), commit=True)
    return {"token": new_session(user_id), "user": public_user((user_id, email, body.name.strip(), "[]"))}


@app.post("/api/auth/login")
def login(body: LoginIn):
    rows = sql("SELECT user_id, email, name, services, pw_hash, salt FROM accounts WHERE email=?",
               (body.email.strip().lower(),))
    if not rows or not hmac.compare_digest(rows[0][4], hash_password(body.password, rows[0][5])):
        raise HTTPException(401, "Wrong email or password")
    return {"token": new_session(rows[0][0]), "user": public_user(rows[0][:4])}


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default="")):
    sql("DELETE FROM sessions WHERE token_hash=?", (hash_token(authorization.removeprefix("Bearer ").strip()),),
        commit=True)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {**user, "n_ratings": len(user_ratings(user["user_id"]))}


@app.put("/api/me/services")
def set_services(body: ServicesIn, user=Depends(current_user)):
    chosen = [s for s in body.services if s in SERVICE_KEYS]
    sql("UPDATE accounts SET services=? WHERE user_id=?", (json.dumps(chosen), user["user_id"]), commit=True)
    return {**user, "services": chosen}


# ---------- movies to rate ----------
@app.get("/api/onboarding")
def onboarding(n: int = 24, region: str = "US"):
    """Well-known movies from many genres, for a new user's first ratings."""
    picked, genres_used = [], {}
    for i in np.argsort(-POP_COUNTS):              # at most 3 starter movies per main genre
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


# ---------- ratings ----------
@app.get("/api/me/ratings")
def my_ratings(region: str = "US", user=Depends(current_user)):
    ratings = user_ratings(user["user_id"])
    cards = [{**movie_card(MOVIE_POS[m]), "rating": r} for m, r in ratings.items() if m in MOVIE_POS]
    return tmdb.enrich(cards, region)


@app.put("/api/me/ratings")
def rate(body: RatingIn, user=Depends(current_user)):
    if body.movieId not in MOVIE_POS:
        raise HTTPException(404, "Unknown movieId")
    sql("INSERT OR REPLACE INTO ratings VALUES (?, ?, ?, ?)",
        (user["user_id"], body.movieId, body.rating, time.time()), commit=True)
    return {"ok": True}


@app.delete("/api/me/ratings/{movie_id}")
def unrate(movie_id: int, user=Depends(current_user)):
    sql("DELETE FROM ratings WHERE user_id=? AND movie_id=?", (user["user_id"], movie_id), commit=True)
    return {"ok": True}


# ---------- My List ----------
@app.get("/api/me/list")
def my_list(region: str = "US", user=Depends(current_user)):
    return tmdb.enrich([movie_card(MOVIE_POS[m]) for m in user_list(user["user_id"]) if m in MOVIE_POS], region)


@app.put("/api/me/list/{movie_id}")
def add_to_list(movie_id: int, user=Depends(current_user)):
    sql("INSERT OR REPLACE INTO my_list VALUES (?, ?, ?)", (user["user_id"], movie_id, time.time()), commit=True)
    return {"ok": True}


@app.delete("/api/me/list/{movie_id}")
def remove_from_list(movie_id: int, user=Depends(current_user)):
    sql("DELETE FROM my_list WHERE user_id=? AND movie_id=?", (user["user_id"], movie_id), commit=True)
    return {"ok": True}


# ---------- the home page ----------
@app.get("/api/me/home")
def home(region: str = "US", only_mine: bool = False, per_genre: int = 5, max_genres: int = 6,
         user=Depends(current_user)):
    ratings = user_ratings(user["user_id"])
    t = time.time()
    allowed = streamable_ids(ratings, user["services"], region) if only_mine else None

    groups = HYBRID.recommend_by_genre(ratings, per_genre=per_genre, max_genres=max_genres, allowed=allowed)
    shown = set(ratings) | {m["movieId"] for g in groups for m in g["movies"]}
    rows = [{"id": f"genre-{g['genre']}", "title": f"{g['genre']} picks for you", "kind": "genre",
             "movies": explain(g["movies"], ratings)} for g in groups]

    because = []
    for seed in liked_seeds(ratings):
        sims = similar_to(seed, shown, allowed)
        if sims:
            shown |= {m["movieId"] for m in sims}
            because.append({"id": f"because-{seed}", "kind": "because", "movies": sims,
                            "title": f"Because you liked {MOVIES.at[MOVIE_POS[seed], 'clean_title']}"})

    top_idx = [i for i in np.argsort(-POP_COUNTS)
               if int(MOVIES.at[i, "movieId"]) not in ratings
               and (allowed is None or int(MOVIES.at[i, "movieId"]) in allowed)][:10]
    top10 = {"id": "top10", "title": "Top 10 on CineMatch", "kind": "top10",
             "movies": [movie_card(i) for i in top_idx]}

    in_list = user_list(user["user_id"])
    mylist = {"id": "mylist", "title": "My List", "kind": "mylist",
              "movies": [movie_card(MOVIE_POS[m]) for m in in_list if m in MOVIE_POS]}

    # order of rows on the page: first genre row, Top 10, Because..., other genres, My List
    ordered = rows[:1] + [top10] + because + rows[1:] + ([mylist] if mylist["movies"] else [])
    model_ms = round((time.time() - t) * 1000)
    for r in ordered:
        r["movies"] = tmdb.enrich(r["movies"], region)
    return {"user": user, "n_ratings": len(ratings), "only_mine": only_mine, "region": region.upper(),
            "weights": {k: round(v, 2) for k, v in HYBRID.weights(len(ratings)).items()},
            "my_list": in_list, "model_ms": model_ms, "rows": ordered}
