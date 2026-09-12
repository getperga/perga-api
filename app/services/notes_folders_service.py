from collections import defaultdict
from sqlalchemy.orm import Session, load_only
from sqlalchemy.orm.attributes import set_committed_value

from app.const.notes import NotesFolderType
from app.models.notes import Note, NotesFolder
from app.schemas.notes_folders import NotesFolderCreateSchema, NotesFolderUpdateSchema
from app.services.base_service import BaseService


class NotesFolderService(BaseService[NotesFolder]):
    model = NotesFolder

    @classmethod
    def get_folder(cls, db: Session, folder_id: int, user_id: int) -> NotesFolder | None:
        return cls.get_base_query(db, user_id=user_id).filter(NotesFolder.id == folder_id).first()

    @classmethod
    def create_folder(cls, db: Session, user_id: int, create_data: NotesFolderCreateSchema) -> NotesFolder:
        data = create_data.model_dump()
        if data.get('parent_id') is None:
            root_folder = cls.get_root_folder(db, user_id)
            data['parent_id'] = root_folder.id
            
        db_folder = NotesFolder(
            user_id=user_id,
            folder_type=NotesFolderType.REGULAR,
            **data
        )
        db.add(db_folder)
        db.commit()
        db.refresh(db_folder)
        return db_folder

    @classmethod
    def update_folder(
        cls, db: Session, folder_id: int, user_id: int, update_data: NotesFolderUpdateSchema
    ) -> NotesFolder | None:
        db_folder = cls.get_folder(db, folder_id, user_id)
        if not db_folder:
            return None
        update_data = update_data.model_dump(exclude_unset=True)
        
        if 'parent_id' in update_data and update_data['parent_id'] is not None:
            new_parent_id = update_data['parent_id']
            if (
                new_parent_id == folder_id or
                    cls.is_subfolder_of(db, folder_id, new_parent_id, user_id)
            ):
                return None

        for field, value in update_data.items():
            setattr(db_folder, field, value)
        db.commit()
        db.refresh(db_folder)
        return db_folder

    @classmethod
    def delete_folder(cls, db: Session, folder_id: int, user_id: int) -> bool:
        db_folder = cls.get_folder(db, folder_id, user_id)
        if not db_folder:
            return False
        db_folder.mark_as_deleted()
        db.commit()
        return True

    @classmethod
    def get_root_folder(cls, db: Session, user_id: int) -> NotesFolder:
        instance, _ = cls.get_or_create(
            db,
            user_id=user_id,
            folder_type=NotesFolderType.ROOT,
            defaults={'name': 'Root'}
        )
        return instance

    @classmethod
    def get_trash_folder(cls, db: Session, user_id: int) -> NotesFolder:
        instance, _ = cls.get_or_create(
            db,
            user_id=user_id,
            folder_type=NotesFolderType.TRASH,
            defaults={'name': 'Trash'}
        )
        return instance

    @classmethod
    def get_folders(cls, db: Session, user_id: int) -> dict:
        root_folder = cls.get_root_folder(db, user_id)
        trash_folder = cls.get_trash_folder(db, user_id)

        user_folders = cls.get_base_query(db, user_id=user_id).all()
        folders_map = {folder.id: folder for folder in user_folders}

        subfolders_map = defaultdict(list)
        for folder in user_folders:
            subfolders_map[folder.parent_id].append(folder)

        # fetch only fields required for folders tree
        user_notes = db.query(Note).options(load_only(
            Note.id,
            Note.folder_id,
            Note.is_deleted,
            Note.title,
            Note.updated_dt,
        )).filter(
            Note.user_id == user_id,
            Note.is_deleted.is_(False),
        ).order_by(Note.updated_dt.desc()).all()

        folder_notes_map = defaultdict(list)
        for note in user_notes:
            folder_notes_map[note.folder_id].append(note)

        # add notes and subfolders as fields to folders
        for folder in user_folders:
            set_committed_value(folder, 'notes', folder_notes_map[folder.id])
            set_committed_value(folder, 'subfolders', subfolders_map[folder.id])

        return {
            'root_folder': folders_map[root_folder.id],
            'trash_folder': folders_map[trash_folder.id],
        }

    @classmethod
    def empty_trash(cls, db: Session, user_id: int) -> None:
        trash_folder = cls.get_trash_folder(db, user_id)
        
        def mark_children_as_deleted(folder: NotesFolder):
            """ Recursively mark subfolders and notes as deleted """
            # Mark all notes in this folder as deleted
            for note in folder.notes:
                if not note.is_deleted:
                    note.mark_as_deleted()
            
            # Recursively mark subfolders and their contents as deleted
            for subfolder in folder.subfolders:
                if not subfolder.is_deleted:
                    subfolder.mark_as_deleted()
                mark_children_as_deleted(subfolder)

        mark_children_as_deleted(trash_folder)
        db.commit()

    @classmethod
    def get_folders_path_map(cls, db: Session, user_id: int) -> dict[int, list[str]]:
        """ Builds a map folder_id -> breadcrumb path names, e.g. {5: ['Folder1', 'Subfolder'], 6: ['Trash']} """
        user_folders = cls.get_base_query(db, user_id=user_id).all()
        folders_id_map: dict[int, NotesFolder]  = {folder.id: folder for folder in user_folders}
        folders_path_map: dict[int, list[str]] = {}

        def _get_path_names(folder: NotesFolder) -> list[str]:
            """ Returns a list of folder names from the root to the given folder """
            if folder.folder_type == NotesFolderType.ROOT:
                return []
            if folder.folder_type == NotesFolderType.TRASH:
                return ['Trash']

            parent: NotesFolder | None = folders_id_map.get(folder.parent_id)
            names = _get_path_names(parent) if parent else []
            names.append(folder.name)
            return names

        for folder in folders_id_map.values():
            folders_path_map[folder.id] = _get_path_names(folder)

        return folders_path_map

    @classmethod
    def is_subfolder_of(cls, db: Session, folder1_id: int, folder2_id: int, user_id: int) -> bool:
        """ Check if folder2_id is a subfolder of folder1_id """
        folder2 = cls.get_folder(db, folder2_id, user_id)
        while folder2 and folder2.parent_id:
            if folder2.parent_id == folder1_id:
                return True
            folder2 = folder2.parent
        return False
