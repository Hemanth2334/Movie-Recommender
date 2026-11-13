"""STEP 8 + STEP 9 - Matrix factorization with biases (Koren, Bell & Volinsky 2009).

Model:   r_hat(u, i) = mu + b_u + b_i + p_u . q_i
Loss:    sum (r - r_hat)^2 + reg * (b_u^2 + b_i^2 + |p_u|^2 + |q_i|^2)
Trained with stochastic gradient descent (in small mini-batches so it is fast in NumPy).

STEP 9 (new users): `fold_in` keeps the movie vectors fixed and solves a tiny
ridge regression for the new user's (b_u, p_u). It takes milliseconds, so the
profile can be updated every time the user rates another movie.
"""
import numpy as np
import pandas as pd


class MatrixFactorization:
    def __init__(self, item_ids, n_factors=50, lr=0.01, reg=0.05, n_epochs=30,
                 batch_size=512, init_std=0.1, fold_in_reg=None, seed=42):
        self.item_ids = np.asarray(item_ids)
        self.pos = {m: i for i, m in enumerate(self.item_ids)}
        self.k, self.lr, self.reg, self.n_epochs = n_factors, lr, reg, n_epochs
        self.batch_size, self.init_std, self.seed = batch_size, init_std, seed
        self.fold_in_reg = fold_in_reg if fold_in_reg is not None else max(reg * 20, 0.5)

    def _predict_idx(self, u, i):
        return self.mu + self.bu[u] + self.bi[i] + np.sum(self.P[u] * self.Q[i], axis=1)

    def fit(self, train, val=None, verbose=True):
        rng = np.random.default_rng(self.seed)
        users = np.sort(train["userId"].unique())
        self.uidx = {u: i for i, u in enumerate(users)}
        u_all = train["userId"].map(self.uidx).values
        i_all = train["movieId"].map(self.pos).values
        r_all = train["rating"].values.astype(np.float64)

        self.mu = r_all.mean()
        nu, ni = len(users), len(self.item_ids)
        self.P = rng.normal(0, self.init_std, (nu, self.k))
        self.Q = rng.normal(0, self.init_std, (ni, self.k))
        self.bu, self.bi = np.zeros(nu), np.zeros(ni)

        if val is not None:
            val = val[val["userId"].isin(self.uidx) & val["movieId"].isin(self.pos)]
            vu, vi = val["userId"].map(self.uidx).values, val["movieId"].map(self.pos).values
            vr = val["rating"].values
        self.history, best = [], (np.inf, None)
        lr, reg = self.lr, self.reg

        for epoch in range(1, self.n_epochs + 1):
            order = rng.permutation(len(r_all))
            for start in range(0, len(order), self.batch_size):
                b = order[start:start + self.batch_size]
                u, i, r = u_all[b], i_all[b], r_all[b]
                Pu, Qi = self.P[u], self.Q[i]
                err = r - (self.mu + self.bu[u] + self.bi[i] + np.sum(Pu * Qi, axis=1))
                # gradient steps (np.add.at handles a user/movie appearing twice in a batch)
                np.add.at(self.bu, u, lr * (err - reg * self.bu[u]))
                np.add.at(self.bi, i, lr * (err - reg * self.bi[i]))
                np.add.at(self.P, u, lr * (err[:, None] * Qi - reg * Pu))
                np.add.at(self.Q, i, lr * (err[:, None] * Pu - reg * Qi))

            train_rmse = np.sqrt(np.mean((r_all - np.clip(self._predict_idx(u_all, i_all), 0.5, 5)) ** 2))
            row = {"epoch": epoch, "train_rmse": train_rmse}
            if val is not None:
                val_rmse = np.sqrt(np.mean((vr - np.clip(self._predict_idx(vu, vi), 0.5, 5)) ** 2))
                row["val_rmse"] = val_rmse
                if val_rmse < best[0]:   # remember the best epoch (early stopping)
                    best = (val_rmse, (self.P.copy(), self.Q.copy(), self.bu.copy(), self.bi.copy(), epoch))
            self.history.append(row)
            if verbose:
                print("  epoch {epoch:2d}  train RMSE {train_rmse:.4f}".format(**row)
                      + (f"  val RMSE {row['val_rmse']:.4f}" if "val_rmse" in row else ""))

        if best[1] is not None:
            self.P, self.Q, self.bu, self.bi, self.best_epoch = best[1]
            if verbose:
                print(f"  -> keeping epoch {self.best_epoch} (best val RMSE {best[0]:.4f})")
        return self

    def predict(self, user_ids, movie_ids):
        out = np.empty(len(user_ids))
        for k, (u, m) in enumerate(zip(user_ids, movie_ids)):
            ui, ii = self.uidx.get(u), self.pos.get(m)
            pred = self.mu
            if ui is not None:
                pred += self.bu[ui]
            if ii is not None:
                pred += self.bi[ii]
            if ui is not None and ii is not None:
                pred += self.P[ui] @ self.Q[ii]
            out[k] = pred
        return np.clip(out, 0.5, 5.0)

    # ---------- STEP 9: instant profile for a new (or updated) user ----------
    def fold_in(self, user_ratings):
        """Return (b_u, p_u) for a user who is NOT in the training data."""
        movies = [m for m in user_ratings if m in self.pos]
        if not movies:
            return 0.0, np.zeros(self.k)
        idx = np.array([self.pos[m] for m in movies])
        y = np.array([user_ratings[m] for m in movies]) - self.mu - self.bi[idx]
        A = np.hstack([np.ones((len(idx), 1)), self.Q[idx]])          # columns: [bias, factors]
        lam = self.fold_in_reg * np.eye(self.k + 1)
        x = np.linalg.solve(A.T @ A + lam, A.T @ y)                     # ridge regression
        return x[0], x[1:]

    def scores(self, user_ratings, user_id=None):
        if user_id in getattr(self, "uidx", {}):
            u = self.uidx[user_id]
            b_u, p_u = self.bu[u], self.P[u]
        else:
            b_u, p_u = self.fold_in(user_ratings or {})
        return self.mu + b_u + self.bi + self.Q @ p_u

    def history_frame(self):
        return pd.DataFrame(self.history)
