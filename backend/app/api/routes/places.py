from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

from app.core.i18n import normalize_language
from app.core.responses import api_ok
from app.services.google_places_service import fetch_place_photo_bytes, get_default_place_image
from app.services.place_service import get_place, list_places

router = APIRouter()


@router.get("")
async def list_places_route(
    request: Request,
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    sort: str = Query(default="popular"),
) -> dict:
    api_base_url = str(request.base_url).rstrip("/")
    language = normalize_language(request.headers.get("accept-language"))
    places = await list_places(api_base_url=api_base_url, search=search, category=category, sort=sort, language=language)
    return api_ok(places)


@router.get("/photo")
async def get_place_photo_route(
    name: str = Query(..., min_length=1),
    max_width_px: int = Query(default=1200, ge=200, le=1600),
) -> Response:
    try:
        content, media_type = await fetch_place_photo_bytes(photo_name=name, max_width_px=max_width_px)
        return Response(content=content, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})
    except Exception:
        return RedirectResponse(get_default_place_image())


@router.get("/{place_id}")
async def get_place_route(
    request: Request,
    place_id: str,
) -> dict:
    api_base_url = str(request.base_url).rstrip("/")
    language = normalize_language(request.headers.get("accept-language"))
    return api_ok(await get_place(api_base_url=api_base_url, place_id=place_id, language=language))
