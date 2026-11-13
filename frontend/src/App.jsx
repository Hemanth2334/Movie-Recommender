import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Navbar from "./components/Navbar.jsx";
import Hero from "./components/Hero.jsx";
import Row, { SkeletonRows } from "./components/Row.jsx";
import MovieModal from "./components/MovieModal.jsx";
import MovieCard from "./components/MovieCard.jsx";
import AuthPage from "./components/AuthPage.jsx";
import ServicesPicker from "./components/ServicesPicker.jsx";

const MIN_RATINGS = 5;

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(!!getToken()); // true while we check a saved sign-in
  const [region, setRegion] = useState(localStorage.getItem("region") || "US");
  const [onlyMine, setOnlyMine] = useState(localStorage.getItem("onlyMine") === "true");
  const [view, setView] = useState(null); // "home" | "rate" | "mylist" | "mine"
  const [ratings, setRatings] = useState({}); // movieId -> rating
  const [myList, setMyList] = useState(new Set());
  const [modal, setModal] = useState(null); // { movie, trailer }
  const [servicesOpen, setServicesOpen] = useState(null); // null | "first" | "edit"
  const [dirty, setDirty] = useState(false); // ratings changed since the home rows were loaded
  const [refreshKey, setRefreshKey] = useState(0);

  // Load everything for a signed-in user
  const loadUser = useCallback(async (u) => {
    const [mine, list] = await Promise.all([api.myRatings(region), api.myList(region)]);
    setRatings(Object.fromEntries(mine.map((m) => [m.movieId, m.rating])));
    setMyList(new Set(list.map((m) => m.movieId)));
    setUser(u);
    setView(mine.length >= MIN_RATINGS ? "home" : "rate");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Signed in from an earlier visit?
  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then(loadUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, [loadUser]);

  // If the session expires, go back to the sign-in page
  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("cinematch-signed-out", out);
    return () => window.removeEventListener("cinematch-signed-out", out);
  }, []);

  useEffect(() => {
    localStorage.setItem("region", region);
  }, [region]);
  useEffect(() => {
    localStorage.setItem("onlyMine", String(onlyMine));
  }, [onlyMine]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [view]);

  async function onAuthed(u, isNew) {
    await loadUser(u);
    if (isNew) setServicesOpen("first");
  }

  async function signOut() {
    try {
      await api.logout();
    } catch {
      /* already signed out */
    }
    setToken(null);
    setUser(null);
    setRatings({});
    setMyList(new Set());
    setView(null);
  }

  async function rate(movieId, rating) {
    setRatings((r) => ({ ...r, [movieId]: rating }));
    setDirty(true);
    await api.rate(movieId, rating);
  }

  async function unrate(movieId) {
    setRatings(({ [movieId]: _, ...rest }) => rest);
    setDirty(true);
    await api.unrate(movieId);
  }

  async function toggleList(movieId) {
    const inList = myList.has(movieId);
    setMyList((s) => {
      const next = new Set(s);
      inList ? next.delete(movieId) : next.add(movieId);
      return next;
    });
    setDirty(true);
    await (inList ? api.removeFromList(movieId) : api.addToList(movieId));
  }

  const openMovie = useCallback((movie, trailer = false) => setModal({ movie, trailer }), []);
  const closeModal = useCallback(() => {
    setModal(null);
    // ratings or My List changed inside the pop-up -> reload the home rows once it closes
    setDirty((d) => {
      if (d) setRefreshKey((k) => k + 1);
      return false;
    });
  }, []);

  const goTo = (v) => {
    if (v === "home" && dirty) {
      setDirty(false);
      setRefreshKey((k) => k + 1);
    }
    setView(v);
  };

  if (checking) return <div className="splash"><span className="logo">Cine<span>Match</span></span></div>;
  if (!user) return <AuthPage onAuthed={onAuthed} />;

  const count = Object.keys(ratings).length;
  return (
    <div className="app">
      <Navbar
        view={view}
        setView={goTo}
        region={region}
        setRegion={setRegion}
        count={count}
        minRatings={MIN_RATINGS}
        user={user}
        onlyMine={onlyMine}
        setOnlyMine={setOnlyMine}
        onEditServices={() => setServicesOpen("edit")}
        onSignOut={signOut}
      />

      {view === "home" && (
        <HomePage region={region} onlyMine={onlyMine} user={user} ratings={ratings} onOpen={openMovie} refreshKey={refreshKey}
          onEditServices={() => setServicesOpen("edit")} />
      )}
      {view === "rate" && (
        <RatePage region={region} ratings={ratings} onRate={rate} onOpen={openMovie} count={count} goHome={() => goTo("home")} />
      )}
      {view === "mylist" && <MyListPage region={region} myList={myList} ratings={ratings} onOpen={openMovie} />}
      {view === "mine" && (
        <MyRatingsPage region={region} ratings={ratings} onRate={rate} onRemove={unrate} onOpen={openMovie} />
      )}

      {modal && (
        <MovieModal
          movie={modal.movie}
          startWithTrailer={modal.trailer}
          rating={ratings[modal.movie.movieId]}
          onRate={rate}
          inList={myList.has(modal.movie.movieId)}
          onToggleList={() => toggleList(modal.movie.movieId)}
          onClose={closeModal}
        />
      )}

      {servicesOpen && (
        <ServicesPicker
          initial={user.services}
          firstTime={servicesOpen === "first"}
          onCancel={() => setServicesOpen(null)}
          onDone={(updated) => {
            if (updated) {
              setUser((u) => ({ ...u, services: updated.services }));
              setRefreshKey((k) => k + 1);
            }
            setServicesOpen(null);
          }}
        />
      )}

      <footer>
        <span className="logo small">Cine<span>Match</span></span>
        <p>
          This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming availability data provided by
          JustWatch. Ratings data: MovieLens (GroupLens, University of Minnesota). CSE 575 course project.
        </p>
      </footer>
    </div>
  );
}

function HomePage({ region, onlyMine, user, ratings, onOpen, refreshKey, onEditServices }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    api.home(region, onlyMine)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [region, onlyMine, refreshKey]);

  const rows = data?.rows || [];
  // Hero slides: the top pick of each genre row (no repeats), up to 5
  const slides = [];
  rows.filter((r) => r.kind === "genre").forEach((r, i) => {
    const m = r.movies[0];
    if (m && slides.length < 5 && !slides.some((s) => s.movie.movieId === m.movieId)) {
      slides.push({ movie: m, label: i === 0 ? "Your #1 pick" : `Top ${r.title.replace(" picks for you", "")} pick for you` });
    }
  });

  return (
    <main className="home">
      {error && <p className="error page">{error}</p>}
      <Hero
        slides={data ? slides : null}
        weights={data?.weights}
        nRatings={data?.n_ratings}
        onOpen={onOpen}
      />
      <div className="rows">
        {onlyMine && (
          <div className="filter-note">
            Showing only movies on {user.services.length ? "your services" : "free services"} (and free ones) in this country.{" "}
            <button className="link-btn" onClick={onEditServices}>
              {user.services.length ? "Change services" : "Pick your services"}
            </button>
            {!data && " · Checking availability, this takes a few seconds the first time…"}
          </div>
        )}
        {!data ? (
          <SkeletonRows />
        ) : (
          rows.map((r) => (
            <Row key={r.id} title={r.title} movies={r.movies} ratings={ratings} onOpen={onOpen} ranked={r.kind === "top10"} />
          ))
        )}
        {data && rows.every((r) => r.movies.length === 0) && (
          <p className="muted page-note">Nothing matched. Try turning off “Only what I can stream” or adding services.</p>
        )}
      </div>
    </main>
  );
}

function RatePage({ region, ratings, onRate, onOpen, count, goHome }) {
  const [movies, setMovies] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);

  useEffect(() => {
    api.onboarding(region).then(setMovies);
  }, [region]);

  async function search(e) {
    e.preventDefault();
    if (query.trim()) setResults(await api.search(query.trim(), region));
  }

  const progress = Math.min(count / MIN_RATINGS, 1);
  return (
    <main className="page">
      <section className="rate-header">
        <div>
          <h1>Rate movies you've seen</h1>
          <p className="muted">
            {count < MIN_RATINGS
              ? `Rate ${MIN_RATINGS - count} more to unlock your CineMatch home.`
              : "Nice. The more you rate, the more CineMatch learns from people with similar taste."}
          </p>
          <div className="progress"><div style={{ width: `${progress * 100}%` }} /></div>
        </div>
        <button className="btn btn-accent" disabled={count < MIN_RATINGS} onClick={goHome}>
          See my recommendations →
        </button>
      </section>

      <form onSubmit={search} className="search">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search for a movie you've seen…" />
        <button type="submit" className="btn btn-glass">Search</button>
      </form>

      {results && (
        <>
          <h2 className="section-title">Search results</h2>
          {results.length === 0 && <p className="muted">No movies found.</p>}
          <div className="grid">
            {results.map((m) => (
              <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} onOpen={onOpen} />
            ))}
          </div>
        </>
      )}

      <h2 className="section-title">Popular movies to get started</h2>
      <div className="grid">
        {movies.map((m) => (
          <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} onOpen={onOpen} />
        ))}
      </div>
    </main>
  );
}

function MyListPage({ region, myList, ratings, onOpen }) {
  const [list, setList] = useState(null);
  useEffect(() => {
    api.myList(region).then(setList);
  }, [region, myList]);

  return (
    <main className="page">
      <h1>My List</h1>
      <p className="muted">Movies you saved for later. Open one and press “+ My List” again to remove it.</p>
      {list && list.length === 0 && <p className="muted">Your list is empty. Open any movie and press “+ My List”.</p>}
      <div className="grid">
        {(list || []).map((m) => (
          <button key={m.movieId} className="rate-poster" onClick={() => onOpen(m)} title={m.title}>
            {m.poster ? <img src={m.poster} alt={m.title} loading="lazy" /> : <div className="tile-fallback">{m.title}</div>}
            {ratings[m.movieId] ? <span className="tile-badge">★ {ratings[m.movieId]}</span> : null}
          </button>
        ))}
      </div>
    </main>
  );
}

function MyRatingsPage({ region, ratings, onRate, onRemove, onOpen }) {
  const [list, setList] = useState(null);
  useEffect(() => {
    api.myRatings(region).then(setList);
  }, [region]);

  const remove = (id) => {
    onRemove(id);
    setList((l) => l.filter((x) => x.movieId !== id));
  };

  return (
    <main className="page">
      <h1>My ratings</h1>
      <p className="muted">Change a rating or remove it. Your recommendations update when you go back to Home.</p>
      {list && list.length === 0 && <p className="muted">Nothing yet.</p>}
      <div className="grid">
        {(list || []).map((m) => (
          <MovieCard key={m.movieId} movie={m} rating={ratings[m.movieId]} onRate={onRate} onOpen={onOpen} onRemove={remove} />
        ))}
      </div>
    </main>
  );
}
