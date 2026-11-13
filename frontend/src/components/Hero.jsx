import { useEffect, useState } from "react";

// Big banner at the top of the home page. It slides through the user's top picks
// (one per genre) every few seconds, like Netflix. Hovering pauses it.
const SLIDE_MS = 7000;
const pct = (x) => `${Math.round(x * 100)}%`;

export function runtimeText(min) {
  return min ? `${Math.floor(min / 60)}h ${min % 60}m` : null;
}

export default function Hero({ slides, weights, nRatings, onOpen }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const count = slides?.length || 0;

  useEffect(() => {
    setIndex(0);
  }, [count]);

  useEffect(() => {
    if (paused || count < 2) return undefined;
    const timer = setInterval(() => setIndex((i) => (i + 1) % count), SLIDE_MS);
    return () => clearInterval(timer);
  }, [paused, count]);

  if (!count) return <section className="hero hero-skeleton" />;
  const go = (i) => setIndex((i + count) % count);

  return (
    <section className="hero" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="hero-track" style={{ transform: `translateX(-${index * 100}%)` }}>
        {slides.map(({ movie, label }, i) => {
          const bg = movie.backdrop || movie.poster;
          return (
            <div className={`hero-slide ${i === index ? "active" : ""}`} key={movie.movieId} aria-hidden={i !== index}>
              <div className="hero-bg" style={{ backgroundImage: bg ? `url(${bg})` : "none" }} />
              <div className="hero-shade" />
              <div className="hero-content">
                <div className="hero-kicker">{label}</div>
                <h1 className="hero-title">{movie.title}</h1>
                <div className="meta">
                  {movie.year && <span>{movie.year}</span>}
                  {runtimeText(movie.runtime) && <span>{runtimeText(movie.runtime)}</span>}
                  {movie.tmdb_rating ? <span className="meta-score">★ {movie.tmdb_rating.toFixed(1)}</span> : null}
                  {movie.genres && <span>{movie.genres.split("|").slice(0, 3).join(" · ")}</span>}
                </div>
                <p className="hero-overview">{movie.overview}</p>
                <div className="hero-buttons">
                  {movie.trailer && (
                    <button className="btn btn-light" tabIndex={i === index ? 0 : -1} onClick={() => onOpen(movie, true)}>
                      ▶ Play trailer
                    </button>
                  )}
                  <button className="btn btn-glass" tabIndex={i === index ? 0 : -1} onClick={() => onOpen(movie)}>
                    ⓘ More info
                  </button>
                </div>
                {weights && (
                  <div className="hero-mix">
                    Based on your {nRatings} ratings · {pct(weights.cf)} similar users · {pct(weights.content)} movie content ·{" "}
                    {pct(weights.pop)} popularity
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {count > 1 && (
        <>
          <button className="hero-arrow left" onClick={() => go(index - 1)} aria-label="Previous pick">‹</button>
          <button className="hero-arrow right" onClick={() => go(index + 1)} aria-label="Next pick">›</button>
          <div className="hero-dots">
            {slides.map((s, i) => (
              <button
                key={s.movie.movieId}
                className={`hero-dot ${i === index ? "active" : ""}`}
                onClick={() => go(i)}
                aria-label={`Show ${s.movie.title}`}
              >
                {i === index && !paused && <span className="hero-dot-fill" style={{ animationDuration: `${SLIDE_MS}ms` }} />}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
