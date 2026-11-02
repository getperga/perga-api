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
        assert note.is_pinned is False

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

    def test_pin_and_unpin_note(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Important', folder_id=root_folder.id)
        )

        pinned = NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(is_pinned=True),
        )
        assert pinned is not None
        assert pinned.is_pinned is True

        unpinned = NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(is_pinned=False),
        )
        assert unpinned is not None
        assert unpinned.is_pinned is False

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

    def test_search_notes_supports_english_stemming_and_prefixes(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Weekly meeting',
                body='<p>The team planned the launch</p>',
                folder_id=root_folder.id,
            ),
        )

        stemming_results = NoteService.search_notes(test_db, user_id=test_user.id, query='planning')
        assert [note.title for note in stemming_results] == ['Weekly meeting']
        assert stemming_results[0].matched_in_title is False
        assert stemming_results[0].matched_in_body is True
        assert stemming_results[0].match_kind == 'exact'
        assert stemming_results[0].find_query is None

        prefix_results = NoteService.search_notes(test_db, user_id=test_user.id, query='wee')
        assert [note.title for note in prefix_results] == ['Weekly meeting']
        assert prefix_results[0].matched_in_title is True
        assert prefix_results[0].matched_in_body is False
        assert prefix_results[0].match_kind == 'prefix'

    def test_search_notes_supports_title_typos(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Project roadmap',
                body='<p>Launch schedule</p>',
                folder_id=root_folder.id,
            ),
        )

        results = NoteService.search_notes(test_db, user_id=test_user.id, query='roadmp')

        assert [note.title for note in results] == ['Project roadmap']
        assert results[0].matched_in_title is True
        assert results[0].matched_in_body is False
        assert results[0].match_kind == 'fuzzy'

    def test_search_notes_ranks_title_above_body_and_returns_literal_find_query(
        self,
        test_db: Session,
        test_user,
    ):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Roadmap',
                body='<p>Milestones</p>',
                folder_id=root_folder.id,
            ),
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Meeting notes',
                body='<p>Discuss the roadmap tomorrow</p>',
                folder_id=root_folder.id,
            ),
        )

        results = NoteService.search_notes(test_db, user_id=test_user.id, query='roadmap')

        assert [note.title for note in results] == ['Roadmap', 'Meeting notes']
        assert results[0].find_query is None
        assert results[1].matched_in_body is True
        assert results[1].find_query == 'roadmap'
