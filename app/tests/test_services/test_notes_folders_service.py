import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.const.notes import NotesFolderType
from app.models.user import User
from app.schemas.notes import NoteCreateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema, NotesFolderUpdateSchema
from app.services.notes_service import NoteService
from app.services.notes_folders_service import NotesFolderService


class TestNotesFolderService:
    def test_create_subfolder(self, test_db: Session, test_user):
        # 1. Create a parent folder
        parent_create = NotesFolderCreateSchema(name='Parent Folder')
        parent = NotesFolderService.create_folder(test_db, user_id=test_user.id, create_data=parent_create)
        assert parent.id is not None
        assert parent.name == parent_create.name
        
        # 2. Create a subfolder
        subfolder_create = NotesFolderCreateSchema(name='Subfolder', parent_id=parent.id)
        subfolder = NotesFolderService.create_folder(test_db, user_id=test_user.id, create_data=subfolder_create)
        
        assert subfolder.id is not None
        assert subfolder.parent_id == parent.id
        
        # 3. Verify relationship
        test_db.refresh(parent)
        assert len(parent.subfolders) == 1
        assert parent.subfolders[0].id == subfolder.id
        assert subfolder.parent.id == parent.id

    def test_get_folders_includes_trash_and_root(self, test_db: Session, test_user):
        root_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        regular_folder =NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Regular', parent_id=root_folder.id)
        )

        data = NotesFolderService.get_folders(test_db, user_id=test_user.id)
        
        assert 'root_folder' in data
        assert 'trash_folder' in data
        
        assert data['root_folder'].folder_type == NotesFolderType.ROOT
        assert data['trash_folder'].folder_type == NotesFolderType.TRASH
        
        test_db.refresh(data['root_folder'])
        assert len(data['root_folder'].subfolders) == 1
        assert data['root_folder'].subfolders[0].name == regular_folder.name

    def test_empty_trash(self, test_db: Session, test_user):
        trash_folder = NotesFolderService.get_trash_folder(test_db, user_id=test_user.id)
        folder = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='To Trash')
        )
        note = NoteService.create_note(
            test_db,
            user_id=test_user.id,
            create_data=NoteCreateSchema(title='Note', body='Body', folder_id=folder.id)
        )
        
        NotesFolderService.update_folder(
            test_db, folder.id, test_user.id, NotesFolderUpdateSchema(parent_id=trash_folder.id),
        )
        NotesFolderService.empty_trash(test_db, user_id=test_user.id)
        
        test_db.refresh(folder)
        test_db.refresh(note)
        assert folder.is_deleted
        assert note.is_deleted

    def test_is_subfolder_of(self, test_db: Session, test_user):
        # Create folder A
        folder_a = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder A')
        )
        
        # Create folder B as subfolder of A
        folder_b = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder B', parent_id=folder_a.id)
        )
        
        # Create folder C as subfolder of B
        folder_c = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder C', parent_id=folder_b.id)
        )
        
        assert NotesFolderService.is_subfolder_of(test_db, folder_a.id, folder_b.id, test_user.id) is True
        assert NotesFolderService.is_subfolder_of(test_db, folder_a.id, folder_c.id, test_user.id) is True
        assert NotesFolderService.is_subfolder_of(test_db, folder_b.id, folder_c.id, test_user.id) is True
        
        assert NotesFolderService.is_subfolder_of(test_db, folder_b.id, folder_a.id, test_user.id) is False
        assert NotesFolderService.is_subfolder_of(test_db, folder_c.id, folder_a.id, test_user.id) is False

    def test_prevent_move_to_subfolder(self, test_db: Session, test_user):
        folder_a = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder A')
        )
        folder_b = NotesFolderService.create_folder(
            test_db,
            user_id=test_user.id,
            create_data=NotesFolderCreateSchema(name='Folder B', parent_id=folder_a.id)
        )
        
        result = NotesFolderService.update_folder(
            test_db,
            folder_id=folder_a.id,
            user_id=test_user.id,
            update_data=NotesFolderUpdateSchema(parent_id=folder_b.id)
        )
        assert result is None

    def test_owner_constraint_preserves_existing_tree(self, test_db, test_user):
        owner_folder = NotesFolderService.get_root_folder(test_db, user_id=test_user.id)
        other = User(username='other-owner', email='other-owner@example.test', is_active=True)
        test_db.add(other)
        test_db.commit()

        regular = NotesFolderService.create_folder(
            test_db, other.id, NotesFolderCreateSchema(name='Other account'),
        )
        original_parent = regular.parent_id
        with pytest.raises(IntegrityError):
            with test_db.begin_nested():
                regular.parent_id = owner_folder.id
                test_db.flush()

        test_db.refresh(regular)
        assert regular.parent_id == original_parent
