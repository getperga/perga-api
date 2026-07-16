from sqlalchemy.orm import Session

from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


class TestNoteService:
    def test_create_and_get_note(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        create = NoteCreateSchema(title='My Note', body='Hello world', folder_id=root_folder.id)
        note = NoteService.create_note(test_db, user_id=test_user.id, create_data=create)

        assert note.id is not None
        assert note.title == create.title
        assert note.body == create.body
        assert note.user_id == test_user.id

        fetched = NoteService.get_note(test_db, note_id=note.id, user_id=test_user.id)
        assert fetched is not None
        assert fetched.id == note.id

    def test_update_note(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='', body='old', folder_id=root_folder.id)
        )
        updated = NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(title='New Title', body='new')
        )
        assert updated is not None
        assert updated.title == 'New Title'
        assert updated.body == 'new'

    def test_mark_note_as_deleted(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(body='to delete',folder_id=root_folder.id)
        )
        delete_result = NoteService.delete_note(test_db, note_id=note.id, user_id=test_user.id)
        assert delete_result is True

        # Should not appear in base query anymore
        found = NoteService.get_note(test_db, note_id=note.id, user_id=test_user.id)
        assert found is None

    def test_extract_plain_text(self):
        html = '<p>Hello <strong>world</strong></p><ul><li>item one</li></ul>'
        assert NoteService.extract_plain_text(html) == 'Hello world item one'
        assert NoteService.extract_plain_text('') == ''

    def test_create_note_sets_body_plain_text(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='My Note',
                body='<p>Hello <b>world</b></p>',
                folder_id=root_folder.id
            )
        )
        assert note.body_plain_text == 'Hello world'

    def test_update_note_recomputes_body_plain_text(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(body='<p>old text</p>', folder_id=root_folder.id)
        )
        updated = NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(body='<p>new content</p>')
        )
        assert updated.body_plain_text == 'new content'

    def test_search_notes(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Grocery list',
                body='<p>buy milk and eggs</p>',
                folder_id=root_folder.id
            )
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Meeting notes',
                body='<p>discuss roadmap</p>',
                folder_id=root_folder.id
            )
        )

        results = NoteService.search_notes(test_db, user_id=test_user.id, query='milk')
        assert len(results) == 1
        assert results[0].title == 'Grocery list'

        results = NoteService.search_notes(test_db, user_id=test_user.id, query='roadmap')
        assert len(results) == 1
        assert results[0].title == 'Meeting notes'

        results = NoteService.search_notes(test_db, user_id=test_user.id, query='nonexistentword')
        assert results == []
