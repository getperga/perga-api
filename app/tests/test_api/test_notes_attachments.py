import datetime as dt
import io
import pytest
import zipfile
from bs4 import BeautifulSoup
from PIL import Image
from uuid import UUID

from app.core.config import settings
from app.core.file_storage import LocalFileStorage, StorageError, get_file_storage
from app.main import app
from app.models.notes import NotesAttachment
from app.models.user import User
from app.schemas.notes import NoteCreateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.auth_utils import create_access_token, generate_password_hash
from app.services.notes_attachments_service import NotesAttachmentsService
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_import_service import NotesImportService
from app.services.notes_service import NoteService


@pytest.fixture
def attachment_storage(tmp_path, monkeypatch):
    storage = LocalFileStorage(str(tmp_path))
    app.dependency_overrides[get_file_storage] = lambda: storage
    monkeypatch.setattr('app.services.notes_export_service.get_file_storage', lambda: storage)
    monkeypatch.setattr('app.services.notes_import_service.get_file_storage', lambda: storage)
    yield storage
    app.dependency_overrides.pop(get_file_storage, None)


@pytest.fixture
def image_bytes():
    output = io.BytesIO()
    Image.new('RGB', (8, 6), 'red').save(output, format='PNG')
    return output.getvalue()


@pytest.fixture
def note(test_db, test_user):
    folder = NotesFolderService.get_root_folder(test_db, test_user.id)
    return NoteService.create_note(test_db, test_user.id,
                                  NoteCreateSchema(folder_id=folder.id, title='Images', body='<p>Hello</p>'))


def upload(client, note, auth_headers, image_bytes):
    return client.post(f'/api/v1/notes/{note.id}/attachments/', headers=auth_headers,
                       files={'file': ('../../screenshot.png', image_bytes, 'text/plain')})


def test_upload_canonicalize_download_and_usage(client, test_db, note, auth_headers, attachment_storage, image_bytes):
    response = upload(client, note, auth_headers, image_bytes)
    assert response.status_code == 201, response.text
    data = response.json()
    assert isinstance(data['id'], int)
    uploaded = test_db.get(NotesAttachment, data['id'])
    assert uploaded.is_deleted is True
    assert uploaded.deleted_dt is not None
    UUID(uploaded.storage_key.rsplit('/', 1)[-1].split('.')[0])
    assert data['original_filename'] == 'screenshot.png'
    assert data['content_type'] == 'image/png'
    assert (data['width'], data['height']) == (8, 6)
    assert 'storage_key' not in data
    listing = client.get(f'/api/v1/notes/{note.id}/attachments/', headers=auth_headers)
    assert listing.json() == [data]
    content = client.get(data['url'], headers=auth_headers)
    assert content.content == image_bytes
    assert content.headers['cache-control'] == 'private, no-store'
    assert content.headers['x-content-type-options'] == 'nosniff'
    body = f'<p>Image</p><img data-attachment-id="{data["id"]}" src="https://evil.test/image.png">'
    saved = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers, json={'body': body})
    assert saved.status_code == 200, saved.text
    assert data['url'] in saved.json()['body']
    assert 'evil.test' not in saved.json()['body']
    attachment = test_db.get(NotesAttachment, data['id'])
    assert attachment.is_deleted is False
    assert attachment.deleted_dt is None
    client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers, json={'body': '<p>Removed</p>'})
    test_db.refresh(attachment)
    assert attachment.is_deleted is True
    assert attachment.deleted_dt is not None
    restored = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                            json={'body': f'<img src="{data["url"]}">'})
    assert restored.status_code == 200
    test_db.refresh(attachment)
    assert attachment.is_deleted is False
    assert attachment.deleted_dt is None


def test_auth_and_cross_note_isolation(client, test_db, test_user, note, auth_headers,
                                       attachment_storage, image_bytes):
    data = upload(client, note, auth_headers, image_bytes).json()
    assert client.get(data['url']).status_code == 401
    assert upload(client, note, {}, image_bytes).status_code == 401
    # a second note of the same user must not reuse this attachment
    other = NoteService.create_note(test_db, test_user.id, NoteCreateSchema(folder_id=note.folder_id))
    assert client.get(data['url'].replace(f'/{note.id}/', f'/{other.id}/'), headers=auth_headers).status_code == 404
    result = client.patch(f'/api/v1/notes/{other.id}/', headers=auth_headers,
                          json={'body': f'<img data-attachment-id="{data["id"]}"> '})
    assert result.status_code == 422
    test_db.rollback()
    foreign = User(username='images-other', email='images-other@example.test',
                   hashed_password=generate_password_hash('password'), is_active=True)
    test_db.add(foreign)
    test_db.commit()
    headers = {'Authorization': f'Bearer {create_access_token(data={"sub": str(foreign.id)})}'}
    assert client.get(data['url'], headers=headers).status_code == 404
    assert client.get(f'/api/v1/notes/{note.id}/attachments/', headers=headers).status_code == 404
    assert upload(client, note, headers, image_bytes).status_code == 404


