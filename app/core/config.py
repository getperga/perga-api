import logging
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
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

    SQLALCHEMY_POOL_SIZE: int = Field(default=5, ge=1)
    SQLALCHEMY_MAX_OVERFLOW: int = Field(default=10, ge=0)
    SQLALCHEMY_POOL_TIMEOUT: int = Field(default=30, ge=1)
    SQLALCHEMY_POOL_RECYCLE: int = Field(default=1800, ge=1)

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    IS_SIGNUP_DISABLED: bool = False
    ROOT_URL_REDIRECT: str | None = None

    ATTACHMENTS_STORAGE: Literal['local', 's3'] = 'local'
    ATTACHMENTS_LOCAL_ROOT: str = './data/attachments'
    ATTACHMENTS_MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=100)
    ATTACHMENTS_MAX_IMAGE_PIXELS: int = Field(default=25000000, ge=1)
    ATTACHMENTS_MAX_USER_STORAGE_MB: int = Field(default=1024, ge=1)
    ATTACHMENTS_MAX_PER_NOTE: int = Field(default=100, ge=1)
    ATTACHMENTS_UNUSED_TTL_DAYS: int = Field(default=7, ge=1)
    ATTACHMENTS_S3_BUCKET: str | None = None
    ATTACHMENTS_S3_ENDPOINT_URL: str | None = None
    ATTACHMENTS_S3_REGION: str = 'us-east-1'
    ATTACHMENTS_S3_ADDRESSING_STYLE: Literal['auto', 'path', 'virtual'] = 'auto'

    @model_validator(mode='after')
    def validate_attachment_storage(self):
        if self.ATTACHMENTS_STORAGE == 's3' and not self.ATTACHMENTS_S3_BUCKET:
            raise ValueError('ATTACHMENTS_S3_BUCKET is required for S3 storage')

        if not self.ATTACHMENTS_LOCAL_ROOT.strip():
            raise ValueError('ATTACHMENTS_LOCAL_ROOT must not be empty')

        if self.ATTACHMENTS_S3_ENDPOINT_URL:
            url = urlsplit(self.ATTACHMENTS_S3_ENDPOINT_URL)
            if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
                raise ValueError('ATTACHMENTS_S3_ENDPOINT_URL must be an HTTP(S) endpoint without credentials')

        return self

    @property
    def sqlalchemy_database_uri(self) -> str:
        return f'postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}/{self.POSTGRES_DB}'

    class Config:
        env_file = '.env'
        case_sensitive = True
        cache_enabled = False

settings = Settings()
