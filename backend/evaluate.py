"""STEP 14 - Final evaluation on the TEST set + cold-start experiment + charts for the report.

Run:  python evaluate.py
Outputs (in results/):  test_results.csv/.md, cold_start.csv, and three .png charts.
"""
import argparse
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import DATASET, MODELS_DIR, RESULTS_DIR, TOP_K
from data_pipeline import load_processed
from metrics import evaluate_ranking, evaluate_rating_model
from popularity import PopularityModel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--max-users", type=int, default=0, help="evaluate a sample of users (big data)")
    args = ap.parse_args()
    max_users = args.max_users or None

    movies, train, val, test = load_processed(args.dataset)
    with open(MODELS_DIR / f"{args.dataset}.pkl", "rb") as f:
        M = pickle.load(f)
    ids = movies["movieId"].values
    pop_bayes = PopularityModel(ids, score_type="bayes").fit(train)

    # ---------- 1) every model on the test set ----------
    models = {
        "Popularity (most rated)": (M["popularity"], True),
        "Popularity (Bayesian avg)": (pop_bayes, False),
        "User-based CF": (M["user_cf"], True),
        "Content-based": (M["content"], True),
        "Matrix factorization": (M["mf"], True),
        "Hybrid": (M["hybrid"], False),
    }
    rows = []
    for name, (model, has_rmse) in models.items():
        print(f"Evaluating {name} ...")
        row = {"Model": name}
        if has_rmse:
            row.update(evaluate_rating_model(model, test))
        row.update(evaluate_ranking(lambda u, s, m=model: m.scores(s, u), ids, train, test,
                                    max_users=max_users))
        rows.append(row)
    table = pd.DataFrame(rows).drop(columns="users_evaluated").round(4)
    table.to_csv(RESULTS_DIR / "test_results.csv", index=False)
    (RESULTS_DIR / "test_results.md").write_text(table.to_markdown(index=False))
    print("\n" + table.to_markdown(index=False))

    # ---------- 2) cold start: pretend each test user is NEW and has rated only n movies ----------
    rng = np.random.default_rng(0)
    cold_rows = []
    for n in [1, 3, 5, 10, 20, 50]:
        def keep_n(seen):
            items = list(seen.items())
            pick = rng.choice(len(items), size=min(n, len(items)), replace=False)
            return dict(items[j] for j in pick)
        for name, fn in {
            "Popularity": lambda s: M["popularity"].scores(),
            "Content-based": lambda s: M["content"].scores(s),
            "MF (fold-in)": lambda s: M["mf"].scores(s),          # no user_id -> fold-in
            "User-based CF": lambda s: M["user_cf"].scores(s),   # no user_id -> neighbours on the fly
            "Hybrid": lambda s: M["hybrid"].scores(s),
        }.items():
            res = evaluate_ranking(lambda u, seen, fn=fn: fn(keep_n(seen)), ids, train, test,
                                   max_users=max_users or 300)
            cold_rows.append({"n_ratings": n, "model": name, f"NDCG@{TOP_K}": res[f"NDCG@{TOP_K}"],
                              f"Precision@{TOP_K}": res[f"Precision@{TOP_K}"]})
        print(f"cold-start n={n} done")
    cold = pd.DataFrame(cold_rows)
    cold.to_csv(RESULTS_DIR / "cold_start.csv", index=False)

    # ---------- 3) charts ----------
    fig, ax = plt.subplots(figsize=(8, 4))
    t = table.set_index("Model")[f"NDCG@{TOP_K}"].sort_values()
    ax.barh(t.index, t.values, color="#4C72B0")
    ax.set_xlabel(f"NDCG@{TOP_K} (test set, higher is better)")
    ax.set_title("Top-10 recommendation quality by model")
    fig.tight_layout(); fig.savefig(RESULTS_DIR / "model_comparison.png", dpi=150)

    fig, ax = plt.subplots(figsize=(7, 4))
    for name, g in cold.groupby("model"):
        ax.plot(g["n_ratings"], g[f"NDCG@{TOP_K}"], marker="o", label=name)
    ax.set_xscale("log"); ax.set_xticks([1, 3, 5, 10, 20, 50], labels=["1", "3", "5", "10", "20", "50"])
    ax.set_xlabel("Number of ratings the new user has given")
    ax.set_ylabel(f"NDCG@{TOP_K}"); ax.set_title("Cold start: quality vs. ratings given")
    ax.legend(loc="center right"); fig.tight_layout(); fig.savefig(RESULTS_DIR / "cold_start.png", dpi=150)

    lc_path = RESULTS_DIR / "mf_learning_curve.csv"
    if lc_path.exists():
        lc = pd.read_csv(lc_path)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(lc["epoch"], lc["train_rmse"], label="train")
        if "val_rmse" in lc:
            ax.plot(lc["epoch"], lc["val_rmse"], label="validation")
        ax.set_xlabel("Epoch"); ax.set_ylabel("RMSE"); ax.set_title("Matrix factorization learning curve")
        ax.legend(); fig.tight_layout(); fig.savefig(RESULTS_DIR / "mf_learning_curve.png", dpi=150)
    print(f"\nSaved tables and charts to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
