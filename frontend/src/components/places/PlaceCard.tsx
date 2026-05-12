import type { Place } from "../../types";
import { getPlaceCategoryLabel, getPlaceTagLabel } from "../../utils/placeLabels";
import { useLanguage } from "../../store/LanguageContext";

type PlaceCardProps = {
  place: Place;
  onSelect: (place: Place) => void;
};

export function PlaceCard({ place, onSelect }: PlaceCardProps) {
  const { language } = useLanguage();

  return (
    <article className="place-card" onClick={() => onSelect(place)}>
      <div className="place-image-frame">
        <img src={place.image_url} alt={place.name} />
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
