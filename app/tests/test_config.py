import pytest

from sqlalchemy import create_engine

from app.core.config import Settings


@pytest.mark.parametrize('host, database, port', [
    ('localhost', 'perga', None),
    ('localhost:55440', 'review+notes', 55440),
    ('[::1]:5432', 'notes ?#/% ü', 5432),
])
def test_database_connection_preserves_special_characters(host, database, port):
    username = 'user@:/%?#'
    password = 'password@:/%?#'
    config = Settings(
        _env_file=None,
        SECRET_KEY='test-only-signing-key-32-bytes-long',
        CORS_ORIGINS=[],
        POSTGRES_HOST=host,
        POSTGRES_USER=username,
        POSTGRES_PASSWORD=password,
        POSTGRES_DB=database,
    )
    engine = create_engine(config.sqlalchemy_database_uri)

    try:
        _, connect_args = engine.dialect.create_connect_args(engine.url)
        assert connect_args['dbname'] == database
        assert connect_args['user'] == username
        assert connect_args['password'] == password
        assert connect_args['host'] == ('::1' if host.startswith('[') else 'localhost')
        assert connect_args.get('port') == port
    finally:
        engine.dispose()
