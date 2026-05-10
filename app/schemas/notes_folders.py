from pydantic import BaseModel, field_validator

from app.schemas.notes import NoteMetaSchema


class NotesFolderCreateSchema(BaseModel):
    parent_id: int | None = None
    name: str


class NotesFolderUpdateSchema(BaseModel):
    parent_id: int | None = None
    name: str = None


class NotesFolderSchema(BaseModel):
    parent_id: int | None = None
    id: int
    folder_type: str
    name: str

    class Config:
        from_attributes = True


class NotesFolderResponseSchema(NotesFolderSchema):
    notes: list[NoteMetaSchema] = []
    subfolders: list['NotesFolderResponseSchema'] = []

    @field_validator('subfolders', mode='before')
    @classmethod
    def filter_subfolders(cls, subfolders):
        if isinstance(subfolders, list):
            return [
                folder for folder in subfolders if not folder.is_deleted
            ]
        return subfolders

    @field_validator('notes', mode='before')
    @classmethod
    def filter_notes(cls, notes):
        if isinstance(notes, list):
            return [
                note for note in notes if not note.is_deleted
            ]
        return notes

    @field_validator('notes', mode='after')
    @classmethod
    def sort_notes(cls, v: list[NoteMetaSchema]) -> list[NoteMetaSchema]:
        # Sort notes by updated_dt desc.
        return sorted(v, key=lambda x: x.updated_dt, reverse=True)

    class Config:
        from_attributes = True


class GetFoldersResponseSchema(BaseModel):
    root_folder: NotesFolderResponseSchema
    trash_folder: NotesFolderResponseSchema
