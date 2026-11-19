import pytest

from app.models.auth import User
from app.services.auth_service import AuthService
from app.helpers.auth_helper import AuthHelper
from app.tests.const import TEST_USERNAME, TEST_EMAIL, TEST_PASSWORD


@pytest.fixture(scope="function")
def test_user(test_db):
    """Create a test user for authentication tests"""
    user = User(
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        hashed_password=AuthHelper.generate_password_hash(TEST_PASSWORD),
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_db, test_user):
    access_token = AuthService.create_user_tokens(test_db, test_user)["access_token"]
    return {"Authorization": f"Bearer {access_token}"}
