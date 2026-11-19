from fastapi import HTTPException, Request, Response
from urllib.parse import urlsplit

from app.const.auth import REFRESH_TOKEN_EXPIRE_DAYS
from app.core.config import settings
from app.schemas.auth import RefreshTokenSchema


__all__ = (
    'BrowserSessionHelper',
)


class BrowserSessionHelper:
    BROWSER_SESSION_HEADER = 'X-Perga-Session'
    BROWSER_SESSION_VALUE = 'browser'
    SECURE_REFRESH_COOKIE = '__Host-perga_refresh'
    LOCAL_REFRESH_COOKIE = 'perga_refresh'
    LOCAL_REFRESH_COOKIE_PATH = f'{settings.API_V1_STR}/auth/'
    LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '::1'}

    @classmethod
    def get_browser_cookie(cls, origin: str) -> tuple[str, str, bool]:
        if origin.startswith('https://'):
            return cls.SECURE_REFRESH_COOKIE, '/', True
        return cls.LOCAL_REFRESH_COOKIE, cls.LOCAL_REFRESH_COOKIE_PATH, False

    @classmethod
    def get_browser_origin(cls, request: Request) -> str | None:
        if request.headers.get(cls.BROWSER_SESSION_HEADER) != cls.BROWSER_SESSION_VALUE:
            return None

        origin = request.headers.get('origin')
        if not origin or origin not in settings.CORS_ORIGINS:
            raise HTTPException(status_code=403, detail='Origin not allowed for browser session')

        url = urlsplit(origin)
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in cls.LOOPBACK_HOSTS):
            raise HTTPException(status_code=403, detail='Browser sessions require HTTPS outside loopback')

        return origin

    @classmethod
    def prepare_tokens_response(cls, response: Response, tokens: dict, origin: str | None) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        if not origin:
            return tokens

        name, path, secure = cls.get_browser_cookie(origin)
        response.set_cookie(
            name, tokens['refresh_token'], max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path=path, secure=secure, httponly=True, samesite='lax',
        )
        return {**tokens, 'refresh_token': None}

    @classmethod
    def get_submitted_refresh_token(cls, request: Request, refresh_request: RefreshTokenSchema | None) -> str:
        origin = cls.get_browser_origin(request)
        if not origin:
            return refresh_request.refresh_token if refresh_request else ''

        name, _, _ = cls.get_browser_cookie(origin)
        return request.cookies.get(name, '')
