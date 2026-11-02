from sqlalchemy import Boolean, Column, Computed, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import deferred, relationship

from app.const.notes import NotesFolderType
from app.models.base import BaseModel

__all__ = (
    'NotesFolder',
    'Note',
)


class NotesFolder(BaseModel):
    __tablename__ = 'notes_folders'

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey('notes_folders.id'), nullable=True, index=True)
    folder_type = Column(String(length=256), nullable=False, default=NotesFolderType.REGULAR)
    name = Column(String(length=256), nullable=False)

    # Relationships
    user = relationship('User', back_populates='notes_folders')
    notes = relationship('Note', back_populates='folder')
    parent = relationship('NotesFolder', remote_side='NotesFolder.id', back_populates='subfolders')
    subfolders = relationship('NotesFolder', back_populates='parent', cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            'idx_notes_folders_user_root',
            'user_id',
            unique=True,
            postgresql_where=(folder_type == NotesFolderType.ROOT),
        ),
        Index(
            'idx_notes_folders_user_trash',
            'user_id',
            unique=True,
            postgresql_where=(folder_type == NotesFolderType.TRASH),
        ),
    )

    def __repr__(self):
        return f"<NotesFolder(id={self.id}, name={self.name!r}, user_id={self.user_id})>"


class Note(BaseModel):
    __tablename__ = 'notes'

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey('notes_folders.id'), nullable=False, index=True)
    title = Column(String(length=256), nullable=False, default='')
    body = Column(Text, nullable=False, default='')
    body_plain_text = Column(Text, nullable=False, default='')
    is_pinned = Column(Boolean, nullable=False, default=False)

    # English full-text search with title matches weighted above body matches.
    search_vector = deferred(
        Column(
            TSVECTOR,
            Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(body_plain_text, '')), 'B')",
                persisted=True,
            ),
        )
    )

    # Relationships
    user = relationship('User', back_populates='notes')
    folder = relationship('NotesFolder', back_populates='notes')

    __table_args__ = (
        Index('idx_notes_search_vector', 'search_vector', postgresql_using='gin'),
        Index(
            'idx_notes_title_trgm',
            func.lower(title).label('title_lower'),
            postgresql_using='gin',
            postgresql_ops={'title_lower': 'gin_trgm_ops'},
        ),
    )

    def __repr__(self):
        return f"<Note(id={self.id}, title={self.title!r}, user_id={self.user_id})>"
