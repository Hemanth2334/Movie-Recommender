// 5 stars; clicking the left half of a star gives x.5, the right half gives a whole number.
export default function StarRating({ value = 0, onChange }) {
  return (
    <div className="stars" role="radiogroup" aria-label="Your rating">
      {[1, 2, 3, 4, 5].map((star) => {
        const fill = value >= star ? "full" : value >= star - 0.5 ? "half" : "empty";
        return (
          <span key={star} className={`star ${fill}`}>
            ★
            <button aria-label={`${star - 0.5} stars`} className="half-left" onClick={() => onChange(star - 0.5)} />
            <button aria-label={`${star} stars`} className="half-right" onClick={() => onChange(star)} />
          </span>
        );
      })}
      {value > 0 && <span className="star-value">{value}</span>}
    </div>
  );
}
