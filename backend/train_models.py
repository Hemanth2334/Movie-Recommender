"""Train every model with the best settings and save them to models/<dataset>.pkl.

Run:  python train_models.py
The FastAPI backend (main.py) and evaluate.py load this file instead of re-training.
"""
import argparse
import json
import pickle
import time

from config import DATASET, MODELS_DIR, RESULTS_DIR
from content import ContentModel
from data_pipeline import load_processed
from hybrid import HybridRecommender
from mf import MatrixFactorization
from popularity import PopularityModel
from user_cf import UserKNN


def load_best_params():
    path = RESULTS_DIR / "best_params.json"
    if path.exists():
        print(f"Using tuned settings from {path}")
        return json.loads(path.read_text())
    print("No best_params.json yet -> using defaults (run tune.py later)")
    return {"mf": {"n_factors": 50, "reg": 0.05, "lr": 0.01, "n_epochs": 30},
            "user_cf": {"k": 40}, "hybrid": {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    args = ap.parse_args()
    movies, train, val, _ = load_processed(args.dataset)
    ids = movies["movieId"].values
    params = load_best_params()

    t = time.time()
    pop = PopularityModel(ids).fit(train)
    content = ContentModel(movies).fit(train)
    ucf = UserKNN(ids, **params["user_cf"]).fit(train)
    print(f"popularity + content + user-CF trained in {time.time()-t:.1f}s")

    t = time.time()
    mf = MatrixFactorization(ids, **params["mf"]).fit(train, val)
    mf.history_frame().to_csv(RESULTS_DIR / "mf_learning_curve.csv", index=False)
    print(f"matrix factorization trained in {time.time()-t:.1f}s")

    hybrid = HybridRecommender(movies, pop, content, mf, user_cf=ucf, **params.get("hybrid", {}))
    out = MODELS_DIR / f"{args.dataset}.pkl"
    with open(out, "wb") as f:
        pickle.dump({"movies": movies, "popularity": pop, "content": content,
                     "user_cf": ucf, "mf": mf, "hybrid": hybrid}, f)
    print(f"Saved all models to {out}")


if __name__ == "__main__":
    main()
