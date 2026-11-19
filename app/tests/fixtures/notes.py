import pytest
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import User, Note, NotesFolder
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


@pytest.fixture
def note(test_db, test_user):
    root = NotesFolderService.get_root_folder(test_db, test_user.id)
    note = NoteService.create_note(
        test_db, test_user.id, NoteCreateSchema(folder_id=root.id, title='Collected material', body='<p>Original</p>'),
    )
    return NoteService.update_note(test_db, note.id, test_user.id, NoteUpdateSchema(is_pinned=True))


@pytest.fixture
def committed_note(test_engine):
    """ Creates a committed note visible to independent sessions in concurrency tests. """
    with Session(test_engine) as db:
        identifier = uuid4().hex
        user = User(username=identifier, email=f'{identifier}@example.test', hashed_password='unused', is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id
        root = NotesFolderService.get_root_folder(db, user_id)
        note = NoteService.create_note(db, user_id, NoteCreateSchema(folder_id=root.id, body='<p>Original</p>'))
        note_id = note.id

    try:
        yield user_id, note_id
    finally:
        with Session(test_engine) as db:
            db.query(Note).filter(Note.user_id == user_id).delete(synchronize_session=False)
            db.query(NotesFolder).filter(NotesFolder.user_id == user_id).delete(synchronize_session=False)
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()
