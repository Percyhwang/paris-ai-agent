from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

PARIS_CENTER = {"lat": 48.8566, "lng": 2.3522}
MEAL_CATEGORIES = {"bar", "bakery", "bistro", "brasserie", "cafe", "restaurant"}

CANONICAL_PLACES: list[dict[str, Any]] = [
    {
        "name": "Eiffel Tower",
        "category": "landmark",
        "coordinates": {"lat": 48.8584, "lng": 2.2945},
        "aliases": ["Tour Eiffel", "Bureau de Gustave Eiffel", "에펠탑", "에펠타워"],
    },
    {
        "name": "Louvre Museum",
        "category": "museum",
        "coordinates": {"lat": 48.8606, "lng": 2.3376},
        "aliases": ["Louvre", "Musee du Louvre", "Musee Louvre", "루브르", "루브르 박물관"],
    },
    {
        "name": "Musee d'Orsay",
        "category": "museum",
        "coordinates": {"lat": 48.86, "lng": 2.3266},
        "aliases": ["Musee d'Orsay", "Orsay Museum", "Musée d'Orsay", "오르세", "오르세 미술관"],
    },
    {
        "name": "Notre-Dame",
        "category": "landmark",
        "coordinates": {"lat": 48.853, "lng": 2.3499},
        "aliases": ["Notre-Dame Cathedral", "Tours de Notre-Dame", "노트르담", "노트르담 대성당"],
    },
    {
        "name": "Montmartre",
        "category": "landmark",
        "coordinates": {"lat": 48.8867, "lng": 2.3431},
        "aliases": ["Sacre-Coeur", "Sacré-Cœur", "Le Montmartre", "몽마르트르", "사크레쾨르"],
    },
    {
        "name": "Le Marais",
        "category": "landmark",
        "coordinates": {"lat": 48.8575, "lng": 2.358},
        "aliases": ["Marais", "Café du Marais", "마레", "마레 지구"],
    },
    {
        "name": "Luxembourg Gardens",
        "category": "park",
        "coordinates": {"lat": 48.8462, "lng": 2.3372},
        "aliases": ["Luxembourg Garden", "Jardin du Luxembourg", "뤽상부르 공원"],
    },
    {
        "name": "Tuileries Garden",
        "category": "park",
        "coordinates": {"lat": 48.8635, "lng": 2.327},
        "aliases": ["Jardin des Tuileries", "Tuileries", "튈르리 정원"],
    },
    {
        "name": "Seine River",
        "category": "landmark",
        "coordinates": {"lat": 48.8583, "lng": 2.3375},
        "aliases": ["Seine", "Pont des Arts", "센강", "센강 산책"],
    },
    {
        "name": "Le Bon Marche",
        "category": "shopping",
        "coordinates": {"lat": 48.8512, "lng": 2.3255},
        "aliases": ["Le Bon Marché", "봉마르셰"],
    },
    {
        "name": "Galeries Lafayette",
        "category": "shopping",
        "coordinates": {"lat": 48.8738, "lng": 2.3321},
        "aliases": ["Galeries Lafayette Haussmann", "갤러리 라파예트"],
    },
    {
        "name": "Saint-Germain-des-Pres",
        "category": "landmark",
        "coordinates": {"lat": 48.8538, "lng": 2.3336},
        "aliases": ["Saint-Germain cafe walk", "Saint-Germain-des-Prés", "생제르맹", "생제르맹데프레"],
    },
    {
        "name": "Arc de Triomphe",
        "category": "landmark",
        "coordinates": {"lat": 48.8738, "lng": 2.295},
        "aliases": ["개선문", "Arc de Triomphe de l'Étoile"],
    },
    {
        "name": "Champs-Elysees",
        "category": "landmark",
        "coordinates": {"lat": 48.8698, "lng": 2.3078},
        "aliases": ["Champs Élysées", "샹젤리제", "샹젤리제 거리"],
    },
    {
        "name": "Sainte-Chapelle",
        "category": "cathedral",
        "coordinates": {"lat": 48.8554, "lng": 2.345},
        "aliases": ["생트샤펠"],
    },
    {
        "name": "Palais Garnier",
        "category": "landmark",
        "coordinates": {"lat": 48.8719, "lng": 2.3316},
        "aliases": ["오페라 가르니에", "Opéra Garnier"],
    },
]


