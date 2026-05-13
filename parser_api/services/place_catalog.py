from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

FEATURED_PLACES: list[dict[str, Any]] = [
    {
        "slug": "eiffel-tower",
        "name": "에펠탑",
        "category": "landmark",
        "coordinates": {"lat": 48.8584, "lng": 2.2945},
        "image_url": "/images/paris-sunset-hero.png",
        "short_description": "파리 여행의 상징이자 야경이 가장 아름다운 랜드마크",
        "full_description": "센 강변에 우뚝 선 에펠탑은 파리를 처음 방문하는 여행자에게 가장 강렬한 첫 장면을 선물합니다.",
        "history": "1889년 만국박람회를 위해 귀스타브 에펠의 회사가 건설했으며, 오늘날 파리를 대표하는 상징이 되었습니다.",
        "photo_spot_tips": ["트로카데로 광장", "샹 드 마르스 잔디밭", "해 질 무렵 센 강변"],
        "estimated_visit_duration": "2-3시간",
        "admission_fee": "전망대 티켓 약 18-29 EUR",
        "location": "Champ de Mars, 75007 Paris",
        "tags": ["landmark", "night_view", "classic"],
        "popularity": 100,
    },
    {
        "slug": "louvre-museum",
        "name": "루브르 박물관",
        "category": "museum",
        "coordinates": {"lat": 48.8606, "lng": 2.3376},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "모나리자와 유리 피라미드로 유명한 세계적인 미술관",
        "full_description": "고전 회화와 조각, 고대 문명 컬렉션이 방대해 취향에 맞춘 동선 설계가 특히 중요합니다.",
        "history": "왕궁으로 시작해 프랑스 혁명 이후 공공 박물관으로 개관했습니다.",
        "photo_spot_tips": ["유리 피라미드 정면", "리슐리외 관 회랑", "야간 개장일 조명"],
        "estimated_visit_duration": "3-5시간",
        "admission_fee": "온라인 티켓 약 22 EUR",
        "location": "Rue de Rivoli, 75001 Paris",
        "tags": ["museum", "art", "history"],
        "popularity": 98,
    },
    {
        "slug": "musee-dorsay",
        "name": "오르세 미술관",
        "category": "museum",
        "coordinates": {"lat": 48.86, "lng": 2.3266},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "인상주의 작품과 거대한 시계창이 아름다운 미술관",
        "full_description": "기차역을 개조한 공간 자체가 매력적이며 모네, 르누아르, 고흐 작품을 만날 수 있습니다.",
        "history": "1900년 파리 만국박람회용 기차역이었고 1986년 미술관으로 재개관했습니다.",
        "photo_spot_tips": ["5층 시계창", "중앙 홀 전경", "세느 강변 외관"],
        "estimated_visit_duration": "2-3시간",
        "admission_fee": "일반 티켓 약 16 EUR",
        "location": "1 Rue de la Légion d'Honneur, 75007 Paris",
        "tags": ["museum", "art", "impressionism"],
        "popularity": 89,
    },
    {
        "slug": "notre-dame",
        "name": "노트르담 대성당",
        "category": "cathedral",
        "coordinates": {"lat": 48.853, "lng": 2.3499},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "시테섬의 중심에서 만나는 고딕 건축의 정수",
        "full_description": "섬 주변 산책과 함께 즐기기 좋고 세느 강변의 분위기를 느끼기에 좋은 장소입니다.",
        "history": "12세기부터 건축된 대표적인 고딕 성당으로 프랑스 역사와 문학에 깊이 남아 있습니다.",
        "photo_spot_tips": ["시테섬 다리 위 전경", "강 건너편 서점가", "석양 시간대 측면"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "외부 관람 무료",
        "location": "Île de la Cité, 75004 Paris",
        "tags": ["cathedral", "history", "architecture"],
        "popularity": 94,
    },
    {
        "slug": "montmartre",
        "name": "몽마르트르",
        "category": "neighborhood",
        "coordinates": {"lat": 48.8867, "lng": 2.3431},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "예술가의 언덕과 사크레쾨르가 있는 감성 산책 코스",
        "full_description": "골목, 계단, 작은 카페가 이어지는 동네로 여유로운 오후 일정에 잘 어울립니다.",
        "history": "19-20세기 예술가들이 모여 살던 지역으로 피카소와 모딜리아니의 흔적이 남아 있습니다.",
        "photo_spot_tips": ["사크레쾨르 앞 전경", "라 메종 로즈 골목", "해 질 무렵 언덕 계단"],
        "estimated_visit_duration": "2-4시간",
        "admission_fee": "대부분 무료",
        "location": "Montmartre, 75018 Paris",
        "tags": ["neighborhood", "romantic", "walk", "cafe"],
        "popularity": 91,
    },
    {
        "slug": "luxembourg-gardens",
        "name": "뤽상부르 공원",
        "category": "park",
        "coordinates": {"lat": 48.8462, "lng": 2.3372},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "여유로운 산책과 휴식에 좋은 파리식 정원",
        "full_description": "일정 사이에 쉬어가기 좋고 의자에 앉아 파리의 일상을 바라보는 시간이 매력적입니다.",
        "history": "17세기 마리 드 메디시스를 위해 조성된 정원으로 현재는 시민과 여행자 모두에게 사랑받습니다.",
        "photo_spot_tips": ["분수 주변 초록 의자", "궁전 정면", "오전 햇살의 산책로"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "무료",
        "location": "75006 Paris",
        "tags": ["park", "relax", "family", "walk"],
        "popularity": 84,
    },
    {
        "slug": "arc-de-triomphe",
        "name": "개선문",
        "category": "landmark",
        "coordinates": {"lat": 48.8738, "lng": 2.295},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "샹젤리제의 시작을 알리는 대표 랜드마크",
        "full_description": "에펠탑과 함께 묶기 좋은 클래식 동선이며 저녁 무렵 전망이 인상적입니다.",
        "history": "나폴레옹이 전승을 기념해 건설을 시작한 기념문입니다.",
        "photo_spot_tips": ["샹젤리제 방향 축선", "전망대 파노라마", "야경 타임"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "전망대 티켓 약 16 EUR",
        "location": "Place Charles de Gaulle, 75008 Paris",
        "tags": ["landmark", "classic", "night_view"],
        "popularity": 88,
    },
    {
        "slug": "champs-elysees",
        "name": "샹젤리제 거리",
        "category": "neighborhood",
        "coordinates": {"lat": 48.8698, "lng": 2.3078},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "쇼핑과 야간 산책이 모두 잘 어울리는 중심 거리",
        "full_description": "개선문과 콩코르드 사이를 잇는 대표 거리로 쇼핑과 야경, 대로의 분위기를 즐기기 좋습니다.",
        "history": "17세기 조경 계획으로 시작해 오늘날 파리의 대표적인 대로가 되었습니다.",
        "photo_spot_tips": ["대로 중앙 축선", "해 질 무렵 가로수", "거리 조명"],
        "estimated_visit_duration": "2-3시간",
        "admission_fee": "무료",
        "location": "Avenue des Champs-Élysées, 75008 Paris",
        "tags": ["shopping", "night_view", "walk"],
        "popularity": 86,
    },
    {
        "slug": "sainte-chapelle",
        "name": "생트샤펠",
        "category": "cathedral",
        "coordinates": {"lat": 48.8554, "lng": 2.345},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "스테인드글라스가 압도적인 성당",
        "full_description": "노트르담과 함께 묶기 좋고 실내 중심으로도 만족도가 높은 명소입니다.",
        "history": "13세기 루이 9세가 성유물을 보관하기 위해 세운 왕실 예배당입니다.",
        "photo_spot_tips": ["상층부 스테인드글라스", "오전 햇살 시간", "기둥과 창의 반복 패턴"],
        "estimated_visit_duration": "1시간",
        "admission_fee": "티켓 약 13 EUR",
        "location": "10 Bd du Palais, 75001 Paris",
        "tags": ["history", "architecture", "indoor"],
        "popularity": 82,
    },
    {
        "slug": "marais",
        "name": "마레 지구",
        "category": "neighborhood",
        "coordinates": {"lat": 48.8578, "lng": 2.3622},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "부티크, 갤러리, 카페가 모인 감각적인 동네",
        "full_description": "로컬 감성과 쇼핑, 카페 탐방을 함께 즐기기 좋은 대표적인 파리 동네입니다.",
        "history": "귀족 저택과 유대인 지구의 흔적이 공존하는 역사 깊은 동네입니다.",
        "photo_spot_tips": ["보쥬 광장", "골목 상점가", "노천 카페 테라스"],
        "estimated_visit_duration": "2-4시간",
        "admission_fee": "무료",
        "location": "Le Marais, 75003/75004 Paris",
        "tags": ["shopping", "cafe", "local", "walk"],
        "popularity": 87,
    },
    {
        "slug": "tuileries-garden",
        "name": "튈르리 정원",
        "category": "park",
        "coordinates": {"lat": 48.8635, "lng": 2.3273},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "루브르와 콩코르드를 잇는 클래식 산책 동선",
        "full_description": "루브르와 오르세 사이를 연결하기 좋고, 박물관 일정 사이 숨을 고르기 좋은 정원입니다.",
        "history": "왕실 궁정 정원으로 출발해 오늘날 시민과 여행자의 산책로가 되었습니다.",
        "photo_spot_tips": ["조각과 분수", "정원 중앙 산책로", "노을빛 정원 전경"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "무료",
        "location": "Jardin des Tuileries, 75001 Paris",
        "tags": ["park", "walk", "classic"],
        "popularity": 80,
    },
    {
        "slug": "palais-garnier",
        "name": "오페라 가르니에",
        "category": "landmark",
        "coordinates": {"lat": 48.8719, "lng": 2.3316},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "화려한 내부와 파리 중심의 우아한 분위기를 느낄 수 있는 공간",
        "full_description": "오페라 지구의 쇼핑과 카페, 백화점을 함께 묶기 좋은 코스입니다.",
        "history": "나폴레옹 3세 시기 완공된 대표적인 보자르 양식의 오페라 극장입니다.",
        "photo_spot_tips": ["대계단", "샹들리에 천장", "오스만 거리 방향 외관"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "셀프 가이드 약 15 EUR",
        "location": "Pl. de l'Opéra, 75009 Paris",
        "tags": ["culture", "shopping", "architecture"],
        "popularity": 83,
    },
    {
        "slug": "seine-river-walk",
        "name": "센강 산책",
        "category": "landmark",
        "coordinates": {"lat": 48.8588, "lng": 2.347},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "파리의 분위기를 가장 자연스럽게 느낄 수 있는 강변 동선",
        "full_description": "노트르담, 루브르, 에펠탑 어느 쪽과도 연결하기 좋고 야경 만족도가 높습니다.",
        "history": "세느 강은 파리의 생활과 역사, 상업의 중심축으로 오랫동안 도시의 정체성을 형성해왔습니다.",
        "photo_spot_tips": ["강변 계단석", "다리 위 전경", "야간 조명 반영"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "무료",
        "location": "Seine river banks, Paris",
        "tags": ["walk", "night_view", "romantic"],
        "popularity": 90,
    },
]

DATA_ASSETS_PATH = Path(__file__).resolve().parents[2] / "data_assets"
OSM_PLACES_PATH = DATA_ASSETS_PATH / "paris_places_clean.json"
OSM_RAW_PATH = DATA_ASSETS_PATH / "paris_osm.geojson"

PARIS_LAT_MIN = 48.80
PARIS_LAT_MAX = 48.90
PARIS_LNG_MIN = 2.20
PARIS_LNG_MAX = 2.47

CUISINE_FALLBACKS: dict[str, set[str]] = {
    "pasta": {"pasta", "italian"},
    "pizza": {"pizza", "italian"},
    "italian": {"italian", "pasta", "pizza"},
    "french": {"french", "bistro", "brasserie", "regional"},
    "sushi": {"sushi", "japanese"},
    "ramen": {"ramen", "japanese"},
    "japanese": {"japanese", "sushi", "ramen"},
    "vietnamese": {"vietnamese", "pho", "banh_mi"},
    "mexican": {"mexican", "taco"},
    "mediterranean": {"mediterranean"},
    "lebanese": {"lebanese"},
    "moroccan": {"moroccan"},
    "steak": {"steak", "steakhouse"},
    "seafood": {"seafood", "fish"},
    "vegetarian": {"vegetarian", "vegan"},
    "brunch": {"brunch", "breakfast"},
    "bakery": {"bakery", "croissant"},
    "coffee": {"coffee", "coffee_shop", "coffeeshop"},
    "dessert": {"dessert", "cake", "ice_cream", "waffles"},
}

ADMISSION_FEE_BY_SLUG: dict[str, float] = {
    "eiffel-tower": 36.7,
    "louvre-museum": 32,
    "musee-dorsay": 16,
    "arc-de-triomphe": 22,
    "sainte-chapelle": 22,
    "palais-garnier": 25,
}

ADMISSION_FEE_LABEL_BY_SLUG: dict[str, str] = {
    "eiffel-tower": "Top lift ticket: 36.70 EUR adult",
    "louvre-museum": "General admission: 32 EUR non-EEA adult / 22 EUR EEA adult",
    "musee-dorsay": "Online general admission: 16 EUR adult",
    "arc-de-triomphe": "Individual ticket: 22 EUR Apr-Sep, 16 EUR Wed or Oct-Mar",
    "sainte-chapelle": "Individual ticket: 22 EUR non-EEA adult / 16 EUR EEA adult",
    "palais-garnier": "Self-guided tour: 25 EUR full price",
}

THEME_CATEGORY_WEIGHTS = {
    "museum": {"museum": 4.0, "landmark": 1.5},
    "art": {"museum": 4.0},
    "history": {"museum": 2.5, "cathedral": 3.0, "landmark": 2.0},
    "culture": {"landmark": 2.5, "museum": 2.0, "cathedral": 2.0},
    "cafe": {"cafe": 4.0, "neighborhood": 2.0},
    "foodie": {"cafe": 3.0, "neighborhood": 1.5},
    "night_view": {"landmark": 3.5, "neighborhood": 2.0},
    "shopping": {"neighborhood": 3.5, "cafe": 1.5},
    "nature": {"park": 4.0, "landmark": 1.0},
    "landmark": {"landmark": 4.0},
    "local": {"neighborhood": 3.0, "cafe": 2.0},
    "romantic": {"neighborhood": 2.5, "landmark": 2.0, "cafe": 1.5},
}

RAW_ALIASES = {
    "에펠탑": "eiffel-tower",
    "에펠타워": "eiffel-tower",
    "루브르": "louvre-museum",
    "루브르박물관": "louvre-museum",
    "오르세": "musee-dorsay",
    "오르세미술관": "musee-dorsay",
    "노트르담": "notre-dame",
    "몽마르트": "montmartre",
    "몽마르트르": "montmartre",
    "개선문": "arc-de-triomphe",
    "샹젤리제": "champs-elysees",
    "생트샤펠": "sainte-chapelle",
    "마레": "marais",
    "튈르리": "tuileries-garden",
    "오페라": "palais-garnier",
    "센강": "seine-river-walk",
    "뤽상부르": "luxembourg-gardens",
    "luxembourg": "luxembourg-gardens",
    "louvre": "louvre-museum",
    "orsay": "musee-dorsay",
    "eiffel": "eiffel-tower",
    "eiffeltower": "eiffel-tower",
    "eiffel_tower": "eiffel-tower",
    "neareiffeltower": "eiffel-tower",
    "louvremuseum": "louvre-museum",
    "museedorsay": "musee-dorsay",
    "arcdetriomphe": "arc-de-triomphe",
    "champselysees": "champs-elysees",
    "saintchapelle": "sainte-chapelle",
    "notredame": "notre-dame",
    "marais": "marais",
}


def normalize_text(text: str) -> str:
    pieces: list[str] = []
    for char in text.lower():
        if re.match(r"[a-z0-9가-힣]", char):
            pieces.append(char)
            continue
        normalized = unicodedata.normalize("NFKD", char)
        normalized = "".join(item for item in normalized if not unicodedata.combining(item))
        cleaned = re.sub(r"[^a-z0-9가-힣]+", "", normalized)
        if cleaned:
            pieces.append(cleaned)
    return "".join(pieces)


def _name_key(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    return normalize_text(raw) or raw


def _coordinate_key(place: dict[str, Any]) -> str:
    coordinates = place.get("coordinates") or {}
    try:
        lat = float(coordinates.get("lat"))
        lng = float(coordinates.get("lng"))
    except (TypeError, ValueError):
        return ""
    return f"{lat:.4f},{lng:.4f}"


def _place_slug(place: dict[str, Any]) -> str:
    return str(place.get("slug") or place.get("place_id") or "")


def _is_place_used(
    place: dict[str, Any],
    *,
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
) -> bool:
    slug = _place_slug(place)
    name = _name_key(place.get("name"))
    coordinates = _coordinate_key(place)
    return bool(
        (slug and slug in used_slugs)
        or (name and name in used_names)
        or (coordinates and coordinates in used_coordinates)
    )


def _mark_place_used(
    place: dict[str, Any],
    *,
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
) -> None:
    slug = _place_slug(place)
    name = _name_key(place.get("name"))
    coordinates = _coordinate_key(place)
    if slug:
        used_slugs.add(slug)
    if name:
        used_names.add(name)
    if coordinates:
        used_coordinates.add(coordinates)


ALIASES = {normalize_text(key): value for key, value in RAW_ALIASES.items()}


def _admission_fee_amount(place: dict[str, Any]) -> float | None:
    amount = place.get("admission_fee_amount")
    if amount is not None:
        return float(amount)
    slug = str(place.get("slug") or "")
    if slug in ADMISSION_FEE_BY_SLUG:
        return ADMISSION_FEE_BY_SLUG[slug]
    return None


def _admission_fee_label(place: dict[str, Any]) -> str | None:
    slug = str(place.get("slug") or "")
    return ADMISSION_FEE_LABEL_BY_SLUG.get(slug) or place.get("admission_fee")


def _split_cuisine_terms(value: Any) -> list[str]:
    raw = str(value or "").lower().replace("_", ";")
    terms = [term.strip() for term in re.split(r"[;,\s/]+", raw) if term.strip()]
    return list(dict.fromkeys(terms))


def _in_paris_bounds(lat: float, lng: float) -> bool:
    return PARIS_LAT_MIN <= lat <= PARIS_LAT_MAX and PARIS_LNG_MIN <= lng <= PARIS_LNG_MAX


def _meal_popularity(props: dict[str, Any], cuisine_terms: list[str], category: str) -> int:
    score = 42 if category == "restaurant" else 35
    if cuisine_terms:
        score += 4
    if props.get("website") or props.get("contact:website"):
        score += 2
    if props.get("contact:tripadvisor") or props.get("michelin"):
        score += 4
    return min(score, 65)


def _load_osm_food_places(
    *,
    existing_names: set[str],
    start_index: int,
) -> list[dict[str, Any]]:
    if not OSM_RAW_PATH.exists():
        return []

    try:
        raw = json.loads(OSM_RAW_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    places: list[dict[str, Any]] = []
    for offset, feature in enumerate(raw.get("features") or []):
        props = feature.get("properties") or {}
        amenity = str(props.get("amenity") or "").lower()
        if amenity not in {"restaurant", "cafe"}:
            continue

        name = str(props.get("name") or "").strip()
        if len(name) < 4:
            continue

        coordinates = (feature.get("geometry") or {}).get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        lng = float(coordinates[0])
        lat = float(coordinates[1])
        if not _in_paris_bounds(lat, lng):
            continue

        normalized_name = normalize_text(name)
        if normalized_name in existing_names:
            continue
        existing_names.add(normalized_name)

        category = "restaurant" if amenity == "restaurant" else "cafe"
        cuisine_terms = _split_cuisine_terms(props.get("cuisine") or props.get("cuisine:fr"))
        tags = [category, "paris", "foodie", *cuisine_terms]
        if category == "cafe":
            tags.append("cafe")
        place_index = start_index + offset
        cuisine_label = ", ".join(cuisine_terms[:3]) if cuisine_terms else category
        places.append(
            {
                "slug": f"osm-{normalize_text(name)}-{place_index}",
                "name": name,
                "category": category,
                "coordinates": {"lat": lat, "lng": lng},
                "image_url": "/images/paris-default-hero.jpeg",
                "short_description": f"Paris {cuisine_label} spot selected from OSM data near the route.",
                "full_description": f"{name} is a Paris {cuisine_label} place that can be matched to food-specific itinerary edits.",
                "history": "",
                "photo_spot_tips": [name, "Nearby streets", "Meal stop"],
                "estimated_visit_duration": "1 hour",
                "admission_fee": None,
                "location": str(props.get("addr:street") or props.get("addr:full") or "Paris"),
                "tags": list(dict.fromkeys(tags)),
                "cuisine": cuisine_terms,
                "popularity": _meal_popularity(props, cuisine_terms, category),
                "source": "osm",
            }
        )
    return places


def _load_osm_places() -> list[dict[str, Any]]:
    items = json.loads(OSM_PLACES_PATH.read_text(encoding="utf-8"))
    places: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        coordinates = item.get("location", {}).get("coordinates", [2.3522, 48.8566])
        lng = float(coordinates[0])
        lat = float(coordinates[1])
        raw_category = str(item.get("category") or "landmark").lower()
        category = raw_category if raw_category in {"museum", "landmark", "park", "cafe"} else "landmark"
        name = str(item.get("name") or f"Paris Place {index + 1}")
        slug = f"osm-{normalize_text(name)}-{index}"
        tags = [category, "paris"]
        if category == "cafe":
            tags.extend(["cafe", "foodie"])
        if category == "museum":
            tags.extend(["museum", "art"])
        if category == "park":
            tags.extend(["park", "nature", "walk"])
        if category == "landmark":
            tags.extend(["landmark", "walk"])
        places.append(
            {
                "slug": slug,
                "name": name,
                "category": category,
                "coordinates": {"lat": lat, "lng": lng},
                "image_url": "/images/paris-default-hero.jpeg",
                "short_description": f"{name} 주변 분위기를 가볍게 즐기기 좋은 파리 스팟",
                "full_description": f"{name}은 현재 데이터셋에서 탐색 가능한 파리 장소입니다.",
                "history": "",
                "photo_spot_tips": [f"{name} 정면", "근처 골목", "짧은 휴식 코스"],
                "estimated_visit_duration": "45-90분" if category == "cafe" else "1-2시간",
                "admission_fee": None,
                "location": "Paris",
                "tags": list(dict.fromkeys(tags)),
                "popularity": 35 if category == "cafe" else 30,
                "source": "osm",
            }
        )
    existing_names = {normalize_text(str(place.get("name") or "")) for place in places}
    return places + _load_osm_food_places(existing_names=existing_names, start_index=len(places))


FEATURED_BY_SLUG = {place["slug"]: place for place in FEATURED_PLACES}
CATALOG = FEATURED_PLACES + _load_osm_places()
CATALOG_BY_SLUG = {place["slug"]: place for place in CATALOG}


def export_place(place: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": place["slug"],
        "slug": place["slug"],
        "name": place["name"],
        "category": place["category"],
        "coordinates": dict(place["coordinates"]),
        "image_url": place["image_url"],
        "short_description": place["short_description"],
        "full_description": place["full_description"],
        "history": place["history"],
        "photo_spot_tips": list(place["photo_spot_tips"]),
        "estimated_visit_duration": place["estimated_visit_duration"],
        "admission_fee": _admission_fee_label(place),
        "location": place["location"],
        "tags": list(place["tags"]),
        "cuisine": place.get("cuisine"),
        "admission_fee_amount": _admission_fee_amount(place),
        "popularity": place["popularity"],
        "rating": place.get("rating"),
        "source": place.get("source", "featured"),
    }


def _area_label(place: dict[str, Any]) -> str:
    lat = place["coordinates"]["lat"]
    lng = place["coordinates"]["lng"]
    if lat > 48.881:
        return "몽마르트 언덕"
    if lng < 2.305:
        return "에펠탑-샹젤리제 권역"
    if 2.326 <= lng <= 2.34 and lat >= 48.858:
        return "루브르-오르세 권역"
    if 2.343 <= lng <= 2.352 and lat <= 48.856:
        return "시테섬-라탱 지구"
    if lng >= 2.355:
        return "마레 지구"
    if lat < 48.85:
        return "뤽상부르 남측 권역"
    return "파리 중심부"


def _distance_km(a: dict[str, float], b: dict[str, float]) -> float:
    lat1 = math.radians(a["lat"])
    lng1 = math.radians(a["lng"])
    lat2 = math.radians(b["lat"])
    lng2 = math.radians(b["lng"])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def _score_place(
    place: dict[str, Any],
    *,
    categories: dict[str, float],
    themes: list[str],
    anchor: dict[str, Any] | None = None,
    allow_category_fallback: bool = True,
) -> float:
    score = float(place.get("popularity", 0)) / 10.0
    score += categories.get(place["category"], 0.0)
    if allow_category_fallback and not categories:
        score += 1.5 if place["category"] in {"landmark", "museum", "neighborhood"} else 0.5
    normalized_tags = {normalize_text(tag) for tag in place.get("tags", [])}
    for theme in themes:
        if normalize_text(theme) in normalized_tags:
            score += 2.5
    if place["slug"] in FEATURED_BY_SLUG:
        score += 4.0
    if anchor is not None:
        distance = _distance_km(place["coordinates"], anchor["coordinates"])
        score += max(0.0, 4.0 - distance)
    return score


def _build_category_weights(venue_type: str, themes: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for theme in themes:
        for category, value in THEME_CATEGORY_WEIGHTS.get(theme, {}).items():
            weights[category] = weights.get(category, 0.0) + value
    normalized_type = "cafe" if venue_type == "restaurant" else venue_type
    if normalized_type == "mixed":
        for category in ("landmark", "museum", "neighborhood", "cafe"):
            weights[category] = weights.get(category, 0.0) + 1.2
    elif normalized_type:
        weights[normalized_type] = weights.get(normalized_type, 0.0) + 3.0
    return weights


def resolve_place(query: str | None) -> dict[str, Any] | None:
    if not query:
        return None
    normalized = normalize_text(query)
    alias_slug = ALIASES.get(normalized)
    if alias_slug and alias_slug in CATALOG_BY_SLUG:
        return export_place(CATALOG_BY_SLUG[alias_slug])

    direct = next(
        (
            place
            for place in CATALOG
            if normalize_text(place["name"]) == normalized
            or normalize_text(place["slug"]) == normalized
        ),
        None,
    )
    if direct is not None:
        return export_place(direct)

    partial = next(
        (
            place
            for place in CATALOG
            if normalized and normalized in normalize_text(place["name"])
        ),
        None,
    )
    return export_place(partial) if partial is not None else None


def search_places(
    *,
    search: str = "",
    category: str = "",
    sort: str = "",
    limit: int = 60,
) -> list[dict[str, Any]]:
    normalized_search = normalize_text(search)
    normalized_category = category.strip().lower()
    items = CATALOG

    if normalized_search:
        items = [
            place
            for place in items
            if normalized_search in normalize_text(place["name"])
            or normalized_search in normalize_text(place["slug"])
            or any(normalized_search in normalize_text(tag) for tag in place.get("tags", []))
        ]
    if normalized_category and normalized_category != "all":
        items = [place for place in items if place["category"] == normalized_category]
    if sort == "popular":
        items = sorted(items, key=lambda place: place.get("popularity", 0), reverse=True)
    return [export_place(place) for place in items[:limit]]


def recommend_places(
    *,
    venue_type: str,
    themes: list[str],
    count: int,
    must_include: list[str] | None = None,
    must_avoid: list[str] | None = None,
    anchor_name: str | None = None,
) -> list[dict[str, Any]]:
    resolved_anchor = resolve_place(anchor_name)
    categories = _build_category_weights(venue_type, themes)
    banned = {normalize_text(name) for name in (must_avoid or [])}
    picks: list[tuple[float, dict[str, Any]]] = []

    for place in CATALOG:
        normalized_name = normalize_text(place["name"])
        if normalized_name in banned:
            continue
        if venue_type == "attraction" and place["category"] == "cafe":
            continue
        if venue_type == "cafe" and place["category"] not in {"cafe", "neighborhood"}:
            continue
        if venue_type == "restaurant" and place["category"] not in {"restaurant", "cafe", "neighborhood"}:
            continue
        score = _score_place(place, categories=categories, themes=themes, anchor=resolved_anchor)
        picks.append((score, place))

    picks.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    used_names: set[str] = set()
    used_coordinates: set[str] = set()

    for requested in must_include or []:
        resolved = resolve_place(requested)
        if resolved and not _is_place_used(
            resolved,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        ):
            _mark_place_used(
                resolved,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
            )
            results.append(
                {
                    **export_place(resolved),
                    "area": _area_label(resolved),
                    "reason": "요청에 직접 포함된 장소입니다.",
                }
            )

    for _, place in picks:
        if len(results) >= count:
            break
        if _is_place_used(
            place,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        ):
            continue
        _mark_place_used(
            place,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        )
        results.append(
            {
                **export_place(place),
                "area": _area_label(place),
                "reason": f"{place['category']} 선호와 동선 기준을 반영한 추천입니다.",
            }
        )
    return results


def _select_support_places(
    anchor: dict[str, Any],
    *,
    themes: list[str],
    daily_slots: list[str],
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
) -> list[dict[str, Any]]:
    categories = _build_category_weights("mixed", themes)
    theme_set = {normalize_text(theme) for theme in themes}
    prefer_cafe = bool(theme_set.intersection({"cafe", "foodie"}))
    prefer_local = bool(theme_set.intersection({"local", "hidden_gems"}))
    prefer_featured = not prefer_local and not prefer_cafe
    ordered = sorted(
        (
            place
            for place in CATALOG
            if not _is_place_used(
                place,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
            )
            and place["slug"] != anchor["slug"]
            and (
                not prefer_featured
                or place["slug"] in FEATURED_BY_SLUG
            )
        ),
        key=lambda place: _score_place(place, categories=categories, themes=themes, anchor=anchor),
        reverse=True,
    )
    picks: list[dict[str, Any]] = []
    day_used_slugs: set[str] = set()
    day_used_names: set[str] = set()
    day_used_coordinates: set[str] = set()

    for slot in daily_slots:
        if slot == "morning" and not picks:
            picks.append(anchor)
            _mark_place_used(
                anchor,
                used_slugs=day_used_slugs,
                used_names=day_used_names,
                used_coordinates=day_used_coordinates,
            )
            continue
        candidate = next(
            (
                place
                for place in ordered
                if not _is_place_used(
                    place,
                    used_slugs=day_used_slugs,
                    used_names=day_used_names,
                    used_coordinates=day_used_coordinates,
                )
                and (
                    (
                        slot == "lunch"
                        and place["category"] in {"restaurant", "cafe", "neighborhood"}
                    )
                    or (slot == "afternoon" and place["category"] in {"museum", "landmark", "neighborhood", "park", "cathedral"})
                    or (slot == "evening" and place["category"] in {"landmark", "neighborhood", "cafe"})
                )
            ),
            None,
        )
        if candidate is None:
            candidate_pool = CATALOG
            candidate = next(
                (
                    place
                    for place in sorted(
                        candidate_pool,
                        key=lambda item: _score_place(item, categories=categories, themes=themes, anchor=anchor),
                        reverse=True,
                    )
                    if not _is_place_used(
                        place,
                        used_slugs=day_used_slugs,
                        used_names=day_used_names,
                        used_coordinates=day_used_coordinates,
                    )
                    and not _is_place_used(
                        place,
                        used_slugs=used_slugs,
                        used_names=used_names,
                        used_coordinates=used_coordinates,
                    )
                    and place["slug"] != anchor["slug"]
                ),
                None,
            )
        if candidate is None:
            continue
        picks.append(candidate)
        _mark_place_used(
            candidate,
            used_slugs=day_used_slugs,
            used_names=day_used_names,
            used_coordinates=day_used_coordinates,
        )
    return picks


def build_itinerary(create_plan_payload: dict[str, Any]) -> dict[str, Any]:
    dates = create_plan_payload.get("dates") or {}
    start_date = dates.get("start_date")
    days = max(1, int(dates.get("days") or 1))
    preferences = create_plan_payload.get("preferences") or {}
    pace = (create_plan_payload.get("pace") or {}).get("level", "normal")
    themes = list(preferences.get("themes") or [])
    must_include = list(preferences.get("must_include") or [])
    must_avoid = list(preferences.get("must_avoid") or [])

    venue_seed = recommend_places(
        venue_type="mixed",
        themes=themes,
        count=max(days * 3, 10),
        must_include=must_include,
        must_avoid=must_avoid,
    )
    if not venue_seed:
        venue_seed = [dict(place) for place in FEATURED_PLACES[: max(4, days)]]

    slot_templates = {
        "slow": [
            ("morning", "10:00"),
            ("lunch", "12:30"),
            ("afternoon", "15:30"),
        ],
        "normal": [
            ("morning", "09:00"),
            ("morning", "10:45"),
            ("lunch", "12:30"),
            ("afternoon", "14:30"),
            ("evening", "18:30"),
        ],
        "fast": [
            ("morning", "08:30"),
            ("morning", "10:00"),
            ("lunch", "12:00"),
            ("afternoon", "13:45"),
            ("afternoon", "15:30"),
            ("evening", "18:00"),
            ("evening", "20:00"),
        ],
    }
    daily_template = slot_templates.get(pace, slot_templates["normal"])
    daily_slots = [slot for slot, _ in daily_template]
    used_slugs: set[str] = set()
    used_names: set[str] = set()
    used_coordinates: set[str] = set()
    itinerary_days: list[dict[str, Any]] = []
    route_names: list[str] = []

    for day_number in range(1, days + 1):
        anchor = next(
            (
                venue_seed[(day_number - 1 + offset) % len(venue_seed)]
                for offset in range(len(venue_seed))
                if not _is_place_used(
                    venue_seed[(day_number - 1 + offset) % len(venue_seed)],
                    used_slugs=used_slugs,
                    used_names=used_names,
                    used_coordinates=used_coordinates,
                )
            ),
            venue_seed[(day_number - 1) % len(venue_seed)],
        )
        supports = _select_support_places(
            anchor,
            themes=themes,
            daily_slots=daily_slots,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        )
        items: list[dict[str, Any]] = []
        for index, ((slot, start_time), place) in enumerate(zip(daily_template, supports), start=1):
            _mark_place_used(
                place,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
            )
            route_names.append(place["name"])
            items.append(
                {
                    "id": f"{day_number}-{place['slug']}-{index}",
                    "time_slot": slot,
                    "start_time": start_time,
                    "title": place["name"],
                    "place": {
                        "place_id": place["slug"],
                        "name": place["name"],
                        "coordinates": dict(place["coordinates"]),
                        "category": place["category"],
                        "cuisine": place.get("cuisine"),
                        "admission_fee": _admission_fee_label(place),
                        "admission_fee_amount": _admission_fee_amount(place),
                    },
                    "description": place["short_description"],
                    "estimated_duration": place["estimated_visit_duration"],
                    "area": _area_label(place),
                }
            )

        day_date = None
        if start_date:
            day_date = (datetime.fromisoformat(start_date) + timedelta(days=day_number - 1)).date().isoformat()

        anchor_area = _area_label(anchor)
        itinerary_days.append(
            {
                "id": f"day-{day_number}",
                "day_number": day_number,
                "date": day_date,
                "title": f"{anchor_area} 중심 코스",
                "items": items,
                "route_summary": f"{anchor_area}에서 {', '.join(item['title'] for item in items[:3])} 중심으로 걷기 좋은 순서를 잡았습니다.",
            }
        )

    unique_route_names = list(dict.fromkeys(route_names))
    route_summary = f"{' / '.join(unique_route_names[:5])}을 잇는 데이터 기반 파리 동선을 구성했습니다."
    return {
        "itinerary_days": itinerary_days,
        "route_summary": route_summary,
        "selected_places": unique_route_names,
    }


def _build_day_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "아직 확정된 장소가 없습니다."
    titles = [str(item["title"]) for item in items[:4]]
    return f"{', '.join(titles)} 중심으로 이동 부담을 줄인 순서입니다."


def _build_itinerary_item_from_place(
    *,
    place: dict[str, Any],
    day_number: int,
    slot: str,
    item_index: int,
) -> dict[str, Any]:
    start_time = {
        "morning": "09:00",
        "lunch": "12:30",
        "afternoon": "15:00",
        "evening": "19:00",
    }.get(slot, "15:00")
    return {
        "id": f"{day_number}-{place['slug']}-{item_index}",
        "time_slot": slot,
        "start_time": start_time,
        "title": place["name"],
        "place": {
            "place_id": place["slug"],
            "name": place["name"],
            "coordinates": dict(place["coordinates"]),
            "category": place["category"],
            "cuisine": place.get("cuisine"),
            "admission_fee": _admission_fee_label(place),
            "admission_fee_amount": _admission_fee_amount(place),
        },
        "description": place["short_description"],
        "estimated_duration": place["estimated_visit_duration"],
        "area": _area_label(place),
    }


def _find_item_index(items: list[dict[str, Any]], place_name: str | None) -> int | None:
    if not place_name:
        return None
    normalized_name = normalize_text(place_name)
    for index, item in enumerate(items):
        item_name = str(((item.get("place") or {}).get("name")) or item.get("title") or "")
        normalized_item_name = normalize_text(item_name)
        if (
            normalized_item_name == normalized_name
            or normalized_name in normalized_item_name
            or normalized_item_name in normalized_name
        ):
            return index
    return None


def _find_slot_item_index(items: list[dict[str, Any]], target_slot: str | None) -> int | None:
    if not target_slot:
        return None
    normalized_slot = {"dinner": "evening", "night": "evening"}.get(target_slot, target_slot)
    return next(
        (index for index, item in enumerate(items) if item.get("time_slot") == normalized_slot),
        None,
    )


def _replacement_categories(category: str | None, target_slot: str | None) -> set[str]:
    if category in {"restaurant", "food", "foodie"}:
        return {"restaurant", "cafe"}
    if category == "cafe":
        return {"cafe", "neighborhood"}
    if category == "night_view":
        return {"landmark", "neighborhood"}
    if category:
        return {category}
    if target_slot == "lunch":
        return {"restaurant", "cafe", "neighborhood"}
    return {"landmark", "museum", "neighborhood", "park", "cathedral"}


def _item_coordinates(item: dict[str, Any]) -> dict[str, float] | None:
    coordinates = (item.get("place") or {}).get("coordinates")
    if not isinstance(coordinates, dict):
        return None
    lat = coordinates.get("lat")
    lng = coordinates.get("lng")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def _candidate_route_distance(
    place: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    replace_index: int | None,
) -> float:
    if replace_index is None:
        return 0.0

    anchors: list[dict[str, float]] = []
    previous_coordinates = _item_coordinates(items[replace_index - 1]) if replace_index > 0 else None
    next_coordinates = _item_coordinates(items[replace_index + 1]) if replace_index + 1 < len(items) else None
    if previous_coordinates:
        anchors.append(previous_coordinates)
    if next_coordinates:
        anchors.append(next_coordinates)
    if not anchors:
        return 0.0

    return sum(_distance_km(place["coordinates"], anchor) for anchor in anchors)


def _candidate_route_distance_rank(
    place: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    replace_index: int | None,
) -> float:
    return round(_candidate_route_distance(place, items=items, replace_index=replace_index), 2)


def _candidate_rating_score(place: dict[str, Any]) -> float:
    return float(place.get("rating") or place.get("popularity") or 0)


def _desired_cuisine_terms(cuisine: Any) -> set[str]:
    primary = str(cuisine or "").strip().lower()
    if not primary:
        return set()
    return CUISINE_FALLBACKS.get(primary, {primary})


def _primary_cuisine_term(cuisine: Any) -> str:
    return str(cuisine or "").strip().lower()


def _place_cuisine_terms(place: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    cuisine = place.get("cuisine")
    if isinstance(cuisine, list):
        for item in cuisine:
            terms.update(_split_cuisine_terms(item))
    else:
        terms.update(_split_cuisine_terms(cuisine))
    terms.update(str(tag).lower() for tag in place.get("tags") or [])
    return terms


def _matches_cuisine(place: dict[str, Any], cuisine: Any) -> bool:
    desired = _desired_cuisine_terms(cuisine)
    if not desired:
        return True
    if _place_cuisine_terms(place) & desired:
        return True
    haystack = normalize_text(
        " ".join(
            [
                str(place.get("name") or ""),
                str(place.get("short_description") or ""),
                str(place.get("full_description") or ""),
            ]
        )
    )
    return any(normalize_text(term) in haystack for term in desired)


def _matches_primary_cuisine(place: dict[str, Any], cuisine: Any) -> bool:
    primary = _primary_cuisine_term(cuisine)
    if not primary:
        return True
    if primary in _place_cuisine_terms(place):
        return True
    haystack = normalize_text(
        " ".join(
            [
                str(place.get("name") or ""),
                str(place.get("short_description") or ""),
                str(place.get("full_description") or ""),
            ]
        )
    )
    return normalize_text(primary) in haystack


def _pick_replacement_place(
    *,
    category: str | None,
    target_slot: str | None,
    items: list[dict[str, Any]],
    replace_index: int | None,
    cuisine: Any = None,
) -> dict[str, Any] | None:
    allowed_categories = _replacement_categories(category, target_slot)
    used_place_ids = {
        str((item.get("place") or {}).get("place_id") or "")
        for item in items
    }
    used_names = {
        normalize_text(str((item.get("place") or {}).get("name") or item.get("title") or ""))
        for item in items
    }

    base_candidates = [
        place
        for place in CATALOG
        if place["category"] in allowed_categories
        and place["slug"] not in used_place_ids
        and normalize_text(place["name"]) not in used_names
    ]
    primary_cuisine_candidates = (
        [place for place in base_candidates if _matches_primary_cuisine(place, cuisine)] if cuisine else []
    )
    cuisine_candidates = [place for place in base_candidates if _matches_cuisine(place, cuisine)] if cuisine else []
    candidates = sorted(
        primary_cuisine_candidates or cuisine_candidates or base_candidates,
        key=lambda place: (
            _candidate_route_distance_rank(place, items=items, replace_index=replace_index),
            -_candidate_rating_score(place),
            place["category"] != ("restaurant" if cuisine else "cafe"),
            place["slug"] not in FEATURED_BY_SLUG,
            place["name"],
        ),
    )
    return export_place(candidates[0]) if candidates else None


def _rebuild_selected_places(itinerary_days: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for day in itinerary_days:
        for item in day.get("items", []):
            place_name = str(((item.get("place") or {}).get("name")) or item.get("title") or "").strip()
            if place_name:
                names.append(place_name)
    return list(dict.fromkeys(names))


def apply_modifications(
    *,
    plan_payload: dict[str, Any],
    modify_payload: dict[str, Any],
    existing_itinerary_days: list[dict[str, Any]] | None = None,
    existing_route_summary: str | None = None,
) -> dict[str, Any]:
    base_days = list(existing_itinerary_days or [])
    if not base_days:
        base_days = build_itinerary(plan_payload).get("itinerary_days", [])

    itinerary_days = json.loads(json.dumps(base_days))
    operations = list(modify_payload.get("operations") or [])
    pace = ((plan_payload.get("pace") or {}).get("level")) or "normal"
    mobility = plan_payload.get("mobility") or {}

    for operation in operations:
        day_number = int(operation.get("target_day") or 1)
        day = next((item for item in itinerary_days if int(item.get("day_number") or 0) == day_number), None)
        if day is None:
            continue

        items = list(day.get("items") or [])
        op = str(operation.get("op") or "")
        target_slot = str(operation.get("target_slot") or "afternoon")
        place_name = operation.get("place_name")
        patch = operation.get("constraints_patch") or {}
        from_place = patch.get("from_place") or place_name
        to_place = patch.get("to_place") or place_name

        if op == "remove":
            remove_index = _find_item_index(items, place_name or from_place)
            if remove_index is not None:
                items.pop(remove_index)
        elif op == "replace":
            replace_index = _find_item_index(items, from_place)
            replacement = resolve_place(to_place)
            if replace_index is None:
                replace_index = _find_slot_item_index(items, target_slot)
            if replacement is None:
                replacement = _pick_replacement_place(
                    category=operation.get("category") or patch.get("to_category"),
                    target_slot=target_slot,
                    items=items,
                    replace_index=replace_index,
                    cuisine=patch.get("cuisine"),
                )
            if replace_index is not None and replacement is not None:
                slot = str(items[replace_index].get("time_slot") or target_slot)
                items[replace_index] = _build_itinerary_item_from_place(
                    place=replacement,
                    day_number=day_number,
                    slot=slot,
                    item_index=replace_index + 1,
                )
        elif op == "add":
            resolved = resolve_place(place_name or to_place)
            if resolved is not None:
                items.append(
                    _build_itinerary_item_from_place(
                        place=resolved,
                        day_number=day_number,
                        slot=target_slot,
                        item_index=len(items) + 1,
                    )
                )
        elif op == "swap":
            swap_slots = list(operation.get("swap_slots") or [])
            if len(swap_slots) == 2:
                first_index = next(
                    (index for index, item in enumerate(items) if item.get("time_slot") == swap_slots[0]),
                    None,
                )
                second_index = next(
                    (index for index, item in enumerate(items) if item.get("time_slot") == swap_slots[1]),
                    None,
                )
                if first_index is not None and second_index is not None:
                    items[first_index], items[second_index] = items[second_index], items[first_index]
        elif op == "set_pace" and operation.get("pace"):
            pace = str(operation["pace"])
        elif op == "set_mobility" and operation.get("mobility"):
            mobility = dict(operation["mobility"])

        items.sort(key=lambda item: str(item.get("start_time") or ""))
        day["items"] = items
        day["route_summary"] = _build_day_summary(items)

    selected_places = _rebuild_selected_places(itinerary_days)
    mobility_mode = mobility.get("travel_mode") or "both"
    optimize_mode = mobility.get("optimize") or "min_time"
    route_summary = (
        f"{', '.join(selected_places[:5])} 중심으로 {mobility_mode} 이동과 {pace} 템포를 반영해 재구성했습니다."
        if selected_places
        else existing_route_summary or "수정 결과를 반영한 동선을 준비했습니다."
    )
    if not selected_places and existing_route_summary:
        route_summary = existing_route_summary
    else:
        route_summary = f"{route_summary} 최적화 기준은 {optimize_mode}입니다."

    return {
        "itinerary_days": itinerary_days,
        "route_summary": route_summary,
        "selected_places": selected_places,
    }


def optimize_route(
    *,
    route_points: list[str],
    trip_route_points: list[str] | None = None,
) -> dict[str, Any]:
    point_names = route_points or list(trip_route_points or [])
    resolved = [resolve_place(name) for name in point_names]
    resolved_places = [place for place in resolved if place is not None]
    if not resolved_places:
        return {
            "ordered_points": point_names,
            "resolved_places": [],
            "route_summary": "좌표를 찾을 수 없어 입력 순서를 유지했습니다.",
            "estimated_distance_km": 0.0,
        }

    remaining = [dict(place) for place in resolved_places]
    ordered = [remaining.pop(0)]
    while remaining:
        current = ordered[-1]
        next_place = min(
            remaining,
            key=lambda place: _distance_km(current["coordinates"], place["coordinates"]),
        )
        ordered.append(next_place)
        remaining.remove(next_place)

    total_distance = 0.0
    for current, nxt in zip(ordered, ordered[1:]):
        total_distance += _distance_km(current["coordinates"], nxt["coordinates"])

    return {
        "ordered_points": [place["name"] for place in ordered],
        "resolved_places": ordered,
        "route_summary": f"{_area_label(ordered[0])}에서 시작해 가장 가까운 순서로 동선을 재정렬했습니다.",
        "estimated_distance_km": round(total_distance, 2),
    }
