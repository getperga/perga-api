from unittest.mock import patch

from app.core.config import settings
from app.services.auth_service import AuthService
from app.services.user_service import UserService


class TestGoogleAuth:
    @patch('app.services.auth_service.requests.post')
    @patch('app.services.auth_service.id_token.verify_oauth2_token')
    def test_exchange_google_code_success(self, mock_verify, mock_post):
        # Mocking the exchange of code for token
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'id_token': 'fake-id-token'}
        
        # Mocking the verification of id_token
        mock_verify.return_value = {
            'sub': 'google-id-123',
            'email': 'test@example.com',
        }
        
        token_info = AuthService.exchange_google_code('fake-code')
        assert token_info is not None
        assert token_info['sub'] == 'google-id-123'
        assert token_info['email'] == 'test@example.com'

    @patch('app.services.auth_service.requests.post')
    def test_exchange_google_code_fail(self, mock_post):
        mock_post.return_value.status_code = 400
        token_info = AuthService.exchange_google_code('invalid-code')
        assert token_info is None

    def test_get_or_create_google_user_new(self, test_db):
        google_id = 'new-google-id'
        email = 'new@example.com'

        user = UserService.get_or_create_google_user(test_db, google_id, email)
        
        assert user.google_id == google_id
        assert user.email == email
        assert user.hashed_password is not None

    def test_get_or_create_google_user_existing_email(self, test_db, test_user):
        email = test_user.email
        google_id = 'google-id-for-existing-user'
        
        user = UserService.get_or_create_google_user(test_db, google_id, email)
        
        assert user.id == test_user.id
        assert user.google_id == google_id
        assert user.email == email

    def test_get_or_create_google_user_existing_google_id(self, test_db):
        google_id = 'unique-google-id'
        email = 'unique@example.com'
        existing_user = UserService.get_or_create_google_user(test_db, google_id, email)

        new_user = UserService.get_or_create_google_user(test_db, google_id, 'different@example.com')
        assert existing_user.id == new_user.id
        assert new_user.google_id == google_id

    def test_google_auth_endpoint(self, client, test_db):
        google_id = 'endpoint-google-id'
        email = 'endpoint@example.com'
        
        with patch('app.services.auth_service.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'id_token': 'fake-id-token'}

            with patch('app.services.auth_service.id_token.verify_oauth2_token') as mock_verify:
                mock_verify.return_value = {
                    'sub': google_id,
                    'email': email,
                }
                
                response = client.post(
                    '/api/v1/auth/google/',
                    json={'code': 'valid-google-code'}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert 'access_token' in data
                assert 'refresh_token' in data
                
                user = UserService.get_user_by_google_id(test_db, google_id)
                assert user is not None
                assert user.email == email

    def test_get_or_create_google_user_signup_disabled(self, test_db):
        with patch.object(settings, 'IS_SIGNUP_DISABLED', True):
            google_id = 'disabled-google-id'
            email = 'disabled@example.com'
            
            user = UserService.get_or_create_google_user(test_db, google_id, email)
            assert user is None

    def test_google_auth_endpoint_signup_disabled(self, client, test_db):
        with patch.object(settings, 'IS_SIGNUP_DISABLED', True):
            google_id = 'endpoint-disabled-google-id'
            email = 'endpoint-disabled@example.com'
            
            with patch('app.services.auth_service.requests.post') as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {'id_token': 'fake-id-token'}

                with patch('app.services.auth_service.id_token.verify_oauth2_token') as mock_verify:
                    mock_verify.return_value = {
                        'sub': google_id,
                        'email': email,
                    }
                    
                    response = client.post(
                        '/api/v1/auth/google/',
                        json={'code': 'valid-google-code'}
                    )
                    
                    assert response.status_code == 404
                    assert response.json()['detail'] == 'User not found'
