from fastapi import Depends, HTTPException, APIRouter, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.const.notes import ExportTarget, EXPORT_MEDIA_TYPE_MAP, ExportType
from app.core.database import get_db
from app.schemas.user import UserSchema
from app.services.auth_service import AuthService
from app.services.notes_export_service import NotesExportService

router = APIRouter()


@router.get('/')
def notes_export(
    export_type: ExportType = Query(..., description='Export type: HTML, Markdown, PDF'),
    export_target: ExportTarget = Query(..., description='Export target: Single note, Folder notes, All notes'),
    export_target_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    media_type = EXPORT_MEDIA_TYPE_MAP.get(export_type)

    if export_target == ExportTarget.SINGLE_NOTE and export_target_id:
        content, filename = NotesExportService.export_single_note(
            db,
            user_id=current_user.id,
            note_id=export_target_id,
            export_type=export_type
        )
        if not content:
            raise HTTPException(status_code=404, detail='Note not found')

        headers = NotesExportService.generate_export_headers(filename)
        return Response(
            content=content,
            media_type=media_type,
            headers=headers
        )
    elif export_target == ExportTarget.FOLDER_NOTES and export_target_id:
        zip_buffer, filename = NotesExportService.export_folder(
            db,
            user_id=current_user.id,
            folder_id=export_target_id,
            export_type=export_type
        )
        if not zip_buffer:
            raise HTTPException(status_code=404, detail='Folder not found')
    elif export_target == ExportTarget.ALL_NOTES:
        zip_buffer, filename = NotesExportService.export_all_notes(
            db, user_id=current_user.id, export_type=export_type
        )
    else:
        raise HTTPException(status_code=400, detail='Invalid request')

    headers = NotesExportService.generate_export_headers(filename)
    return StreamingResponse(
        zip_buffer,
        media_type='application/x-zip-compressed',
        headers=headers
    )
