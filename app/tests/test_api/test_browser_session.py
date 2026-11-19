from app.core.config import settings
from app.tests.const import TEST_PASSWORD


def test_browser_session_uses_secure_cookie_and_revokes_on_logout(client, test_user, monkeypatch):
    origin = 'https://app.example.test'
    monkeypatch.setattr(settings, 'CORS_ORIGINS', [origin])
    headers = {'Origin': origin, 'X-Perga-Session': 'browser'}
    auth = 'https://testserver/api/v1/auth'
    response = client.post(
        f'{auth}/access_token_json/', headers=headers,
        json={'username': test_user.username, 'password': TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()['refresh_token'] is None
    cookie = response.headers['set-cookie']
    assert cookie.startswith('__Host-perga_refresh=')
    assert all(flag in cookie for flag in ['HttpOnly', 'Secure', 'SameSite=lax'])
    assert response.headers['cache-control'] == 'no-store'

    refresh = client.post(f'{auth}/refresh_token/', headers=headers)
    assert refresh.status_code == 200
    assert refresh.json()['refresh_token'] is None
    authorization = {'Authorization': f"Bearer {refresh.json()['access_token']}"}
    assert client.get(f'{auth}/user/', headers=authorization).status_code == 200

    assert client.post(f'{auth}/logout/', headers=headers).status_code == 204
    assert client.get(f'{auth}/user/', headers=authorization).status_code == 401
    assert client.post(f'{auth}/refresh_token/', headers=headers).status_code == 401
