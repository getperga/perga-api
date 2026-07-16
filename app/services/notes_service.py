import nh3
from bs4 import BeautifulSoup
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.const.notes import NOTE_BODY_ALLOWED_ATTRIBUTES, NOTE_BODY_ALLOWED_TAGS, NOTE_BODY_ALLOWED_PROTOCOLS
from app.models.notes import Note
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.base_service import BaseService
from app.services.notes_folders_service import NotesFolderService


class NoteService(BaseService[Note]):
    model = Note

    @staticmethod
    def _filter_html_attrs(tag: str, attr: str, value: str) -> str | None:
        """ Adds extra validation of HTML tags attrubutes to nh3 sanitization """
        # allow only specific tiptap task list attributes
        if tag in ('ul', 'li'):
            if attr == 'data-type' and value not in ('taskList', 'taskItem'):
                return None
        return value

    @classmethod
    def _clean_html(cls, html: str) -> str:
        return nh3.clean(
            html,
            tags=NOTE_BODY_ALLOWED_TAGS,
            attributes=NOTE_BODY_ALLOWED_ATTRIBUTES,
            url_schemes=NOTE_BODY_ALLOWED_PROTOCOLS,
            attribute_filter=cls._filter_html_attrs,
            link_rel='noopener noreferrer'
        )

    @staticmethod
    def extract_plain_text(html: str) -> str:
        """ Extracts plain text from a note's HTML body for use in search """
        if not html:
            return ''
        return BeautifulSoup(html, 'html.parser').get_text(separator=' ', strip=True)

    @classmethod
    def get_note(cls, db: Session, note_id: int, user_id: int) -> Note | None:
        return cls.get_base_query(db).filter(Note.user_id == user_id, Note.id == note_id).first()

    @classmethod
    def search_notes(cls, db: Session, user_id: int, query: str, limit: int = 50) -> list[Note]:
        """ Search notes with a postgres full-text vector query """
        ts_query = func.websearch_to_tsquery('simple', query)
        filtered_query = cls.get_base_query(db).filter(
            Note.user_id == user_id,
            Note.search_vector.op('@@')(ts_query)
        )
        return filtered_query.order_by(
            func.ts_rank(Note.search_vector, ts_query).desc()
        ).limit(limit).all()

    @classmethod
    def create_note(cls, db: Session, user_id: int, create_data: NoteCreateSchema) -> Note:
        data = create_data.model_dump()
        if data.get('body'):
            data['body'] = cls._clean_html(data['body'])
        data['body_plain_text'] = cls.extract_plain_text(data.get('body', ''))
        if data.get('folder_id') is None:
            root_folder = NotesFolderService.get_root_folder(db, user_id)
            data['folder_id'] = root_folder.id
            
        db_note = Note(user_id=user_id, **data)
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        return db_note

    @classmethod
    def update_note(cls, db: Session, note_id: int, user_id: int, update_data: NoteUpdateSchema) -> Note | None:
        db_note = cls.get_note(db, note_id, user_id)
        if not db_note:
            return None
        update_data_dict = update_data.model_dump(exclude_unset=True)
        if 'body' in update_data_dict:
            update_data_dict['body'] = cls._clean_html(update_data_dict['body']) if update_data_dict['body'] else ''
            update_data_dict['body_plain_text'] = cls.extract_plain_text(update_data_dict['body'])

        for field, value in update_data_dict.items():
            setattr(db_note, field, value)
        db.commit()

        db.refresh(db_note)
        return db_note

    @classmethod
    def delete_note(cls, db: Session, note_id: int, user_id: int) -> bool:
        db_note = cls.get_note(db, note_id, user_id)
        if not db_note:
            return False
        db_note.mark_as_deleted()
        db.commit()
        return True