async def ensure_places_seed_data(db: AsyncIOMotorDatabase) -> None:
    await _upsert_canonical_places(db)

    existing_osm = await db.places.count_documents({"source": "osm"}, limit=1)
    if existing_osm:
        return

    data_path = Path(__file__).resolve().parents[3] / "data_assets" / "paris_places_clean.json"
    if not data_path.exists():
        logger.warning("Paris places seed file was not found at %s", data_path)
        return

    with data_path.open("r", encoding="utf-8") as file:
        raw_places = json.load(file)

    now = datetime.now(UTC)
    documents = []
    seen_slugs = {slug_for_place(place["name"]) for place in CANONICAL_PLACES}
    for raw_place in raw_places:
        normalized = _normalize_seed_place(raw_place, now)
        if not normalized or normalized["slug"] in seen_slugs:
            continue
        seen_slugs.add(normalized["slug"])
        documents.append(normalized)

    for index in range(0, len(documents), 500):
        await db.places.insert_many(documents[index : index + 500], ordered=False)


async def resolve_place(
    db: AsyncIOMotorDatabase,
    place_name: str,
    category: str | None = None,
    fallback_coordinates: dict[str, float] | None = None,
) -> dict[str, Any]:
    doc = await _find_place_document(db, place_name, category)
    if doc:
        return itinerary_place_from_document(doc, fallback_name=place_name, fallback_category=category)

    return {
        "name": place_name,
        "category": category,
        "coordinates": fallback_coordinates,
    }


async def find_nearby_meal_place(
    db: AsyncIOMotorDatabase,
    near: dict[str, float],
    exclude_names: set[str] | None = None,
) -> dict[str, Any] | None:
    exclude_names = {name.lower() for name in (exclude_names or set())}
    geometry = {"type": "Point", "coordinates": [near["lng"], near["lat"]]}
    query = {
        "category": {"$in": sorted(MEAL_CATEGORIES)},
        "location": {"$near": {"$geometry": geometry, "$maxDistance": 1400}},
    }

    try:
        docs = await db.places.find(query).limit(12).to_list(length=12)
    except Exception as exc:
        logger.info("Mongo $near lookup failed, using in-memory meal fallback: %s", exc)
        docs = await db.places.find({"category": {"$in": sorted(MEAL_CATEGORIES)}}).limit(2500).to_list(length=2500)
        docs.sort(key=lambda doc: distance_meters(near, coordinates_from_place_document(doc) or PARIS_CENTER))

    for doc in docs:
        name = str(doc.get("name") or "").strip()
        if name and name.lower() not in exclude_names and coordinates_from_place_document(doc):
            return itinerary_place_from_document(doc, fallback_name=name, fallback_category="cafe")
    return None


def itinerary_place_from_document(
    doc: dict[str, Any],
    fallback_name: str,
    fallback_category: str | None = None,
) -> dict[str, Any]:
    return {
        "place_id": str(doc.get("_id")) if doc.get("_id") else None,
        "name": str(doc.get("name") or fallback_name),
        "category": str(doc.get("category") or fallback_category or "landmark"),
        "coordinates": coordinates_from_place_document(doc),
    }


