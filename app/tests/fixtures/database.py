import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.main import app


@pytest.fixture(scope='session')
def test_engine():
    engine = create_engine(settings.sqlalchemy_database_uri)

    cfg = Config('alembic.ini')
    command.upgrade(cfg, 'head')

    yield engine

    command.downgrade(cfg, 'base')
    engine.dispose()


@pytest.fixture(scope='function')
def test_db(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode='create_savepoint')

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope='function')
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
