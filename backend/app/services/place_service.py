from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from app.services.google_places_service import fetch_place_by_id, search_paris_places
from app.services.place_repository_service import coordinates_from_place_document


async def list_places(
    api_base_url: str,
    db: Any | None = None,
    search: str | None = None,
    category: str | None = None,
    sort: str = "popular",
    language: str = "ko",
) -> list[dict]:
    db_places = await _list_places_from_db(
        db,
        api_base_url=api_base_url,
        search=search,
        category=category,
        sort=sort,
        language=language,
    )
    if len(db_places) >= 8:
        return db_places
    try:
        return await search_paris_places(
            search=search,
            category=category,
            sort=sort,
            api_base_url=api_base_url,
            language=language,
        )
    except HTTPException:
        if db_places:
            return db_places
        raise


async def get_place(
    api_base_url: str,
    place_id: str,
    db: Any | None = None,
    language: str = "ko",
) -> dict:
    db_place = await _get_place_from_db(db, api_base_url=api_base_url, place_id=place_id, language=language)
    if db_place:
        return db_place
    return await fetch_place_by_id(place_id=place_id, api_base_url=api_base_url, language=language)


async def _list_places_from_db(
    db: Any | None,
    *,
    api_base_url: str,
    search: str | None,
    category: str | None,
    sort: str,
    language: str,
) -> list[dict]:
    if db is None:
        return []
    query: dict[str, Any] = {}
    if category and category != "all":
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"aliases": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.places.find(query).limit(60).to_list(length=60)
    places = [_normalize_db_place(doc, api_base_url=api_base_url, language=language) for doc in docs if isinstance(doc, dict)]
    if sort == "name":
        places.sort(key=lambda place: str(place.get("name") or "").lower())
    else:
        places.sort(key=lambda place: (-int(place.get("popularity") or 0), str(place.get("name") or "").lower()))
    return places[:30]


async def _get_place_from_db(db: Any | None, *, api_base_url: str, place_id: str, language: str) -> dict | None:
    if db is None:
        return None
    doc = await db.places.find_one({"$or": [{"slug": place_id}, {"place_id": place_id}, {"name": place_id}]})
    if not isinstance(doc, dict):
        try:
            from bson import ObjectId

            doc = await db.places.find_one({"_id": ObjectId(place_id)})
        except Exception:
            doc = None
    if not isinstance(doc, dict):
        return None
    return _normalize_db_place(doc, api_base_url=api_base_url, language=language)


def _normalize_db_place(doc: dict[str, Any], *, api_base_url: str, language: str) -> dict:
    coordinates = coordinates_from_place_document(doc)
    slug = str(doc.get("slug") or doc.get("place_id") or doc.get("_id") or "")
    raw_name = str(doc.get("name") or "")
    name = _localized_place_name(raw_name, language)
    category = str(doc.get("category") or "landmark")
    description = str(doc.get("short_description") or doc.get("description") or _fallback_place_description(name, category, language))
    full_description = str(doc.get("full_description") or description)
    duration = doc.get("estimated_visit_duration") or doc.get("estimated_duration") or "1-2 hours"
    image_url = doc.get("image_url") or doc.get("photo_url") or _build_place_photo_url(api_base_url, raw_name or name)
    location = _string_location(doc)
    history = doc.get("history") or _fallback_place_history(name, category, language)
    photo_tips = list(doc.get("photo_spot_tips") or _fallback_photo_tips(category, language))
    return {
        "id": slug,
        "slug": slug,
        "place_id": slug,
        "name": name,
        "category": category,
        "categoryLabel": category,
        "category_label": category,
        "description": description,
        "short_description": description,
        "full_description": full_description,
        "history": history,
        "address": location,
        "location": location,
        "coordinates": coordinates,
        "tags": list(doc.get("tags") or []),
        "popularity": int(doc.get("popularity") or 0),
        "estimatedDuration": duration,
        "estimated_visit_duration": duration,
        "image_url": image_url,
        "photoUrl": image_url,
        "photo_spot_tips": photo_tips,
        "admission_fee": doc.get("admission_fee"),
        "googleMapsUri": doc.get("google_maps_uri"),
        "google_maps_uri": doc.get("google_maps_uri"),
        "rating": doc.get("rating"),
        "reviewCount": doc.get("review_count"),
        "review_count": doc.get("review_count"),
        "source": doc.get("source") or "place_db",
    }


