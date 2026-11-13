import { useEffect, useState } from "react";
import StarRating from "./StarRating.jsx";
import { runtimeText } from "./Hero.jsx";

// Details pop-up: backdrop or trailer, description, your rating, and clickable streaming services.
export default function MovieModal({ movie, startWithTrailer, rating, onRate, inList, onToggleList, onClose }) {
  const [playing, setPlaying] = useState(!!startWithTrailer);

  useEffect(() => {
    setPlaying(!!startWithTrailer);
  }, [movie, startWithTrailer]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden"; // stop the page behind from scrolling
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  if (!movie) return null;
  const bg = movie.backdrop || movie.poster;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={movie.title}>
        <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>

        <div className="modal-media">
          {playing && movie.trailer ? (
            <iframe
              src={`https://www.youtube.com/embed/${movie.trailer}?autoplay=1&rel=0`}
              title={`${movie.title} trailer`}
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <div className="modal-backdrop" style={{ backgroundImage: bg ? `url(${bg})` : "none" }}>
              <div className="modal-shade" />
              <div className="modal-head">
                <h2>{movie.title}</h2>
                {movie.trailer && (
                  <button className="btn btn-light" onClick={() => setPlaying(true)}>▶ Play trailer</button>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="modal-body">
          <div className="modal-main">
            {playing && <h2 className="modal-title-below">{movie.title}</h2>}
            <div className="meta">
              {movie.year && <span>{movie.year}</span>}
              {runtimeText(movie.runtime) && <span>{runtimeText(movie.runtime)}</span>}
              {movie.tmdb_rating ? <span className="meta-score">★ {movie.tmdb_rating.toFixed(1)} on TMDB</span> : null}
            </div>
            {movie.genres && (
              <div className="chips">
                {movie.genres.split("|").filter(Boolean).map((g) => <span className="chip" key={g}>{g}</span>)}
              </div>
            )}
            <div className="modal-actions">
              <button className={`btn ${inList ? "btn-glass" : "btn-light"} btn-small`} onClick={onToggleList}>
                {inList ? "✓ In My List" : "+ My List"}
              </button>
              {movie.because && <span className="because">Because you liked <b>{movie.because}</b></span>}
            </div>
            {movie.tagline && <p className="tagline">{movie.tagline}</p>}
            <p className="overview-full">{movie.overview || "No description available."}</p>
            <div className="modal-rate">
              <span>{rating ? "Your rating" : "Seen it? Rate it"}</span>
              <StarRating value={rating || 0} onChange={(r) => onRate(movie.movieId, r)} />
            </div>
          </div>

          <aside className="modal-side">
            <h3>Where to watch</h3>
            <Providers providers={movie.providers} link={movie.watch_link} />
          </aside>
        </div>
      </div>
    </div>
  );
}

function Providers({ providers, link }) {
  const groups = Object.entries(providers || {});
  if (groups.length === 0) return <p className="muted">Not available to stream in this country right now.</p>;
  return (
    <div className="providers">
      {groups.map(([type, list]) => (
        <div key={type} className="provider-group">
          <span className={`badge badge-${type.replace(/\s+/g, "-").toLowerCase()}`}>{type}</span>
          <div className="provider-list">
            {list.map((p) => (
              <a key={p.name} className="provider" href={p.link} target="_blank" rel="noreferrer" title={`Open ${p.name}`}>
                {p.logo ? <img src={p.logo} alt="" /> : <span className="provider-dot" />}
                <span>{p.name}</span>
                <span className="provider-arrow">↗</span>
              </a>
            ))}
          </div>
        </div>
      ))}
      {link && (
        <a href={link} target="_blank" rel="noreferrer" className="watch-link">All options on TMDB ↗</a>
      )}
      <p className="attribution">Availability data from JustWatch via TMDB.</p>
    </div>
  );
}
