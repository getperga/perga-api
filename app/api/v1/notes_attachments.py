from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.core.file_storage import FileStorage, get_file_storage
from app.schemas.notes_attachments import NotesAttachmentSchema
from app.schemas.user import UserSchema
from app.services.auth_service import AuthService
from app.services.notes_attachments_service import NotesAttachmentsService

router = APIRouter()


@router.post('/{note_id}/attachments/', response_model=NotesAttachmentSchema, status_code=201)
def upload_attachment(
    note_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user),
    storage: FileStorage = Depends(get_file_storage),
):
    filename = file.filename or ''
    attachment = NotesAttachmentsService.upload(db, storage, note_id, current_user.id, file.file, filename)
    return NotesAttachmentsService.metadata(attachment)


@router.get('/{note_id}/attachments/', response_model=list[NotesAttachmentSchema])
def list_attachments(
    note_id: int, db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user),
):
    attachments = NotesAttachmentsService.list_attachments(db, note_id, current_user.id)
    return [NotesAttachmentsService.metadata(item) for item in attachments]


@router.get('/{note_id}/attachments/{attachment_id}/content/')
def get_attachment_content(
    note_id: int, attachment_id: int, db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user),
    storage: FileStorage = Depends(get_file_storage),
):
    attachment = NotesAttachmentsService.get_attachment(db, note_id, attachment_id, current_user.id)
    stream = storage.open(attachment.storage_key)

    def chunks():
        try:
            while chunk := stream.read(64 * 1024):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        chunks(),
        media_type=attachment.content_type,
        headers={
            'Content-Length': str(attachment.size_bytes),
            'Content-Disposition': 'inline',
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        },
        background=BackgroundTask(stream.close),
    )
