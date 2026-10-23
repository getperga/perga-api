import datetime as dt
from pydantic import BaseModel


class NoteCreateSchema(BaseModel):
    folder_id: int
    title: str = ''
    body: str = ''


class NoteUpdateSchema(BaseModel):
    folder_id: int = None
    title: str = None
    body: str = None
    is_pinned: bool = False


# NoteSchema without body to reduce get_folders response size
class NoteMetaSchema(BaseModel):
    id: int
    folder_id: int
    title: str
    updated_dt: dt.datetime
    is_pinned: bool

    class Config:
        from_attributes = True


class NoteSchema(NoteMetaSchema):
    body: str

    class Config:
        from_attributes = True


class NoteSearchResultSchema(NoteMetaSchema):
    folders_path: list[str] = []

    class Config:
        from_attributes = True