@pytest.mark.parametrize('content', [b'not an image', b'<svg xmlns="http://www.w3.org/2000/svg"/>'])
def test_invalid_images(client, note, auth_headers, attachment_storage, content):
    assert upload(client, note, auth_headers, content).status_code == 415


def test_pixel_file_and_request_limits(client, note, auth_headers, attachment_storage, image_bytes, monkeypatch):
    monkeypatch.setattr(settings, 'ATTACHMENTS_MAX_IMAGE_PIXELS', 1)
    assert upload(client, note, auth_headers, image_bytes).status_code == 413
    monkeypatch.setattr(settings, 'ATTACHMENTS_MAX_IMAGE_PIXELS', 25000000)
    monkeypatch.setattr(settings, 'ATTACHMENTS_MAX_FILE_SIZE_MB', 1)
    assert upload(client, note, auth_headers, b'x' * (1024 * 1024 + 1)).status_code == 413
    # a streaming request without Content-Length must be bounded before multipart parsing
    response = client.post(f'/api/v1/notes/{note.id}/attachments/', headers=auth_headers,
                           content=iter([b'x' * (1024 * 1024), b'x' * (128 * 1024)]))
    assert response.status_code == 413


def test_animation_rejected(client, note, auth_headers, attachment_storage):
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG', save_all=True,
                                       append_images=[Image.new('RGB', (2, 2), 'blue')], duration=100)
    assert upload(client, note, auth_headers, buffer.getvalue()).status_code == 415


def test_count_quota(client, note, auth_headers, attachment_storage, image_bytes, monkeypatch):
    monkeypatch.setattr(settings, 'ATTACHMENTS_MAX_PER_NOTE', 1)
    assert upload(client, note, auth_headers, image_bytes).status_code == 201
    assert upload(client, note, auth_headers, image_bytes).status_code == 413


def test_storage_failure_compensated(client, test_db, note, auth_headers, attachment_storage, image_bytes, monkeypatch):
    def fail(*args):
        raise StorageError('unavailable')
    monkeypatch.setattr(attachment_storage, 'put', fail)
    assert upload(client, note, auth_headers, image_bytes).status_code == 503
    assert test_db.query(NotesAttachment).count() == 0


def test_cleanup_preserves_references_and_retries(client, test_db, note, auth_headers,
                                                 attachment_storage, image_bytes, monkeypatch):
    data = upload(client, note, auth_headers, image_bytes).json()
    attachment = test_db.get(NotesAttachment, data['id'])
    attachment.deleted_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    test_db.commit()
    delete = attachment_storage.delete
    def fail(key):
        raise StorageError('offline')
    monkeypatch.setattr(attachment_storage, 'delete', fail)
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 0
    failed = test_db.get(NotesAttachment, data['id'])
    assert failed.status == 'ready'
    assert failed.is_deleted is True
    assert failed.deleted_dt < NotesAttachmentsService.retention_cutoff()
    saved = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                          json={'body': f'<img data-attachment-id="{data["id"]}"> '})
    assert saved.status_code == 422
    test_db.rollback()
    monkeypatch.setattr(attachment_storage, 'delete', delete)
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 1
    assert client.get(data['url'], headers=auth_headers).status_code == 404
    data = upload(client, note, auth_headers, image_bytes).json()
    client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                 json={'body': f'<img data-attachment-id="{data["id"]}">'})
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 0


def test_trash_and_deleted_note(client, test_db, note, test_user, auth_headers, attachment_storage, image_bytes):
    data = upload(client, note, auth_headers, image_bytes).json()
    trash = NotesFolderService.get_trash_folder(test_db, test_user.id)
    child = NotesFolderService.create_folder(test_db, test_user.id,
                                            NotesFolderCreateSchema(parent_id=trash.id, name='Nested'))
    note.folder_id = child.id
    test_db.commit()
    assert upload(client, note, auth_headers, image_bytes).status_code == 409
    assert client.get(data['url'], headers=auth_headers).status_code == 200
    note.mark_as_deleted()
    test_db.commit()
    assert client.get(data['url'], headers=auth_headers).status_code == 404
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 1


def test_missing_reference_and_external_images_rejected(client, note, auth_headers, attachment_storage):
    for image in ('<img data-attachment-id="999999999">', '<img src="https://example.test/image.png">'):
        assert client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers, json={'body': image}).status_code == 422
        assert client.post('/api/v1/notes/', headers=auth_headers,
                           json={'folder_id': note.folder_id, 'body': image}).status_code == 422


