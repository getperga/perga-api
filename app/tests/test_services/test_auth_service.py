import pytest
from fastapi import HTTPException
from jose import jwt
from unittest.mock import patch

from app.const.auth import SIGNING_ALGORITHM, TokenType
from app.core.config import settings
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.auth_utils import create_access_token, create_refresh_token, generate_password_hash
from app.services.user_service import UserService
from app.tests.const import TEST_USERNAME, TEST_EMAIL, TEST_PASSWORD


class TestAuthService:
    def test_authenticate_user_success(self, test_db):
        # Create a test user
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=generate_password_hash(TEST_PASSWORD),
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
            hashed_password=generate_password_hash(TEST_PASSWORD),
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

    def test_create_user_tokens(self, test_user):
        # Create tokens for the test user
        tokens = AuthService.create_user_tokens(test_user.id)
        
        # Check that the response contains the expected keys
        assert 'access_token' in tokens
        assert 'token_type' in tokens
        assert 'refresh_token' in tokens
        assert tokens['token_type'] == TokenType.BEARER
        
        # Decode the access token and verify its contents
        access_payload = jwt.decode(tokens['access_token'], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM])
        assert access_payload['sub'] == str(test_user.id)
        assert access_payload['token_type'] == TokenType.ACCESS
        
        # Decode the refresh token and verify its contents
        refresh_payload = jwt.decode(tokens['refresh_token'], settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM])
        assert refresh_payload['sub'] == str(test_user.id)
        assert refresh_payload['token_type'] == TokenType.REFRESH

    def test_validate_refresh_token_valid(self, test_db, test_user):
        # Create a refresh token for the test user
        refresh_token = create_refresh_token({'sub': test_user.id})
        
        # Validate the refresh token
        user = AuthService.validate_refresh_token(test_db, refresh_token)
        
        assert user is not None
        assert user.id == test_user.id

    def test_validate_refresh_token_invalid(self, test_db, test_user):
        # Create an access token (not a refresh token)
        access_token = create_access_token({'sub': test_user.id})
        
        # Validate the access token as a refresh token (should fail)
        user = AuthService.validate_refresh_token(test_db, access_token)
        assert user is None
        
        # Validate the invalid token
        invalid_token = 'invalid.token.string'
        user = AuthService.validate_refresh_token(test_db, invalid_token)
        assert user is None

    def test_validate_refresh_token_nonexistent_user(self, test_db):
        # Validate the refresh token
        refresh_token = create_refresh_token({'sub': 999})
        user = AuthService.validate_refresh_token(test_db, refresh_token)
        assert user is None

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_success(self, mock_decode, test_db, test_user):
        # Mock the jwt.decode function to return a payload with the test user's ID
        mock_decode.return_value = {'sub': str(test_user.id)}
        
        # Get the current user
        user = await AuthService.get_current_user('valid_token', test_db)
        assert user is not None
        assert user.id == test_user.id
        
        # Verify that jwt.decode was called with the expected arguments
        mock_decode.assert_called_once_with('valid_token', settings.SECRET_KEY, algorithms=[SIGNING_ALGORITHM])

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_jwt_error(self, mock_decode, test_db):
        # Mock the jwt.decode function to raise a JWTError
        mock_decode.side_effect = jwt.JWTError()
        
        # Attempt to get the current user with an invalid token
        with pytest.raises(Exception) as excinfo:
            await AuthService.get_current_user('invalid_token', test_db)
        
        # Check that the exception is an HTTPException with status code 401
        assert excinfo.value.status_code == 401
        assert 'Could not validate credentials' in excinfo.value.detail

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_missing_sub(self, mock_decode, test_db):
        # Mock the jwt.decode function to return a payload without a sub claim
        mock_decode.return_value = {'token_type': TokenType.ACCESS}
        
        # Attempt to get the current user with a token missing the sub claim
        with pytest.raises(Exception) as excinfo:
            await AuthService.get_current_user('token_without_sub', test_db)
        
        # Check that the exception is an HTTPException with status code 401
        assert excinfo.value.status_code == 401
        assert 'Could not validate credentials' in excinfo.value.detail

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_invalid_sub(self, mock_decode, test_db):
        # Mock the jwt.decode function to return a payload with an invalid sub claim
        mock_decode.return_value = {'sub': 'not_an_integer'}
        
        # Attempt to get the current user with a token with an invalid sub claim
        with pytest.raises(Exception) as excinfo:
            await AuthService.get_current_user('token_with_invalid_sub', test_db)
        
        # Check that the exception is an HTTPException with status code 401
        assert excinfo.value.status_code == 401
        assert 'Could not validate credentials' in excinfo.value.detail

    def test_authenticate_user_inactive(self, test_db):
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=generate_password_hash(TEST_PASSWORD),
            is_active=False,
        )
        test_db.add(user)
        test_db.commit()

        authenticated_user = AuthService.authenticate_user(test_db, user.username, TEST_PASSWORD)
        assert authenticated_user is None

    def test_validate_refresh_token_inactive(self, test_db):
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=generate_password_hash(TEST_PASSWORD),
            is_active=False,
        )
        test_db.add(user)
        test_db.commit()

        refresh_token = create_refresh_token({'sub': user.id})
        
        validated_user = AuthService.validate_refresh_token(test_db, refresh_token)
        assert validated_user is None

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_inactive(self, mock_decode, test_db):
        user = User(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            hashed_password=generate_password_hash(TEST_PASSWORD),
            is_active=False,
        )
        test_db.add(user)
        test_db.commit()

        mock_decode.return_value = {'sub': str(user.id)}
        
        with pytest.raises(HTTPException) as excinfo:
            await AuthService.get_current_user('valid_token', test_db)
        
        assert excinfo.value.status_code == 401
        assert 'Could not validate credentials' in excinfo.value.detail

    @pytest.mark.anyio
    @pytest.mark.parametrize('anyio_backend', ['asyncio'])
    @patch('app.services.auth_service.jwt.decode')
    async def test_get_current_user_nonexistent_user(self, mock_decode, test_db):
        mock_decode.return_value = {'sub': '999'}
        
        with pytest.raises(HTTPException) as excinfo:
            await AuthService.get_current_user('token_for_nonexistent_user', test_db)
        
        assert excinfo.value.status_code == 401
        assert 'Could not validate credentials' in excinfo.value.detail

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
