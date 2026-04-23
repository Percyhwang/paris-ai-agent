import type { Place } from "../../types";

type PlaceCardProps = {
  place: Place;
  onSelect: (place: Place) => void;
};

export function PlaceCard({ place, onSelect }: PlaceCardProps) {
  return (
    <article className="place-card" onClick={() => onSelect(place)}>
      <img src={place.image_url} alt={place.name} />
      <div>
        <span className="category-pill">{place.category}</span>
        <h3>{place.name}</h3>
        <p>{place.short_description}</p>
        <div className="tag-row">
          {place.tags.slice(0, 3).map((tag) => (
            <span key={tag}>#{tag}</span>
          ))}
        </div>
      </div>
    </article>
  );
}
