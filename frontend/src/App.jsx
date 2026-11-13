import { useEffect, useState } from "react";
import { api } from "./api.js";
import MovieCard from "./components/MovieCard.jsx";
import StarRating from "./components/StarRating.jsx";

const REGIONS = { US: "United States", GB: "United Kingdom", IN: "India", CA: "Canada", DE: "Germany", AU: "Australia" };
const MIN_RATINGS = 5;

export default function App() {
  const [userId, setUserId] = useState(localStorage.getItem("userId"));
  const [region, setRegion] = useState(localStorage.getItem("region") || "US");
  const [view, setView] = useState("rate"); // "rate" | "recs" | "mine"
  const [ratings, setRatings] = useState({}); // movieId -> rating
  const [error, setError] = useState("");

  // 1) make sure we have a user id (stored in the browser so a refresh keeps your ratings)
  useEffect(() => {
    async function init() {
      try {
        let id = userId;
        if (!id) {
          id = (await api.createUser()).user_id;
          localStorage.setItem("userId", id);
          setUserId(id);
        }
        const mine = await api.myRatings(id);
        setRatings(Object.fromEntries(mine.map((m) => [m.movieId, m.rating])));
      } catch (e) {
        localStorage.removeItem("userId"); // e.g. the backend database was reset
        setUserId(null);
        setError("Could not reach the backend. Is it running on port 8000?");
      }
    }
    init();
  }, [userId]);

  useEffect(() => localStorage.setItem("region", region), [region]);

  async function rate(movieId, rating) {
    setRatings((r) => ({ ...r, [movieId]: rating }));
    await api.rate(userId, movieId, rating);
  }

  async function unrate(movieId) {
    setRatings(({ [movieId]: _, ...rest }) => rest);
    await api.unrate(userId, movieId);
  }

  const count = Object.keys(ratings).length;
  return (
    <div className="app">
      <header>
        <h1>🎬 Movie Recommender</h1>
        <nav>
          <button className={view === "rate" ? "active" : ""} onClick={() => setView("rate")}>Rate movies</button>
          <button className={view === "recs" ? "active" : ""} disabled={count < MIN_RATINGS} onClick={() => setView("recs")}>
            My recommendations
          </button>
          <button className={view === "mine" ? "active" : ""} onClick={() => setView("mine")}>My ratings ({count})</button>
        </nav>
        <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Country">
          {Object.entries(REGIONS).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
      </header>

      {error && <p className="error">{error}</p>}
      {userId && view === "rate" && <RatePage region={region} ratings={ratings} onRate={rate} count={count} goToRecs={() => setView("recs")} />}
      {userId && view === "recs" && <RecsPage userId={userId} region={region} ratings={ratings} onRate={rate} />}
      {userId && view === "mine" && <MyRatingsPage userId={userId} ratings={ratings} onRate={rate} onRemove={unrate} />}

      <footer>
        This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming availability data provided by JustWatch.
        Ratings data: MovieLens (GroupLens, University of Minnesota).
      </footer>
    </div>
  );
}

function RatePage({ region, ratings, onRate, count, goToRecs }) {
  const [movies, setMovies] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  useEffect(() => { api.onboarding(region).then(setMovies); }, [region]);

  async function search(e) {
    e.preventDefault();
    if (query.trim()) setResults(await api.search(query.trim(), region));
  }

  return (
    <main>
      <div className="intro">
        <p>
          Rate at least {MIN_RATINGS} movies you have seen ({count} so far). The more you rate, the more the
          recommendations rely on people with similar taste.
        </p>
        <button className="primary" disabled={count < MIN_RATINGS} onClick={goToRecs}>Show my recommendations →</button>
      </div>
      <form onSubmit={search} className="search">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search for a movie you've seen…" />
        <button type="submit">Search</button>
      </form>
      {results.length > 0 && (
        <>
          <h2>Search results</h2>
          <div className="grid">{results.map((m) => <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} />)}</div>
        </>
      )}
      <h2>Popular movies to get started</h2>
      <div className="grid">{movies.map((m) => <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} />)}</div>
    </main>
  );
}

function RecsPage({ userId, region, ratings, onRate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setData(await api.recommendations(userId, region));
    setLoading(false);
  }
  useEffect(() => { load(); }, [region]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return <main><p>Finding movies for you…</p></main>;
  const w = data.weights;
  return (
    <main>
      <div className="intro">
        <p>
          Based on your {data.n_ratings} ratings · mix used: <b>{Math.round(w.cf * 100)}%</b> similar users,{" "}
          <b>{Math.round(w.content * 100)}%</b> movie content, <b>{Math.round(w.pop * 100)}%</b> popularity · showing
          availability in {REGIONS[data.region] || data.region}
        </p>
        <button onClick={load} disabled={loading}>{loading ? "Updating…" : "↻ Update with my new ratings"}</button>
      </div>
      {data.groups.map((g) => (
        <section key={g.genre}>
          <h2>{g.genre}</h2>
          <div className="row">
            {g.movies.map((m) => (
              <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} showDetails />
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}

function MyRatingsPage({ userId, ratings, onRate, onRemove }) {
  const [list, setList] = useState([]);
  useEffect(() => { api.myRatings(userId).then(setList); }, [userId]);
  return (
    <main>
      <h2>Movies you rated</h2>
      {list.length === 0 && <p className="muted">Nothing yet.</p>}
      <ul className="my-ratings">
        {list.map((m) => (
          <li key={m.movieId}>
            <span>{m.title} {m.year && `(${m.year})`}</span>
            <StarRating value={ratings[m.movieId]} onChange={(r) => onRate(m.movieId, r)} />
            <button onClick={() => { onRemove(m.movieId); setList((l) => l.filter((x) => x.movieId !== m.movieId)); }}>Remove</button>
          </li>
        ))}
      </ul>
    </main>
  );
}
