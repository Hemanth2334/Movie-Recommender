"""STEP 3 - Clean MovieLens data and split it into train / validation / test.

Run (from the backend folder):
    python data_pipeline.py
    python data_pipeline.py --dataset ml-32m --sample-users 20000
"""
import argparse
import re

import numpy as np
import pandas as pd

from config import PROCESSED_DIR, RAW_DIR, SEED

YEAR_RE = re.compile(r"\((\d{4})\)\s*$")


def load_raw(dataset):
    folder = RAW_DIR / dataset
    print(f"Loading raw files from {folder}")
    # small number types halve the memory needed for the 32-million-row file
    ratings = pd.read_csv(folder / "ratings.csv",
                          dtype={"userId": "int32", "movieId": "int32", "rating": "float32", "timestamp": "int64"})
    ratings["rating"] = ratings["rating"].astype("float64")
    movies = pd.read_csv(folder / "movies.csv")
    tags = pd.read_csv(folder / "tags.csv")
    links = pd.read_csv(folder / "links.csv")
    return ratings, movies, tags, links


def clean_movies(movies, tags, links):
    m = movies.copy()
    m["title"] = m["title"].astype(str).str.strip()
    # "Toy Story (1995)" -> year 1995, clean_title "Toy Story"
    m["year"] = pd.to_numeric(m["title"].str.extract(YEAR_RE)[0], errors="coerce").astype("Int64")
    m["clean_title"] = m["title"].str.replace(YEAR_RE, "", regex=True).str.strip()
    m["genres"] = m["genres"].fillna("").replace("(no genres listed)", "")

    # Tags: lower-case, strip spaces, drop empty, keep unique tags per movie joined by "|"
    t = tags.dropna(subset=["tag"]).copy()
    t["tag"] = t["tag"].astype(str).str.lower().str.strip()
    t = t[t["tag"] != ""]
    tag_text = t.groupby("movieId")["tag"].apply(lambda s: "|".join(sorted(set(s)))).rename("tags")

    # Links: movieId -> tmdbId (some are missing)
    l = links[["movieId", "tmdbId"]].copy()
    l["tmdbId"] = pd.to_numeric(l["tmdbId"], errors="coerce").astype("Int64")

    m = m.merge(l, on="movieId", how="left").merge(tag_text, on="movieId", how="left")
    m["tags"] = m["tags"].fillna("")
    print(f"  movies: {len(m):,} | missing tmdbId: {m['tmdbId'].isna().sum():,} "
          f"| no genres: {(m['genres'] == '').sum():,} | with tags: {(m['tags'] != '').sum():,}")
    return m[["movieId", "title", "clean_title", "year", "genres", "tags", "tmdbId"]]


def clean_ratings(ratings, movies, min_user_ratings=5):
    r = ratings.dropna(subset=["userId", "movieId", "rating"]).copy()
    r = r[r["rating"].between(0.5, 5.0)]
    # if a user rated the same movie twice, keep the latest rating
    r = r.sort_values("timestamp").drop_duplicates(["userId", "movieId"], keep="last")
    r = r[r["movieId"].isin(movies["movieId"])]
    counts = r["userId"].value_counts()
    r = r[r["userId"].isin(counts[counts >= min_user_ratings].index)]
    return r.reset_index(drop=True)


def sample_users(r, n_users, seed=SEED):
    users = r["userId"].unique()
    if n_users >= len(users):
        return r
    rng = np.random.default_rng(seed)
    keep = rng.choice(users, size=n_users, replace=False)
    return r[r["userId"].isin(keep)].reset_index(drop=True)


def split_per_user(r, val_frac=0.1, test_frac=0.2, seed=SEED):
    """Randomly hold out a share of EACH user's ratings, so every test user also has training data."""
    r = r.sample(frac=1.0, random_state=seed).copy()        # shuffle rows
    r["rank"] = r.groupby("userId").cumcount()               # 0,1,2,... inside each user
    n = r.groupby("userId")["movieId"].transform("size")
    n_test = np.floor(n * test_frac).astype(int).clip(lower=1)
    n_val = np.floor(n * val_frac).astype(int)
    test = r[r["rank"] < n_test]
    val = r[(r["rank"] >= n_test) & (r["rank"] < n_test + n_val)]
    train = r[r["rank"] >= n_test + n_val]
    cols = ["userId", "movieId", "rating", "timestamp"]
    return train[cols], val[cols], test[cols]


def load_processed(dataset):
    """Used by every later script: returns movies, train, val, test DataFrames."""
    folder = PROCESSED_DIR / dataset
    movies = pd.read_csv(folder / "movies.csv", dtype={"year": "Int64", "tmdbId": "Int64"})
    movies["genres"] = movies["genres"].fillna("")
    movies["tags"] = movies["tags"].fillna("")
    train, val, test = (pd.read_csv(folder / f"{s}.csv") for s in ("train", "val", "test"))
    return movies, train, val, test


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="ml-latest-small")
    ap.add_argument("--sample-users", type=int, default=0, help="0 = keep all users")
    ap.add_argument("--min-user-ratings", type=int, default=5)
    args = ap.parse_args()

    ratings, movies, tags, links = load_raw(args.dataset)
    n_raw = len(ratings)
    if args.sample_users:                      # sample first, so the big file is cleaned in small form
        ratings = sample_users(ratings, args.sample_users)
    movies_c = clean_movies(movies, tags, links)
    ratings_c = clean_ratings(ratings, movies_c, args.min_user_ratings)

    # keep only movies that have at least one rating (makes the item index smaller)
    movies_c = movies_c[movies_c["movieId"].isin(ratings_c["movieId"])].reset_index(drop=True)
    train, val, test = split_per_user(ratings_c)

    n_u, n_i = ratings_c["userId"].nunique(), ratings_c["movieId"].nunique()
    print(f"  ratings: {n_raw:,} raw -> {len(ratings_c):,} clean")
    print(f"  users: {n_u:,} | movies: {n_i:,} | sparsity: {1 - len(ratings_c) / (n_u * n_i):.4%}")
    print(f"  split -> train {len(train):,} | val {len(val):,} | test {len(test):,}")

    out = PROCESSED_DIR / args.dataset
    out.mkdir(parents=True, exist_ok=True)
    movies_c.to_csv(out / "movies.csv", index=False)
    train.to_csv(out / "train.csv", index=False)
    val.to_csv(out / "val.csv", index=False)
    test.to_csv(out / "test.csv", index=False)
    print(f"Saved processed files to {out}")


if __name__ == "__main__":
    main()