def coordinates_from_place_document(doc: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(doc, dict):
        return None

    coordinates = doc.get("coordinates")
    if isinstance(coordinates, dict) and _is_number(coordinates.get("lat")) and _is_number(coordinates.get("lng")):
        return {"lat": float(coordinates["lat"]), "lng": float(coordinates["lng"])}

    location = doc.get("location")
    if isinstance(location, dict):
        point = location.get("coordinates")
        if isinstance(point, list) and len(point) >= 2 and _is_number(point[0]) and _is_number(point[1]):
            return {"lat": float(point[1]), "lng": float(point[0])}

    return None


def midpoint(origin: dict[str, float], destination: dict[str, float]) -> dict[str, float]:
    return {
        "lat": (origin["lat"] + destination["lat"]) / 2,
        "lng": (origin["lng"] + destination["lng"]) / 2,
    }


def distance_meters(origin: dict[str, float], destination: dict[str, float]) -> int:
    radius_meters = 6_371_000
    lat1 = math.radians(origin["lat"])
    lat2 = math.radians(destination["lat"])
    delta_lat = math.radians(destination["lat"] - origin["lat"])
    delta_lng = math.radians(destination["lng"] - origin["lng"])
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    return round(radius_meters * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def slug_for_place(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return normalized or "place"


async def _upsert_canonical_places(db: AsyncIOMotorDatabase) -> None:
    now = datetime.now(UTC)
    for place in CANONICAL_PLACES:
        coordinates = dict(place["coordinates"])
        doc = {
            "slug": slug_for_place(place["name"]),
            "name": place["name"],
            "category": place["category"],
            "coordinates": coordinates,
            "location": {"type": "Point", "coordinates": [coordinates["lng"], coordinates["lat"]]},
            "aliases": place.get("aliases", []),
            "source": "canonical",
            "popularity": 100,
            "updated_at": now,
        }
        await db.places.update_one(
            {"slug": doc["slug"]},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )


def _normalize_seed_place(raw_place: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    name = str(raw_place.get("name") or "").strip()
    location = raw_place.get("location")
    if not name or not isinstance(location, dict):
        return None

    coordinates = coordinates_from_place_document(raw_place)
    if not coordinates:
        return None

    category = str(raw_place.get("category") or "landmark")
    return {
        "slug": slug_for_place(name),
        "name": name,
        "category": category,
        "coordinates": coordinates,
        "location": {"type": "Point", "coordinates": [coordinates["lng"], coordinates["lat"]]},
        "source": raw_place.get("source") or "osm",
        "popularity": _seed_popularity(category),
        "created_at": now,
        "updated_at": now,
    }


async def _find_place_document(
    db: AsyncIOMotorDatabase,
    place_name: str,
    category: str | None = None,
) -> dict[str, Any] | None:
    name = place_name.strip()
    if not name:
        return None

    slug = slug_for_place(name)
    exact_matchers: list[dict[str, Any]] = [
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"aliases": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
    ]
    if slug != "place":
        exact_matchers.append({"slug": slug})

    exact = await db.places.find_one(
        {"$or": exact_matchers}
    )
    if exact:
        return exact

    canonical = _canonical_match(name)
    if canonical:
        return await db.places.find_one({"slug": slug_for_place(canonical["name"])})

    token_query = _token_query(name, category)
    if token_query:
        return await db.places.find_one(token_query, sort=[("popularity", -1), ("name", 1)])

    return None


def _canonical_match(name: str) -> dict[str, Any] | None:
    lowered = name.lower()
    for place in CANONICAL_PLACES:
        names = [place["name"], *place.get("aliases", [])]
        if any(candidate.lower() in lowered or lowered in candidate.lower() for candidate in names):
            return place
    return None


def _token_query(name: str, category: str | None) -> dict[str, Any] | None:
    tokens = [token for token in re.split(r"[^a-zA-Z0-9À-ÿ가-힣']+", name) if len(token) >= 2]
    if not tokens:
        return None
    expressions: list[dict[str, Any]] = [{"name": {"$regex": re.escape(token), "$options": "i"}} for token in tokens[:3]]
    expressions.extend({"aliases": {"$regex": re.escape(token), "$options": "i"}} for token in tokens[:3])
    query: dict[str, Any] = {"$or": expressions}
    if category:
        query["category"] = category
    return query


def _seed_popularity(category: str) -> int:
    if category == "museum":
        return 72
    if category == "landmark":
        return 68
    if category == "park":
        return 62
    if category in MEAL_CATEGORIES:
        return 54
    return 40


def _is_number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool)
