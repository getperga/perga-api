import datetime as dt
import jwt
import pytest

from fastapi import HTTPException

from app.const.auth import SIGNING_ALGORITHM, TokenType
from app.core.config import settings
from app.helpers import AuthHelper
from app.models import User
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.tests.const import TEST_USERNAME, TEST_EMAIL, TEST_PASSWORD


class TestAuthService:
    def test_authenticate_user_success(self, test_db):
        # Create a test user
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=AuthHelper.generate_password_hash(TEST_PASSWORD),
            is_active=True,
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        # Authenticate with correct credentials
        authenticated_user = AuthService.authenticate_user(test_db, user.username, TEST_PASSWORD)
        
        assert authenticated_user is not None
        assert authenticated_user.id == user.id
        assert authenticated_user.email == TEST_EMAIL

    def test_authenticate_user_wrong_password(self, test_db):
        # Create a test user
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=AuthHelper.generate_password_hash(TEST_PASSWORD),
            is_active=True,
        )
        test_db.add(user)
        test_db.commit()

        # Authenticate with wrong password
        authenticated_user = AuthService.authenticate_user(test_db, TEST_EMAIL, 'wrong_password')
        assert authenticated_user is None

    def test_authenticate_user_nonexistent(self, test_db):
        # Authenticate with non-existent user
        authenticated_user = AuthService.authenticate_user(test_db, 'nonexistent@example.com', TEST_PASSWORD)
        assert authenticated_user is None

    def test_create_user_tokens(self, test_db, test_user):
        # Create tokens for the test user
        tokens = AuthService.create_user_tokens(test_db, test_user)
        
        # Check that the response contains the expected keys
        assert 'access_token' in tokens
        assert 'token_type' in tokens
        assert 'refresh_token' in tokens
        assert tokens['token_type'] == TokenType.BEARER
        
        # Decode the access token and verify its contents
        access_payload = jwt.decode(
            tokens['access_token'], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False},
        )
        assert access_payload['sub'] == str(test_user.id)
        assert access_payload['token_type'] == TokenType.ACCESS
        
        # Decode the refresh token and verify its contents
        refresh_payload = jwt.decode(
            tokens['refresh_token'], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM], options={'verify_aud': False},
        )
        assert refresh_payload['sub'] == str(test_user.id)
        assert refresh_payload['token_type'] == TokenType.REFRESH

    def test_refresh_stays_inside_the_existing_session(self, test_db, test_user):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        renewed = AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert renewed['refresh_token'] == tokens['refresh_token']

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    async def test_access_and_refresh_tokens_have_distinct_scopes(self, test_db, test_user):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        assert (await AuthService.get_current_user(tokens['access_token'], test_db)).id == test_user.id
        with pytest.raises(HTTPException, match='401'):
            AuthService.refresh_user_tokens(test_db, tokens['access_token'])
        with pytest.raises(HTTPException, match='401'):
            await AuthService.get_current_user(tokens['refresh_token'], test_db)

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    async def test_malformed_tokens_are_rejected(self, test_db):
        invalid_token = 'invalid.token.string'

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(invalid_token, test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, invalid_token)
        assert refresh_error.value.status_code == 401

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @pytest.mark.parametrize('claim', ['sub', 'exp', 'aud', 'token_type', 'sid'])
    async def test_tokens_missing_required_claims_are_rejected(self, test_db, test_user, claim):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        for token_type in (TokenType.ACCESS, TokenType.REFRESH):
            token_key = f'{token_type.value}_token'
            payload = jwt.decode(
                tokens[token_key], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM],
                audience=AuthHelper.get_token_audience(token_type),
            )
            del payload[claim]
            tokens[token_key] = jwt.encode(payload, settings.SECRET_KEY, algorithm=SIGNING_ALGORITHM)

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @pytest.mark.parametrize('subject', [None, '', 'not_an_integer'])
    async def test_tokens_with_invalid_subject_are_rejected(self, test_db, test_user, subject):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        for token_type in (TokenType.ACCESS, TokenType.REFRESH):
            token_key = f'{token_type.value}_token'
            payload = jwt.decode(
                tokens[token_key], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM],
                audience=AuthHelper.get_token_audience(token_type),
            )
            payload['sub'] = subject
            tokens[token_key] = jwt.encode(payload, settings.SECRET_KEY, algorithm=SIGNING_ALGORITHM)

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @pytest.mark.parametrize('token_error', ['expired', 'wrong_signature'])
    async def test_expired_or_incorrectly_signed_tokens_are_rejected(self, test_db, test_user, token_error):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        for token_type in (TokenType.ACCESS, TokenType.REFRESH):
            token_key = f'{token_type.value}_token'
            payload = jwt.decode(
                tokens[token_key], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM],
                audience=AuthHelper.get_token_audience(token_type),
            )
            signing_key = settings.SECRET_KEY
            if token_error == 'expired':
                payload['exp'] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
            else:
                signing_key = f'{settings.SECRET_KEY}-different-key'
            tokens[token_key] = jwt.encode(payload, signing_key, algorithm=SIGNING_ALGORITHM)

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    async def test_tokens_for_deleted_user_are_rejected(self, test_db, test_user):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        test_db.delete(test_user)
        test_db.commit()

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

    def test_logout_revokes_only_its_session(self, test_db, test_user):
        first = AuthService.create_user_tokens(test_db, test_user)
        second = AuthService.create_user_tokens(test_db, test_user)
        AuthService.revoke_session(test_db, first['refresh_token'])
        with pytest.raises(HTTPException, match='401'):
            AuthService.refresh_user_tokens(test_db, first['refresh_token'])
        assert AuthService.refresh_user_tokens(test_db, second['refresh_token'])

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @pytest.mark.parametrize('change, value', [
        ('hashed_password', 'changed-password'),
        ('is_active', False),
        ('is_deleted', True),
    ])
    async def test_account_changes_invalidate_existing_sessions(self, test_db, test_user, change, value):
        tokens = AuthService.create_user_tokens(test_db, test_user)
        setattr(test_user, change, value)
        test_db.commit()

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

        if change in {'is_active', 'is_deleted'}:
            setattr(test_user, change, not value)
            test_db.commit()

        with pytest.raises(HTTPException) as access_error:
            await AuthService.get_current_user(tokens['access_token'], test_db)
        assert access_error.value.status_code == 401

        with pytest.raises(HTTPException) as refresh_error:
            AuthService.refresh_user_tokens(test_db, tokens['refresh_token'])
        assert refresh_error.value.status_code == 401

    def test_authenticate_user_inactive(self, test_db):
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=AuthHelper.generate_password_hash(TEST_PASSWORD),
            is_active=False,
        )
        test_db.add(user)
        test_db.commit()

        authenticated_user = AuthService.authenticate_user(test_db, user.username, TEST_PASSWORD)
        assert authenticated_user is None

    def test_get_or_create_google_user_inactive(self, test_db):
        google_id = 'google_123'
        email = 'google@example.com'
        user = User(
            username='google_user',
            email=email,
            google_id=google_id,
            hashed_password='...',
            is_active=False,
        )
        test_db.add(user)
        test_db.commit()
        
        result = UserService.get_or_create_google_user(test_db, google_id, email)
        assert result is None
