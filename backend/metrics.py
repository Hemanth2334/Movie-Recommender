"""STEP 4 - Evaluation metrics.

Rating accuracy:  RMSE, MAE  (lower is better)
Top-K accuracy:   Precision@K, Recall@K, NDCG@K  (higher is better)
"""
import numpy as np

from config import RELEVANCE_THRESHOLD, TOP_K


def rmse(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mae(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    return float(np.mean(np.abs(y_true - y_pred)))


def precision_recall_ndcg(recommended, relevant, k):
    """recommended: ordered list of movieIds. relevant: set of movieIds the user liked in the test set."""
    rec = list(recommended)[:k]
    hits = np.array([1.0 if m in relevant else 0.0 for m in rec])
    precision = hits.sum() / k
    recall = hits.sum() / len(relevant)
    discounts = 1.0 / np.log2(np.arange(2, k + 2))           # 1/log2(rank+1)
    dcg = float((hits * discounts[: len(hits)]).sum())
    idcg = float(discounts[: min(len(relevant), k)].sum())     # best possible ordering
    return precision, recall, dcg / idcg


def evaluate_rating_model(model, test_df):
    preds = model.predict(test_df["userId"].values, test_df["movieId"].values)
    return {"RMSE": rmse(test_df["rating"], preds), "MAE": mae(test_df["rating"], preds)}


def evaluate_ranking(score_fn, item_ids, train_df, test_df, k=TOP_K,
                     threshold=RELEVANCE_THRESHOLD, max_users=None, seed=0):
    """score_fn(user_id, user_train_ratings_dict) -> np.array of scores aligned with item_ids.

    For every test user: rank all movies they did NOT rate in training,
    take the top k, and compare with the movies they rated >= threshold in the test set.
    """
    train_by_user = {u: dict(zip(g["movieId"], g["rating"])) for u, g in train_df.groupby("userId")}
    liked = test_df[test_df["rating"] >= threshold].groupby("userId")["movieId"].apply(set)
    users = [u for u in liked.index if u in train_by_user]
    if max_users and len(users) > max_users:
        users = list(np.random.default_rng(seed).choice(users, max_users, replace=False))

    pos = {m: i for i, m in enumerate(item_ids)}
    P, R, N = [], [], []
    for u in users:
        seen = train_by_user[u]
        scores = np.asarray(score_fn(u, seen), dtype=float).copy()
        seen_idx = [pos[m] for m in seen if m in pos]
        scores[seen_idx] = -np.inf                       # never recommend what they already rated
        top = np.argpartition(-scores, k)[:k]
        top = top[np.argsort(-scores[top])]
        p, r, n = precision_recall_ndcg(item_ids[top], liked[u], k)
        P.append(p); R.append(r); N.append(n)
    return {f"Precision@{k}": float(np.mean(P)), f"Recall@{k}": float(np.mean(R)),
            f"NDCG@{k}": float(np.mean(N)), "users_evaluated": len(users)}
