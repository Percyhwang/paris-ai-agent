from pydantic import BaseModel, Field

from app.schemas.users import UserResponse


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., description="Google Identity Services credential or local dev credential")


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenPair
