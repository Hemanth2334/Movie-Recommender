import StarRating from "./StarRating.jsx";

// Poster + title + stars, used on the "Rate movies" and "My ratings" pages.
export default function MovieCard({ movie, rating, onRate, onOpen, onRemove }) {
  return (
    <div className={`rate-card ${rating ? "rated" : ""}`}>
      <button className="rate-poster" onClick={() => onOpen(movie)} title="More info">
        {movie.poster ? <img src={movie.poster} alt={movie.title} loading="lazy" /> : <div className="tile-fallback">{movie.title}</div>}
        {rating ? <span className="tile-badge">★ {rating}</span> : null}
      </button>
      <div className="rate-body">
        <div className="rate-title">
          {movie.title} {movie.year && <span className="muted">({movie.year})</span>}
        </div>
        <StarRating value={rating || 0} onChange={(r) => onRate(movie.movieId, r)} />
        {onRemove && <button className="link-btn" onClick={() => onRemove(movie.movieId)}>Remove</button>}
      </div>
    </div>
  );
}
