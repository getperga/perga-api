from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.auth_utils import generate_password_hash
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


class TestNotesAPI:
    def test_create_get_pin_and_unpin_note(
        self,
        client: TestClient,
        test_db: Session,
        test_user,
        auth_headers,
    ):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)

        create_response = client.post(
            f'{settings.API_V1_STR}/notes/',
            headers=auth_headers,
            json={'folder_id': root_folder.id, 'title': 'Important'},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created['is_pinned'] is False

        pin_response = client.patch(
            f"{settings.API_V1_STR}/notes/{created['id']}/",
            headers=auth_headers,
            json={'is_pinned': True},
        )
        assert pin_response.status_code == 200
        assert pin_response.json()['is_pinned'] is True

        get_response = client.get(
            f"{settings.API_V1_STR}/notes/{created['id']}/",
            headers=auth_headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()['is_pinned'] is True

        unpin_response = client.patch(
            f"{settings.API_V1_STR}/notes/{created['id']}/",
            headers=auth_headers,
            json={'is_pinned': False},
        )
        assert unpin_response.status_code == 200
        assert unpin_response.json()['is_pinned'] is False
        assert unpin_response.json()['pin_index'] is None

    def test_reorder_pinned_notes(
        self,
        client: TestClient,
        test_db: Session,
        test_user,
        auth_headers,
    ):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)

        notes = [
            NoteService.create_note(
                test_db,
                user_id=test_user.id,
                create_data=NoteCreateSchema(title=f'Pinned {index}', folder_id=root_folder.id),
            )
            for index in range(2)
        ]
        for note in notes:
            NoteService.update_note(
                test_db,
                note_id=note.id,
                user_id=test_user.id,
                update_data=NoteUpdateSchema(is_pinned=True),
            )

        response = client.post(
            f'{settings.API_V1_STR}/notes/pinned/reorder/',
            headers=auth_headers,
            json={'note_ids': [notes[0].id, notes[1].id]},
        )

        assert response.status_code == 200
        assert [note['id'] for note in response.json()] == [notes[0].id, notes[1].id]
        assert [note['pin_index'] for note in response.json()] == [0, 1]

    def test_user_cannot_pin_another_users_note(
        self,
        client: TestClient,
        test_db: Session,
        test_user,
        auth_headers,
    ):
        other_user = User(
            username='notes-owner',
            email='notes-owner@example.com',
            hashed_password=generate_password_hash('other-password'),
            is_active=True,
        )
        test_db.add(other_user)
        test_db.commit()
        test_db.refresh(other_user)
        other_root = NotesFolderService.get_root_folder(test_db, user_id=other_user.id)
        other_note = NoteService.create_note(
            test_db,
            user_id=other_user.id,
            create_data=NoteCreateSchema(title='Private', folder_id=other_root.id),
        )

        response = client.patch(
            f'{settings.API_V1_STR}/notes/{other_note.id}/',
            headers=auth_headers,
            json={'is_pinned': True},
        )

        assert response.status_code == 404
        test_db.refresh(other_note)
        assert other_note.is_pinned is False
