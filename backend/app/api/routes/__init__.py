from fastapi import APIRouter

from app.api.routes import auth, budgets, diary, itinerary, places, reservations, trips, users, weather

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(trips.router, prefix="/trips", tags=["trips"])
api_router.include_router(itinerary.router, prefix="/trips", tags=["itinerary"])
api_router.include_router(budgets.router, prefix="/trips", tags=["budgets"])
api_router.include_router(reservations.router, prefix="/trips", tags=["reservations"])
api_router.include_router(diary.router, prefix="/trips", tags=["diary"])
api_router.include_router(places.router, prefix="/places", tags=["places"])
api_router.include_router(weather.router, prefix="/weather", tags=["weather"])
