import type { Language } from "../i18n/config";

const CATEGORY_LABELS: Record<Language, Record<string, string>> = {
  ko: {
    all: "전체",
    landmark: "랜드마크",
    museum: "박물관",
    cathedral: "성당",
    park: "공원",
    neighborhood: "동네",
  },
  en: {
    all: "All",
    landmark: "Landmark",
    museum: "Museum",
    cathedral: "Cathedral",
    park: "Park",
    neighborhood: "Neighborhood",
  },
};

const TAG_LABELS: Record<Language, Record<string, string>> = {
  ko: {
    landmark: "랜드마크",
    museum: "박물관",
    cathedral: "성당",
    park: "공원",
    neighborhood: "동네",
    tourist_attraction: "관광 명소",
    art_gallery: "미술관",
    art_museum: "미술관",
    church: "성당",
    historical_landmark: "역사 명소",
    cultural_landmark: "문화 명소",
    monument: "기념물",
    point_of_interest: "관심 장소",
    establishment: "방문 장소",
    garden: "정원",
    botanical_garden: "식물원",
    place_of_worship: "종교 명소",
    paris: "파리",
  },
  en: {
    landmark: "Landmark",
    museum: "Museum",
    cathedral: "Cathedral",
    park: "Park",
    neighborhood: "Neighborhood",
    tourist_attraction: "Tourist Attraction",
    art_gallery: "Art Gallery",
    art_museum: "Art Museum",
    church: "Church",
    historical_landmark: "Historical Landmark",
    cultural_landmark: "Cultural Landmark",
    monument: "Monument",
    point_of_interest: "Point of Interest",
    establishment: "Establishment",
    garden: "Garden",
    botanical_garden: "Botanical Garden",
    place_of_worship: "Place of Worship",
    paris: "Paris",
  },
};

function toDisplayCase(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function getPlaceCategoryLabel(category: string, language: Language) {
  return CATEGORY_LABELS[language][category] ?? category;
}

export function getPlaceTagLabel(tag: string, language: Language) {
  const normalized = tag.trim().toLowerCase().replace(/[-\s]+/g, "_");
  return TAG_LABELS[language][normalized] ?? toDisplayCase(tag);
}
