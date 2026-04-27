from pydantic import BaseModel
from typing import TypedDict


class TokenSchema(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str | None = None


class SigninSchema(BaseModel):
    username: str
    password: str


class RefreshTokenSchema(BaseModel):
    refresh_token: str


class GoogleSigninSchema(BaseModel):
    id_token: str


# only used for google signin attributes
class GoogleTokenInfo(TypedDict, total=False):
    sub: str
    email: str
