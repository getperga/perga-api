from sqlalchemy.orm import Session

from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_import_service import NotesImportService
from app.services.notes_service import NoteService


class TestNoteSanitization:
    def test_create_note_with_malicious_html(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        malicious_body = "<p>Safe content</p><script>alert('xss')</script><img src='x' onerror='alert(1)'>"
        create = NoteCreateSchema(title='Malicious Note', body=malicious_body, folder_id=root_folder.id)
        note = NoteService.create_note(test_db, user_id=test_user.id, create_data=create)

        # Now it SHOULD be sanitized.
        assert '<script>' not in note.body
        assert 'onerror' not in note.body
        assert '<p>Safe content</p>' in note.body

    def test_update_note_with_malicious_html(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Initial', body='Initial body', folder_id=root_folder.id)
        )

        malicious_body = "<div onclick='alert(1)'>Click me</div>"
        updated = NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(body=malicious_body)
        )

        assert 'onclick' not in updated.body
        assert 'Click me' in updated.body
        assert '<div' not in updated.body

    def test_import_note_with_malicious_html(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        malicious_html = ("<html><head><title>Bad Note</title></head><body><script>alert(1)</script>"
                          "<p>Imported content</p></body></html>")

        note = NotesImportService.import_file(
            test_db,
            user_id=test_user.id,
            filename='bad.html',
            content=malicious_html.encode('utf-8'),
            folder_id=root_folder.id
        )

        assert note is not None
        assert '<script>' not in note.body
        assert '<p>Imported content</p>' in note.body

    def test_note_body_from_editor_clean(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        input_html = (
            "<h1>Title</h1>"
            "<p>Paragraph with <strong>bold</strong> and <em>italic</em></p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "<table><tbody><tr><td>Cell 1</td><td>Cell 2</td></tr></tbody></table>"
            "<pre><code>print('hello')</code></pre>"
            "<blockquote class='my-quote'>Quote</blockquote>"
            "<a href='https://example.com' target='_blank' rel='noopener'>Link</a>"
            "</div>"
        )
        create = NoteCreateSchema(title='Editor Note', body=input_html, folder_id=root_folder.id)
        note = NoteService.create_note(test_db, user_id=test_user.id, create_data=create)

        # Basic tags should be preserved
        assert '<h1>Title</h1>' in note.body
        assert '<strong>bold</strong>' in note.body
        assert '<em>italic</em>' in note.body
        assert '<ul><li>Item 1</li><li>Item 2</li></ul>' in note.body
        assert '<table><tbody><tr><td>Cell 1</td><td>Cell 2</td></tr></tbody></table>' in note.body
        assert '<pre><code>print(\'hello\')</code></pre>' in note.body
        assert '<blockquote>Quote</blockquote>' in note.body

        # Attributes should be preserved
        assert 'href="https://example.com"' in note.body
        assert 'target="_blank"' in note.body
        assert 'rel="noopener noreferrer"' in note.body

    def test_note_body_editor_special_attrs(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        task_list_html = (
            '<ul data-type="taskList">'
            '<li data-type="taskItem" data-checked="true">Task 1</li>'
            '<li data-type="taskItem" data-checked="false">Task 2</li>'
            '</ul>'
            '<ul data-type="normalList"><li>Normal</li></ul>'
        )
        create = NoteCreateSchema(title='Task List', body=task_list_html, folder_id=root_folder.id)
        note = NoteService.create_note(test_db, user_id=test_user.id, create_data=create)

        assert '<ul data-type="taskList">' in note.body
        assert '<li data-type="taskItem"' in note.body
        assert 'data-checked="true"' in note.body
        assert 'data-type="normalList"' not in note.body
        assert '<ul><li>Normal</li></ul>' in note.body
