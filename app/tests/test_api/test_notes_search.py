from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


class TestNotesSearchAPI:
    def test_search_notes(self, client: TestClient, test_db: Session, test_user, auth_headers):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Grocery list',
                body='<p>buy milk and eggs</p>',
                folder_id=root_folder.id
            )
        )
        NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(is_pinned=True),
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

        response = client.get(
            f'{settings.API_V1_STR}/notes/search/',
            params={'query': 'milk'},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['title'] == 'Grocery list'
        assert data[0]['is_pinned'] is True
        assert 'body' not in data[0]
        assert data[0]['folders_path'] == []

    def test_search_notes_includes_folder_path(self, client: TestClient, test_db: Session, test_user, auth_headers):
        folder1 = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder1')
        )
        folder2 = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder2')
        )
        subfolder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Subfolder', parent_id=folder2.id)
        )
        trash_folder = NotesFolderService.get_trash_folder(test_db, user_id=test_user.id)

        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Project roadmap',
                body='<p>roadmap</p>',
                folder_id=folder1.id
            )
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Roadmap details',
                body='<p>roadmap</p>',
                folder_id=subfolder.id
            )
        )
        NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Old roadmap',
                body='<p>roadmap</p>',
                folder_id=trash_folder.id
            )
        )

        response = client.get(
            f'{settings.API_V1_STR}/notes/search/',
            params={'query': 'roadmap'},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        paths_by_title = {note['title']: note['folders_path'] for note in data}
        assert paths_by_title == {
            'Project roadmap': ['Folder1'],
            'Roadmap details': ['Folder2', 'Subfolder'],
            'Old roadmap': ['Trash'],
        }
