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
        "slug": "palais-royal",
        "name": "팔레 루아얄",
        "category": "landmark",
        "coordinates": {"lat": 48.8635, "lng": 2.3376},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "회랑, 정원, 부티크가 이어지는 우아한 파리 산책지",
        "full_description": "오페라와 루브르 사이에서 쇼핑 분위기와 조용한 정원 산책을 함께 느끼기 좋은 클래식 코스입니다.",
        "history": "왕실 궁전과 정원을 바탕으로 형성된 공간으로, 오늘날에는 회랑과 부티크, 미술적인 기둥 광장으로 사랑받습니다.",
        "photo_spot_tips": ["다니엘 뷔랑 기둥", "정원 회랑", "부티크 앞 골목"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "무료",
        "location": "8 Rue de Montpensier, 75001 Paris",
        "tags": ["landmark", "garden", "shopping", "walk", "classic", "local"],
        "popularity": 81,
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
    {
        "slug": "caveau-de-la-huchette",
        "name": "르 카보 드 라 위셰트",
        "category": "bar",
        "coordinates": {"lat": 48.8528, "lng": 2.3458},
        "image_url": "/images/paris-default-hero.jpeg",
        "short_description": "라탱 지구의 오래된 재즈 클럽",
        "full_description": "늦은 저녁 파리의 음악적인 분위기로 하루를 닫기 좋은 클래식 재즈바입니다.",
        "history": "1940년대부터 라이브 재즈와 스윙 공연으로 알려진 파리의 대표적인 재즈 클럽입니다.",
        "photo_spot_tips": ["입구 간판", "공연 전 골목 분위기", "라탱 지구 야간 산책"],
        "estimated_visit_duration": "1-2시간",
        "admission_fee": "공연별 커버 차지 확인 필요",
        "location": "5 Rue de la Huchette, 75005 Paris",
        "tags": ["bar", "jazz", "music", "nightlife", "local", "romantic"],
        "cuisine": ["jazz_bar", "wine"],
        "popularity": 82,
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
    "nightlife": {"bar": 4.0, "restaurant": 1.5, "neighborhood": 1.0},
    "jazz": {"bar": 4.5, "restaurant": 1.0},
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
    "사크레쾨르": "montmartre",
    "사크레쾨르성당": "montmartre",
    "sacrecoeur": "montmartre",
    "sacrecoeurbasilica": "montmartre",
    "개선문": "arc-de-triomphe",
    "샹젤리제": "champs-elysees",
    "생트샤펠": "sainte-chapelle",
    "생트샤펠성당": "sainte-chapelle",
    "마레": "marais",
    "튈르리": "tuileries-garden",
    "튈르리정원": "tuileries-garden",
    "오페라": "palais-garnier",
    "오페라가르니에": "palais-garnier",
    "팔레가르니에": "palais-garnier",
    "가르니에": "palais-garnier",
    "팔레루아얄": "palais-royal",
    "팔레 루아얄": "palais-royal",
    "센강": "seine-river-walk",
    "센강산책": "seine-river-walk",
    "세느강": "seine-river-walk",
    "세느강산책": "seine-river-walk",
    "뤽상부르": "luxembourg-gardens",
    "뤽상부르공원": "luxembourg-gardens",
    "룩셈부르크": "luxembourg-gardens",
    "룩셈부르크공원": "luxembourg-gardens",
    "재즈바": "caveau-de-la-huchette",
    "재즈": "caveau-de-la-huchette",
    "위셰트": "caveau-de-la-huchette",
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
    "palaisgarnier": "palais-garnier",
    "operagarnier": "palais-garnier",
    "palaisroyal": "palais-royal",
    "jazzbar": "caveau-de-la-huchette",
    "caveaudelahuchette": "caveau-de-la-huchette",
    "huchette": "caveau-de-la-huchette",
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
    if "budget" in {normalize_text(theme) for theme in themes} or "save" in {normalize_text(theme) for theme in themes}:
        admission = _admission_fee_amount(place) or 0
        if admission > 0:
            score -= min(5.0, admission / 8.0)
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
    *,
    blueprint: dict[str, Any],
    profile: dict[str, Any],
    must_include_pool: list[dict[str, Any]],
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    day_used_slugs: set[str] = set()
    day_used_names: set[str] = set()
    day_used_coordinates: set[str] = set()
    slot_specs = list(blueprint.get("slots") or [])
    day_anchor = _locked_day_anchor(slot_specs)
    previous_place: dict[str, Any] | None = None
    index = 0

    while index < len(slot_specs):
        spec = slot_specs[index]
        next_spec = slot_specs[index + 1] if index + 1 < len(slot_specs) else None

        if spec.get("meal") and next_spec and "night_view" in _spec_tags(next_spec):
            next_place = _pick_place_for_spec(
                spec=next_spec,
                profile=profile,
                must_include_pool=must_include_pool,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
                day_used_slugs=day_used_slugs,
                day_used_names=day_used_names,
                day_used_coordinates=day_used_coordinates,
                reference_place=previous_place,
                day_anchor=day_anchor,
                context_place=None,
            )
            meal_candidate = _pick_place_for_spec(
                spec=spec,
                profile=profile,
                must_include_pool=must_include_pool,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
                day_used_slugs=day_used_slugs,
                day_used_names=day_used_names,
                day_used_coordinates=day_used_coordinates,
                reference_place=previous_place,
                day_anchor=day_anchor,
                context_place=next_place,
            )
            if meal_candidate is not None:
                picks.append({"place": meal_candidate, "spec": spec})
                _mark_place_used(
                    meal_candidate,
                    used_slugs=day_used_slugs,
                    used_names=day_used_names,
                    used_coordinates=day_used_coordinates,
                )
                previous_place = meal_candidate
            if next_place is not None:
                picks.append({"place": next_place, "spec": next_spec})
                _mark_place_used(
                    next_place,
                    used_slugs=day_used_slugs,
                    used_names=day_used_names,
                    used_coordinates=day_used_coordinates,
                )
                if day_anchor is None and not next_spec.get("meal"):
                    day_anchor = next_place
                previous_place = next_place
            index += 2
            continue

        candidate = _pick_place_for_spec(
            spec=spec,
            profile=profile,
            must_include_pool=must_include_pool,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
            day_used_slugs=day_used_slugs,
            day_used_names=day_used_names,
            day_used_coordinates=day_used_coordinates,
            reference_place=previous_place,
            day_anchor=day_anchor,
            context_place=None,
        )
        if candidate is not None:
            picks.append({"place": candidate, "spec": spec})
            _mark_place_used(
                candidate,
                used_slugs=day_used_slugs,
                used_names=day_used_names,
                used_coordinates=day_used_coordinates,
            )
            if day_anchor is None and not spec.get("meal"):
                day_anchor = candidate
            previous_place = candidate
        index += 1
    return picks


def _locked_day_anchor(slot_specs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for spec in slot_specs:
        locked_slug = str(spec.get("locked_slug") or "")
        if locked_slug and locked_slug in CATALOG_BY_SLUG:
            return export_place(CATALOG_BY_SLUG[locked_slug])
    return None


def _canonical_preference_token(value: Any) -> str:
    normalized = normalize_text(str(value or ""))
    mapping = {
        "nightview": "night_view",
        "night": "night_view",
        "sunset": "night_view",
        "romance": "romantic",
        "hiddengems": "local",
        "relax": "slow",
        "relaxed": "slow",
        "healing": "slow",
        "breakfast": "brunch",
        "coffeeshop": "coffee",
    }
    return mapping.get(normalized, normalized)


def _merge_unique_tokens(*groups: list[Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group or []:
            token = _canonical_preference_token(value)
            if token and token not in seen:
                merged.append(token)
                seen.add(token)
    return merged


def _spec_tags(spec: dict[str, Any]) -> set[str]:
    return {_canonical_preference_token(tag) for tag in spec.get("tags") or [] if tag}


def _place_theme_tags(place: dict[str, Any]) -> set[str]:
    base = {_canonical_preference_token(tag) for tag in place.get("tags") or [] if tag}
    category = _canonical_preference_token(place.get("category"))
    if category:
        base.add(category)
    return base


def _planning_brief(create_plan_payload: dict[str, Any]) -> dict[str, Any]:
    raw = create_plan_payload.get("planning_brief")
    return dict(raw) if isinstance(raw, dict) else {}


def _itinerary_profile(create_plan_payload: dict[str, Any]) -> dict[str, Any]:
    preferences = create_plan_payload.get("preferences") or {}
    brief = _planning_brief(create_plan_payload)
    pace = str((create_plan_payload.get("pace") or {}).get("level") or "normal").lower()
    mobility = create_plan_payload.get("mobility") or {}
    budget = create_plan_payload.get("budget") or {}
    party = create_plan_payload.get("party") or {}
    themes = _merge_unique_tokens(
        list(brief.get("travel_style") or []),
        list(preferences.get("themes") or []),
        list(preferences.get("travel_style") or []),
    )
    preferred_slots = _merge_unique_tokens(list(brief.get("preferred_time_slots") or []), list(preferences.get("preferred_time_slots") or []))
    meal_preferences = _merge_unique_tokens(list(brief.get("meal_preference") or []), list(preferences.get("meal_preference") or []))
    theme_set = set(themes)
    must_include_names = _merge_unique_tokens(list(brief.get("must_include") or []), list(preferences.get("must_include") or []))
    must_avoid = {
        normalize_text(str(name or ""))
        for name in [*(brief.get("must_avoid") or []), *(preferences.get("must_avoid") or [])]
        if str(name or "").strip()
    }
    try:
        adults = int(party.get("adult") or 0)
        children = int(party.get("elementary") or 0) + int(party.get("toddler") or 0)
    except (TypeError, ValueError):
        adults = 0
        children = 0
    resolved_pace = str(brief.get("pace") or pace or "normal").lower()
    locked_stops = _derive_locked_stops(
        brief=brief,
        must_include_names=must_include_names,
        night_view_required=bool(brief.get("night_view_required")) or bool(preferences.get("night_view_required")) or "night_view" in theme_set,
    )
    meal_preference_set = set(meal_preferences)
    return {
        "planning_brief": brief,
        "themes": themes,
        "theme_set": theme_set,
        "quality_focus": str(brief.get("quality_focus") or "").strip().lower(),
        "must_include_names": must_include_names,
        "preferred_slots": preferred_slots,
        "preferred_slot_set": set(preferred_slots),
        "meal_preferences": meal_preferences,
        "meal_preference_set": meal_preference_set,
        "pace": resolved_pace,
        "slow": resolved_pace == "slow" or "slow" in theme_set,
        "fast": resolved_pace == "fast" or "fast" in theme_set,
        "night_view": bool(brief.get("night_view_required")) or bool(preferences.get("night_view_required")) or "night_view" in theme_set,
        "museum": bool(theme_set.intersection({"museum", "art", "culture", "history"})),
        "local": bool(theme_set.intersection({"local", "walk", "romantic", "cafe"})),
        "foodie": bool(meal_preferences or theme_set.intersection({"foodie", "cafe"})),
        "prefers_cafe_dessert": bool(theme_set.intersection({"cafe", "foodie", "dessert"})) or bool(meal_preference_set.intersection({"cafe", "dessert", "coffee", "bakery"})),
        "prefers_brunch": bool(meal_preference_set.intersection({"brunch", "breakfast"})),
        "prefers_french_dinner": bool(meal_preference_set.intersection({"french", "bistro", "brasserie", "romantic"})),
        "prefers_late_bar": bool(theme_set.intersection({"jazz", "nightlife"})) or bool(meal_preference_set.intersection({"jazz", "jazz_bar", "wine", "bar"})),
        "transport": str(brief.get("transport_preference") or mobility.get("travel_mode") or "both"),
        "budget_mode": str((brief.get("budget_range") or {}).get("budget_mode") or budget.get("budget_mode") or "normal"),
        "travelers": max(1, adults + children),
        "must_avoid": must_avoid,
        "strict_constraints": bool(brief.get("strict_constraints")),
        "locked_stops": locked_stops,
        "preferred_blueprints": list(brief.get("preferred_blueprints") or []),
    }


_EIFFEL_LOCK_ALIASES = ("eiffel", "eiffeltower", "toureiffel", "\uc5d0\ud3a0", "\uc5d0\ud3a0\ud0d1")
_SEINE_LOCK_ALIASES = ("seine", "seineriver", "\uc13c\uac15")
_ARC_LOCK_ALIASES = ("arc", "arcdetriomphe", "\uac1c\uc120\ubb38")
_JAZZ_LOCK_ALIASES = ("jazz", "jazzbar", "caveaudelahuchette", "huchette", "\uc7ac\uc988", "\uc7ac\uc988\ubc14", "\uc704\uc158\ud2b8")
_NIGHT_LOCK_CUES = ("night", "nightview", "night_view", "sparkling", "\uc57c\uacbd", "\ubc24", "\uc57c\uac04")
_SUNSET_LOCK_CUES = ("sunset", "\uc11d\uc591", "\uc120\uc14b", "\ub178\uc744", "\ud574\uc9c8\ub158")
_FINAL_LOCK_CUES = ("finish", "final", "end", "\ub9c8\ubb34\ub9ac", "\ub9c8\uc9c0\ub9c9", "\ub05d")


def _compact_lock_source(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", str(value or "")).lower()


def _has_lock_cue(source_text: str, aliases: tuple[str, ...], cues: tuple[str, ...], *, before: int = 12, after: int = 22) -> bool:
    text = _compact_lock_source(source_text)
    if not text:
        return False
    cue_values = [_compact_lock_source(cue) for cue in cues if _compact_lock_source(cue)]
    for alias in aliases:
        alias_value = _compact_lock_source(alias)
        if not alias_value:
            continue
        start = text.find(alias_value)
        if start < 0:
            continue
        window = text[max(0, start - before) : start + len(alias_value) + after]
        if any(cue in window for cue in cue_values):
            return True
    return False


def _locked_stop(entity: str, slug: str, target_slot: str, label: str) -> dict[str, Any]:
    return {
        "entity": entity,
        "slug": slug,
        "modifier": "night_view",
        "target_slot": target_slot,
        "locked": True,
        "preferred_day": 1,
        "label": label,
    }


def _derive_locked_stops(*, brief: dict[str, Any], must_include_names: list[str], night_view_required: bool) -> list[dict[str, Any]]:
    explicit_locks = brief.get("locked_stops")
    if isinstance(explicit_locks, list) and explicit_locks:
        return [dict(lock) for lock in explicit_locks if isinstance(lock, dict)]

    has_late_bar_request = any(_lockable_slug_for_name(name) == "caveau-de-la-huchette" for name in must_include_names)
    has_seine_request = any(_lockable_slug_for_name(name) == "seine-river-walk" for name in must_include_names)
    if not night_view_required and not has_late_bar_request and not has_seine_request:
        return []

    source_text = str(brief.get("source_text") or "").strip()
    has_source_text = bool(source_text)
    locks: list[dict[str, Any]] = []
    for name in must_include_names:
        slug = _lockable_slug_for_name(name)
        if slug == "eiffel-tower":
            if has_source_text and not _has_lock_cue(source_text, _EIFFEL_LOCK_ALIASES, _NIGHT_LOCK_CUES):
                continue
            locks.append(_locked_stop("eiffel_tower", slug, "evening", "에펠탑 야경"))
        elif slug == "seine-river-walk":
            has_sunset = _has_lock_cue(source_text, _SEINE_LOCK_ALIASES, _SUNSET_LOCK_CUES)
            has_night = _has_lock_cue(source_text, _SEINE_LOCK_ALIASES, _NIGHT_LOCK_CUES)
            has_final = _has_lock_cue(source_text, _SEINE_LOCK_ALIASES, _FINAL_LOCK_CUES, before=4, after=28)
            target_slot = "night" if has_night and not has_sunset else "evening" if (has_sunset or has_night or has_final) else "afternoon"
            label = "센강 석양 산책" if has_sunset else "센강 야간 산책" if target_slot in {"evening", "night"} else "센강 산책"
            locks.append(_locked_stop("seine_river", slug, target_slot, label))
        elif slug == "arc-de-triomphe":
            has_night = _has_lock_cue(source_text, _ARC_LOCK_ALIASES, _NIGHT_LOCK_CUES)
            has_final = _has_lock_cue(source_text, _ARC_LOCK_ALIASES, _FINAL_LOCK_CUES, before=4, after=28)
            if has_source_text and not (has_night or has_final):
                continue
            locks.append(_locked_stop("arc_de_triomphe", slug, "night" if has_final else "evening", "개선문 야경"))
        elif slug == "caveau-de-la-huchette":
            locks.append(_locked_stop("jazz_bar", slug, "night", "재즈바"))
    return locks


def _lockable_slug_for_name(value: str) -> str | None:
    resolved = resolve_place(value)
    if resolved is not None:
        slug = str(resolved.get("slug") or "")
        if slug in {"eiffel-tower", "seine-river-walk", "arc-de-triomphe", "louvre-museum", "caveau-de-la-huchette"}:
            return slug
    normalized = normalize_text(value)
    if normalized and ("eiffel" in normalized or "에펠" in value):
        return "eiffel-tower"
    if normalized and ("seine" in normalized or "센강" in value):
        return "seine-river-walk"
    if normalized and ("arc" in normalized or "개선문" in value):
        return "arc-de-triomphe"
    if normalized and ("louvre" in normalized or "루브르" in value):
        return "louvre-museum"
    if normalized and any(alias in normalized for alias in _JAZZ_LOCK_ALIASES):
        return "caveau-de-la-huchette"
    return None


def _select_blueprint_archetype(day_index: int, total_days: int, profile: dict[str, Any]) -> str:
    preferred = [str(value) for value in profile.get("preferred_blueprints") or [] if str(value).strip()]
    if day_index < len(preferred):
        return preferred[day_index]

    has_eiffel_night_lock = any(
        str(lock.get("slug") or "") == "eiffel-tower" and str(lock.get("target_slot") or "") in {"evening", "night"}
        for lock in profile.get("locked_stops") or []
    )
    wants_evening_first = bool(profile.get("preferred_slot_set", set()).intersection({"afternoon", "evening", "night"}))

    if day_index == 0 and has_eiffel_night_lock and profile.get("slow") and profile.get("prefers_cafe_dessert") and profile.get("prefers_french_dinner"):
        return "slow_cafe_evening_day"
    if day_index == 0 and has_eiffel_night_lock:
        return "night_view_focused_day"
    if profile.get("museum") and not has_eiffel_night_lock and (day_index == 1 or (day_index == 0 and not profile.get("night_view"))):
        return "museum_focused_day"
    if profile.get("night_view") and profile.get("prefers_french_dinner"):
        return "romantic_evening_day"
    if profile.get("prefers_late_bar") or (profile.get("prefers_french_dinner") and wants_evening_first):
        return "romantic_evening_day"
    if profile.get("slow") and profile.get("prefers_cafe_dessert"):
        return "slow_cafe_day" if not wants_evening_first else "romantic_evening_day"
    if profile.get("local") or day_index % 3 == 2 or (profile.get("foodie") and profile.get("slow")):
        return "slow_cafe_day"
    return "general_landmark_day"


def _lock_for_slot(profile: dict[str, Any], slot: str, day_index: int) -> dict[str, Any] | None:
    for lock in profile.get("locked_stops") or []:
        if not bool(lock.get("locked")):
            continue
        preferred_day = int(lock.get("preferred_day") or 1)
        target_slot = str(lock.get("target_slot") or "")
        if preferred_day == day_index + 1 and target_slot == slot:
            return dict(lock)
    return None


def _day_blueprint(day_index: int, total_days: int, profile: dict[str, Any]) -> dict[str, Any]:
    meal_tags = set(profile.get("meal_preferences") or [])
    slow = bool(profile.get("slow"))
    wants_night = bool(profile.get("night_view"))
    wants_museum = bool(profile.get("museum"))
    meal_categories = {"restaurant", "cafe", "bakery", "bistro", "brasserie"}
    archetype = _select_blueprint_archetype(day_index, total_days, profile)

    def stop_spec(
        slot: str,
        start_time: str,
        categories: set[str],
        tags: set[str],
        *,
        prefer_featured: bool = True,
        locked_stop: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = {
            "slot": slot,
            "start_time": start_time,
            "categories": categories,
            "tags": sorted(tags),
            "prefer_featured": prefer_featured,
        }
        if locked_stop:
            spec.update(
                {
                    "locked_slug": locked_stop.get("slug"),
                    "locked_label": locked_stop.get("label"),
                    "locked_modifier": locked_stop.get("modifier"),
                    "locked_target_slot": locked_stop.get("target_slot"),
                }
            )
        return spec

    def meal_spec(slot: str, start_time: str, extra_tags: set[str] | None = None) -> dict[str, Any]:
        tags = set(extra_tags or set())
        categories = set(meal_categories)
        if slot == "lunch":
            tags.update(meal_tags.intersection({"brunch", "breakfast", "cafe", "coffee", "bakery", "dessert"}))
            tags.update({"brunch"} if (slow or profile.get("prefers_brunch")) else {"french"})
            if profile.get("prefers_cafe_dessert") or tags.intersection({"brunch", "cafe", "coffee", "bakery", "dessert"}):
                categories = {"cafe", "bakery"}
        else:
            tags.update(meal_tags.intersection({"french", "bistro", "brasserie", "romantic"}))
            tags.update({"french", "romantic"} if wants_night or profile.get("prefers_french_dinner") else {"french"})
        return {
            "slot": slot,
            "start_time": start_time,
            "meal": True,
            "categories": categories,
            "tags": sorted(tags),
            "prefer_featured": False,
        }
    evening_lock = _lock_for_slot(profile, "evening", day_index) or _lock_for_slot(profile, "night", day_index)
    late_bar_spec = stop_spec("evening", "21:20", {"bar"}, {"jazz", "music", "nightlife", "romantic"}, prefer_featured=False) if profile.get("prefers_late_bar") else None

    if archetype == "slow_cafe_evening_day":
        slots = [
            stop_spec("afternoon", "11:15", {"cafe", "bakery"}, {"brunch", "coffee", "dessert", "local"}, prefer_featured=False),
            meal_spec("lunch", "13:00", {"bakery", "coffee", "dessert"}),
            stop_spec("afternoon", "15:00", {"park", "landmark"}, {"walk", "romantic", "photo", "scenic"}, prefer_featured=False),
            stop_spec("afternoon", "16:35", {"cafe", "bakery"}, {"dessert", "coffee", "relax", "romantic"}, prefer_featured=False),
            meal_spec("evening", "18:35", {"french", "romantic"}),
            stop_spec("evening", "20:25", {"landmark", "neighborhood"}, {"night_view", "romantic", "walk", "classic"}, locked_stop=evening_lock),
        ]
        if late_bar_spec:
            slots[-1] = late_bar_spec if not wants_night else slots[-1]
            if wants_night:
                slots.append(late_bar_spec)
        return {
            "archetype": archetype,
            "theme": "파리 첫날, 센강과 에펠탑 야경에 천천히 스며드는 하루" if day_index == 0 else "센강과 에펠탑 야경에 천천히 스며드는 하루",
            "summary": "늦은 브런치, 카페와 디저트, 가벼운 산책, 프렌치 디너, 야경 하이라이트로 무리하지 않게 감정을 끌어올리는 evening-first 흐름입니다.",
            "route_summary": "권역을 과하게 넓히지 않고 카페와 산책으로 호흡을 맞춘 뒤, 저녁 식사와 야경 클라이맥스로 감정을 모으도록 설계했습니다.",
            "slots": slots,
        }

    if archetype == "night_view_focused_day":
        slots = [
            stop_spec("afternoon", "12:00", {"cafe", "neighborhood", "park"}, {"brunch", "coffee", "local", "relax"}, prefer_featured=False),
            stop_spec("afternoon", "14:15", {"landmark", "park", "neighborhood"}, {"walk", "photo", "scenic", "classic"}),
            stop_spec("afternoon", "16:10", {"cafe", "bakery", "neighborhood"}, {"dessert", "coffee", "relax"}, prefer_featured=False),
            meal_spec("evening", "18:40", {"french", "romantic"}),
            stop_spec("evening", "20:30", {"landmark", "neighborhood"}, {"night_view", "romantic", "classic"}, locked_stop=evening_lock),
        ]
        return {
            "archetype": archetype,
            "theme": "파리 첫날, 해 질 무렵부터 빛나는 야경 포인트를 따라가는 하루" if day_index == 0 else "해 질 무렵부터 빛나는 파리 야경 포인트를 따라가는 하루",
            "summary": "낮에는 가볍게 에너지를 아끼고, 저녁 식사 이후 야경 카드가 연속으로 살아나는 night-view 중심 흐름입니다.",
            "route_summary": "오후에는 짧은 산책과 카페로 리듬을 만들고, 밤에는 대표 야경 포인트가 하루의 마지막 장면을 차지하도록 구성했습니다.",
            "slots": slots,
        }

    if archetype == "romantic_evening_day":
        if profile.get("prefers_brunch"):
            slots = [
                meal_spec("lunch", "11:15", {"brunch", "coffee", "bakery"}),
                stop_spec("afternoon", "12:50", {"neighborhood", "cathedral", "landmark"}, {"walk", "local", "romantic", "history"}, prefer_featured=False),
                stop_spec("afternoon", "15:15", {"cafe", "bakery", "neighborhood"}, {"coffee", "dessert", "local"}, prefer_featured=False),
                meal_spec("evening", "18:35", {"french", "romantic"}),
            ]
            if wants_night:
                slots.append(stop_spec("evening", "20:20", {"landmark", "neighborhood"}, {"night_view", "romantic", "walk", "classic"}, locked_stop=evening_lock))
        else:
            slots = [
                stop_spec("morning", "10:15", {"neighborhood", "landmark", "cathedral"}, {"walk", "romantic", "history"}, prefer_featured=False),
                stop_spec("afternoon", "12:00", {"cafe", "bakery", "neighborhood"}, {"coffee", "dessert", "local"}, prefer_featured=False),
                meal_spec("lunch", "13:30", {"coffee", "bakery"} if profile.get("prefers_cafe_dessert") else {"french"}),
                stop_spec("afternoon", "15:30", {"park", "neighborhood", "landmark"}, {"walk", "romantic", "photo", "scenic"}, prefer_featured=False),
                meal_spec("evening", "18:35", {"french", "romantic"}),
                stop_spec("evening", "20:20", {"landmark", "neighborhood"}, {"night_view", "romantic", "walk", "classic"}, locked_stop=evening_lock),
            ]
        if late_bar_spec:
            if profile.get("prefers_brunch"):
                slots.append(late_bar_spec)
            elif wants_night:
                slots.append(late_bar_spec)
            else:
                slots[-1] = late_bar_spec
        return {
            "archetype": archetype,
            "theme": "저녁 식사와 야경으로 감정을 끌어올리는 로맨틱한 하루",
            "summary": "낮에는 걷고 쉬는 리듬을 만들고, 저녁에는 분위기 있는 식사와 빛나는 파리 장면으로 하루를 마무리합니다.",
            "route_summary": "멀리 튀는 이동보다 카페와 산책, 저녁 식사, 야경 클라이맥스가 한 권역 안에서 이어지도록 구성했습니다.",
            "slots": slots,
        }

    if archetype == "museum_focused_day":
        slots = [
            stop_spec("morning", "09:30", {"museum"}, {"museum", "art", "history"}),
            meal_spec("lunch", "12:45", {"coffee" if slow else "french"}),
            stop_spec("afternoon", "14:35", {"park", "neighborhood", "landmark"}, {"walk", "classic", "romantic", "photo"}),
            stop_spec("afternoon", "16:10", {"cafe", "neighborhood", "park"}, {"coffee", "relax", "art"}, prefer_featured=False),
        ]
        if wants_night:
            slots.extend(
                [
                    meal_spec("evening", "18:30", {"romantic"}),
                    stop_spec("evening", "20:20", {"landmark", "neighborhood"}, {"night_view", "classic", "walk"}, locked_stop=evening_lock),
                ]
            )
        else:
            slots.append(stop_spec("evening", "18:30", {"neighborhood", "cafe", "landmark"}, {"cafe", "walk", "local"}, prefer_featured=False))
        return {
            "archetype": archetype,
            "theme": "대표 미술관과 센강 산책으로 이어지는 예술의 하루",
            "summary": "오전에는 대표 컬렉션에 집중하고, 오후에는 강변·정원·카페로 감상 피로를 자연스럽게 풀어 주는 예술 중심 흐름입니다.",
            "route_summary": "한 권역 안에서 미술관 몰입, 점심, 산책, 카페, 저녁으로 리듬을 눌렀다 풀었다 하는 날입니다.",
            "slots": slots,
        }

    if archetype == "slow_cafe_day":
        late_theme = "마지막 날, 브런치와 산책으로 파리의 여운을 남기는 하루" if day_index == total_days - 1 and slow else "카페와 골목 감성을 따라 천천히 걷는 느린 하루"
        late_summary = (
            "마지막 날은 촘촘한 명소보다 브런치, 공원, 강변 산책처럼 여운이 남는 블록 위주로 구성했습니다."
            if day_index == total_days - 1 and slow
            else "카페와 디저트, 산책, 작은 랜드마크를 연결해 체크리스트보다 머무는 감각이 남는 흐름을 만들었습니다."
        )
        slots = [
            stop_spec("morning", "10:00", {"neighborhood", "landmark", "cathedral"}, {"local", "walk", "romantic", "history"}, prefer_featured=False),
            stop_spec("morning", "11:30", {"cafe", "bakery"}, {"coffee", "bakery", "dessert", "local"}, prefer_featured=False),
            meal_spec("lunch", "13:05", {"coffee", "bakery"} if profile.get("prefers_cafe_dessert") else {"french"}),
            stop_spec("afternoon", "15:10", {"neighborhood", "park", "cafe"}, {"local", "walk", "cafe", "romantic"}, prefer_featured=False),
        ]
        if wants_night:
            slots.extend(
                [
                    meal_spec("evening", "18:35", {"romantic", "french"} if profile.get("prefers_french_dinner") else {"romantic"}),
                    stop_spec("evening", "20:15", {"landmark", "neighborhood"}, {"night_view", "romantic", "walk"}, locked_stop=evening_lock),
                ]
            )
        elif late_bar_spec:
            slots.extend([meal_spec("evening", "18:35", {"romantic", "french"}), late_bar_spec])
        return {
            "archetype": archetype,
            "theme": late_theme,
            "summary": late_summary,
            "route_summary": "한 동네와 인접 권역 안에서 산책, 카페, 식사, 저녁 장면이 이어지도록 클러스터링한 날입니다.",
            "slots": slots,
        }

    slots = [
        stop_spec("morning", "09:40", {"landmark", "museum", "cathedral"}, {"classic", "landmark", "history"}),
        meal_spec("lunch", "12:40", {"french"}),
        stop_spec("afternoon", "14:50", {"park", "landmark", "neighborhood"}, {"walk", "classic", "photo"}),
        stop_spec("afternoon", "16:25", {"cafe", "neighborhood", "park"}, {"coffee", "relax", "classic"}, prefer_featured=False),
    ]
    if wants_night:
        slots.extend(
            [
                meal_spec("evening", "18:25", {"romantic", "french"} if profile.get("prefers_french_dinner") else {"romantic"}),
                stop_spec("evening", "20:10", {"landmark", "neighborhood"}, {"night_view", "classic", "walk"}, locked_stop=evening_lock),
            ]
        )
    elif late_bar_spec:
        slots.extend([meal_spec("evening", "18:25", {"french", "romantic"}), late_bar_spec])
    else:
        slots.append(stop_spec("evening", "18:35", {"neighborhood", "cafe", "landmark"}, {"cafe", "walk", "classic"}, prefer_featured=False))
    return {
        "archetype": archetype,
        "theme": "개선문에서 정원 산책까지, 클래식 파리를 걷는 하루",
        "summary": "대표 명소를 빠르게 소비하지 않고, 오전 하이라이트와 오후 산책·카페·저녁 흐름이 이어지는 클래식한 하루로 구성했습니다.",
        "route_summary": "랜드마크만 줄 세우지 않고 정원·카페·식사 리듬을 끼워 넣어 실제 여행 하루처럼 느껴지도록 조정했습니다.",
        "slots": slots,
    }


def _apply_slot_preferences(blueprint: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    preferred = set(profile.get("preferred_slot_set") or set())
    if not preferred:
        return blueprint

    updated = dict(blueprint)
    slots: list[dict[str, Any]] = []
    for spec in blueprint.get("slots") or []:
        slot = str(spec.get("slot") or "")
        next_spec = dict(spec)
        if slot == "morning" and "morning" not in preferred and preferred.intersection({"afternoon", "evening", "night"}):
            next_spec["start_time"] = "10:45"
            next_spec["tags"] = sorted(set(spec.get("tags") or []).union({"walk", "cafe"}))
        if slot == "morning" and "morning" in preferred:
            next_spec["start_time"] = "09:00"
        if slot == "evening" and preferred.intersection({"evening", "night"}):
            next_spec["start_time"] = "19:15" if not next_spec.get("meal") else str(next_spec.get("start_time") or "18:15")
        slots.append(next_spec)

    if "morning" not in preferred and preferred.intersection({"afternoon", "evening", "night"}) and len(slots) >= 4:
        non_meal_morning_indices = [index for index, spec in enumerate(slots) if spec.get("slot") == "morning" and not spec.get("meal")]
        if non_meal_morning_indices:
            slots.pop(non_meal_morning_indices[0])

    if profile.get("strict_constraints") and profile.get("slow"):
        reduce_helper_focus = profile.get("quality_focus") == "reduce_helper_blocks"
        max_slots = 6 if (profile.get("night_view") and reduce_helper_focus) else 5 if profile.get("night_view") else 5 if reduce_helper_focus else 4
        while len(slots) > max_slots:
            removable_indices = []
            for index, spec in enumerate(slots):
                if spec.get("meal"):
                    continue
                tags = {str(tag) for tag in spec.get("tags") or []}
                categories = {str(category) for category in spec.get("categories") or set()}
                if "night_view" in tags:
                    continue
                score = 0
                if categories and categories.issubset({"cafe", "park", "neighborhood"}):
                    score += 4
                if tags.intersection({"relax", "coffee", "photo", "local", "walk"}):
                    score += 2
                if reduce_helper_focus and str(spec.get("slot") or "") == "afternoon":
                    score -= 3
                if str(spec.get("slot") or "") in {"morning", "afternoon"}:
                    score += 1
                removable_indices.append((score, index))
            if not removable_indices:
                break
            _, remove_index = max(removable_indices)
            slots.pop(remove_index)

    updated["slots"] = slots
    return updated


def _matches_slot_spec(place: dict[str, Any], spec: dict[str, Any], *, loose: bool = False) -> bool:
    categories = set(spec.get("categories") or [])
    tags = _spec_tags(spec)
    place_tags = _place_theme_tags(place)
    meal_categories = {"restaurant", "cafe", "bakery", "bistro", "brasserie", "bar"}
    locked_slug = str(spec.get("locked_slug") or "")
    if locked_slug:
        return str(place.get("slug") or place.get("place_id") or "") == locked_slug
    if spec.get("meal"):
        if place.get("category") in meal_categories:
            return True
        return loose and bool(place_tags.intersection(meal_categories))
    if not categories:
        return True
    if "night_view" in tags and not spec.get("meal"):
        return (
            "night_view" in place_tags
            or place.get("category") in {"landmark", "neighborhood"}
            and _is_night_sensitive_place(place)
        )
    if place.get("category") in categories:
        return True
    if tags and place_tags.intersection(tags):
        return True
    return loose and place.get("category") in {"landmark", "museum", "neighborhood", "park", "cathedral", "cafe", "restaurant"}


def _slot_candidate_score(
    place: dict[str, Any],
    *,
    spec: dict[str, Any],
    profile: dict[str, Any],
    reference_place: dict[str, Any] | None,
    day_anchor: dict[str, Any] | None,
    context_place: dict[str, Any] | None,
    must_include: bool,
) -> float:
    categories = {category: 2.8 for category in spec.get("categories") or []}
    base_anchor = context_place or reference_place or day_anchor
    score = _score_place(place, categories=categories, themes=list(profile.get("themes") or []), anchor=base_anchor)
    slot = str(spec.get("slot") or "")
    spec_tags = _spec_tags(spec)
    place_tags = _place_theme_tags(place)
    locked_slug = str(spec.get("locked_slug") or "")
    score += 2.4 * len(spec_tags.intersection(place_tags))
    if place.get("category") in set(spec.get("categories") or []):
        score += 3.4
    if locked_slug and str(place.get("slug") or place.get("place_id") or "") == locked_slug:
        score += 12.0
    if must_include:
        score += 7.5
    if spec.get("meal"):
        if place.get("category") == "restaurant":
            score += 4.8
        elif place.get("category") == "cafe":
            score += 3.2
        elif place.get("category") in {"bakery", "bistro", "brasserie", "bar"}:
            score += 3.6
        meal_spec_tokens = set(profile.get("meal_preference_set") or set()).intersection(spec_tags)
        if meal_spec_tokens and (
            meal_spec_tokens.intersection(place_tags)
            or any(_matches_cuisine(place, token) for token in meal_spec_tokens)
        ):
            score += 4.5
    if slot == "morning" and spec_tags.intersection({"brunch", "coffee", "bakery"}):
        if place.get("category") in {"cafe", "bakery"}:
            score += 4.2
        elif place.get("category") == "neighborhood":
            score += 1.0
    if slot == "afternoon" and profile.get("prefers_cafe_dessert"):
        if place.get("category") in {"cafe", "bakery"}:
            score += 5.2
        elif any(token in place_tags for token in {"dessert", "bakery", "coffee", "cafe"}):
            score += 3.8
    if slot == "evening" and "night_view" in spec_tags and "night_view" in place_tags:
        score += 6.2
    if slot == "night" and "night_view" in spec_tags and "night_view" in place_tags:
        score += 4.8
    if profile.get("night_view") and slot in {"morning", "afternoon"} and "night_view" in place_tags and not spec.get("meal"):
        score -= 1.5 if must_include else 4.8
    if profile.get("prefers_french_dinner") and spec.get("meal") and slot == "evening":
        if any(_matches_cuisine(place, token) for token in ("french", "bistro", "brasserie")):
            score += 5.6
        elif place.get("category") in {"restaurant", "bistro", "brasserie"}:
            score += 3.0
    if profile.get("slow") and place.get("category") in {"park", "neighborhood", "cafe"} and slot in {"afternoon", "evening"}:
        score += 2.8
    if profile.get("budget_mode") == "save":
        admission = _admission_fee_amount(place) or 0
        if admission > 0:
            score -= min(7.0, admission / 6.0)
        if place.get("category") in {"park", "neighborhood"} or "walk" in place_tags:
            score += 2.4
    if profile.get("museum") and place.get("category") == "museum" and slot == "morning":
        score += 3.1
    if profile.get("local") and place.get("source") == "osm" and place.get("category") in {"restaurant", "cafe"}:
        score += 1.8
    prefer_featured = spec.get("prefer_featured", True)
    if prefer_featured and place.get("slug") in FEATURED_BY_SLUG:
        score += 3.0
    if not prefer_featured and place.get("slug") in FEATURED_BY_SLUG:
        score -= 1.2
    if reference_place is not None and place.get("slug") != reference_place.get("slug"):
        score += max(0.0, 2.6 - _distance_km(place["coordinates"], reference_place["coordinates"]))
    if day_anchor is not None and place.get("slug") != day_anchor.get("slug"):
        anchor_bonus = 4.4 if any(str(lock.get("slug") or "") == str(day_anchor.get("slug") or "") for lock in profile.get("locked_stops") or []) else 2.1
        score += max(0.0, anchor_bonus - _distance_km(place["coordinates"], day_anchor["coordinates"]))
    if context_place is not None and place.get("slug") != context_place.get("slug"):
        score += max(0.0, 2.9 - _distance_km(place["coordinates"], context_place["coordinates"]))
    return score


def _pick_place_for_spec(
    *,
    spec: dict[str, Any],
    profile: dict[str, Any],
    must_include_pool: list[dict[str, Any]],
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
    day_used_slugs: set[str],
    day_used_names: set[str],
    day_used_coordinates: set[str],
    reference_place: dict[str, Any] | None,
    day_anchor: dict[str, Any] | None,
    context_place: dict[str, Any] | None,
) -> dict[str, Any] | None:
    slot = str(spec.get("slot") or "")

    def is_available(place: dict[str, Any]) -> bool:
        normalized_name = normalize_text(str(place.get("name") or ""))
        normalized_slug = normalize_text(str(place.get("slug") or place.get("place_id") or ""))
        avoid_set = set(profile.get("must_avoid") or set())
        if normalized_name in avoid_set or normalized_slug in avoid_set:
            return False
        if _should_reserve_night_sensitive_place(place, profile=profile, slot=slot, spec=spec):
            return False
        return not _is_place_used(
            place,
            used_slugs=used_slugs.union(day_used_slugs),
            used_names=used_names.union(day_used_names),
            used_coordinates=used_coordinates.union(day_used_coordinates),
        )

    strict_unresolved = [place for place in must_include_pool if is_available(place) and _matches_slot_spec(place, spec, loose=False)]
    if strict_unresolved:
        chosen = max(
            strict_unresolved,
            key=lambda place: _slot_candidate_score(
                place,
                spec=spec,
                profile=profile,
                reference_place=reference_place,
                day_anchor=day_anchor,
                context_place=context_place,
                must_include=True,
            ),
        )
        must_include_pool[:] = [place for place in must_include_pool if place.get("slug") != chosen.get("slug")]
        return chosen

    allow_loose_must_include = (
        not profile.get("strict_constraints")
        and
        "night_view" not in _spec_tags(spec)
        and not spec.get("meal")
        and bool(set(spec.get("categories") or set()).intersection({"landmark", "museum", "cathedral"}))
    )
    loose_unresolved = [
        place for place in must_include_pool if allow_loose_must_include and is_available(place) and _matches_slot_spec(place, spec, loose=True)
    ]
    if loose_unresolved:
        chosen = max(
            loose_unresolved,
            key=lambda place: _slot_candidate_score(
                place,
                spec=spec,
                profile=profile,
                reference_place=reference_place,
                day_anchor=day_anchor,
                context_place=context_place,
                must_include=True,
            ),
        )
        must_include_pool[:] = [place for place in must_include_pool if place.get("slug") != chosen.get("slug")]
        return chosen

    strict_candidates = [place for place in CATALOG if is_available(place) and _matches_slot_spec(place, spec, loose=False)]
    loose_candidates = [place for place in CATALOG if is_available(place) and _matches_slot_spec(place, spec, loose=True)]
    candidates = strict_candidates or loose_candidates
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda place: _slot_candidate_score(
            place,
            spec=spec,
            profile=profile,
            reference_place=reference_place,
            day_anchor=day_anchor,
            context_place=context_place,
            must_include=False,
        ),
    )


def _should_reserve_night_sensitive_place(
    place: dict[str, Any],
    *,
    profile: dict[str, Any],
    slot: str,
    spec: dict[str, Any],
) -> bool:
    if slot in {"evening", "night"}:
        return False
    locked_stops = [lock for lock in profile.get("locked_stops") or [] if bool(lock.get("locked"))]
    if not locked_stops:
        return False
    place_slug = str(place.get("slug") or place.get("place_id") or "")
    return any(
        str(lock.get("target_slot") or "") in {"evening", "night"} and str(lock.get("slug") or "") == place_slug
        for lock in locked_stops
    )


def _force_remaining_must_includes(
    *,
    must_include_pool: list[dict[str, Any]],
    profile: dict[str, Any],
    used_slugs: set[str],
    used_names: set[str],
    used_coordinates: set[str],
) -> list[dict[str, Any]]:
    forced: list[dict[str, Any]] = []
    avoid_set = set(profile.get("must_avoid") or set())
    locked_by_slug = {
        str(lock.get("slug") or ""): dict(lock)
        for lock in profile.get("locked_stops") or []
        if bool(lock.get("locked")) and str(lock.get("slug") or "").strip()
    }
    remaining: list[dict[str, Any]] = []
    for place in must_include_pool:
        normalized_name = normalize_text(str(place.get("name") or ""))
        normalized_slug = normalize_text(str(place.get("slug") or place.get("place_id") or ""))
        if normalized_name in avoid_set or normalized_slug in avoid_set:
            continue
        if _is_place_used(place, used_slugs=used_slugs, used_names=used_names, used_coordinates=used_coordinates):
            continue
        remaining.append(place)

    for offset, place in enumerate(remaining):
        place_tags = _place_theme_tags(place)
        category = str(place.get("category") or "")
        place_slug = str(place.get("slug") or place.get("place_id") or "")
        locked_stop = locked_by_slug.get(place_slug)
        locked_target_slot = str((locked_stop or {}).get("target_slot") or "")
        preferred_slots = set(profile.get("preferred_slot_set") or set())
        if locked_target_slot in {"evening", "night"}:
            slot = "evening"
            start_time = "20:15" if locked_target_slot == "night" else "18:50"
        elif category in {"cathedral", "museum"}:
            slot = "morning"
            start_time = f"{9 + min(offset, 2)}:45"
        elif category == "park" and ("afternoon" in preferred_slots or profile.get("budget_mode") == "save"):
            slot = "afternoon"
            start_time = "15:10"
        else:
            slot = "afternoon"
            start_time = f"{15 + min(offset, 2)}:10"
        forced.append(
            {
                "place": place,
                "spec": {
                    "slot": slot,
                    "start_time": start_time,
                    "categories": {str(place.get("category") or "landmark")},
                    "tags": sorted(place_tags.union({"must_include"})),
                    "prefer_featured": True,
                    "forced_must_include": True,
                },
            }
        )
        _mark_place_used(
            place,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        )
    must_include_pool[:] = []
    return forced


def _selection_start_minutes(selection: dict[str, Any]) -> int:
    raw = str((selection.get("spec") or {}).get("start_time") or "")
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) * 60 + int(minute)
    except (ValueError, TypeError):
        slot = str((selection.get("spec") or {}).get("slot") or "")
        return {"morning": 9 * 60, "lunch": 12 * 60 + 30, "afternoon": 15 * 60, "evening": 18 * 60 + 30}.get(slot, 15 * 60)


def _sort_selections_by_time(selections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(selections, key=_selection_start_minutes)


def _compact_selections_for_constraints(selections: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    hard_slugs = {
        str(place.get("slug") or "")
        for place in (resolve_place(name) for name in profile.get("must_include_names") or [])
        if place is not None
    }
    meal_preferences = {str(value).lower() for value in profile.get("meal_preferences") or []}
    needs_evening_meal = bool(meal_preferences.intersection({"french", "bistro", "brasserie", "romantic"}))
    needs_cafe = bool(meal_preferences.intersection({"cafe", "coffee", "brunch", "dessert", "bakery"})) or bool(profile.get("prefers_cafe_dessert"))
    has_unneeded_evening_meal = any(
        bool((selection.get("spec") or {}).get("meal"))
        and str((selection.get("spec") or {}).get("slot") or "") == "evening"
        and not needs_evening_meal
        for selection in selections
    )
    target_count = 5 if len(selections) <= 6 and len(hard_slugs) >= 2 and has_unneeded_evening_meal else 6
    if len(selections) <= target_count:
        return selections

    compacted = list(selections)
    while len(compacted) > target_count:
        removable: list[tuple[int, int]] = []
        for index, selection in enumerate(compacted):
            place = selection.get("place") or {}
            spec = selection.get("spec") or {}
            slug = str(place.get("slug") or place.get("place_id") or "")
            if slug in hard_slugs or spec.get("forced_must_include") or spec.get("locked_slug"):
                continue

            category = str(place.get("category") or "")
            slot = str(spec.get("slot") or "")
            is_meal = bool(spec.get("meal"))
            score = 10
            if is_meal and slot == "evening" and not needs_evening_meal:
                score = 100
            elif not is_meal and slot in {"evening", "night"} and not profile.get("night_view"):
                score = 90
            elif not is_meal and category in {"landmark", "neighborhood"}:
                score = 80
            elif is_meal and not meal_preferences:
                score = 70
            elif category in {"cafe", "bakery"} and not needs_cafe:
                score = 60
            elif category in {"park", "garden"} and not profile.get("slow") and not profile.get("budget_mode") == "save":
                score = 40
            removable.append((score, index))
        if not removable:
            break
        _, remove_index = max(removable)
        compacted.pop(remove_index)
    return compacted


def _is_night_sensitive_place(place: dict[str, Any]) -> bool:
    name = normalize_text(str(place.get("name") or ""))
    tags = _place_theme_tags(place)
    if "night_view" in tags:
        return True
    return any(token in name for token in ("에펠", "eiffel", "센강", "seine", "개선문", "arc", "루브르", "louvre"))


def build_itinerary(create_plan_payload: dict[str, Any]) -> dict[str, Any]:
    dates = create_plan_payload.get("dates") or {}
    start_date = dates.get("start_date")
    days = max(1, int(dates.get("days") or 1))
    preferences = create_plan_payload.get("preferences") or {}
    planning_brief = _planning_brief(create_plan_payload)
    themes = _merge_unique_tokens(
        list(planning_brief.get("travel_style") or []),
        list(preferences.get("themes") or []),
        list(preferences.get("travel_style") or []),
    )
    must_include = list(planning_brief.get("must_include") or preferences.get("must_include") or [])
    must_avoid = list(planning_brief.get("must_avoid") or preferences.get("must_avoid") or [])
    profile = _itinerary_profile(create_plan_payload)
    used_slugs: set[str] = set()
    used_names: set[str] = set()
    used_coordinates: set[str] = set()
    itinerary_days: list[dict[str, Any]] = []
    route_names: list[str] = []
    selected_blueprints: list[str] = []
    must_include_pool = [place for place in (resolve_place(name) for name in must_include) if place is not None]

    for day_number in range(1, days + 1):
        blueprint = _apply_slot_preferences(_day_blueprint(day_number - 1, days, profile), profile)
        selected_blueprints.append(str(blueprint.get("archetype") or "general_landmark_day"))
        selections = _select_support_places(
            blueprint=blueprint,
            profile=profile,
            must_include_pool=must_include_pool,
            used_slugs=used_slugs,
            used_names=used_names,
            used_coordinates=used_coordinates,
        )
        selections.extend(
            _force_remaining_must_includes(
                must_include_pool=must_include_pool,
                profile=profile,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
            )
        )
        selections = _compact_selections_for_constraints(_sort_selections_by_time(selections), profile)
        items: list[dict[str, Any]] = []
        for index, selection in enumerate(selections, start=1):
            place = selection["place"]
            spec = selection["spec"]
            _mark_place_used(
                place,
                used_slugs=used_slugs,
                used_names=used_names,
                used_coordinates=used_coordinates,
            )
            route_names.append(place["name"])
            items.append(
                _build_itinerary_item_from_place(
                    place=place,
                    day_number=day_number,
                    slot=str(spec.get("slot") or "afternoon"),
                    item_index=index,
                    start_time=str(spec.get("start_time") or ""),
                    slot_tags=list(spec.get("tags") or []),
                    is_meal=bool(spec.get("meal")),
                    story_fields=_item_story_fields(place, spec=spec, blueprint=blueprint, profile=profile),
                )
            )

        day_date = None
        if start_date:
            day_date = (datetime.fromisoformat(start_date) + timedelta(days=day_number - 1)).date().isoformat()
        route_summary = blueprint.get("route_summary") or _build_day_summary(items)
        itinerary_days.append(
            {
                "id": f"day-{day_number}",
                "day_number": day_number,
                "date": day_date,
                "title": f"Day {day_number} - {blueprint['theme']}",
                "theme": f"Day {day_number} - {blueprint['theme']}",
                "dayTheme": f"Day {day_number} - {blueprint['theme']}",
                "daySummary": blueprint.get("summary") or _build_day_summary(items),
                "blueprintArchetype": blueprint.get("archetype"),
                "dayArchetype": blueprint.get("archetype"),
                "items": items,
                "route_summary": route_summary,
                "routeSummary": route_summary,
            }
        )

    unique_route_names = list(dict.fromkeys(route_names))
    if profile.get("night_view"):
        route_summary = "야경 취향을 우선해 저녁 하이라이트가 하루 후반부에 살아나도록 각 날짜의 흐름을 나눴습니다."
    elif profile.get("slow"):
        route_summary = "slow pace에 맞춰 하루 장소 수를 줄이고, 카페·산책·휴식이 끼어드는 리듬으로 파리 동선을 설계했습니다."
    else:
        route_summary = f"{' / '.join(unique_route_names[:5])}을 잇되, 하루마다 감정선이 달라지는 파리 코스로 정리했습니다."
    return {
        "planning_brief": planning_brief,
        "itinerary_days": itinerary_days,
        "route_summary": route_summary,
        "selected_places": unique_route_names,
        "selected_blueprints": selected_blueprints,
    }


def _build_day_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "아직 확정된 장소가 없습니다."
    highlights = [str(item.get("title") or "") for item in items[:3] if str(item.get("title") or "").strip()]
    if any(bool(item.get("isNightViewSpot")) for item in items):
        return f"{', '.join(highlights)} 중심으로 낮에는 감상 흐름을 만들고, 저녁에는 야경으로 감정을 모으는 구성입니다."
    if any(str(item.get("time_slot") or "") == "lunch" for item in items):
        return f"{', '.join(highlights)}을 중심축으로 두고 식사와 휴식이 자연스럽게 이어지도록 잡았습니다."
    return f"{', '.join(highlights)} 중심으로 이동 부담을 줄인 순서입니다."


def _build_itinerary_item_from_place(
    *,
    place: dict[str, Any],
    day_number: int,
    slot: str,
    item_index: int,
    start_time: str | None = None,
    slot_tags: list[str] | None = None,
    is_meal: bool = False,
    story_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_slot = {"dinner": "evening", "night": "evening"}.get(slot, slot)
    resolved_start_time = start_time or {
        "morning": "09:00",
        "lunch": "12:30",
        "afternoon": "15:00",
        "evening": "19:00",
    }.get(normalized_slot, "15:00")
    item = {
        "id": f"{day_number}-{place['slug']}-{item_index}",
        "time_slot": normalized_slot,
        "start_time": resolved_start_time,
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
        "slotTags": list(slot_tags or []),
        "isMeal": is_meal,
        "description": place["short_description"],
        "estimated_duration": place["estimated_visit_duration"],
        "area": _area_label(place),
    }
    if story_fields:
        item.update({key: value for key, value in story_fields.items() if value is not None})
    return item


def _item_story_fields(
    place: dict[str, Any],
    *,
    spec: dict[str, Any],
    blueprint: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    slot = str(spec.get("slot") or "")
    categories = set(spec.get("categories") or [])
    place_name = str(place.get("name") or "")
    place_category = str(place.get("category") or "")
    place_tags = _place_theme_tags(place)
    locked_label = str(spec.get("locked_label") or "")
    is_night_view = slot in {"evening", "night"} and "night_view" in place_tags

    if spec.get("meal") and slot == "evening" and profile.get("night_view"):
        preference_reason = f"야경 여행 스타일에 맞춰 {place_name}에서 식사한 뒤 저녁 하이라이트로 자연스럽게 이어지도록 배치했습니다."
        time_reason = "저녁 식사 뒤 빛이 살아나는 시간대의 포인트로 넘어갈 수 있게 해가 진 이후 구간으로 고정했습니다."
        description = f"{place_name}에서 한 번 쉬고 난 뒤 야경 포인트로 이어지는 흐름을 상정한 저녁 식사 구간입니다."
        slot_purpose = "야경 전 에너지를 비축하는 저녁 식사 구간입니다."
        expected = "식사와 이동이 따로 노는 느낌보다, 저녁 장면으로 넘어가기 전 호흡을 고르는 연결 구간처럼 느껴집니다."
        editable = "비슷한 가격대·분위기의 근처 저녁 식당으로 바꿔도 밤 장면 흐름은 유지하기 쉽습니다."
    elif spec.get("meal") and profile.get("slow"):
        preference_reason = f"slow pace에 맞춰 {place_name}에서 충분히 앉아 쉬며 다음 구간으로 넘어가도록 넣었습니다."
        time_reason = "오전 또는 직전 감상 구간 뒤에 식사를 배치해 하루 리듬이 뻣뻣해지지 않도록 했습니다."
        description = f"{place_name}은 빠르게 끼니만 해결하는 곳이 아니라 하루 속도를 한 번 낮추는 휴식용 식사 포인트입니다."
        slot_purpose = "관광 체크포인트 사이에 속도를 낮추는 휴식 식사 구간입니다."
        expected = "앉아 있는 시간이 일정의 일부처럼 느껴지는 여유 있는 식사 경험을 기대할 수 있습니다."
        editable = "인근 카페나 브런치 스팟으로 바꿔도 slow한 하루 리듬을 유지하기 쉽습니다."
    elif spec.get("meal"):
        preference_reason = f"{blueprint['theme']} 흐름을 끊지 않도록 {place_name}을 이동선 안쪽의 식사 구간으로 묶었습니다."
        time_reason = "다음 구간으로 넘어가기 전 체력과 집중력을 다시 채우기 좋은 타이밍에 넣었습니다."
        description = f"{place_name}은 단순한 식사 추가가 아니라 하루 동선을 무리 없이 이어 주는 중간 정차점입니다."
        slot_purpose = "하루 흐름을 이어 주는 식사 정차 구간입니다."
        expected = "식사 때문에 따로 먼 우회를 하지 않고도 분위기와 동선을 함께 챙길 수 있습니다."
        editable = "근처 다른 식당으로 바꿔도 전체 동선은 크게 흔들리지 않습니다."
    elif is_night_view:
        preference_reason = (
            f"{locked_label} 요청을 반영해 {place_name}을 빛과 분위기가 살아나는 시간대로 고정했습니다."
            if locked_label
            else f"야경 취향을 반영해 {place_name}의 빛과 분위기가 살아나는 시간대로 배치했습니다."
        )
        time_reason = "저녁 이후에 도착해야 장면의 밀도가 올라가는 포인트라 하루 후반부로 고정했습니다."
        description = f"{place_name}은 {blueprint['theme']}의 마지막 장면이 되도록 저녁 하이라이트로 잡은 장소입니다."
        slot_purpose = "하루의 감정선을 묶는 야경 하이라이트입니다."
        expected = "사진 한 장보다도 그날의 마지막 분위기가 기억에 남는 클로징 장면을 기대할 수 있습니다."
        editable = "다른 야경 포인트로 교체해도 저녁 클로징 구조는 그대로 유지하기 쉽습니다."
    elif place_category == "museum" or "museum" in categories:
        preference_reason = f"미술관·예술 선호를 반영해 {place_name}에 하루 초반 집중력을 쓰는 구조로 배치했습니다."
        time_reason = "오전이나 이른 오후에 두어 작품 감상 피로가 누적되기 전에 핵심 컬렉션을 보는 쪽이 유리합니다."
        description = f"{place_name}은 하루 서사의 중심축으로 두고, 앞뒤 동선을 가볍게 만들어 몰입감을 확보한 문화 감상 구간입니다."
        slot_purpose = "집중력이 좋은 시간대에 깊게 머무는 예술 감상 구간입니다."
        expected = "대표 작품을 훑고 지나가기보다, 한두 구역에 실제 시간을 쓰는 감상 경험을 기대할 수 있습니다."
        editable = "비슷한 성격의 다른 미술관으로 교체해도 오전 집중 구간이라는 구조는 유지됩니다."
    elif place_category in {"park", "neighborhood", "cafe"} or profile.get("slow"):
        preference_reason = f"{blueprint['theme']} 흐름에 맞춰 {place_name}을 체크리스트보다 분위기 체감이 중요한 구간으로 골랐습니다."
        time_reason = "오후에 두어 빛이 부드럽고 걷기 좋은 시간대를 활용하도록 했습니다."
        description = f"{place_name}은 장소 하나를 소비하기보다 거리의 호흡을 느끼는 산책·휴식 포인트 역할을 맡습니다."
        slot_purpose = "하루 속도를 늦추고 장면 전환을 만드는 산책 구간입니다."
        expected = "다음 장소로 급히 넘기지 않고 파리의 거리감을 몸으로 느끼는 시간이 됩니다."
        editable = "비슷한 분위기의 공원·거리·카페로 조정해도 하루 감성 축은 유지됩니다."
    else:
        preference_reason = f"{blueprint['theme']} 콘셉트에 맞춰 {place_name}을 그날 대표 장면 중 하나로 골랐습니다."
        time_reason = "앞뒤 이동과 체류 시간을 고려했을 때 이 시간대가 가장 무리 없이 이어지는 순서입니다."
        description = f"{place_name}은 단순히 점수를 높여 넣은 장소가 아니라 {blueprint['theme']}의 분위기를 지탱하는 핵심 스톱입니다."
        slot_purpose = "그날의 핵심 장면을 만드는 대표 명소 구간입니다."
        expected = "하루 안에서 이 장소가 왜 들어갔는지 납득되는 연결감을 느끼게 됩니다."
        editable = "비슷한 결의 명소로 바꿔도 전체 하루 콘셉트는 유지할 수 있습니다."

    return {
        "description": description,
        "reasoning": preference_reason,
        "slotPurpose": slot_purpose,
        "userPreferenceReason": preference_reason,
        "timeReason": time_reason,
        "expectedExperience": expected,
        "editableReason": editable,
        "isNightViewSpot": is_night_view,
        "slotLockReason": locked_label or None,
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
        return {"restaurant", "cafe", "bakery", "bistro", "brasserie", "bar"}
    if category == "cafe":
        return {"cafe", "bakery", "restaurant"}
    if category == "night_view":
        return {"landmark", "neighborhood"}
    if category:
        return {category}
    if target_slot == "lunch":
        return {"restaurant", "cafe", "bakery", "bistro", "brasserie", "bar"}
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
    preferred_category = "restaurant" if target_slot in {"lunch", "evening", "dinner"} or cuisine else "cafe"
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
            place["category"] != preferred_category,
            place["slug"] not in FEATURED_BY_SLUG,
            place["name"],
        ),
    )
    return export_place(candidates[0]) if candidates else None


def _rebuild_selected_places(itinerary_days: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for day in itinerary_days:
        for item in day.get("items", []):
            if item.get("itemKind") == "gap" or item.get("nearbyMealNeeded"):
                continue
            category = str(((item.get("place") or {}).get("category")) or "").lower()
            if category in {"free_time", "rest", "buffer", "meal_placeholder"}:
                continue
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
        day_summary = _build_day_summary(items)
        day["daySummary"] = day_summary
        day["route_summary"] = day_summary
        day["routeSummary"] = day_summary

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
