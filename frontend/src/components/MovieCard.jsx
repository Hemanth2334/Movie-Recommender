import StarRating from "./StarRating.jsx";

// One movie: poster, title, (optional) overview + where to watch, and stars to rate it.
export default function MovieCard({ movie, rating, onRate, showDetails = false }) {
  return (
    <div className="card">
      {movie.poster ? (
        <img src={movie.poster} alt={movie.title} loading="lazy" />
      ) : (
        <div className="no-poster">{movie.title}</div>
      )}
      <div className="card-body">
        <div className="card-title">
          {movie.title} {movie.year && <span className="year">({movie.year})</span>}
        </div>
        <StarRating value={rating || 0} onChange={(r) => onRate(movie.movieId, r)} />
        {showDetails && (
          <>
            {movie.overview && <p className="overview">{movie.overview}</p>}
            <Providers providers={movie.providers} link={movie.watch_link} />
          </>
        )}
      </div>
    </div>
  );
}

function Providers({ providers, link }) {
  if (!providers || Object.keys(providers).length === 0) {
    return <p className="muted">Not streaming in this country right now.</p>;
  }
  return (
    <div className="providers">
      {Object.entries(providers).map(([type, list]) => (
        <div key={type} className="provider-row">
          <span className={`badge badge-${type.replace(/\s+/g, "-").toLowerCase()}`}>{type}</span>
          {list.slice(0, 4).map((p) =>
            p.logo ? <img key={p.name} src={p.logo} alt={p.name} title={p.name} className="logo" /> : <span key={p.name}>{p.name}</span>
          )}
        </div>
      ))}
      {link && (
        <a href={link} target="_blank" rel="noreferrer" className="watch-link">
          All options ↗
        </a>
      )}
    </div>
  );
}
