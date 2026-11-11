import datetime as dt

from pydantic import BaseModel


class NotesAttachmentSchema(BaseModel):
    id: int
    note_id: int
    original_filename: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    created_dt: dt.datetime
    url: str
