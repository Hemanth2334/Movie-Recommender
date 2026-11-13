"""STEP 6 - User-based collaborative filtering ("people like you also watched/liked ...").

This model does two jobs, each with its own kind of neighbour:

A) RATING PREDICTION (for RMSE / MAE)  -> neighbours from CENTRED RATINGS
   1. Centre each user's ratings by their own mean (some people rate everything high).
   2. sim(u, v) = cosine of the centred rating vectors.
   3. r_hat(u, i) = mean_u + shrink * sum_v sim(u,v) * (r_vi - mean_v) / sum_v |sim(u,v)|

B) TOP-N RANKING (for Precision / Recall / NDCG and the app) -> neighbours from WHO WATCHED WHAT
   This is the "one-class" view (Yao et al., CIKM 2014): a rating, any rating, means "watched".
   1. sim(u, v) = cosine of the 0/1 "has rated" vectors.
   2. score(u, i) = sum over the k most similar users v who watched i of sim(u, v).
   On MovieLens this ranks far better than predicted star ratings do.
"""
import numpy as np
import pandas as pd
from scipy import sparse


def row_normalise(X):
    norms = np.sqrt(np.asarray(X.multiply(X).sum(axis=1))).ravel()
    norms[norms == 0] = 1.0
    return (sparse.diags(1.0 / norms) @ X).tocsr()


class UserKNN:
    def __init__(self, item_ids, k=40, k_topn=100, shrink=5.0, chunk=1000):
        self.item_ids = np.asarray(item_ids)
        self.pos = {m: i for i, m in enumerate(self.item_ids)}
        self.k, self.k_topn, self.shrink, self.chunk = k, k_topn, shrink, chunk

    # ------------------------------------------------------------------ training
    def fit(self, train):
        self.mu = float(train["rating"].mean())
        users = np.sort(train["userId"].unique())
        self.uidx = {u: i for i, u in enumerate(users)}
        rows = train["userId"].map(self.uidx).values
        cols = train["movieId"].map(self.pos).values
        r = train["rating"].values.astype(np.float32)
        self.user_mean = train.groupby("userId")["rating"].mean().reindex(users).values.astype(np.float32)
        shape = (len(users), len(self.item_ids))
        self.Rc = sparse.csr_matrix((r - self.user_mean[rows], (rows, cols)), shape=shape)   # centred
        self.M = sparse.csr_matrix((np.ones_like(r), (rows, cols)), shape=shape)            # 0/1 watched
        self.Rn = row_normalise(self.Rc)
        self.Mn = row_normalise(self.M)
        self.nbr_idx, self.nbr_sim = self._all_neighbours(self.Rn, self.k)
        self.top_idx, self.top_sim = self._all_neighbours(self.Mn, self.k_topn)
        return self

    def _all_neighbours(self, X, k):
        """Top-k most similar users for every user, computed in chunks to save memory."""
        n = X.shape[0]
        idx_all = np.zeros((n, k), dtype=np.int32)
        sim_all = np.zeros((n, k), dtype=np.float32)
        for start in range(0, n, self.chunk):
            stop = min(start + self.chunk, n)
            S = (X[start:stop] @ X.T).toarray()
            S[np.arange(stop - start), np.arange(start, stop)] = -np.inf   # not your own neighbour
            idx_all[start:stop], sim_all[start:stop] = self._top_k(S, k)
        return idx_all, sim_all

    @staticmethod
    def _top_k(S, k):
        kk = min(k, S.shape[1] - 1)
        idx = np.argpartition(-S, kk, axis=1)[:, :kk]
        sim = np.take_along_axis(S, idx, axis=1)
        sim = np.where(sim > 0, sim, 0.0)          # ignore dissimilar users
        if kk < k:                                  # tiny datasets
            idx, sim = np.pad(idx, ((0, 0), (0, k - kk))), np.pad(sim, ((0, 0), (0, k - kk)))
        return idx, sim.astype(np.float32)

    # ------------------------------------------------------------------ A) rating prediction
    def _predict_row(self, mean_u, idx, sim):
        num = np.asarray(sim @ self.Rc[idx]).ravel()          # weighted neighbour deviations
        den = np.asarray(np.abs(sim) @ self.M[idx]).ravel()   # sum |sim| over neighbours who rated it
        support = np.asarray(self.M[idx].sum(axis=0)).ravel()
        dev = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        dev *= support / (support + self.shrink)              # trust deviations backed by more neighbours
        return mean_u + dev

    def predict(self, user_ids, movie_ids):
        df = pd.DataFrame({"u": user_ids, "m": movie_ids})
        out = np.full(len(df), self.mu)
        for u, g in df.groupby("u"):
            if u not in self.uidx:
                continue
            ui = self.uidx[u]
            row = self._predict_row(self.user_mean[ui], self.nbr_idx[ui], self.nbr_sim[ui])
            out[g.index.values] = [row[self.pos[m]] if m in self.pos else self.user_mean[ui] for m in g["m"]]
        return np.clip(out, 0.5, 5.0)

    # ------------------------------------------------------------------ B) top-N ranking
    def scores(self, user_ratings, user_id=None):
        if user_id in getattr(self, "uidx", {}):
            ui = self.uidx[user_id]
            idx, sim = self.top_idx[ui], self.top_sim[ui]
        else:                                                  # new user: find neighbours on the fly
            movies = [m for m in (user_ratings or {}) if m in self.pos]
            if not movies:
                return np.zeros(len(self.item_ids))
            vec = np.zeros(len(self.item_ids), dtype=np.float32)
            vec[[self.pos[m] for m in movies]] = 1.0 / np.sqrt(len(movies))
            S = (self.Mn @ vec).reshape(1, -1)
            idx, sim = self._top_k(S, self.k_topn)
            idx, sim = idx[0], sim[0]
        return np.asarray(sim @ self.M[idx]).ravel()