@pytest.mark.parametrize('export_type', ['html', 'markdown'])
def test_export_import_images(client, test_db, test_user, note, auth_headers, attachment_storage,
                              image_bytes, export_type):
    data = upload(client, note, auth_headers, image_bytes).json()
    client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                 json={'body': f'<p>Picture</p><img data-attachment-id="{data["id"]}" alt="Screenshot">'})
    response = client.get('/api/v1/notes/export/', headers=auth_headers,
                          params={'export_type': export_type, 'export_target': 'single_note',
                                  'export_target_id': note.id})
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        asset = next(path for path in archive.namelist() if path.startswith('assets/'))
        assert archive.read(asset) == image_bytes
        document = next(path for path in archive.namelist() if not path.startswith('assets/'))
        assert asset in archive.read(document).decode()
        assert 'data-attachment-id' not in archive.read(document).decode()
    imported = NotesImportService.import_zip(test_db, test_user.id, response.content, note.folder_id)
    assert len(imported) == 1
    assert imported[0].id != note.id
    image = BeautifulSoup(imported[0].body, 'html.parser').find('img')
    assert int(image['data-attachment-id']) != data['id']
    attachments = NotesAttachmentsService.list_attachments(test_db, imported[0].id, test_user.id)
    assert len(attachments) == 1
    with attachment_storage.open(attachments[0].storage_key) as stream:
        assert stream.read() == image_bytes


def test_pdf_contains_private_image(client, note, auth_headers, attachment_storage, image_bytes):
    data = upload(client, note, auth_headers, image_bytes).json()
    client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                 json={'body': f'<img data-attachment-id="{data["id"]}">'})
    response = client.get('/api/v1/notes/export/', headers=auth_headers,
                          params={'export_type': 'pdf', 'export_target': 'single_note',
                                  'export_target_id': note.id})
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF')
    assert b'/Subtype /Image' in response.content


@pytest.mark.parametrize('path', ['../escape.png', '/absolute.png', 'C:/escape.png'])
def test_unsafe_import_archive_paths(client, note, auth_headers, attachment_storage, image_bytes, path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('note.html', '<h1>Image</h1><p>Body</p>')
        archive.writestr(path, image_bytes)
    response = client.post('/api/v1/notes/import/', headers=auth_headers,
                           params={'folder_id': note.folder_id},
                           files={'files': ('images.zip', output.getvalue(), 'application/zip')})
    assert response.status_code == 422


def test_legacy_external_image_preserved_but_not_modified(client, test_db, note, auth_headers):
    note.body = '<p>Old</p><img src="https://example.test/old.png" alt="Old">'
    test_db.commit()
    saved = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                          json={'body': note.body.replace('<p>Old</p>', '<p>New</p>')})
    assert saved.status_code == 200
    changed = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                            json={'body': saved.json()['body'].replace('alt="Old"', 'alt="Changed"')})
    assert changed.status_code == 422


def test_cleanup_stale_upload(client, test_db, note, auth_headers, attachment_storage, image_bytes):
    data = upload(client, note, auth_headers, image_bytes).json()
    attachment = test_db.get(NotesAttachment, data['id'])
    attachment.status = 'uploading'
    attachment.created_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    test_db.commit()
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 1
    assert test_db.get(NotesAttachment, data['id']) is None


def test_cleanup_permanently_deleted_parent_folder(client, test_db, note, test_user, auth_headers,
                                                  attachment_storage, image_bytes):
    parent = NotesFolderService.create_folder(test_db, test_user.id,
                                             NotesFolderCreateSchema(parent_id=note.folder_id, name='Parent'))
    child = NotesFolderService.create_folder(test_db, test_user.id,
                                            NotesFolderCreateSchema(parent_id=parent.id, name='Child'))
    note.folder_id = child.id
    test_db.commit()
    data = upload(client, note, auth_headers, image_bytes).json()
    client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                 json={'body': f'<img data-attachment-id="{data["id"]}">'})
    NotesFolderService.delete_folder(test_db, parent.id, test_user.id)
    assert client.get(data['url'], headers=auth_headers).status_code == 404
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 1


def test_expired_soft_deleted_attachment_cannot_be_restored(client, test_db, note, auth_headers,
                                                           attachment_storage, image_bytes):
    data = upload(client, note, auth_headers, image_bytes).json()
    attachment = test_db.get(NotesAttachment, data['id'])
    attachment.deleted_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    deleted_dt = attachment.deleted_dt
    test_db.commit()
    assert attachment.is_deleted is True
    assert client.get(data['url'], headers=auth_headers).status_code == 404
    assert client.get(f'/api/v1/notes/{note.id}/attachments/', headers=auth_headers).json() == []
    response = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                            json={'body': f'<img data-attachment-id="{data["id"]}">'})
    assert response.status_code == 422
    test_db.rollback()
    response = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers, json={'body': '<p>Still removed</p>'})
    assert response.status_code == 200
    test_db.refresh(attachment)
    assert attachment.deleted_dt == deleted_dt
    assert NotesAttachmentsService.cleanup(test_db, attachment_storage) == 1


@pytest.mark.parametrize('invalid_id', ['0', '-1', 'abc', '1.5'])
def test_invalid_integer_attachment_ids(client, note, auth_headers, attachment_storage, invalid_id):
    response = client.patch(f'/api/v1/notes/{note.id}/', headers=auth_headers,
                            json={'body': f'<img data-attachment-id="{invalid_id}">'})
    assert response.status_code == 422
