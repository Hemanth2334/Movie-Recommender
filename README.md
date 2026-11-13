# Personalized Movie Recommendation System (CSE 575)

Hybrid recommender (user-based CF + matrix factorization + content + popularity) on MovieLens,
with posters and where-to-watch data from TMDB, a FastAPI backend, and a React front end.

## Run order (from the `backend` folder, with the virtual environment active)

| # | Command | What it does |
|---|---------|--------------|
| 1 | `python data_pipeline.py` | clean MovieLens + train/val/test split |
| 2 | `python eda.py` | data charts -> results/eda.png |
| 3 | `python tune.py` | pick settings on the validation set -> results/best_params.json |
| 4 | `python train_models.py` | train all models -> models/ml-latest-small.pkl |
| 5 | `python evaluate.py` | test-set metrics + cold-start + charts -> results/ |
| 6 | `uvicorn main:app --reload --port 8000` | start the API (docs at http://localhost:8000/docs) |
| 7 | `cd ../frontend && npm install && npm run dev` | start the website at http://localhost:5173 |

Put the MovieLens files in `data/raw/ml-latest-small/` and your TMDB token in `backend/.env`
(copy `backend/.env.example`).

Big dataset: `python data_pipeline.py --dataset ml-32m --sample-users 20000`, then run steps 3-5 with
`--dataset ml-32m` (`tune.py --quick`, `evaluate.py --max-users 2000`).

Attribution: This product uses the TMDB API but is not endorsed or certified by TMDB.
Streaming availability data provided by JustWatch. Ratings data: MovieLens (GroupLens).
