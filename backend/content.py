"""STEP 7 - Content-based model (uses movie features, not other users).

Each movie becomes a feature vector:
    [ genre multi-hot | TF-IDF of user tags | release decade one-hot ]
User profile = weighted sum of the vectors of movies they rated (weight = rating - their mean).
Score for a movie = cosine similarity between the profile and the movie vector.
"""
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, normalize


def split_pipes(text):
    """Tokenizer for 'tag one|tag two' strings (a named function so the model can be pickled)."""
    return [t for t in text.split("|") if t]


class ContentModel:
    def __init__(self, movies, genre_w=1.0, tag_w=0.7, decade_w=0.3, n_neighbors=30):
        # movies must be in the SAME order as item_ids used by every other model
        self.movies = movies.reset_index(drop=True)
        self.item_ids = self.movies["movieId"].values
        self.pos = {m: i for i, m in enumerate(self.item_ids)}
        self.genre_w, self.tag_w, self.decade_w = genre_w, tag_w, decade_w
        self.n_neighbors = n_neighbors

    def build_features(self):
        genres = self.movies["genres"].fillna("").apply(split_pipes)
        self.mlb = MultiLabelBinarizer(sparse_output=True)
        G = self.mlb.fit_transform(genres).astype(np.float32)
        self.genre_names = list(self.mlb.classes_)

        tags = self.movies["tags"].fillna("")
        if (tags != "").sum() >= 2:
            self.tfidf = TfidfVectorizer(tokenizer=split_pipes, token_pattern=None, lowercase=False, min_df=2)
            T = self.tfidf.fit_transform(tags).astype(np.float32)
        else:
            T = sparse.csr_matrix((len(self.movies), 0), dtype=np.float32)

        decade = (self.movies["year"].astype("float") // 10 * 10).fillna(-1).astype(int).astype(str)
        D = sparse.csr_matrix(pd.get_dummies(decade).values.astype(np.float32))

        X = sparse.hstack([normalize(G) * self.genre_w, T * self.tag_w, D * self.decade_w]).tocsr()
        self.X = normalize(X)                              # each row has length 1 -> dot product = cosine
        self.G = G.tocsr()                                 # kept for the per-genre lists
        return self

    def fit(self, train):
        self.build_features()
        self.mu = float(train["rating"].mean())
        self.train_by_user = {u: dict(zip(g["movieId"], g["rating"])) for u, g in train.groupby("userId")}
        return self

    def profile(self, user_ratings):
        movies = [m for m in user_ratings if m in self.pos]
        if not movies:
            return None
        r = np.array([user_ratings[m] for m in movies], dtype=np.float32)
        w = r - r.mean() if r.std() > 0 else r - 3.0      # liked = positive weight, disliked = negative
        prof = sparse.csr_matrix(w) @ self.X[[self.pos[m] for m in movies]]
        return normalize(prof)

    def scores(self, user_ratings, user_id=None):
        if user_ratings is None:
            user_ratings = self.train_by_user.get(user_id, {})
        prof = self.profile(user_ratings)
        if prof is None:
            return np.zeros(len(self.item_ids))
        return np.asarray((self.X @ prof.T).todense()).ravel()

    def similarity(self, idx_a, idx_b):
        return (self.X[idx_a] @ self.X[idx_b].T).toarray()

    def predict(self, user_ids, movie_ids):
        """Item-kNN on content similarity: average of the user's own ratings on the most similar movies."""
        df = pd.DataFrame({"u": user_ids, "m": movie_ids})
        out = np.full(len(df), self.mu)
        for u, g in df.groupby("u"):
            hist = self.train_by_user.get(u)
            if not hist:
                continue
            h_ids = [m for m in hist if m in self.pos]
            h_r = np.array([hist[m] for m in h_ids])
            mean_u = h_r.mean()
            targets = [self.pos.get(m, -1) for m in g["m"]]
            valid = [t for t in targets if t >= 0]
            preds = np.full(len(targets), mean_u)
            if valid:
                S = self.similarity(valid, [self.pos[m] for m in h_ids])
                k = min(self.n_neighbors, S.shape[1])
                top = np.argpartition(-S, k - 1, axis=1)[:, :k]
                s = np.clip(np.take_along_axis(S, top, axis=1), 0, None)
                dev = (s * (h_r[top] - mean_u)).sum(1) / (s.sum(1) + 1e-9)
                preds[[j for j, t in enumerate(targets) if t >= 0]] = mean_u + dev
            out[g.index.values] = preds
        return np.clip(out, 0.5, 5.0)
