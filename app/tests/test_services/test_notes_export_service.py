import zipfile
from sqlalchemy.orm import Session

from app.const.notes import ExportType
from app.models.notes import Note
from app.services.notes_export_service import NotesExportService
from app.services.notes_service import NoteService
from app.services.notes_folders_service import NotesFolderService
from app.schemas.notes import NoteCreateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema


class TestNotesExportService:
    def test_get_note_content_html(self, test_db: Session, test_user):
        note = Note(title='Test', body='<h1>Hello</h1>', user_id=test_user.id)
        content = NotesExportService._get_note_content(note, ExportType.HTML)
        assert content == '<h1>Test</h1><h1>Hello</h1>'

    def test_get_note_content_markdown(self, test_db: Session, test_user):
        note = Note(title='Test', body='<h1>Hello</h1>', user_id=test_user.id)
        content = NotesExportService._get_note_content(note, ExportType.MARKDOWN)
        assert content.startswith('# Test')
        assert 'Hello' in content

    def test_generate_export_filename(self, test_db: Session, test_user):
        note = Note(id=1, title='My Note!', body='', user_id=test_user.id)
        filename = NotesExportService._generate_export_filename(note, ExportType.HTML)
        # '!' is stripped by WHITELIST_FILENAME_CHARS_RE
        assert filename == 'My Note.html'

        note_no_title = Note(id=2, title='!:!:!', body='', user_id=test_user.id)
        filename = NotesExportService._generate_export_filename(note_no_title, ExportType.MARKDOWN)
        # '!!!' becomes empty, then falls back to note_{id}
        assert filename == 'note_2.md'

    def test_export_single_note(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Test', body='Body', folder_id=root_folder.id)
        )
        
        content, filename = NotesExportService.export_single_note(
            test_db, user_id=test_user.id, note_id=note.id, export_type=ExportType.HTML
        )
        assert content == '<h1>Test</h1>Body'
        assert filename == 'Test.html'

    def test_export_folder(self, test_db: Session, test_user):
        folder = NotesFolderService.create_folder(
            test_db, user_id=test_user.id, create_data=NotesFolderCreateSchema(name='Folder')
        )
        NoteService.create_note(
            test_db, user_id=test_user.id, create_data=NoteCreateSchema(title='Note 1', body='B1', folder_id=folder.id)
        )
        
        zip_buffer, filename = NotesExportService.export_folder(
            test_db, user_id=test_user.id, folder_id=folder.id, export_type=ExportType.HTML
        )
        assert zip_buffer is not None
        assert filename == 'notes_folder_Folder.zip'
        
        with zipfile.ZipFile(zip_buffer) as zf:
            assert 'Note 1.html' in zf.namelist()

    def test_export_all_notes(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 1', body='B1', folder_id=root_folder.id)
        )
        
        zip_buffer, filename = NotesExportService.export_all_notes(
            test_db, user_id=test_user.id, export_type=ExportType.HTML
        )
        assert zip_buffer is not None
        assert filename == 'all_notes.zip'
        
        with zipfile.ZipFile(zip_buffer) as zf:
            assert 'Note 1.html' in zf.namelist()

    def test_export_folder_recursive(self, test_db: Session, test_user):
        folder = NotesFolderService.create_folder(
            test_db, user_id=test_user.id, create_data=NotesFolderCreateSchema(name='Parent')
        )
        subfolder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Child', parent_id=folder.id)
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 1', body='B1', folder_id=folder.id)
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 2', body='B2', folder_id=subfolder.id)
        )
        
        # This note should be ignored
        deleted_note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Deleted Note', body='B3', folder_id=folder.id)
        )
        deleted_note.is_deleted = True
        test_db.commit()

        zip_buffer, filename = NotesExportService.export_folder(
            test_db, user_id=test_user.id, folder_id=folder.id, export_type=ExportType.HTML
        )
        assert zip_buffer is not None
        with zipfile.ZipFile(zip_buffer) as zf:
            filenames = zf.namelist()
            assert 'Note 1.html' in filenames
            assert 'Child/Note 2.html' in filenames
            assert 'Deleted Note.html' not in filenames

    def test_export_folder_recursive_with_deleted_subfolder(self, test_db: Session, test_user):
        folder = NotesFolderService.create_folder(
            test_db, user_id=test_user.id, create_data=NotesFolderCreateSchema(name='Parent')
        )
        subfolder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Deleted Child', parent_id=folder.id)
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 1', body='B1', folder_id=folder.id)
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note 2', body='B2', folder_id=subfolder.id)
        )
        
        subfolder.is_deleted = True
        test_db.commit()

        zip_buffer, filename = NotesExportService.export_folder(
            test_db, user_id=test_user.id, folder_id=folder.id, export_type=ExportType.HTML
        )
        assert zip_buffer is not None
        with zipfile.ZipFile(zip_buffer) as zf:
            filenames = zf.namelist()
            assert 'Note 1.html' in filenames
            assert 'Deleted Child/Note 2.html' not in filenames

    def test_export_zip_duplicate_filenames(self, test_db: Session, test_user):
        folder = NotesFolderService.create_folder(
            test_db, user_id=test_user.id, create_data=NotesFolderCreateSchema(name='Duplicates')
        )
        # Two notes with same title
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Duplicate', body='B1', folder_id=folder.id)
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Duplicate', body='B2', folder_id=folder.id)
        )

        zip_buffer, filename = NotesExportService.export_folder(
            test_db, user_id=test_user.id, folder_id=folder.id, export_type=ExportType.HTML
        )
        with zipfile.ZipFile(zip_buffer) as zf:
            filenames = zf.namelist()
            assert 'Duplicate.html' in filenames
            assert 'Duplicate_1.html' in filenames

    def test_get_note_content_pdf(self, test_db: Session, test_user):
        note = Note(title='Test', body='<h1>Hello</h1>', user_id=test_user.id)
        content = NotesExportService._get_note_content(note, ExportType.PDF)
        assert isinstance(content, bytes)
        assert content.startswith(b'%PDF')

    def test_export_single_note_pdf(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Test PDF', body='Body PDF', folder_id=root_folder.id)
        )
        
        content, filename = NotesExportService.export_single_note(
            test_db, user_id=test_user.id, note_id=note.id, export_type=ExportType.PDF
        )
        assert isinstance(content, bytes)
        assert content.startswith(b'%PDF')
        assert filename == 'Test PDF.pdf'
