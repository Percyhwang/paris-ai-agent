import asyncio
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.core.config import settings

GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
GOOGLE_PLACES_PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{photo_name}/media"
DEFAULT_PLACE_IMAGE = (
    "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=1200&q=80"
)
PARIS_CENTER = {"latitude": 48.8566, "longitude": 2.3522}
PARIS_LOCATION_BIAS = {
    "circle": {
        "center": PARIS_CENTER,
        "radius": 12000.0,
    }
}
SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.name",
        "places.displayName",
        "places.formattedAddress",
        "places.shortFormattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.photos",
        "places.rating",
        "places.userRatingCount",
        "places.googleMapsUri",
    ]
)
DETAIL_FIELD_MASK = ",".join(
    [
        "id",
        "name",
        "displayName",
        "formattedAddress",
        "shortFormattedAddress",
        "location",
        "types",
        "primaryType",
        "primaryTypeDisplayName",
        "photos",
        "rating",
        "userRatingCount",
        "googleMapsUri",
    ]
)
CATEGORY_QUERY_CONFIG = {
    "landmark": {
        "query": "famous landmarks in Paris, France",
        "included_type": "tourist_attraction",
        "page_size": 8,
    },
    "museum": {
        "query": "best museums in Paris, France",
        "included_type": "museum",
        "page_size": 8,
    },
    "cathedral": {
        "query": "famous cathedrals in Paris, France",
        "included_type": "church",
        "page_size": 6,
    },
    "park": {
        "query": "beautiful parks in Paris, France",
        "included_type": "park",
        "page_size": 6,
    },
    "neighborhood": {
        "query": "best neighborhoods to visit in Paris, France",
        "included_type": None,
        "page_size": 6,
    },
}
CATEGORY_DURATIONS = {
    "landmark": "1-2시간",
    "museum": "2-4시간",
    "cathedral": "45-90분",
    "park": "1-2시간",
    "neighborhood": "2-3시간",
}

CATEGORY_DURATIONS_EN = {
    "landmark": "1-2 hours",
    "museum": "2-4 hours",
    "cathedral": "45-90 minutes",
    "park": "1-2 hours",
    "neighborhood": "2-3 hours",
}

CATEGORY_LABELS = {
    "landmark": "랜드마크",
    "museum": "박물관",
    "cathedral": "성당",
    "park": "공원",
    "neighborhood": "동네",
    "all": "전체",
}

CATEGORY_LABELS_EN = {
    "landmark": "landmark",
    "museum": "museum",
    "cathedral": "cathedral",
    "park": "park",
    "neighborhood": "neighborhood",
    "all": "all",
}

PLACE_TYPE_LABELS = {
    "tourist_attraction": "관광명소",
    "museum": "박물관",
    "art_gallery": "미술관",
    "art_museum": "미술관",
    "church": "성당",
    "park": "공원",
    "neighborhood": "동네",
    "historical_landmark": "역사 명소",
    "cultural_landmark": "문화 명소",
    "monument": "기념물",
    "garden": "정원",
    "botanical_garden": "식물원",
    "place_of_worship": "종교 명소",
    "point_of_interest": "관심 장소",
    "establishment": "방문 장소",
}

TAG_LABELS = {
    "landmark": "랜드마크",
    "museum": "박물관",
    "cathedral": "성당",
    "park": "공원",
    "neighborhood": "동네",
    "tourist_attraction": "관광명소",
    "museum_store": "뮤지엄 숍",
    "art_gallery": "미술관",
    "art_museum": "미술관",
    "church": "성당",
    "park": "공원",
    "historical_landmark": "역사 명소",
    "cultural_landmark": "문화 명소",
    "monument": "기념물",
    "garden": "정원",
    "botanical_garden": "식물원",
    "place_of_worship": "종교 명소",
    "point_of_interest": "관심 장소",
    "establishment": "방문 장소",
    "paris": "파리",
}


@dataclass(frozen=True)
class SearchPlan:
    text_query: str
    category: str
    included_type: str | None
    page_size: int


def google_places_enabled() -> bool:
    return bool(settings.google_places_api_key)


