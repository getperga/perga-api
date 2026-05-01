import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.const.auth import SIGNING_ALGORITHM, TokenType
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import GoogleTokenInfo
from app.services.auth_utils import validate_password, create_access_token, create_refresh_token
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
        if not user or not validate_password(password, user.hashed_password):
            return None
        return user

    @classmethod
    def create_user_tokens(cls, user_id: int) -> dict:
        """ Creates and returns dict with access and refresh tokens """
        data = {'sub': user_id}
        return {
            'token_type': TokenType.BEARER,
            'access_token': create_access_token(data=data),
            'refresh_token': create_refresh_token(data=data)
        }

    @classmethod
    def validate_refresh_token(cls, db: Session, refresh_token: str) -> User | None:
        """ Validates refresh token and return the associated user """
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM])
        except JWTError:
            return None

        if payload.get('token_type') != TokenType.REFRESH:
            return None

        user_id = cls._extract_user_id(payload)
        if not user_id:
            return None

        user = UserService.get_user_by_id(db, user_id=user_id)
        return user

    @classmethod
    async def get_current_user(cls, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
        """ Gets the current user from the access token or raises an exception """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM])
        except JWTError:
            raise cls.CREDENTIALS_EXCEPTION

        user_id = cls._extract_user_id(payload)
        if user_id is None:
            raise cls.CREDENTIALS_EXCEPTION

        user = UserService.get_user_by_id(db, user_id=user_id)
        if user is None:
            raise cls.CREDENTIALS_EXCEPTION
            
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

        response = requests.post(cls.GOOGLE_TOKENS_URL, data=data)
        if response.status_code != 200:
            return None

        tokens = response.json()
        id_token_str = tokens.get('id_token')
        if not id_token_str:
            return None

        return cls.verify_google_token(id_token_str)
