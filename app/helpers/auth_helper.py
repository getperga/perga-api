import bcrypt
import datetime as dt
import jwt

from app.const.auth import SIGNING_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, TokenType
from app.core.config import settings


__all__ = (
    'AuthHelper',
)


class AuthHelper:
    @staticmethod
    def generate_password_hash(plain_password: str) -> str:
        """
        Hashes password using bcrypt:
        1. Converts plain password to bytes
        2. Generates salt
        3. Hashes password with salt
        4. Returns hashed bytes as string
        """
        password_bytes = plain_password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password_bytes, salt)
        return hashed_password.decode('utf-8')

    @staticmethod
    def validate_password(plain_password: str, hashed_password: str) -> bool:
        """ Verifies a plain password against a hashed password """
        try:
            password_bytes = plain_password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
        except UnicodeEncodeError:
            return False

        try:
            result = bcrypt.checkpw(password_bytes, hashed_bytes)
        except ValueError:
            # invalid bcrypt hash format
            result = False

        return result

    @staticmethod
    def get_token_audience(token_type: TokenType) -> str:
        return f'perga-api:{token_type.value}'

    @classmethod
    def create_token(
        cls,
        data: dict,
        custom_timeout: dt.timedelta | None = None,
        token_type: TokenType = TokenType.ACCESS
    ) -> str:
        """
        Creates a JWT token with expiration timeout based on token_type or custom_timeout.

        Payload contains the following keys:
        - 'sub' (Subject): user_id, stored as a string.
        - 'exp' (Expiration Time): time after which the token is invalid.
        - 'token_type': The type of token, 'access' or 'refresh'.
        """
        to_encode = data.copy()

        if to_encode.get('sub'):
            to_encode['sub'] = str(to_encode['sub'])

        to_encode['token_type'] = token_type
        to_encode['aud'] = cls.get_token_audience(token_type)

        now = dt.datetime.now(dt.timezone.utc)
        if custom_timeout:
            expire_dt = now + custom_timeout
        elif token_type == TokenType.REFRESH:
            expire_dt = now + dt.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expire_dt = now + dt.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode['exp'] = expire_dt

        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=SIGNING_ALGORITHM)
        return encoded_jwt

    @classmethod
    def create_access_token(cls, data: dict, custom_timeout: dt.timedelta | None = None) -> str:
        return cls.create_token(data, custom_timeout=custom_timeout, token_type=TokenType.ACCESS)

    @classmethod
    def create_refresh_token(cls, data: dict, custom_timeout: dt.timedelta | None = None) -> str:
        return cls.create_token(data, custom_timeout=custom_timeout, token_type=TokenType.REFRESH)
