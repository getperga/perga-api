import io
import urllib.parse
import zipfile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.const.notes import ExportType, ExportTarget
from app.core.config import settings
from app.schemas.notes import NoteCreateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_service import NoteService
from app.services.notes_folders_service import NotesFolderService


class TestNotesExportAPI:
    TEST_NOTE_TITLE = 'Test Note'
    TEST_NOTE_BODY = '<h2>Hello</h2><p>World</p>'

    def test_export_single_note_html(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title=self.TEST_NOTE_TITLE,
                body=self.TEST_NOTE_BODY,
                folder_id=root_folder.id
            )
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.HTML.value,
                'export_target': ExportTarget.SINGLE_NOTE.value,
                'export_target_id': note.id,
            },
            headers=auth_headers
        )

        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        expected_filename = urllib.parse.quote(self.TEST_NOTE_TITLE)
        assert f"attachment; filename*=UTF-8''{expected_filename}.html" in response.headers['content-disposition']
        assert response.text == f'<h1>{self.TEST_NOTE_TITLE}</h1>{self.TEST_NOTE_BODY}'

    def test_export_single_note_markdown(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title=self.TEST_NOTE_TITLE,
                body=self.TEST_NOTE_BODY,
                folder_id=root_folder.id
            )
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.MARKDOWN.value,
                'export_target': ExportTarget.SINGLE_NOTE.value,
                'export_target_id': note.id,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert 'text/markdown' in response.headers['content-type']
        expected_filename = urllib.parse.quote(self.TEST_NOTE_TITLE)
        assert f"attachment; filename*=UTF-8''{expected_filename}.md" in response.headers['content-disposition']
        # markdownify of <h2>Hello</h2><p>World</p> should be something like 'Hello\n=====\n\nWorld\n\n'
        assert 'Hello' in response.text
        assert 'World' in response.text

    def test_export_folder_zip(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        folder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='My Folder', parent_id=root_folder.id)
        )
        
        note1 = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 1', body='Body 1', folder_id=folder.id)
        )
        note2 = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 2', body='Body 2', folder_id=folder.id)
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.MARKDOWN.value,
                'export_target': ExportTarget.FOLDER_NOTES.value,
                'export_target_id': folder.id,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/x-zip-compressed'
        expected_zip_name = urllib.parse.quote(f'notes_folder_{folder.name}.zip')
        assert f"attachment; filename*=UTF-8''{expected_zip_name}" in response.headers['content-disposition']
        
        # Verify ZIP content
        zip_content = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_content) as zf:
            filenames = zf.namelist()
            assert f'{note1.title}.md' in filenames
            assert f'{note2.title}.md' in filenames
            assert zf.read(f'{note1.title}.md').decode().strip() == f'# {note1.title}\n\n{note1.body}'

    def test_export_all_notes_zip(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        
        root_note =NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Root Note', body='Root Body', folder_id=root_folder.id)
        )
        
        folder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Subfolder', parent_id=root_folder.id)
        )
        sub_note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Sub Note', body='Sub Body', folder_id=folder.id)
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.HTML.value,
                'export_target': ExportTarget.ALL_NOTES.value,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "attachment; filename*=UTF-8''all_notes.zip" in response.headers['content-disposition']
        
        zip_content = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_content) as zf:
            filenames = zf.namelist()
            assert f'{root_note.title}.html' in filenames
            assert f'{sub_note.title}.html' in filenames

    def test_export_not_found(self, client: TestClient, test_user, auth_headers):
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.MARKDOWN.value,
                'export_target': ExportTarget.SINGLE_NOTE.value,
                'export_target_id': 456,
            },
            headers=auth_headers
        )
        assert response.status_code == 404
        assert response.json()['detail'] == 'Note not found'

    def test_export_single_note_pdf(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Test Note PDF',
                body='<h2>Hello</h2><p>World</p>',
                folder_id=root_folder.id
            )
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.PDF.value,
                'export_target': ExportTarget.SINGLE_NOTE.value,
                'export_target_id': note.id,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert 'application/pdf' in response.headers['content-type']
        expected_filename = urllib.parse.quote(note.title)
        assert f"attachment; filename*=UTF-8''{expected_filename}.pdf" in response.headers['content-disposition']
        assert response.content.startswith(b'%PDF')

    def test_export_folder_zip_recursive(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        folder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Parent', parent_id=root_folder.id)
        )
        subfolder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Child', parent_id=folder.id)
        )
        note1 = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 1', body='B1', folder_id=folder.id)
        )
        note2 = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 2', body='B2', folder_id=subfolder.id)
        )

        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.HTML.value,
                'export_target': ExportTarget.FOLDER_NOTES.value,
                'export_target_id': folder.id,
            },
            headers=auth_headers
        )

        assert response.status_code == 200
        zip_content = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_content) as zf:
            filenames = zf.namelist()
            assert f'{note1.title}.html' in filenames
            assert f'Child/{note2.title}.html' in filenames

    def test_export_folder_zip_pdf(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        folder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='PDF Folder', parent_id=root_folder.id)
        )
        
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note', body='Body', folder_id=folder.id)
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.PDF.value,
                'export_target': ExportTarget.FOLDER_NOTES.value,
                'export_target_id': folder.id,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        expected_zip_name = urllib.parse.quote(f'notes_folder_{folder.name}.zip')
        assert f"attachment; filename*=UTF-8''{expected_zip_name}" in response.headers['content-disposition']
        
        # Verify ZIP content
        zip_content = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_content) as zf:
            filenames = zf.namelist()
            note_filename = f'{note.title}.pdf'
            assert note_filename in filenames
            assert zf.read(note_filename).startswith(b'%PDF')

    def test_export_single_note_non_ascii_filename(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        title = 'Привет мир'
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title=title,
                body='Содержимое',
                folder_id=root_folder.id
            )
        )
        
        response = client.get(
            f'{settings.API_V1_STR}/notes/export/',
            params={
                'export_type': ExportType.HTML.value,
                'export_target': ExportTarget.SINGLE_NOTE.value,
                'export_target_id': note.id,
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        # The filename in Content-Disposition should be encoded or present in filename*
        content_disp = response.headers['content-disposition']
        assert 'filename*=UTF-8\'\'%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82%20%D0%BC%D0%B8%D1%80.html' in content_disp
