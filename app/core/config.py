import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = 'Perga API'
    VERSION: str = '1.0.0'
    API_V1_STR: str = '/api/v1'
    
    SECRET_KEY: str
    CORS_ORIGINS: list[str]
    IS_DEV: bool = True
    LOGGING_LEVEL: int = logging.INFO

    POSTGRES_HOST: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_DB: str | None = None

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    ROOT_URL_REDIRECT: str | None = None

    @property
    def sqlalchemy_database_uri(self) -> str:
        return f'postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}/{self.POSTGRES_DB}'

    class Config:
        env_file = '.env'
        case_sensitive = True
        cache_enabled = False

settings = Settings()
