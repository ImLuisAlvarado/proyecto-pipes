# app/schemas/auth.py
from pydantic import BaseModel
from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    """
    Espejo exacto de AuthResponseDTO.kt:
        val accessToken: String
        val refreshToken: String
        val user: UserDto
    """
    access_token: str
    refresh_token: str
    user: UserResponse

    class Config:
        populate_by_name = True

    def model_dump(self, **kwargs):
        # Android espera camelCase: accessToken, refreshToken
        base = super().model_dump(**kwargs)
        return {
            "accessToken":   base["access_token"],
            "refreshToken":  base["refresh_token"],
            "user":          base["user"],
        }