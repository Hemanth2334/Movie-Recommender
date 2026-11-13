import { useRef } from "react";

// One horizontal row of posters with < > arrows. `ranked` shows big 1-10 numbers (Top 10 row).
export default function Row({ title, movies, ratings, onOpen, ranked = false }) {
  const track = useRef(null);
  if (!movies || movies.length === 0) return null;

  const scroll = (dir) => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.85, behavior: "smooth" });

  return (
    <section className="row">
      <h2 className="row-title">{title}</h2>
      <div className="row-wrap">
        <button className="row-arrow left" onClick={() => scroll(-1)} aria-label="Scroll left">‹</button>
        <div className={`row-track ${ranked ? "ranked" : ""}`} ref={track}>
          {movies.map((m, i) => (
            <div className="tile-wrap" key={m.movieId}>
              {ranked && <span className="rank">{i + 1}</span>}
              <PosterTile movie={m} rating={ratings[m.movieId]} onOpen={onOpen} />
            </div>
          ))}
        </div>
        <button className="row-arrow right" onClick={() => scroll(1)} aria-label="Scroll right">›</button>
      </div>
    </section>
  );
}

export function PosterTile({ movie, rating, onOpen }) {
  return (
    <button className="tile" onClick={() => onOpen(movie)} title={movie.title}>
      {movie.poster ? (
        <img src={movie.poster} alt={movie.title} loading="lazy" />
      ) : (
        <div className="tile-fallback">{movie.title}</div>
      )}
      {rating ? <span className="tile-badge">★ {rating}</span> : null}
      <div className="tile-info">
        <span className="tile-title">{movie.title}</span>
        <span className="tile-sub">
          {movie.year}
          {movie.tmdb_rating ? ` · ★ ${movie.tmdb_rating.toFixed(1)}` : ""}
        </span>
      </div>
    </button>
  );
}

export function SkeletonRows({ count = 3 }) {
  return Array.from({ length: count }, (_, r) => (
    <section className="row" key={r}>
      <div className="skeleton skeleton-title" />
      <div className="row-track">
        {Array.from({ length: 7 }, (_, i) => <div className="skeleton skeleton-tile" key={i} />)}
      </div>
    </section>
  ));
}
