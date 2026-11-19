import datetime as dt
import pytest
from bs4 import BeautifulSoup

from app.models import User, NotesAttachment
from app.schemas.notes import NoteCreateSchema, NoteSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


@pytest.mark.parametrize('initial_body', ['', '<p>Original</p>'])
def test_append_preserves_metadata_and_returns_updated_note(client, test_db, note, auth_headers, initial_body):
    note.body = initial_body
    note.updated_dt = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    test_db.commit()
    previous_updated_dt = note.updated_dt

    fragment = '<p>Comment</p><blockquote><p>Selected text</p></blockquote><p><a href="https://example.com">Source</a></p>'
    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json={'body': fragment})

    assert response.status_code == 200, response.text
    result = NoteSchema.model_validate(response.json())
    assert (result.id, result.folder_id, result.title, result.is_pinned, result.pin_index) == (
        note.id, note.folder_id, 'Collected material', True, 0,
    )
    assert result.updated_dt > previous_updated_dt
    assert result.body == initial_body + fragment.replace(
        'href="https://example.com"', 'href="https://example.com" rel="noopener noreferrer"',
    )
    test_db.refresh(note)
    expected_text = 'Original Comment Selected text Source' if initial_body else 'Comment Selected text Source'
    assert note.body_plain_text == expected_text
    fetched = client.get(f'/api/v1/notes/{note.id}/', headers=auth_headers)
    assert fetched.json() == response.json()


def test_sequential_appends_preserve_order(client, test_db, note, auth_headers):
    for fragment in ['<p>First</p>', '<p>Second</p>']:
        response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json={'body': fragment})
        assert response.status_code == 200, response.text

    assert response.json()['body'] == '<p>Original</p><p>First</p><p>Second</p>'
    test_db.refresh(note)
    assert note.body_plain_text == 'Original First Second'


def test_append_sanitizes_html_and_urls(client, test_db, note, auth_headers):
    response = client.post(
        f'/api/v1/notes/{note.id}/append/', headers=auth_headers,
        json={'body': '<script>secret()</script><p onclick="secret()">Safe</p>'
                      '<a href="javascript:secret()">Unsafe URL</a><a href="https://example.com">Source</a>'},
    )

    assert response.status_code == 200, response.text
    body = response.json()['body']
    assert '<p>Original</p><p>Safe</p>' in body
    assert 'script' not in body and 'onclick' not in body and 'secret' not in body
    links = BeautifulSoup(body, 'html.parser').find_all('a')
    assert 'href' not in links[0].attrs
    assert links[1]['href'] == 'https://example.com'
    test_db.refresh(note)
    assert note.body_plain_text == 'Original Safe Unsafe URL Source'


@pytest.mark.parametrize('payload', [
    {}, {'body': None}, {'body': 42}, {'body': []},
    {'body': ''}, {'body': ' \n\t'}, {'body': '<!-- comment -->'},
    {'body': '<script>alert(1)</script><style>p { color: red; }</style>'},
    {'body': '<p> &nbsp; <br></p><blockquote></blockquote>'},
    {'body': '<p>New</p>', 'title': 'Changed'},
    {'body': '<p>New</p>', 'folder_id': 123},
    {'body': '<p>New</p>', 'is_pinned': False},
])
def test_invalid_append_does_not_change_note(client, test_db, note, auth_headers, payload):
    previous_updated_dt = note.updated_dt
    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json=payload)

    assert response.status_code == 422, response.text
    test_db.refresh(note)
    assert note.body == '<p>Original</p>'
    assert note.updated_dt == previous_updated_dt
    assert note.is_pinned is True


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer invalid'}])
def test_append_requires_authentication(client, test_db, note, headers):
    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=headers, json={'body': '<p>New</p>'})

    assert response.status_code == 401
    test_db.refresh(note)
    assert note.body == '<p>Original</p>'


@pytest.mark.parametrize('target', ['missing', 'deleted', 'foreign', 'deleted_parent'])
def test_append_hides_unavailable_notes(client, test_db, test_user, note, auth_headers, target):
    note_id = note.id
    if target == 'missing':
        note_id = -1
    elif target == 'deleted':
        note.mark_as_deleted()
        test_db.commit()
    elif target == 'foreign':
        owner = User(
            username='append-owner', email='append-owner@example.test', hashed_password='unused', is_active=True,
        )
        test_db.add(owner)
        test_db.commit()
        root = NotesFolderService.get_root_folder(test_db, owner.id)
        foreign = NoteService.create_note(
            test_db, owner.id, NoteCreateSchema(folder_id=root.id, body='<p>Private</p>'),
        )
        note_id = foreign.id
    elif target == 'deleted_parent':
        parent = NotesFolderService.create_folder(
            test_db, test_user.id, NotesFolderCreateSchema(parent_id=note.folder_id, name='Parent'),
        )
        child = NotesFolderService.create_folder(
            test_db, test_user.id, NotesFolderCreateSchema(parent_id=parent.id, name='Child'),
        )
        note.folder_id = child.id
        parent.mark_as_deleted()
        test_db.commit()

    response = client.post(f'/api/v1/notes/{note_id}/append/', headers=auth_headers, json={'body': '<p>New</p>'})

    assert response.status_code == 404
    assert response.json() == {'detail': 'Note not found'}
    test_db.refresh(note)
    assert note.body == '<p>Original</p>'
    if target == 'foreign':
        test_db.refresh(foreign)
        assert foreign.body == '<p>Private</p>'


@pytest.mark.parametrize('nested', [False, True])
def test_append_rejects_notes_in_trash(client, test_db, test_user, note, auth_headers, nested):
    folder = NotesFolderService.get_trash_folder(test_db, test_user.id)
    if nested:
        folder = NotesFolderService.create_folder(
            test_db, test_user.id, NotesFolderCreateSchema(parent_id=note.folder_id, name='Child'),
        )
        folder.parent_id = NotesFolderService.get_trash_folder(test_db, test_user.id).id
    note.folder_id = folder.id
    test_db.commit()

    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json={'body': '<p>New</p>'})

    assert response.status_code == 409
    test_db.refresh(note)
    assert note.body == '<p>Original</p>'


def test_append_preserves_existing_attachment_and_legacy_image(client, test_db, note, auth_headers):
    attachment = NotesAttachment(
        note_id=note.id, attachment_type='image', content_type='image/png', status='ready',
        original_filename='image.png', storage_key='append/image.png', size_bytes=10,
    )
    test_db.add(attachment)
    test_db.flush()
    attachment_url = f'/api/v1/notes/{note.id}/attachments/{attachment.id}/content/'
    note.body = f'<p>Original</p><img data-attachment-id="{attachment.id}" src="{attachment_url}">'
    note.body += '<img src="https://example.com/legacy.png">'
    test_db.commit()

    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json={'body': '<p>New</p>'})

    assert response.status_code == 200, response.text
    body = response.json()['body']
    assert f'data-attachment-id="{attachment.id}"' in body
    assert f'src="{attachment_url}"' in body
    assert 'src="https://example.com/legacy.png"' in body
    assert body.endswith('<p>New</p>')
    test_db.refresh(attachment)
    assert attachment.is_deleted is False


@pytest.mark.parametrize('fragment', [
    '<img src="https://example.com/new.png">',
    '<a data-attachment-id="999999">Unavailable file</a>',
])
def test_append_validates_attachment_references(client, test_db, note, auth_headers, fragment):
    response = client.post(f'/api/v1/notes/{note.id}/append/', headers=auth_headers, json={'body': fragment})

    assert response.status_code == 422
    test_db.refresh(note)
    assert note.body == '<p>Original</p>'
