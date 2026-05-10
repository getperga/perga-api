from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.notes_folders import (
    NotesFolderSchema,
    NotesFolderCreateSchema,
    NotesFolderUpdateSchema,
    GetFoldersResponseSchema,
)
from app.schemas.user import UserSchema
from app.services.auth_service import AuthService
from app.services.notes_folders_service import NotesFolderService

router = APIRouter()


@router.get("/", response_model=GetFoldersResponseSchema)
def get_folders(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    return NotesFolderService.get_folders(db, user_id=current_user.id)


@router.post("/", response_model=NotesFolderSchema)
def create_notes_folder(
    request_data: NotesFolderCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    return NotesFolderService.create_folder(db, user_id=current_user.id, create_data=request_data)


@router.patch("/{folder_id}/", response_model=NotesFolderSchema)
def update_notes_folder(
    folder_id: int,
    request_data: NotesFolderUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    folder =  NotesFolderService.get_folder(db, user_id=current_user.id, folder_id=folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    success = NotesFolderService.update_folder(
        db, folder_id=folder_id, user_id=current_user.id, update_data=request_data
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot move folder to its subfolder or itself")

    return folder


@router.post("/empty-trash/")
def empty_trash(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    NotesFolderService.empty_trash(db, user_id=current_user.id)
    return {"message": "Trash emptied"}
