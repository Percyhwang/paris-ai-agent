import type { Place } from "../../types";
import { getPlaceCategoryLabel, getPlaceTagLabel } from "../../utils/placeLabels";
import { useLanguage } from "../../store/LanguageContext";

type PlaceCardProps = {
  place: Place;
  onSelect: (place: Place) => void;
};

export function PlaceCard({ place, onSelect }: PlaceCardProps) {
  const { language } = useLanguage();
  const imageUrl = place.image_url || "/images/paris-default-hero.jpeg";

  return (
    <article className="place-card" onClick={() => onSelect(place)} role="button" tabIndex={0} onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(place);
      }
    }}>
      <div className="place-image-frame">
        <img
          src={imageUrl}
          alt={place.name}
          loading="lazy"
          onError={(event) => {
            event.currentTarget.src = "/images/paris-default-hero.jpeg";
          }}
        />
      </div>
      <div className="place-card-body">
        <span className="category-pill">{getPlaceCategoryLabel(place.category, language)}</span>
        <h3>{place.name}</h3>
        <p>{place.short_description}</p>
        <div className="tag-row">
          {place.tags.slice(0, 3).map((tag) => (
            <span key={tag}>#{getPlaceTagLabel(tag, language)}</span>
          ))}
        </div>
      </div>
    </article>
  );
}
