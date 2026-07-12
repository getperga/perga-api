import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreateSchema, UserUpdateSchema
from app.services.auth_utils import validate_password
from app.services.user_service import UserService
from app.tests.const import TEST_USERNAME, TEST_PASSWORD


class TestUserService:
    def test_get_user_by_email(self, test_db: Session, test_user):
        # Get the user by email
        db_user = UserService.get_user_by_email(test_db, test_user.email)
        assert db_user is not None
        assert db_user.id == test_user.id
        assert db_user.email == test_user.email

        # Try to get a non-existent user
        db_user = UserService.get_user_by_email(test_db, 'nonexistent@example.com')
        assert db_user is None

    def test_get_user_by_username(self, test_db: Session, test_user):
        # Set a username for the test user
        test_user.username = TEST_USERNAME
        test_db.commit()
        test_db.refresh(test_user)

        # Get the user by username
        db_user = UserService.get_user_by_username(test_db, TEST_USERNAME)
        assert db_user is not None
        assert db_user.id == test_user.id
        assert db_user.username == test_user.username

        # Try to get a non-existent user
        db_user = UserService.get_user_by_username(test_db, 'nonexistent')
        assert db_user is None

    def test_get_user_by_id(self, test_db: Session, test_user):
        # Get the user by ID
        db_user = UserService.get_user_by_id(test_db, test_user.id)
        assert db_user is not None
        assert db_user.id == test_user.id
        assert db_user.email == test_user.email

        # Try to get a non-existent user
        db_user = UserService.get_user_by_id(test_db, 7)
        assert db_user is None

    def test_create_user(self, test_db: Session):
        # Create a user
        user_create = UserCreateSchema(
            username='newuser',
            email='newuser@example.com',
            password='password123'
        )
        db_user = UserService.create_user(test_db, user_create)
        
        # Check that the user was created correctly
        assert db_user.id is not None
        assert db_user.username == user_create.username
        assert db_user.email == user_create.email
        assert db_user.hashed_password and validate_password(user_create.password, db_user.hashed_password)
        assert db_user.is_active is True

    def test_create_user_duplicate_email(self, test_db: Session, test_user):
        # Try to create a user with the same email
        user_create = UserCreateSchema(
            username='newuser',
            email=test_user.email,
            password='password123'
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError) as excinfo:
            UserService.create_user(test_db, user_create)
        
        assert 'Email already registered' in str(excinfo.value)

    def test_create_user_duplicate_username(self, test_db: Session):
        # Create a user
        user_create1 = UserCreateSchema(
            username='sameusername',
            email='user1@example.com',
            password='password123'
        )
        UserService.create_user(test_db, user_create1)
        
        # Try to create another user with the same username
        user_create2 = UserCreateSchema(
            username='sameusername',
            email='user2@example.com',
            password='password123'
        )
        
        with pytest.raises(ValueError) as excinfo:
            UserService.create_user(test_db, user_create2)
        assert 'Username already taken' in str(excinfo.value)

    def test_update_user(self, test_db: Session, test_user):
        # Update the user
        user_update = UserUpdateSchema(
            email='updated@example.com'
        )
        db_user = UserService.update_user(test_db, test_user.id, user_update)
        
        # Check that the user was updated correctly
        assert db_user.id == test_user.id
        assert db_user.email == user_update.email
        
        # Try to update a non-existent user
        db_user = UserService.update_user(test_db, 7, user_update)
        assert db_user is None

    def test_change_password(self, test_db: Session, test_user):
        # Change the user's password with correct current_password
        db_user = UserService.change_password(
            test_db,
            test_user.id,
            current_password=TEST_PASSWORD,
            new_password='newpassword123'
        )
        assert validate_password('newpassword123', db_user.hashed_password)

        # Attempt to change with wrong current password
        with pytest.raises(ValueError) as excinfo:
            UserService.change_password(test_db, test_user.id, current_password='wrong', new_password='another')
        assert 'Incorrect current password' in str(excinfo.value)

    def test_change_password_no_current(self, test_db: Session):
        """ Checks case with google user signup without password """
        db_user = User(
            username='nopass',
            email='nopass@example.com',
            hashed_password=None,
            is_active=True
        )
        test_db.add(db_user)
        test_db.commit()
        test_db.refresh(db_user)

        updated_user = UserService.change_password(
            test_db,
            db_user.id,
            current_password=None,
            new_password='newpassword123'
        )
        assert (
            updated_user
            and updated_user.hashed_password
            and validate_password('newpassword123', updated_user.hashed_password)
        )

    def test_create_user_signup_disabled(self, test_db: Session):
        user_create = UserCreateSchema(
            username='disableduser',
            email='disabled@example.com',
            password='password123'
        )
        
        with patch.object(settings, 'IS_SIGNUP_DISABLED', True):
            with pytest.raises(ValueError, match="Signup is disabled"):
                UserService.create_user(test_db, user_create)
