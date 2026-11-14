import datetime as dt
from typing import Literal

from pydantic import BaseModel


class NotesAttachmentSchema(BaseModel):
    id: int
    note_id: int
    attachment_type: Literal['image', 'file']
    content_type: str
    original_filename: str
    size_bytes: int
    width: int | None
    height: int | None
    created_dt: dt.datetime
    url: str
