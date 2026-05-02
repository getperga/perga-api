import secrets
import string
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreateSchema, UserUpdateSchema
from app.services.base_service import BaseService
from app.services.auth_utils import generate_password_hash, validate_password


class UserService(BaseService[User]):
    model = User

    @classmethod
    def get_user_by_email(cls, db: Session, email: str) -> User | None:
        return cls.get_base_query(db).filter(User.email == email).first()

    @classmethod
    def get_user_by_username(cls, db: Session, username: str) -> User | None:
        return cls.get_base_query(db).filter(User.username == username).first()

    @classmethod
    def get_user_by_id(cls, db: Session, user_id: int) -> User | None:
        return cls.get_base_query(db).filter(User.id == user_id).first()

    @classmethod
    def get_user_by_google_id(cls, db: Session, google_id: str) -> User | None:
        return cls.get_base_query(db).filter(User.google_id == google_id).first()

    @classmethod
    def create_user(cls, db: Session, create_data: UserCreateSchema) -> User:
        # Check if user with this email or username already exists
        if cls.get_user_by_email(db, create_data.email):
            raise ValueError("Email already registered")

        if cls.get_user_by_username(db, create_data.username):
            raise ValueError("Username already taken")

        # Create new user
        hashed_password = generate_password_hash(create_data.password)
        db_user = User(
            username=create_data.username,
            email=create_data.email,
            hashed_password=hashed_password,
            is_active=True
        )
        db.add(db_user)
        db.commit()

        db.refresh(db_user)
        return db_user

    @classmethod
    def update_user(cls, db: Session, user_id: int, update_data: UserUpdateSchema) -> User | None:
        db_user = cls.get_user_by_id(db, user_id)
        if not db_user:
            return None

        update_data = update_data.model_dump(exclude_unset=True)
        for field, new_value in update_data.items():
            setattr(db_user, field, new_value)
        db.commit()

        db.refresh(db_user)
        return db_user

    @classmethod
    def change_password(cls, db: Session, user_id: int, current_password: str, new_password: str) -> User | None:
        user = cls.get_user_by_id(db, user_id)
        if not user:
            return None

        # Verify current password
        if not validate_password(current_password, user.hashed_password):
            # Do not change anything if verification fails
            raise ValueError("Incorrect current password")

        # Update to new password
        user.hashed_password = generate_password_hash(new_password)
        db.commit()

        db.refresh(user)
        return user

    @classmethod
    def get_or_create_google_user(cls, db: Session, google_id: str, email: str) -> User:
        # try to get user by google_id
        user = cls.get_user_by_google_id(db, google_id)
        if user:
            return user

        # try to get user by email
        user = cls.get_user_by_email(db, email)
        if user:
            user.google_id = google_id  # link existing user with google_id
            db.commit()
            db.refresh(user)
            return user

        # create new user with google_id and random password
        random_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        hashed_password = generate_password_hash(random_password)
        db_user = User(
            email=email,
            username=email,
            google_id=google_id,
            hashed_password=hashed_password,
            is_active=True
        )
        db.add(db_user)
        db.commit()

        db.refresh(db_user)
        return db_user
