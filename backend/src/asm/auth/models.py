from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from asm.tenancy import MembershipRole, Permission


class AuthCode(StrEnum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    SESSION_REQUIRED = "SESSION_REQUIRED"
    ORIGIN_DENIED = "ORIGIN_DENIED"
    CSRF_REJECTED = "CSRF_REJECTED"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INVALID_REQUEST = "INVALID_REQUEST"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AuthError(RuntimeError):
    def __init__(self, code: AuthCode, status: int) -> None:
        self.code, self.status = code, status
        super().__init__(code.value)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class EmptyRequest(StrictModel):
    pass


class LoginRequest(StrictModel):
    login: str = Field(min_length=3, max_length=72)
    password: SecretStr

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 1 <= len(password) <= 128 or len(password.encode("utf-8")) > 1024:
            raise ValueError("Invalid password length")
        return value


class ErrorDetail(StrictModel):
    code: AuthCode


class ErrorResponse(StrictModel):
    error: ErrorDetail


class BootstrapResponse(StrictModel):
    csrf_token: str = Field(repr=False)
    expires_at: datetime


class MembershipResponse(StrictModel):
    workspace_id: UUID
    role: MembershipRole
    permissions: list[Permission]


class SessionResponse(BootstrapResponse):
    user_account_id: UUID
    memberships: list[MembershipResponse]


class BusinessResponse(StrictModel):
    workspace_id: UUID
    id: UUID
    name: str
    status: str
    version: int
    created_at: datetime


class BusinessesResponse(StrictModel):
    businesses: list[BusinessResponse]
