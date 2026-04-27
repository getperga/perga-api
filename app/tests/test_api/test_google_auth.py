from unittest.mock import patch
from app.services.auth_service import AuthService
from app.services.user_service import UserService


class TestGoogleAuth:
    @patch('app.services.auth_service.id_token.verify_oauth2_token')
    def test_verify_google_token_success(self, mock_verify):
        mock_verify.return_value = {
            'sub': 'google-id-123',
            'email': 'test@example.com',
        }
        
        token_info = AuthService.verify_google_token('fake-token')
        assert token_info is not None
        assert token_info['sub'] == 'google-id-123'
        assert token_info['email'] == 'test@example.com'

    @patch('app.services.auth_service.id_token.verify_oauth2_token')
    def test_verify_google_token_fail(self, mock_verify):
        mock_verify.side_effect = ValueError('Invalid token')
        token_info = AuthService.verify_google_token('invalid-token')
        assert token_info is None

    def test_get_or_create_google_user_new(self, test_db):
        google_id = 'new-google-id'
        email = 'new@example.com'

        user = UserService.get_or_create_google_user(test_db, google_id, email)
        
        assert user.google_id == google_id
        assert user.email == email
        assert user.hashed_password is None

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

    def test_google_signin_endpoint(self, client, test_db):
        google_id = 'endpoint-google-id'
        email = 'endpoint@example.com'
        
        with patch('app.services.auth_service.id_token.verify_oauth2_token') as mock_verify:
            mock_verify.return_value = {
                'sub': google_id,
                'email': email,
            }
            
            response = client.post(
                '/api/v1/auth/google/',
                json={'id_token': 'valid-google-token'}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert 'access_token' in data
            assert 'refresh_token' in data
            
            user = UserService.get_user_by_google_id(test_db, google_id)
            assert user is not None
            assert user.email == email
