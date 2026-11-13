"""STEP 8 / STEP 14 - Pick hyper-parameters on the VALIDATION set (never on test!).

Run:  python tune.py            (full grid)
      python tune.py --quick    (smaller grid, for the big dataset)
Writes results/best_params.json, which train_models.py reads.
"""
import argparse
import itertools
import json
import time

import numpy as np
import pandas as pd

from config import DATASET, RESULTS_DIR
from content import ContentModel
from data_pipeline import load_processed
from hybrid import HybridRecommender
from metrics import evaluate_ranking, evaluate_rating_model
from mf import MatrixFactorization
from popularity import PopularityModel
from user_cf import UserKNN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    movies, train, val, _ = load_processed(args.dataset)
    ids = movies["movieId"].values
    rows = []

    # ---- 1) Matrix factorization: number of factors x regularisation ----
    factors = [20, 50] if args.quick else [20, 50, 100]
    regs = [0.1] if args.quick else [0.05, 0.1, 0.2]
    best_mf = None
    for k, reg in itertools.product(factors, regs):
        t = time.time()
        mf = MatrixFactorization(ids, n_factors=k, reg=reg, lr=0.01, n_epochs=60).fit(train, val, verbose=False)
        res = evaluate_rating_model(mf, val)
        print(f"MF  k={k:3d} reg={reg:<5} best_epoch={mf.best_epoch:2d}  val RMSE {res['RMSE']:.4f}  ({time.time()-t:.0f}s)")
        rows.append({"model": "MF", "params": f"k={k}, reg={reg}, epochs={mf.best_epoch}", **res})
        if best_mf is None or res["RMSE"] < best_mf[0]:
            best_mf = (res["RMSE"], {"n_factors": k, "reg": reg, "lr": 0.01, "n_epochs": mf.best_epoch}, mf)

    # ---- 2) User-based CF: neighbours for rating prediction (RMSE) and for top-N (NDCG) ----
    best_ucf = None
    for k in ([40] if args.quick else [20, 40, 80]):
        ucf = UserKNN(ids, k=k, k_topn=10).fit(train)
        res = evaluate_rating_model(ucf, val)
        print(f"UserKNN k={k:3d}  val RMSE {res['RMSE']:.4f}")
        rows.append({"model": "UserKNN (ratings)", "params": f"k={k}", **res})
        if best_ucf is None or res["RMSE"] < best_ucf[0]:
            best_ucf = (res["RMSE"], k)
    best_topn = None
    for k_topn in ([100] if args.quick else [50, 100, 200]):
        ucf = UserKNN(ids, k=best_ucf[1], k_topn=k_topn).fit(train)
        res = evaluate_ranking(lambda u, s: ucf.scores(s, u), ids, train, val, max_users=400)
        print(f"UserKNN k_topn={k_topn:3d}  val NDCG@10 {res['NDCG@10']:.4f}")
        rows.append({"model": "UserKNN (top-N)", "params": f"k_topn={k_topn}", **res})
        if best_topn is None or res["NDCG@10"] > best_topn[0]:
            best_topn = (res["NDCG@10"], k_topn, ucf)
    best_ucf = (best_ucf[0], {"k": best_ucf[1], "k_topn": best_topn[1]})

    # ---- 3) Hybrid weights (for users with many ratings), judged by NDCG@10 on validation ----
    pop = PopularityModel(ids).fit(train)
    content = ContentModel(movies).fit(train)
    mf, ucf = best_mf[2], best_topn[2]
    best_h = None
    grid = itertools.product([0.6, 0.7, 0.8, 0.9, 1.0], [0.0, 0.05, 0.1, 0.2], [0.0, 0.2, 0.4])
    for cf_w, c_w, cf_mix in grid:
        pop_w = round(1 - cf_w - c_w, 2)
        if pop_w < 0:
            continue
        warm = {"cf": cf_w, "content": c_w, "pop": abs(pop_w)}   # abs turns -0.0 into 0.0
        h = HybridRecommender(movies, pop, content, mf, user_cf=ucf, warm=warm, cf_mix=cf_mix)
        res = evaluate_ranking(lambda u, s: h.scores(s, u), ids, train, val, max_users=400)
        print(f"Hybrid warm={warm} cf_mix={cf_mix}  val NDCG@10 {res['NDCG@10']:.4f}")
        rows.append({"model": "Hybrid", "params": f"{warm}, cf_mix={cf_mix}", **res})
        if best_h is None or res["NDCG@10"] > best_h[0]:
            best_h = (res["NDCG@10"], {"warm": warm, "cf_mix": cf_mix})

    # ---- 4) Cold start: weights for brand-new users + how fast CF takes over (n0) ----
    rng = np.random.default_rng(0)
    best_c = None
    for cold, n0 in itertools.product([{"cf": 0.0, "content": 0.4, "pop": 0.6},
                                       {"cf": 0.0, "content": 0.1, "pop": 0.9},
                                       {"cf": 0.0, "content": 0.0, "pop": 1.0}], [3, 10]):
        h = HybridRecommender(movies, pop, content, mf, user_cf=ucf, cold=cold, n0=n0, **best_h[1])
        ndcgs = []
        for n in [1, 3, 5, 10]:          # pretend users have rated only n movies
            def keep_n(seen, n=n):
                items = list(seen.items())
                pick = rng.choice(len(items), size=min(n, len(items)), replace=False)
                return dict(items[j] for j in pick)
            res = evaluate_ranking(lambda u, s: h.scores(keep_n(s)), ids, train, val, max_users=300)
            ndcgs.append(res["NDCG@10"])
        avg = float(np.mean(ndcgs))
        print(f"Cold {cold} n0={n0}  avg val NDCG@10 (1-10 ratings) {avg:.4f}")
        rows.append({"model": "Hybrid cold start", "params": f"{cold}, n0={n0}", "NDCG@10": avg})
        if best_c is None or avg > best_c[0]:
            best_c = (avg, {"cold": cold, "n0": n0})

    best = {"mf": best_mf[1], "user_cf": best_ucf[1], "hybrid": {**best_h[1], **best_c[1]}}
    (RESULTS_DIR / "best_params.json").write_text(json.dumps(best, indent=2))
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "tuning_log.csv", index=False)
    print("\nBEST:", json.dumps(best, indent=2))


if __name__ == "__main__":
    main()
