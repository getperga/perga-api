from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.core.file_storage import FileStorage, StorageError, get_file_storage
from app.schemas.notes_attachments import NotesAttachmentSchema
from app.schemas.user import UserSchema
from app.services.auth_service import AuthService
from app.services.notes_attachments_service import IMAGE_PREVIEW_CONTENT_TYPE, NotesAttachmentsService

router = APIRouter()

CONTENT_HEADERS = {
    'Content-Disposition': 'inline',
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
}


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
    preview: bool = False,
):
    attachment = NotesAttachmentsService.get_attachment(db, note_id, attachment_id, current_user.id)
    headers = {**CONTENT_HEADERS, 'Content-Length': str(attachment.size_bytes)}
    content_type = attachment.content_type

    stream = None
    if preview and attachment.preview_storage_key is not None:
        try:
            stream = storage.open(attachment.preview_storage_key)
        except StorageError:
            # a restored backup may contain the original without the preview
            pass
        else:
            content_type = IMAGE_PREVIEW_CONTENT_TYPE
            if attachment.preview_size_bytes is None:
                headers.pop('Content-Length')
            else:
                headers['Content-Length'] = str(attachment.preview_size_bytes)

    if stream is None:
        stream = storage.open(attachment.storage_key)

    def chunks():
        try:
            while chunk := stream.read(64 * 1024):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        chunks(),
        media_type=content_type,
        headers=headers,
        background=BackgroundTask(stream.close),
    )
