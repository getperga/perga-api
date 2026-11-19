import datetime as dt
import jwt

from app.const.auth import SIGNING_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, TokenType
from app.core.config import settings
from app.helpers.auth_helper import AuthHelper
from app.tests.const import TEST_PASSWORD


class TestAuthHelper:
    TEST_USER_ID = 123

    def test_password_hashing(self):
        # Hash a password
        hashed_password = AuthHelper.generate_password_hash(TEST_PASSWORD)
        
        # Verify that the hash is different from the original password
        assert hashed_password != TEST_PASSWORD
        
        # Verify that the password can be verified against the hash
        assert AuthHelper.validate_password(TEST_PASSWORD, hashed_password) is True
        
        # Verify that an incorrect password fails verification
        assert AuthHelper.validate_password('wrong_password', hashed_password) is False
        
        # Verify that an invalid hash format is handled gracefully
        assert AuthHelper.validate_password(TEST_PASSWORD, 'invalid_hash_format') is False

    def test_create_token(self):
        # Create a token with custom data
        data = {'sub': str(self.TEST_USER_ID)}
        token = AuthHelper.create_token(data)
        
        # Decode the token and verify its contents
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        assert payload['sub'] == str(self.TEST_USER_ID)
        assert payload['token_type'] == TokenType.ACCESS
        
        # Verify that the token has an expiration time
        assert 'exp' in payload
        exp_time = dt.datetime.fromtimestamp(payload['exp'], tz=dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        assert exp_time > now
        
        # Create a token with a custom expiration time
        custom_expires = dt.timedelta(minutes=30)
        token = AuthHelper.create_token(data, custom_timeout=custom_expires)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        exp_time = dt.datetime.fromtimestamp(payload["exp"], tz=dt.timezone.utc)
        expected_exp_time = dt.datetime.now(dt.timezone.utc) + custom_expires
        # Allow for a small difference due to processing time
        assert abs((exp_time - expected_exp_time).total_seconds()) < 5

    def test_create_access_token(self):
        # Create an access token
        data = {'sub': str(self.TEST_USER_ID)}
        token = AuthHelper.create_access_token(data)
        
        # Decode the token and verify its contents
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        assert payload['sub'] == str(self.TEST_USER_ID)
        assert payload['token_type'] == TokenType.ACCESS
        
        # Verify that the token has the default expiration time
        exp_time = dt.datetime.fromtimestamp(payload['exp'], tz=dt.timezone.utc)
        expected_exp_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        # Allow for a small difference due to processing time
        assert abs((exp_time - expected_exp_time).total_seconds()) < 5
        
        # Create an access token with a custom expiration time
        custom_expires = dt.timedelta(minutes=20)
        token = AuthHelper.create_access_token(data, custom_timeout=custom_expires)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        exp_time = dt.datetime.fromtimestamp(payload['exp'], tz=dt.timezone.utc)
        expected_exp_time = dt.datetime.now(dt.timezone.utc) + custom_expires
        # Allow for a small difference due to processing time
        assert abs((exp_time - expected_exp_time).total_seconds()) < 5

    def test_create_refresh_token(self):
        # Create a refresh token
        data = {'sub': str(self.TEST_USER_ID)}
        token = AuthHelper.create_refresh_token(data)
        
        # Decode the token and verify its contents
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        assert payload['sub'] == str(self.TEST_USER_ID)
        assert payload['token_type'] == TokenType.REFRESH
        
        # Verify that the token has the default expiration time
        exp_time = dt.datetime.fromtimestamp(payload['exp'], tz=dt.timezone.utc)
        expected_exp_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        # Allow for a small difference due to processing time
        assert abs((exp_time - expected_exp_time).total_seconds()) < 5
        
        # Create a refresh token with a custom expiration time
        custom_expires = dt.timedelta(days=7)
        token = AuthHelper.create_refresh_token(data, custom_timeout=custom_expires)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        exp_time = dt.datetime.fromtimestamp(payload['exp'], tz=dt.timezone.utc)
        expected_exp_time = dt.datetime.now(dt.timezone.utc) + custom_expires
        # Allow for a small difference due to processing time
        assert abs((exp_time - expected_exp_time).total_seconds()) < 5

    def test_token_with_integer_sub(self):
        # Create a token with an integer sub
        data = {'sub': self.TEST_USER_ID}
        token = AuthHelper.create_token(data)
        
        # Decode the token and verify that sub is a string
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False})
        assert payload['sub'] == str(self.TEST_USER_ID)
        assert isinstance(payload['sub'], str)
