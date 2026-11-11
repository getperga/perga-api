import boto3
import io
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from unittest.mock import Mock

from app.core.config import Settings
from app.core.file_storage import LocalFileStorage, S3FileStorage, StorageError


def test_local_storage_round_trip_and_safe_paths(tmp_path):
    storage = LocalFileStorage(str(tmp_path / 'files'))
    storage.put('notes/1/test.png', io.BytesIO(b'image'), 'image/png')

    with storage.open('notes/1/test.png') as stream:
        assert stream.read() == b'image'

    for key in ('../escape.png', '/outside.png', 'notes/../escape.png'):
        with pytest.raises(ValueError):
            storage.put(key, io.BytesIO(b'bad'), 'image/png')

    outside = tmp_path / 'outside'
    outside.mkdir()
    (storage.root / 'link').symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        storage.open('link/test.png')
    storage.delete('notes/1/test.png')
    storage.delete('notes/1/test.png')
    with pytest.raises(StorageError):
        storage.open('notes/1/test.png')


def test_failed_local_write_keeps_previous_object(tmp_path):
    storage = LocalFileStorage(str(tmp_path))
    storage.put('image.png', io.BytesIO(b'original'), 'image/png')
    broken = Mock()
    broken.read.side_effect = [b'partial', OSError('write failed')]

    with pytest.raises(StorageError):
        storage.put('image.png', broken, 'image/png')
    with storage.open('image.png') as stream:
        assert stream.read() == b'original'
    assert [path.name for path in tmp_path.iterdir()] == ['image.png']


def test_s3_storage_round_trip_contract():
    client = boto3.client(
        's3',
        endpoint_url='https://storage.example.test',
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    storage = object.__new__(S3FileStorage)
    storage.client = client
    storage.bucket = 'perga'
    source = io.BytesIO(b'image')

    with Stubber(client) as stub:
        stub.add_response('put_object', {}, {'Bucket': 'perga', 'Key': 'image.png',
                                            'Body': source, 'ContentType': 'image/png'})
        stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(b'image'), 5)},
                          {'Bucket': 'perga', 'Key': 'image.png'})
        stub.add_response('delete_object', {}, {'Bucket': 'perga', 'Key': 'image.png'})
        stub.add_client_error('get_object', service_error_code='NoSuchKey', http_status_code=404)
        storage.put('image.png', source, 'image/png')
        stream = storage.open('image.png')
        try:
            assert stream.read() == b'image'
        finally:
            stream.close()
        storage.delete('image.png')
        with pytest.raises(StorageError):
            storage.open('missing.png')
        stub.assert_no_pending_responses()


def test_s3_requires_bucket():
    with pytest.raises(ValueError, match='ATTACHMENTS_S3_BUCKET'):
        Settings(_env_file=None, SECRET_KEY='test', CORS_ORIGINS=[], ATTACHMENTS_STORAGE='s3')
