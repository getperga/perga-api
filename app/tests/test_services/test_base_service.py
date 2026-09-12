from sqlalchemy.orm import Session

from app.models.user import User
from app.services.base_service import BaseService
from app.tests.const import TEST_USERNAME, TEST_EMAIL


class UserTestService(BaseService[User]):
    model = User


class TestBaseServiceFunctionality:
    def test_get_base_query(self, test_db: Session):
        user = User(username=TEST_USERNAME, email=TEST_EMAIL, hashed_password="hashed1")
        test_db.add(user)
        test_db.commit()
        
        deleted_user = User(username="deleteduser", email="deleted@example.com", hashed_password="hashed2")
        deleted_user.mark_as_deleted()
        test_db.add(deleted_user)
        test_db.commit()

        non_deleted_users = UserTestService.get_base_query(test_db)
        non_deleted_users_ids = [user.id for user in non_deleted_users]
        assert user.id in non_deleted_users_ids
        assert deleted_user.id not in non_deleted_users_ids

    def test_get_scalars_for_single_column(self, test_db: Session):
        user = User(username=TEST_USERNAME, email=TEST_EMAIL, hashed_password='hashed1')
        deleted_user = User(
            username='deleteduser',
            email='deleted@example.com',
            hashed_password='hashed2',
        )
        deleted_user.mark_as_deleted()
        test_db.add_all([user, deleted_user])
        test_db.commit()

        user_ids = UserTestService.get_scalars_for_single_column(
            test_db,
            User.id,
            filters=(User.id == user.id,),
        ).all()
        assert user_ids == [user.id]

    def test_get_or_create_existing(self, test_db: Session):
        username = 'existing_user'
        email = 'existing@example.com'
        user = User(username=username, email=email, hashed_password="hashed")
        test_db.add(user)
        test_db.commit()

        result, created = UserTestService.get_or_create(test_db, username=username)
        assert not created
        assert result.id == user.id
        assert result.email == email

    def test_get_or_create_new(self, test_db: Session):
        username = 'new_user'
        email = 'new@example.com'
        
        result, created = UserTestService.get_or_create(
            test_db,
            username=username,
            defaults={'email': email, 'hashed_password': 'hashed'}
        )
        assert created
        assert result.username == username
        assert result.email == email
