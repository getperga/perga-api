from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.notes import NoteCreateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


class TestNotesSearchAPI:
    def test_search_notes(self, client: TestClient, test_db: Session, test_user, auth_headers):
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

        response = client.get(
            f'{settings.API_V1_STR}/notes/search/',
            params={'query': 'milk'},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['title'] == 'Grocery list'
        assert 'body' not in data[0]
