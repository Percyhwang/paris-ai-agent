from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Paris AI Agent API"
    app_env: str = "local"
    api_prefix: str = "/api"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "paris_ai_agent"
    frontend_origin: str = ",".join(
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "https://percyhwang.github.io",
        ]
    )

    google_client_id: str | None = None
    google_places_api_key: str | None = None
    enable_google_food_search: bool = True
    google_routes_api_key: str | None = None
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    allow_insecure_dev_auth: bool = True

    weather_api_url: str | None = None
    weather_cache_ttl_minutes: int = 30
    external_agent_api_url: str | None = None
    llm_diary_api_url: str | None = None

    rapidapi_key: str | None = None
    kiwi_rapidapi_host: str = "kiwi-com-flights-api.p.rapidapi.com"
    booking_rapidapi_host: str = "booking-com15.p.rapidapi.com"

    openai_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
