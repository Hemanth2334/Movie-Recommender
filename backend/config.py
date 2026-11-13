"""Shared settings for every script. Change values here, not inside each file."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains backend/, data/, frontend/
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "backend" / ".env")

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"
for d in (PROCESSED_DIR, MODELS_DIR, RESULTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Which MovieLens folder inside data/raw/ to use
DATASET = os.getenv("DATASET", "ml-latest-small")

SEED = 42
RELEVANCE_THRESHOLD = 4.0   # a test rating >= 4.0 counts as "the user liked it"
TOP_K = 10                  # Precision@10, Recall@10, NDCG@10

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN", "")
TMDB_CACHE_HOURS = 24       # watch-provider data changes, so refresh daily
APP_DB = BASE_DIR / "backend" / "app.db"
