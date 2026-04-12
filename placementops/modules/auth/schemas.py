# @forgeplan-node: auth-module
"""
Pydantic schemas for auth-module endpoints.

LoginRequest:  Input for POST /api/v1/auth/login
LoginResponse: Output for POST /api/v1/auth/login  (AC1)
UserProfileResponse: Output for GET /api/v1/auth/me  (AC4)
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC4

from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    """
    Credentials for POST /api/v1/auth/login.

    email must be a valid RFC 5322 address; password must be non-empty.
    """

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("password must not be empty")
        return v


class LoginResponse(BaseModel):
    """
    Successful login response.

    access_token: Supabase JWT
    token_type:   Always 'bearer'
    expires_in:   Seconds until the token expires
    user_id:      UUID of the authenticated user
    organization_id: UUID of the user's organization
    role_key:     Active role for permission checks
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: UUID
    organization_id: UUID
    role_key: str


class UserProfileResponse(BaseModel):
    """
    Authenticated user profile returned by GET /api/v1/auth/me.
    """

    user_id: UUID
    organization_id: UUID
    role_key: str
    email: str
    full_name: str

    model_config = {"from_attributes": True}
