from app.services.google_places_service import fetch_place_by_id, search_paris_places


async def list_places(
    api_base_url: str,
    search: str | None = None,
    category: str | None = None,
    sort: str = "popular",
    language: str = "ko",
) -> list[dict]:
    return await search_paris_places(
        search=search,
        category=category,
        sort=sort,
        api_base_url=api_base_url,
        language=language,
    )


async def get_place(
    api_base_url: str,
    place_id: str,
    language: str = "ko",
) -> dict:
    return await fetch_place_by_id(place_id=place_id, api_base_url=api_base_url, language=language)
