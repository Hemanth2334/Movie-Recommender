"""STEP 3 (extra) - Exploratory charts of the cleaned data, for the report's "Data" section.

Run:  python eda.py
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import DATASET, RESULTS_DIR
from data_pipeline import load_processed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    args = ap.parse_args()
    movies, train, val, test = load_processed(args.dataset)
    ratings = pd.concat([train, val, test])

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    ratings["rating"].value_counts().sort_index().plot.bar(ax=axes[0, 0], color="#4C72B0")
    axes[0, 0].set_title("How often each star value is used"); axes[0, 0].set_xlabel("Rating")

    ratings.groupby("userId").size().plot.hist(bins=50, ax=axes[0, 1], log=True, color="#55A868")
    axes[0, 1].set_title("Ratings per user (log scale)"); axes[0, 1].set_xlabel("# ratings")

    per_movie = ratings.groupby("movieId").size().sort_values(ascending=False).values
    axes[1, 0].plot(per_movie, color="#C44E52")
    axes[1, 0].set_yscale("log"); axes[1, 0].set_title("Long tail: ratings per movie (sorted)")
    axes[1, 0].set_xlabel("Movie rank"); axes[1, 0].set_ylabel("# ratings")

    movies["genres"].str.split("|").explode().replace("", pd.NA).dropna().value_counts().plot.barh(
        ax=axes[1, 1], color="#8172B2")
    axes[1, 1].set_title("Movies per genre")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "eda.png", dpi=150)
    print(f"Saved {RESULTS_DIR / 'eda.png'}")
    print(ratings["rating"].describe())


if __name__ == "__main__":
    main()
