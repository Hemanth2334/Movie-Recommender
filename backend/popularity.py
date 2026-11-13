"""STEP 5 - Popularity baseline.

Rating prediction:  r_hat(u, i) = mu + b_u + b_i   (damped "baseline" biases)
Ranking score:      either number of ratings ("count") or a Bayesian average ("bayes")
"""
import numpy as np


class PopularityModel:
    def __init__(self, item_ids, damping=10, score_type="count"):
        self.item_ids = np.asarray(item_ids)
        self.pos = {m: i for i, m in enumerate(self.item_ids)}
        self.damping = damping
        self.score_type = score_type

    def fit(self, train):
        self.mu = float(train["rating"].mean())
        n_items = len(self.item_ids)
        idx = train["movieId"].map(self.pos).values
        r = train["rating"].values

        self.counts = np.bincount(idx, minlength=n_items).astype(float)
        sums = np.bincount(idx, weights=r - self.mu, minlength=n_items)
        # damped item bias: few ratings -> pulled toward 0 (the global mean)
        self.item_bias = sums / (self.counts + self.damping)
        self.bayes_avg = self.mu + self.item_bias

        resid = r - self.mu - self.item_bias[idx]
        tmp = train.assign(resid=resid).groupby("userId")["resid"].agg(["sum", "count"])
        self.user_bias = (tmp["sum"] / (tmp["count"] + self.damping)).to_dict()
        return self

    def predict(self, user_ids, movie_ids):
        out = np.full(len(movie_ids), self.mu)
        for k, (u, m) in enumerate(zip(user_ids, movie_ids)):
            i = self.pos.get(m)
            out[k] += self.user_bias.get(u, 0.0) + (self.item_bias[i] if i is not None else 0.0)
        return np.clip(out, 0.5, 5.0)

    def scores(self, user_ratings=None, user_id=None):
        """Same list for everybody - that is what makes it a baseline."""
        if self.score_type == "count":
            return np.log1p(self.counts)
        return self.bayes_avg.copy()