def google_food_search_enabled() -> bool:
    return google_places_enabled() and settings.enable_google_food_search


async def search_paris_places(
    search: str | None,
    category: str | None,
    sort: str,
    api_base_url: str,
    language: str = "ko",
) -> list[dict[str, Any]]:
    if not google_places_enabled():
        raise HTTPException(status_code=400, detail="Google Places API is not configured")

    plans = _build_search_plans(search=search, category=category)
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key or "",
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [client.post(GOOGLE_PLACES_TEXT_SEARCH_URL, json=_build_search_body(plan, language), headers=headers) for plan in plans]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    normalized_places: list[dict[str, Any]] = []
    google_errors: list[str] = []
    for plan, response in zip(plans, responses, strict=False):
        if isinstance(response, Exception):
            google_errors.append("Google Places API request failed. Check backend network access.")
            continue
        if response.is_error:
            google_errors.append(_google_places_error_message(response))
            continue
        payload = response.json()
        for place in payload.get("places", []):
            normalized = _normalize_google_place(
                place=place,
                api_base_url=api_base_url,
                forced_category=None if category in (None, "", "all") and search else plan.category,
                language=language,
            )
            if normalized:
                normalized_places.append(normalized)

    deduped_places = list(_dedupe_places(normalized_places).values())
    if not deduped_places:
        if google_errors:
            raise HTTPException(status_code=502, detail=google_errors[0])
        raise HTTPException(status_code=502, detail="Google Places API returned no Paris places")

    if category and category != "all":
        deduped_places = [place for place in deduped_places if place["category"] == category]
    if sort == "name":
        deduped_places.sort(key=lambda place: place["name"].lower())
    else:
        deduped_places.sort(key=lambda place: (-place["popularity"], place["name"].lower()))
    return deduped_places[:30]


async def fetch_place_by_id(place_id: str, api_base_url: str, language: str = "ko") -> dict[str, Any]:
    if not google_places_enabled():
        raise HTTPException(status_code=400, detail="Google Places API is not configured")

    headers = {
        "X-Goog-Api-Key": settings.google_places_api_key or "",
        "X-Goog-FieldMask": DETAIL_FIELD_MASK,
    }
    url = GOOGLE_PLACES_DETAILS_URL.format(place_id=place_id)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            url,
            headers=headers,
            params={"languageCode": _google_places_language_code(language), "regionCode": "FR"},
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Place not found")
    if response.is_error:
        raise HTTPException(status_code=502, detail=_google_places_error_message(response))

    normalized = _normalize_google_place(
        place=response.json(),
        api_base_url=api_base_url,
        forced_category=None,
        language=language,
    )
    if not normalized:
        raise HTTPException(status_code=404, detail="Place not found")
    return normalized


