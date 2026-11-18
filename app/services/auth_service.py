import datetime as dt
import jwt
import requests
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.const.auth import REFRESH_TOKEN_EXPIRE_DAYS, SIGNING_ALGORITHM, TokenType
from app.core.config import settings
from app.core.database import get_db
from app.helpers import AuthHelper
from app.models import AuthSession, User
from app.schemas.auth import GoogleTokenInfo
from app.services.user_service import UserService

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f'{settings.API_V1_STR}/auth/access_token/')


class AuthService:
    CREDENTIALS_EXCEPTION = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    GOOGLE_TOKENS_URL = 'https://oauth2.googleapis.com/token'

    @staticmethod
    def _extract_user_id(payload: dict) -> int | None:
        """ Extracts user_id from payload, it is stored as a jwt subject """
        user_id_str = payload.get('sub')
        if user_id_str is None:
            return None

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None

        return user_id

    @classmethod
    def authenticate_user(cls, db: Session, username: str, password: str) -> User | None:
        # Allow signing in using either username or email in the `username` field
        user = (
            UserService.get_user_by_username(db, username)
            or UserService.get_user_by_email(db, username)
        )
        if (
            not user
            or not user.hashed_password
            or not AuthHelper.validate_password(password, user.hashed_password)
            or not user.is_active
        ):
            return None
        return user

    @classmethod
    def create_user_tokens(cls, db: Session, user: User) -> dict:
        lifetime = dt.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        session = AuthSession(
            id=str(uuid4()),
            user_id=user.id,
            auth_epoch=user.auth_epoch,
            expires_at=dt.datetime.now(dt.timezone.utc) + lifetime,
        )

        data = {'sub': user.id, 'sid': session.id}
        refresh_token = AuthHelper.create_refresh_token(data, custom_timeout=lifetime)
        tokens = cls._token_pair(data, refresh_token)

        db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.expires_at <= func.now()).delete()
        db.add(session)
        db.commit()

        return tokens

    @staticmethod
    def _token_pair(data: dict, refresh_token: str) -> dict:
        return {
            'token_type': TokenType.BEARER,
            'access_token': AuthHelper.create_access_token(data),
            'refresh_token': refresh_token,
        }

    @classmethod
    def _active_session(cls, db: Session, token: str, token_type: TokenType) -> tuple[User, AuthSession] | None:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM],
                audience=AuthHelper.get_token_audience(token_type),
                options={'require': ['sub', 'exp', 'aud', 'token_type', 'sid']},
            )
        except jwt.InvalidTokenError:
            return None

        user_id = cls._extract_user_id(payload)
        session_id = payload['sid']
        if payload['token_type'] != token_type or not user_id or not isinstance(session_id, str):
            return None

        return db.query(User, AuthSession).join(AuthSession, AuthSession.user_id == User.id).filter(
            AuthSession.id == session_id,
            AuthSession.expires_at > func.now(),
            AuthSession.auth_epoch == User.auth_epoch,
            User.id == user_id,
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        ).populate_existing().first()

    @classmethod
    def refresh_user_tokens(cls, db: Session, refresh_token: str) -> dict:
        result = cls._active_session(db, refresh_token, TokenType.REFRESH)
        if not result:
            raise cls.CREDENTIALS_EXCEPTION

        user, session = result
        return cls._token_pair({'sub': user.id, 'sid': session.id}, refresh_token)

    @classmethod
    def revoke_session(cls, db: Session, refresh_token: str) -> None:
        result = cls._active_session(db, refresh_token, TokenType.REFRESH)
        if not result:
            return

        _, session = result
        db.delete(session)
        db.commit()

    @classmethod
    async def get_current_user(cls, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
        result = cls._active_session(db, token, TokenType.ACCESS)
        if not result:
            raise cls.CREDENTIALS_EXCEPTION

        user, _ = result
        return user

    @classmethod
    def verify_google_token(cls, token: str) -> GoogleTokenInfo | None:
        result: GoogleTokenInfo | None

        try:
            token_info = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            # Invalid token
            result = None
        else:
            result = dict(token_info)

        return result

    @classmethod
    def exchange_google_code(cls, code: str) -> GoogleTokenInfo | None:
        """ Exchanges google auth code for tokens and returns user info """
        data = {
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': 'postmessage',
            'grant_type': 'authorization_code',
        }

        response = requests.post(cls.GOOGLE_TOKENS_URL, data=data, timeout=10)
        if response.status_code != 200:
            return None

        tokens = response.json()
        id_token_str = tokens.get('id_token')
        if not id_token_str:
            return None

        return cls.verify_google_token(id_token_str)
