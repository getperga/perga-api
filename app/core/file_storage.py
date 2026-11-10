import boto3
import os
import re
import tempfile
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings


class StorageError(Exception):
    """ A storage operation failed and may be retried. """


class FileStorage(Protocol):
    def put(self, key: str, file: BinaryIO, content_type: str) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


def validate_key(key: str) -> None:
    if not re.fullmatch(r'[a-zA-Z0-9_/-]+[.][a-z0-9]+', key) or '..' in key or key.startswith('/'):
        raise ValueError('Invalid storage key')


class LocalFileStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Invalid storage path')
        return path

    def put(self, key: str, file: BinaryIO, content_type: str) -> None:
        path = self._path(key)

        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = output.name
                while chunk := file.read(64 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise StorageError('Cannot store attachment') from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def open(self, key: str) -> BinaryIO:
        try:
            file = self._path(key).open('rb')
        except OSError as exc:
            raise StorageError('Cannot read attachment') from exc
        return file

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError('Cannot delete attachment') from exc


class S3FileStorage:
    def __init__(self, config=settings):
        self.bucket = config.ATTACHMENTS_S3_BUCKET
        self.client = boto3.client(
            's3', endpoint_url=config.ATTACHMENTS_S3_ENDPOINT_URL,
            region_name=config.ATTACHMENTS_S3_REGION,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': config.ATTACHMENTS_S3_ADDRESSING_STYLE},
                connect_timeout=10, read_timeout=60,
                retries={'max_attempts': 3, 'mode': 'standard'},
                request_checksum_calculation='when_required',
                response_checksum_validation='when_required',
            ),
        )

    def put(self, key: str, file: BinaryIO, content_type: str) -> None:
        validate_key(key)

        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=file, ContentType=content_type)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError('Cannot store attachment') from exc

    def open(self, key: str) -> BinaryIO:
        validate_key(key)

        try:
            object = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        except (BotoCoreError, ClientError) as exc:
            raise StorageError('Cannot read attachment') from exc

        return object

    def delete(self, key: str) -> None:
        validate_key(key)

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError('Cannot delete attachment') from exc


@lru_cache(maxsize=1)
def get_file_storage() -> FileStorage:
    if settings.ATTACHMENTS_STORAGE == 's3':
        return S3FileStorage()
    return LocalFileStorage(settings.ATTACHMENTS_LOCAL_ROOT)