def _build_place_photo_url(api_base_url: str, name: str) -> str:
    base = api_base_url.rstrip("/")
    if not base.endswith("/api"):
        base = f"{base}/api"
    return f"{base}/places/photo?name={quote(name, safe='')}"


def _string_location(doc: dict[str, Any]) -> str:
    for key in ("address", "formatted_address", "short_address"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = doc.get("location")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Paris, France"


def _localized_place_name(name: str, language: str) -> str:
    if language == "en":
        return name
    return _KO_PLACE_NAMES.get(name, name)


def _fallback_place_description(name: str, category: str, language: str) -> str:
    if language == "ko":
        category_label = {
            "landmark": "파리 대표 명소",
            "museum": "파리 미술관/박물관 스팟",
            "cathedral": "역사적인 성당",
            "park": "여유로운 공원 스팟",
            "shopping": "쇼핑 스팟",
            "restaurant": "미식 스팟",
            "cafe": "카페 스팟",
        }.get(category, "파리 스팟")
        return f"{name}은 일정 동선에 자연스럽게 넣기 좋은 {category_label}입니다."

    category_label = {
        "landmark": "classic Paris landmark",
        "museum": "Paris museum stop",
        "cathedral": "historic Paris cathedral",
        "park": "relaxed Paris green space",
        "shopping": "Paris shopping stop",
        "restaurant": "Paris food stop",
        "cafe": "Paris cafe stop",
    }.get(category, "Paris place")
    return f"{name} is a {category_label} that works well in a travel route."


def _fallback_place_history(name: str, category: str, language: str) -> str:
    if language == "ko":
        category_label = {
            "landmark": "파리의 분위기와 상징적인 장면을 함께 느낄 수 있는 명소",
            "museum": "예술과 전시를 중심으로 하루의 깊이를 더해주는 장소",
            "cathedral": "건축과 역사적인 분위기를 함께 경험하기 좋은 장소",
            "park": "산책과 휴식을 일정 중간에 넣기 좋은 장소",
            "shopping": "파리의 쇼핑 리듬과 도심 동선을 함께 잡기 좋은 장소",
        }.get(category, "파리 여행 흐름에 넣기 좋은 장소")
        return f"{name}은 {category_label}입니다."
    return _fallback_place_description(name, category, language)


def _fallback_photo_tips(category: str, language: str) -> list[str]:
    if language == "ko":
        tips = {
            "landmark": ["정면보다 살짝 떨어진 거리에서 전체 실루엣을 담아보세요.", "오전 이른 시간이나 해질녘에는 빛이 부드러워 사진이 더 잘 나옵니다."],
            "museum": ["입장 전 외관과 광장 구도를 먼저 담아보세요.", "주변 정원이나 강변과 함께 잡으면 더 파리다운 장면이 됩니다."],
            "cathedral": ["광장 건너편에서 정면 구도로 담으면 건축의 균형이 잘 살아납니다.", "스테인드글라스나 세부 조각은 밝은 시간대에 보기 좋습니다."],
            "park": ["나무길이나 분수를 프레임으로 활용해보세요.", "아침이나 늦은 오후가 산책 사진에 가장 편안합니다."],
            "shopping": ["쇼윈도와 거리 분위기를 함께 담으면 더 생동감 있습니다.", "실내 조명 아래에서는 넓은 구도보다 디테일 컷이 좋습니다."],
        }
        return tips.get(category, ["방문 전 최근 사진과 혼잡도를 확인하면 더 좋은 시간대를 고르기 쉽습니다."])
    return ["Go early or near sunset for softer light.", "Step back to include the surrounding Paris street scene."]


_KO_PLACE_NAMES = {
    "Arc de Triomphe": "개선문",
    "Champs-Elysees": "샹젤리제 거리",
    "Eiffel Tower": "에펠탑",
    "Galeries Lafayette": "갤러리 라파예트",
    "Le Bon Marche": "르 봉 마르셰",
    "Le Marais": "마레 지구",
    "Louvre Museum": "루브르 박물관",
    "Luxembourg Gardens": "뤽상부르 공원",
    "Montmartre": "몽마르트르",
    "Musee d'Orsay": "오르세 미술관",
    "Notre-Dame": "노트르담 대성당",
    "Palais Garnier": "오페라 가르니에",
    "Palais Royal": "팔레 루아얄",
    "Saint-Germain-des-Pres": "생제르맹데프레",
    "Sainte-Chapelle": "생트 샤펠",
    "Seine River": "센강",
    "Tuileries Garden": "튈르리 정원",
}
