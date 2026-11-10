import datetime as dt
import io
import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from PIL import Image
from sqlalchemy.orm import Session
from threading import Barrier
from uuid import uuid4

from app.core.config import settings
from app.core.file_storage import LocalFileStorage
from app.models.notes import Note, NotesAttachment, NotesFolder
from app.models.user import User
from app.schemas.notes import NoteCreateSchema
from app.services.notes_attachments_service import NotesAttachmentsService
from app.services.notes_folders_service import NotesFolderService
from app.services.notes_service import NoteService


@pytest.fixture
def committed_notes(test_engine):
    with Session(test_engine) as db:
        identifier = uuid4().hex
        user = User(username=identifier, email=f'{identifier}@example.test', hashed_password='unused', is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id
        folder = NotesFolderService.get_root_folder(db, user_id)
        notes = [NoteService.create_note(db, user_id, NoteCreateSchema(folder_id=folder.id)) for _ in range(2)]
        note_ids = [note.id for note in notes]

    try:
        yield user_id, note_ids
    finally:
        with Session(test_engine) as db:
            db.query(NotesAttachment).filter(NotesAttachment.note_id.in_(note_ids)).delete(synchronize_session=False)
            db.query(Note).filter(Note.user_id == user_id).delete(synchronize_session=False)
            db.query(NotesFolder).filter(NotesFolder.user_id == user_id).delete(synchronize_session=False)
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()


def test_concurrent_uploads_respect_user_quota(test_engine, committed_notes, tmp_path, monkeypatch):
    user_id, note_ids = committed_notes
    monkeypatch.setattr(settings, 'ATTACHMENTS_MAX_USER_STORAGE_MB', 1)
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    data = buffer.getvalue() + b'\0' * (600 * 1024)
    storage = LocalFileStorage(str(tmp_path))
    start = Barrier(2)

    def perform_upload(note_id):
        with Session(test_engine) as db:
            start.wait(timeout=10)

            try:
                NotesAttachmentsService.upload(db, storage, note_id, user_id, io.BytesIO(data), 'image.png')
                return 201
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(perform_upload, note_ids)) == [201, 413]
    with Session(test_engine) as db:
        assert db.query(NotesAttachment).filter(NotesAttachment.note_id.in_(note_ids)).count() == 1


def test_cleanup_skips_locked_note_and_rechecks_saved_body(test_engine, committed_notes, tmp_path):
    user_id, note_ids = committed_notes
    storage = LocalFileStorage(str(tmp_path))
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')

    with Session(test_engine) as db:
        attachment = NotesAttachmentsService.upload(db, storage, note_ids[0], user_id,
                                                    io.BytesIO(buffer.getvalue()), 'image.png')
        attachment.deleted_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
        attachment_id = attachment.id
        db.commit()

    with Session(test_engine) as saving, Session(test_engine) as cleaning:
        note = saving.query(Note).filter(Note.id == note_ids[0]).with_for_update().one()
        assert NotesAttachmentsService.cleanup(cleaning, storage) == 0
        body = f'<img data-attachment-id="{attachment_id}">'
        # make the old unused timer deliberately stale; cleanup must re-read HTML under lock
        note.body = NoteService._clean_html(body)
        saving.commit()
        assert NotesAttachmentsService.cleanup(cleaning, storage) == 0
        attachment = cleaning.get(NotesAttachment, attachment_id)
        assert attachment.is_deleted is False
        assert attachment.deleted_dt is None
        assert attachment.status == 'ready'
