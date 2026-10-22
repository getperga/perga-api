from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


class TestNotesFolderAPI:
    def test_get_folders_without_note_body(self, client: TestClient, test_db: Session, test_user, auth_headers):
        # 1. Create a folder and a note with a body
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(
                title='Note',
                body='This is a secret body that should not be in the folders list',
                folder_id=root_folder.id
            )
        )
        NoteService.update_note(
            test_db,
            note_id=note.id,
            user_id=test_user.id,
            update_data=NoteUpdateSchema(is_pinned=True),
        )
        
        # 2. Call the get_folders API
        response = client.get(f'{settings.API_V1_STR}/notes/folders/', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # 3. Verify the note is present but body is missing
        root_folder_data = data['root_folder']
        notes = root_folder_data['notes']
        
        assert len(notes) > 0
        note_data = notes[0]
        assert note_data['title'] == note.title
        assert note_data['is_pinned'] is True
        assert 'body' not in note_data

    def test_get_folders_sorting_and_subfolders(self, client: TestClient, test_db: Session, test_user, auth_headers):
        # 1. Create a subfolder and two notes with different update times
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        subfolder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Subfolder', parent_id=root_folder.id)
        )
        
        old_note =NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Old Note', folder_id=root_folder.id)
        )
        new_note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='New Note', folder_id=root_folder.id)
        )
        
        # 2. Call the get_folders API
        response = client.get(f'{settings.API_V1_STR}/notes/folders/', headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # 3. Verify subfolder is present
        root_folder_data = data['root_folder']
        subfolders = root_folder_data['subfolders']
        assert len(subfolders) == 1
        assert subfolders[0]['id'] == subfolder.id
        
        # 4. Verify notes are sorted (New Note first)
        notes = root_folder_data['notes']
        assert len(notes) == 2
        assert notes[0]['id'] == new_note.id
        assert notes[1]['id'] == old_note.id
