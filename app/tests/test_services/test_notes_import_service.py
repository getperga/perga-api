import io
import zipfile
from sqlalchemy.orm import Session

from app.services.notes_folders_service import NotesFolderService
from app.services.notes_import_service import NotesImportService


class TestNotesImportService:
    def test_parse_txt(self):
        title, body = NotesImportService._parse_txt('Hello World', 'test')
        assert title == 'test'
        assert body == '<p>Hello World</p>'

    def test_parse_markdown(self):
        content = '# My Title\n\nThis is a test note.'
        title, body = NotesImportService._parse_markdown(content, 'test')
        assert title == 'My Title'
        assert body == '<p>This is a test note.</p>'

    def test_parse_markdown_no_h1(self):
        content = 'This is a test note without H1.'
        title, body = NotesImportService._parse_markdown(content, '')
        assert title == 'Untitled Note'
        assert body == '<p>This is a test note without H1.</p>'

    def test_parse_html_with_title(self):
        content = '<html><head><title>Page Title</title></head><body><h1>H1 Title</h1><p>Content</p></body></html>'
        title, body = NotesImportService._parse_html(content, 'test')
        assert title == 'Page Title'
        assert '<h1>H1 Title</h1>' in body
        assert '<p>Content</p>' in body

    def test_parse_html_no_title_with_h1(self):
        content = '<html><body><h1>H1 Only</h1><p>Content</p></body></html>'
        title, body = NotesImportService._parse_html(content, 'test')
        assert title == 'H1 Only'
        assert '<h1>H1 Only</h1>' not in body
        assert '<p>Content</p>' in body

    def test_parse_html_with_title_and_h1(self):
        content = '<html><head><title>Page Title</title></head><body><h1>H1 Title</h1><p>Content</p></body></html>'
        title, body = NotesImportService._parse_html(content, 'test')
        assert title == 'Page Title'
        assert '<h1>H1 Title</h1>' in body
        assert '<p>Content</p>' in body

    def test_import_single_file(self, test_db: Session, test_user):
        content = b'# Note from file\nBody'
        folder = NotesFolderService.get_root_folder(test_db, test_user.id)
        note = NotesImportService.import_file(test_db, test_user.id, 'test.md', content, folder.id)
        assert note is not None
        assert note.title == 'Note from file'
        assert note.body == '<p>Body</p>'
        assert note.user_id == test_user.id
        assert note.folder_id == folder.id

    def test_import_zip(self, test_db: Session, test_user):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
            zip_file.writestr('note1.txt', 'Content 1')
            zip_file.writestr('folder1/note2.md', '# Title 2\nBody 2')
            zip_file.writestr(
                'folder1/subfolder/note3.html',
                '<html><title>Title 3</title><body>Body 3</body></html>'
            )

        zip_content = zip_buffer.getvalue()
        root_folder = NotesFolderService.get_root_folder(test_db, test_user.id)
        notes = NotesImportService.import_zip(test_db, test_user.id, zip_content, root_folder.id)
        assert len(notes) == 3
        
        # Check note 1 (root)
        note1 = next(note for note in notes if note.title == 'note1')
        assert note1.folder_id == root_folder.id
        assert note1.body == '<p>Content 1</p>'
        
        # Check note 2 (in folder1)
        note2 = next(note for note in notes if note.title == 'Title 2')
        assert note2.body == '<p>Body 2</p>'
        folder1 = NotesFolderService.get_base_query(test_db).filter_by(name='folder1', user_id=test_user.id).first()
        assert folder1 is not None
        assert note2.folder_id == folder1.id
        assert folder1.parent_id == root_folder.id
        
        # Check note 3 (in folder1/subfolder)
        note3 = next(note for note in notes if note.title == 'Title 3')
        assert 'Body 3' in note3.body
        subfolder = NotesFolderService.get_base_query(test_db).filter_by(name='subfolder', user_id=test_user.id).first()
        assert subfolder is not None
        assert note3.folder_id == subfolder.id
        assert subfolder.parent_id == folder1.id

    def test_import_zip_non_ascii(self, test_db: Session, test_user):
        name_utf8 = "Папка"
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
            zip_file.writestr(name_utf8 + "/note.txt", 'Content')

        zip_content = zip_buffer.getvalue()
        
        root_folder = NotesFolderService.get_root_folder(test_db, test_user.id)
        NotesImportService.import_zip(test_db, test_user.id, zip_content, root_folder.id)
        
        folder = NotesFolderService.get_base_query(test_db).filter_by(name=name_utf8, user_id=test_user.id).first()
        assert folder is not None, f"Folder with name '{name_utf8}' should exist"