async def search_google_food_places(
    *,
    cuisine: str,
    center: dict[str, float],
    language: str = "ko",
    radius_meters: float = 2500.0,
    page_size: int = 12,
) -> list[dict[str, Any]]:
    if not google_food_search_enabled():
        return []

    body = {
        "textQuery": _google_food_text_query(cuisine),
        "pageSize": page_size,
        "languageCode": _google_places_language_code(language),
        "regionCode": "FR",
        "includedType": _google_food_included_type(cuisine),
        "strictTypeFiltering": True,
        "locationBias": {
            "circle": {
                "center": {"latitude": center["lat"], "longitude": center["lng"]},
                "radius": radius_meters,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key or "",
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }

    async with httpx.AsyncClient(timeout=12) as client:
        try:
            response = await client.post(GOOGLE_PLACES_TEXT_SEARCH_URL, json=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError:
            return []

    return [
        normalized
        for place in response.json().get("places", [])
        if (normalized := _normalize_google_food_candidate(place, cuisine=cuisine, language=language)) is not None
    ]


async def fetch_place_photo_bytes(
    photo_name: str,
    max_width_px: int = 1200,
) -> tuple[bytes, str]:
    if not google_places_enabled():
        raise HTTPException(status_code=404, detail="Google Places photo API is not configured")

    headers = {"X-Goog-Api-Key": settings.google_places_api_key or ""}
    params = {"maxWidthPx": max_width_px}
    url = GOOGLE_PLACES_PHOTO_MEDIA_URL.format(photo_name=photo_name)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.is_error:
        raise HTTPException(status_code=404, detail="Place photo not found")

    return response.content, response.headers.get("content-type", "image/jpeg")


def get_default_place_image() -> str:
    return DEFAULT_PLACE_IMAGE


def _google_places_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "Google Places API request failed. Check the Places API key and project settings."

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "Google Places API request failed. Check the Places API key and project settings."

    details = error.get("details") or []
    reason = None
    for detail in details:
        if isinstance(detail, dict) and detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
            reason = detail.get("reason")
            break

    if reason == "API_KEY_IP_ADDRESS_BLOCKED":
        return (
            "Google Places API key IP restriction is blocking this backend server. "
            "Add the server IP to the key restrictions or use a server-side Places API key."
        )
    if reason == "API_KEY_HTTP_REFERRER_BLOCKED":
        return (
            "Google Places API key referrer restriction is blocking this backend request. "
            "Use an IP-restricted server key for backend Places API calls."
        )
    if reason == "SERVICE_DISABLED":
        return "Google Places API is disabled for this Google Cloud project."
    if reason == "API_KEY_SERVICE_BLOCKED":
        return "This API key is not allowed to call Google Places API."

    message = error.get("message")
    if isinstance(message, str) and message:
        return _sanitize_google_error_message(message)
    return "Google Places API request failed. Check the Places API key and project settings."


def _sanitize_google_error_message(message: str) -> str:
    sanitized = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[server IP]", message)
    sanitized = re.sub(r"AIza[0-9A-Za-z_-]+", "[API key]", sanitized)
    return sanitized


def _build_search_plans(search: str | None, category: str | None) -> list[SearchPlan]:
    normalized_category = category if category and category != "all" else None
    if search:
        if normalized_category and normalized_category in CATEGORY_QUERY_CONFIG:
            config = CATEGORY_QUERY_CONFIG[normalized_category]
            return [
                SearchPlan(
                    text_query=f"{search} in Paris, France",
                    category=normalized_category,
                    included_type=config["included_type"],
                    page_size=12,
                )
            ]
        return [SearchPlan(text_query=f"{search} in Paris, France", category="all", included_type=None, page_size=12)]

    if normalized_category and normalized_category in CATEGORY_QUERY_CONFIG:
        config = CATEGORY_QUERY_CONFIG[normalized_category]
        return [
            SearchPlan(
                text_query=config["query"],
                category=normalized_category,
                included_type=config["included_type"],
                page_size=config["page_size"],
            )
        ]

    return [
        SearchPlan(
            text_query=config["query"],
            category=category_name,
            included_type=config["included_type"],
            page_size=config["page_size"],
        )
        for category_name, config in CATEGORY_QUERY_CONFIG.items()
    ]


def _build_search_body(plan: SearchPlan, language: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "textQuery": plan.text_query,
        "pageSize": plan.page_size,
        "languageCode": _google_places_language_code(language),
        "regionCode": "FR",
        "locationBias": PARIS_LOCATION_BIAS,
    }
    if plan.included_type:
        body["includedType"] = plan.included_type
        body["strictTypeFiltering"] = True
    return body


def _normalize_google_place(
    place: dict[str, Any],
    api_base_url: str,
    forced_category: str | None,
    language: str,
) -> dict[str, Any] | None:
    place_id = place.get("id")
    display_name = _extract_text(place.get("displayName")) or "Paris place"
    category = _map_category(place=place, forced_category=forced_category)
    if not category or not place_id:
        return None

    coordinates = place.get("location") or {}
    lat = coordinates.get("latitude", 48.8566)
    lng = coordinates.get("longitude", 2.3522)
    short_address = place.get("shortFormattedAddress") or place.get("formattedAddress") or "Paris, France"
    primary_type_display = _extract_text(place.get("primaryTypeDisplayName")) or category.title()
    rating = float(place.get("rating", 0) or 0)
    review_count = int(place.get("userRatingCount", 0) or 0)

    return {
        "id": place_id,
        "slug": _slugify(f"{display_name}-{place_id[:6]}"),
        "name": display_name,
        "category": category,
        "coordinates": {"lat": lat, "lng": lng},
        "image_url": _build_photo_proxy_url(place=place, api_base_url=api_base_url),
        "short_description": _build_short_description(
            category=category,
            primary_type_display=primary_type_display,
            rating=rating,
            review_count=review_count,
            language=language,
        ),
        "full_description": _build_full_description(
            name=display_name,
            category=category,
            address=short_address,
            primary_type_display=primary_type_display,
            rating=rating,
            review_count=review_count,
            language=language,
        ),
        "history": _build_history_summary(
            name=display_name,
            category=category,
            primary_type_display=primary_type_display,
            language=language,
        ),
        "photo_spot_tips": _build_photo_tips(category=category, language=language),
        "estimated_visit_duration": (
            CATEGORY_DURATIONS_EN.get(category, "1-2 hours")
            if language == "en"
            else CATEGORY_DURATIONS.get(category, "1-2시간")
        ),
        "admission_fee": _estimate_fee(category=category, language=language),
        "location": short_address,
        "tags": _build_tags(category=category, place=place),
        "popularity": _build_popularity_score(rating=rating, review_count=review_count),
        "rating": rating or None,
        "review_count": review_count,
        "google_place_id": place_id,
        "google_resource_name": place.get("name"),
        "google_maps_uri": place.get("googleMapsUri"),
        "source": "google_places_new",
    }


def _normalize_google_food_candidate(
    place: dict[str, Any],
    *,
    cuisine: str,
    language: str,
) -> dict[str, Any] | None:
    place_id = place.get("id")
    display_name = _extract_text(place.get("displayName"))
    coordinates = place.get("location") or {}
    lat = coordinates.get("latitude")
    lng = coordinates.get("longitude")
    if not place_id or not display_name or lat is None or lng is None:
        return None

    rating = float(place.get("rating", 0) or 0)
    review_count = int(place.get("userRatingCount", 0) or 0)
    short_address = place.get("shortFormattedAddress") or place.get("formattedAddress") or "Paris, France"
    rating_summary = _food_rating_summary(rating=rating, review_count=review_count, language=language)
    return {
        "id": place_id,
        "slug": _slugify(f"{display_name}-{place_id[:6]}"),
        "name": display_name,
        "category": _google_food_category(cuisine),
        "coordinates": {"lat": float(lat), "lng": float(lng)},
        "image_url": DEFAULT_PLACE_IMAGE,
        "short_description": rating_summary,
        "full_description": f"{display_name} near {short_address}. {rating_summary}",
        "history": "",
        "photo_spot_tips": [display_name, short_address, "Check Google Maps before visiting."],
        "estimated_visit_duration": "1 hour",
        "admission_fee": None,
        "location": short_address,
        "tags": list(dict.fromkeys(["restaurant", "foodie", cuisine, *(place.get("types") or [])[:3], "paris"])),
        "cuisine": [cuisine],
        "popularity": _build_popularity_score(rating=rating, review_count=review_count),
        "rating": rating or None,
        "review_count": review_count,
        "google_place_id": place_id,
        "google_resource_name": place.get("name"),
        "google_maps_uri": place.get("googleMapsUri"),
        "source": "google_places_new",
    }


def _google_food_text_query(cuisine: str) -> str:
    cuisine_queries = {
        "pasta": "pasta restaurant in Paris, France",
        "pizza": "pizza restaurant in Paris, France",
        "italian": "Italian restaurant in Paris, France",
        "french": "French bistro restaurant in Paris, France",
        "korean": "Korean restaurant in Paris, France",
        "sushi": "sushi restaurant in Paris, France",
        "ramen": "ramen restaurant in Paris, France",
        "japanese": "Japanese restaurant in Paris, France",
        "chinese": "Chinese restaurant in Paris, France",
        "thai": "Thai restaurant in Paris, France",
        "indian": "Indian restaurant in Paris, France",
        "vietnamese": "Vietnamese restaurant in Paris, France",
        "mexican": "Mexican taco restaurant in Paris, France",
        "mediterranean": "Mediterranean restaurant in Paris, France",
        "lebanese": "Lebanese restaurant in Paris, France",
        "moroccan": "Moroccan restaurant in Paris, France",
        "burger": "burger restaurant in Paris, France",
        "steak": "steakhouse restaurant in Paris, France",
        "seafood": "seafood restaurant in Paris, France",
        "vegetarian": "vegetarian restaurant in Paris, France",
        "brunch": "brunch cafe in Paris, France",
        "bakery": "croissant bakery in Paris, France",
        "coffee": "coffee shop in Paris, France",
        "dessert": "dessert cafe in Paris, France",
    }
    return cuisine_queries.get(cuisine, f"{cuisine} restaurant in Paris, France")


def _google_food_included_type(cuisine: str) -> str:
    if cuisine == "bakery":
        return "bakery"
    if cuisine in {"coffee", "dessert", "brunch"}:
        return "cafe"
    return "restaurant"


def _google_food_category(cuisine: str) -> str:
    return "cafe" if cuisine in {"bakery", "coffee", "dessert", "brunch"} else "restaurant"


def _food_rating_summary(*, rating: float, review_count: int, language: str) -> str:
    if language == "en":
        if rating and review_count:
            return f"Google Maps rating {rating:.1f}/5 from about {review_count} reviews."
        if rating:
            return f"Google Maps rating {rating:.1f}/5."
        return "Food stop selected near the route from Google Places."
    if rating and review_count:
        return f"Google Maps rating {rating:.1f}/5 from about {review_count} reviews."
    if rating:
        return f"Google Maps rating {rating:.1f}/5."
    return "Food stop selected near the route from Google Places."


def _map_category(place: dict[str, Any], forced_category: str | None) -> str | None:
    primary_type = place.get("primaryType") or ""
    types = set(place.get("types") or [])
    normalized_types = {primary_type, *types}

    if "museum" in normalized_types or "art_gallery" in normalized_types:
        return "museum"
    if "park" in normalized_types:
        return "park"
    if "church" in normalized_types or "hindu_temple" in normalized_types or "mosque" in normalized_types:
        return "cathedral"
    if {
        "tourist_attraction",
        "historical_landmark",
        "cultural_landmark",
        "monument",
    } & normalized_types:
        return "landmark"
    if "neighborhood" in normalized_types:
        return "neighborhood"
    return forced_category


def _build_photo_proxy_url(place: dict[str, Any], api_base_url: str) -> str:
    photos = place.get("photos") or []
    if not photos:
        return DEFAULT_PLACE_IMAGE

    photo_name = photos[0].get("name")
    if not photo_name:
        return DEFAULT_PLACE_IMAGE

    encoded_name = quote(photo_name, safe="")
    return f"{api_base_url}/api/places/photo?name={encoded_name}"


def _build_short_description(
    category: str,
    primary_type_display: str,
    rating: float,
    review_count: int,
    language: str,
) -> str:
    place_type = _translate_place_type(primary_type_display, category, language)
    if language == "en":
        if rating and review_count:
            return f"A popular Paris {place_type} with a {rating:.1f}/5 Google rating from about {review_count} reviews."
        if rating:
            return f"A frequently visited Paris {place_type} with a Google Maps rating of {rating:.1f}/5."
        return f"A well-known Paris {place_type} often included in city itineraries."
    if rating and review_count:
        return f"파리에서 꾸준히 사랑받는 대표 {place_type} 명소예요. Google 리뷰 약 {review_count}건 기준 평점 {rating:.1f}/5를 받고 있어요."
    if rating:
        return f"파리에서 많이 찾는 대표 {place_type} 명소예요. Google Maps 평점 {rating:.1f}/5를 기록 중이에요."
    return f"파리 여행 동선에 자주 포함되는 대표 {place_type}입니다."


def _build_full_description(
    name: str,
    category: str,
    address: str,
    primary_type_display: str,
    rating: float,
    review_count: int,
    language: str,
) -> str:
    place_type = _translate_place_type(primary_type_display, category, language)
    if language == "en":
        rating_line = (
            f"It currently holds a {rating:.1f}/5 Google Maps rating from about {review_count} reviews."
            if rating and review_count
            else "Check Google Maps or the official site for the latest visitor guidance and opening details."
        )
        return f"{name} is a notable Paris {place_type} near {address}. {rating_line}"
    rating_line = (
        f"현재 Google Maps에서 약 {review_count}개의 리뷰를 바탕으로 평점 {rating:.1f}/5를 기록하고 있어요."
        if rating and review_count
        else "방문 전에는 Google Maps나 공식 사이트에서 최신 운영 정보와 방문 후기를 확인해 보세요."
    )
    return f"{name}은 {address} 인근에서 만날 수 있는 파리의 대표적인 {place_type}입니다. {rating_line}"


def _build_history_summary(name: str, category: str, primary_type_display: str, language: str) -> str:
    place_type = _translate_place_type(primary_type_display, category, language)
    if language == "en":
        category_lines = {
            "landmark": "it is one of the signature stops travelers often choose first when they want the classic Paris highlights.",
            "museum": "it is a favorite stop for travelers who want to spend more time with Parisian art and exhibitions.",
            "cathedral": "it is often recommended for visitors who want to experience Paris through architecture and atmosphere.",
            "park": "it suits relaxed itineraries that mix walking, rest, and photo stops.",
            "neighborhood": "it is often suggested for strolling, cafe hopping, and soaking up the local rhythm of Paris.",
        }
        return f"Google Places categorizes {name} as {place_type}, and {category_lines.get(category, 'it is an easy place to include in a Paris day plan.')}"
    category_lines = {
        "landmark": "파리를 상징하는 장소를 찾는 여행자들이 자주 먼저 들르는 대표 스팟이에요.",
        "museum": "예술과 전시를 중심으로 파리의 문화적인 매력을 깊게 느끼고 싶을 때 많이 찾는 코스예요.",
        "cathedral": "건축미와 분위기를 함께 즐길 수 있어 파리의 역사적인 장면을 느끼고 싶을 때 추천되는 장소예요.",
        "park": "산책과 휴식, 사진 촬영을 한 번에 즐기기 좋아 여유로운 일정에 잘 어울리는 장소예요.",
        "neighborhood": "골목 산책과 카페, 현지 분위기를 함께 경험하고 싶을 때 자주 추천되는 지역이에요.",
    }
    return f"Google Places에서는 이 장소를 {place_type} 유형으로 분류하고 있으며, {category_lines.get(category, '파리 여행 중 가볍게 들르기 좋은 인기 장소예요.')}"


def _build_photo_tips(category: str, language: str) -> list[str]:
    if language == "en":
        tips = {
            "landmark": [
                "Go early or near sunset for softer light and fewer crowds.",
                "Step back to include more of the surrounding city in the frame.",
                "Check Google Maps crowd levels before you head out.",
            ],
            "museum": [
                "Capture the exterior before ticket lines start to build.",
                "Use nearby courtyards or plazas for a cleaner composition.",
                "Try side angles as well as the main entrance view.",
            ],
            "cathedral": [
                "A front-facing shot from across the square usually works best.",
                "Side light helps architectural details stand out more clearly.",
                "A slightly lower angle gives facades and towers more presence.",
            ],
            "park": [
                "Morning is often calmer and gives you softer walking light.",
                "Use tree lines or fountains to frame the scene naturally.",
                "Take your wide shots before the paths get busier.",
            ],
            "neighborhood": [
                "Small side streets often lead to the most atmospheric photo spots.",
                "Golden hour works especially well for cafes and street scenes.",
                "Walking one block off the main route can give you quieter frames.",
            ],
        }
        return tips.get(category, ["Check recent Google Maps photos and crowd levels before you go."])
    tips = {
        "landmark": [
            "아침 일찍이나 해 질 무렵에 가면 빛이 부드러워 사진이 더 예쁘게 나와요.",
            "조금 멀리 물러서서 도시 풍경까지 함께 담으면 더 인상적인 구도가 나와요.",
            "출발 전에 Google Maps에서 혼잡도를 확인하면 덜 붐비는 시간을 고르기 좋아요.",
        ],
        "museum": [
            "입장 줄이 길어지기 전에 외관부터 먼저 촬영해 두는 편이 좋아요.",
            "주변 광장이나 중정을 활용하면 더 깔끔한 구도로 담을 수 있어요.",
            "정면만 보기보다 측면 각도까지 둘러보면 더 매력적인 컷을 찾기 쉬워요.",
        ],
        "cathedral": [
            "광장 건너편에서 정면 구도로 담으면 건물의 웅장함이 잘 살아나요.",
            "옆에서 들어오는 빛을 활용하면 조각과 장식 디테일이 더 또렷하게 보여요.",
            "살짝 낮은 각도에서 올려다보면 파사드와 탑의 높이감이 잘 표현돼요.",
        ],
        "park": [
            "아침 시간대는 산책로가 비교적 한적하고 빛도 부드러워서 사진 찍기 좋아요.",
            "나무길이나 분수를 프레임처럼 활용하면 장면이 훨씬 풍성해 보여요.",
            "사람이 많아지기 전에 넓은 구도로 먼저 담아 두는 걸 추천해요.",
        ],
        "neighborhood": [
            "큰길보다 작은 골목으로 들어가면 더 분위기 있는 사진 포인트를 찾기 쉬워요.",
            "해 질 무렵에는 카페와 거리 풍경이 따뜻하게 보여서 감성적인 컷이 잘 나와요.",
            "메인 동선에서 한 블록만 벗어나도 훨씬 한적한 장면을 담을 수 있어요.",
        ],
    }
    return tips.get(category, ["출발 전에 Google Maps 사진과 혼잡도 정보를 함께 확인하면 최신 분위기를 파악하기 쉬워요."])


def _estimate_fee(category: str, language: str) -> str | None:
    if language == "en":
        if category in {"park", "neighborhood"}:
            return "Usually free"
        if category == "cathedral":
            return "Check the official site for current entry rules"
        return "Check the official site for current ticket prices"
    if category in {"park", "neighborhood"}:
        return "대체로 무료"
    if category == "cathedral":
        return "공식 사이트에서 최신 입장 규정을 확인해 주세요"
    return "공식 사이트에서 최신 입장료를 확인해 주세요"


def _build_tags(category: str, place: dict[str, Any]) -> list[str]:
    types = place.get("types") or []
    tags = [category, *types[:3], "paris"]
    return list(dict.fromkeys(tag for tag in tags if tag))


def _build_popularity_score(rating: float, review_count: int) -> int:
    if not rating and not review_count:
        return 60
    rating_score = (rating / 5) * 70
    review_score = min(30, math.log10(review_count + 1) * 10) if review_count else 0
    return max(1, min(100, int(round(rating_score + review_score))))


def _dedupe_places(places: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for place in places:
        place_id = place["id"]
        current = deduped.get(place_id)
        if current is None or place["popularity"] > current["popularity"]:
            deduped[place_id] = place
    return deduped


def _extract_text(value: Any) -> str | None:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
    if isinstance(value, str):
        return value
    return None


def _humanize_tag(raw_value: str) -> str:
    return raw_value.replace("_", "-").lower()


def _translate_place_type(label: str, category: str, language: str) -> str:
    if language == "en":
        if re.search(r"[가-힣]", label):
            return CATEGORY_LABELS_EN.get(category, "place")
        return label
    if re.search(r"[가-힣]", label):
        return label

    normalized = label.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in PLACE_TYPE_LABELS:
        return PLACE_TYPE_LABELS[normalized]
    if normalized in CATEGORY_LABELS:
        return CATEGORY_LABELS[normalized]
    return CATEGORY_LABELS.get(category, label)


def _google_places_language_code(language: str) -> str:
    return "en" if language == "en" else "ko"


def _translate_tag(raw_value: str) -> str:
    if re.search(r"[가-힣]", raw_value):
        return raw_value

    normalized = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in TAG_LABELS:
        return TAG_LABELS[normalized]

    humanized = _humanize_tag(raw_value).replace("-", " ")
    return humanized


def _slugify(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "paris-place"
