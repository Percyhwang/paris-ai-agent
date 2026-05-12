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

OSM_PLACES_PATH = Path(__file__).resolve().parents[2] / "data_assets" / "paris_places_clean.json"

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


ALIASES = {normalize_text(key): value for key, value in RAW_ALIASES.items()}


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
    return places


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
        "admission_fee": place["admission_fee"],
        "location": place["location"],
        "tags": list(place["tags"]),
        "popularity": place["popularity"],
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
    if normalized_category == "restaurant":
        normalized_category = "cafe"
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
        if venue_type in {"cafe", "restaurant"} and place["category"] not in {"cafe", "neighborhood"}:
            continue
        score = _score_place(place, categories=categories, themes=themes, anchor=resolved_anchor)
        picks.append((score, place))

    picks.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    used_slugs: set[str] = set()

    for requested in must_include or []:
        resolved = resolve_place(requested)
        if resolved and resolved["slug"] not in used_slugs:
            used_slugs.add(resolved["slug"])
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
        if place["slug"] in used_slugs:
            continue
        used_slugs.add(place["slug"])
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
            if place["slug"] not in used_slugs
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

    for slot in daily_slots:
        if slot == "morning":
            picks.append(anchor)
            day_used_slugs.add(anchor["slug"])
            continue
        candidate = next(
            (
                place
                for place in ordered
                if place["slug"] not in day_used_slugs
                and (
                    (
                        slot == "lunch"
                        and (
                            (prefer_cafe and place["category"] in {"cafe", "neighborhood"})
                            or (not prefer_cafe and place["category"] in {"neighborhood", "park", "landmark", "museum", "cathedral"})
                        )
                    )
                    or (slot == "afternoon" and place["category"] in {"museum", "landmark", "neighborhood", "park", "cathedral"})
                    or (slot == "evening" and place["category"] in {"landmark", "neighborhood", "cafe"})
                )
            ),
            None,
        )
        if candidate is None:
            candidate_pool = FEATURED_PLACES if prefer_featured else CATALOG
            candidate = next(
                (
                    place
                    for place in sorted(
                        candidate_pool,
                        key=lambda item: _score_place(item, categories=categories, themes=themes, anchor=anchor),
                        reverse=True,
                    )
                    if place["slug"] not in day_used_slugs and place["slug"] != anchor["slug"]
                ),
                anchor,
            )
        picks.append(candidate)
        day_used_slugs.add(candidate["slug"])
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
        "slow": ["morning", "afternoon"],
        "normal": ["morning", "lunch", "afternoon"],
        "fast": ["morning", "lunch", "afternoon", "evening"],
    }
    daily_slots = slot_templates.get(pace, slot_templates["normal"])
    used_slugs: set[str] = set()
    itinerary_days: list[dict[str, Any]] = []
    route_names: list[str] = []

    for day_number in range(1, days + 1):
        anchor = venue_seed[(day_number - 1) % len(venue_seed)]
        supports = _select_support_places(
            anchor,
            themes=themes,
            daily_slots=daily_slots,
            used_slugs=used_slugs,
        )
        items: list[dict[str, Any]] = []
        for index, (slot, place) in enumerate(zip(daily_slots, supports), start=1):
            used_slugs.add(place["slug"])
            route_names.append(place["name"])
            start_time = {
                "morning": "09:00",
                "lunch": "12:30",
                "afternoon": "15:00",
                "evening": "19:00",
            }[slot]
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
        if normalize_text(item_name) == normalized_name:
            return index
    return None


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
