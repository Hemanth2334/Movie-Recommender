"""STEP 10 - Hybrid recommender + five movies per genre.

final = w_cf * CF + w_content * Content + w_pop * Popularity
CF itself = cf_mix * MatrixFactorization + (1 - cf_mix) * UserKNN(top-N)
Each part is first scaled to 0..1 (min-max) so they are on the same scale.
The CF share grows with the number of ratings n:  alpha = n / (n + n0).
"""
import numpy as np
import pandas as pd

COLD = {"cf": 0.0, "content": 0.1, "pop": 0.9}    # weights when the user has rated nothing
WARM = {"cf": 0.8, "content": 0.1, "pop": 0.1}    # weights when the user has rated a lot


def scale_0_1(x):
    """Min-max scaling: best movie -> 1, worst -> 0. Keeps how much better the top movies are."""
    x = np.asarray(x, dtype=float)
    lo, hi = x.min(), x.max()
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


class HybridRecommender:
    def __init__(self, movies, popularity, content, mf, user_cf=None, n0=3, cf_mix=0.2,
                 min_ratings=5, cold=None, warm=None):
        self.movies = movies.reset_index(drop=True)
        self.item_ids = self.movies["movieId"].values
        self.pos = {m: i for i, m in enumerate(self.item_ids)}
        self.pop, self.content, self.mf, self.ucf = popularity, content, mf, user_cf
        self.n0, self.cf_mix, self.min_ratings = n0, cf_mix, min_ratings
        self.cold, self.warm = dict(cold or COLD), dict(warm or WARM)
        self.genre_lists = self.movies["genres"].fillna("").str.split("|")

    def weights(self, n_ratings):
        a = n_ratings / (n_ratings + self.n0)
        return {k: (1 - a) * self.cold[k] + a * self.warm[k] for k in self.cold}

    def scores(self, user_ratings, user_id=None):
        user_ratings = user_ratings or {}
        w = self.weights(len(user_ratings))
        cf = scale_0_1(self.mf.scores(user_ratings, user_id))
        if self.ucf is not None and self.cf_mix < 1.0:
            cf = self.cf_mix * cf + (1 - self.cf_mix) * scale_0_1(self.ucf.scores(user_ratings, user_id))
        final = (w["cf"] * cf
                 + w["content"] * scale_0_1(self.content.scores(user_ratings, user_id))
                 + w["pop"] * scale_0_1(self.pop.scores()))
        final[self.pop.counts < self.min_ratings] = -np.inf     # skip very obscure movies
        for m in user_ratings:                                   # never recommend already-rated movies
            if m in self.pos:
                final[self.pos[m]] = -np.inf
        return final

    def genre_order(self, user_ratings, max_genres):
        """Genres the user likes most come first; then the most common genres."""
        pref = {}
        if user_ratings:
            mean = np.mean(list(user_ratings.values()))
            for m, r in user_ratings.items():
                if m in self.pos:
                    for g in self.genre_lists[self.pos[m]]:
                        pref[g] = pref.get(g, 0.0) + (r - mean) + 0.5   # liked + frequently watched
        all_genres = self.genre_lists.explode().value_counts()
        all_genres = [g for g in all_genres.index if g]
        ordered = sorted(all_genres, key=lambda g: (-pref.get(g, -1e9), all_genres.index(g)))
        return ordered[:max_genres]

    def recommend_by_genre(self, user_ratings, per_genre=5, max_genres=8, genres=None,
                           pool=60, diversity=0.5, user_id=None):
        scores = self.scores(user_ratings, user_id)
        genres = genres or self.genre_order(user_ratings, max_genres)
        shown, result = set(), []
        for g in genres:
            mask = self.genre_lists.apply(lambda gs: g in gs).values & np.isfinite(scores)
            cand = np.where(mask)[0]
            cand = [c for c in cand if c not in shown]
            if not cand:
                continue
            cand = np.array(cand)
            cand = cand[np.argsort(-scores[cand])][:pool]
            picks = self._mmr(cand, scores, per_genre, diversity)
            shown.update(picks)
            result.append({"genre": g, "movies": [self._movie_dict(i, scores[i]) for i in picks]})
        return result

    def _mmr(self, cand, scores, n, diversity):
        """Maximal Marginal Relevance: good score, but not too similar to what is already picked."""
        rel = scale_0_1(scores[cand]) if len(cand) > 1 else np.ones(1)
        sim = self.content.similarity(cand, cand)
        # same franchise ("Lord of the Rings: ...", "Toy Story 2") counts as a duplicate
        series = self.movies["clean_title"].iloc[cand].str.split(":").str[0].str.replace(r"\s+\d+$", "", regex=True).str.lower().values
        sim = np.maximum(sim, (series[:, None] == series[None, :]).astype(float))
        picked = [0]
        while len(picked) < min(n, len(cand)):
            max_sim = sim[:, picked].max(axis=1)
            mmr = (1 - diversity) * rel - diversity * max_sim
            mmr[picked] = -np.inf
            picked.append(int(np.argmax(mmr)))
        return [int(cand[p]) for p in picked]

    def _movie_dict(self, i, score):
        row = self.movies.iloc[i]
        return {"movieId": int(row["movieId"]), "title": row["clean_title"],
                "year": None if pd.isna(row["year"]) else int(row["year"]),
                "genres": row["genres"], "tmdbId": None if pd.isna(row["tmdbId"]) else int(row["tmdbId"]),
                "score": round(float(score), 4)}
