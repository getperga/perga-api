import nh3
import re
from bs4 import BeautifulSoup
from sqlalchemy import case, func, literal, or_
from sqlalchemy.orm import Session

from app.const.notes import NOTE_BODY_ALLOWED_ATTRIBUTES, NOTE_BODY_ALLOWED_TAGS, NOTE_BODY_ALLOWED_PROTOCOLS
from app.core.index_utils import set_sequential_indexes
from app.models.notes import Note
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.services.base_service import BaseService
from app.services.notes_attachments_service import NotesAttachmentsService
from app.services.notes_folders_service import NotesFolderService


class NoteService(BaseService[Note]):
    model = Note

    SEARCH_CONFIG = 'english'
    MIN_FUZZY_QUERY_LENGTH = 3
    MAX_PREFIX_TERMS = 10

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
        return cls.get_base_query(db, user_id=user_id).filter(Note.id == note_id).first()

    @classmethod
    def search_notes(cls, db: Session, user_id: int, query: str, limit: int = 50) -> list[Note]:
        """ Searches notes using exact, prefix, and fuzzy-title matches. """
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        exact_query = func.websearch_to_tsquery(cls.SEARCH_CONFIG, normalized_query)
        prefix_terms = re.findall(r'[a-z0-9]+', normalized_query)[:cls.MAX_PREFIX_TERMS]
        prefix_query = func.to_tsquery(
            cls.SEARCH_CONFIG,
            ' & '.join(f'{term}:*' for term in prefix_terms),
        )

        title_vector = func.to_tsvector(cls.SEARCH_CONFIG, func.coalesce(Note.title, ''))
        body_vector = func.to_tsvector(cls.SEARCH_CONFIG, func.coalesce(Note.body_plain_text, ''))

        title_exact_match = title_vector.op('@@')(exact_query)
        body_exact_match = body_vector.op('@@')(exact_query)
        title_prefix_match = title_vector.op('@@')(prefix_query)
        body_prefix_match = body_vector.op('@@')(prefix_query)
        exact_search_match = Note.search_vector.op('@@')(exact_query)
        prefix_search_match = Note.search_vector.op('@@')(prefix_query)
        fuzzy_title_match = False
        if len(normalized_query) >= cls.MIN_FUZZY_QUERY_LENGTH:
            fuzzy_title_match = literal(normalized_query).op('<%')(func.lower(Note.title))

        matched_in_title = or_(title_exact_match, title_prefix_match, fuzzy_title_match)
        matched_in_body = or_(body_exact_match, body_prefix_match)
        literal_body_match = func.strpos(func.lower(Note.body_plain_text), normalized_query) > 0

        match_tier = case(
            (title_exact_match, 5),
            (title_prefix_match, 4),
            (body_exact_match, 3),
            (body_prefix_match, 2),
            (fuzzy_title_match, 1),
            else_=0,
        )
        match_kind = case(
            (or_(title_exact_match, body_exact_match), 'exact'),
            (or_(title_prefix_match, body_prefix_match), 'prefix'),
            else_='fuzzy',
        )
        find_query = case((literal_body_match, query.strip()), else_=None)
        search_rank = func.ts_rank_cd(Note.search_vector, exact_query)
        title_similarity = func.word_similarity(normalized_query, func.lower(Note.title))

        rows = cls.get_base_query(db, user_id=user_id).add_columns(
            matched_in_title.label('matched_in_title'),
            matched_in_body.label('matched_in_body'),
            match_kind.label('match_kind'),
            find_query.label('find_query'),
        ).filter(
            or_(exact_search_match, prefix_search_match, fuzzy_title_match)
        ).order_by(
            match_tier.desc(),
            search_rank.desc(),
            title_similarity.desc(),
            Note.updated_dt.desc(),
        ).limit(limit).all()

        notes = []
        for note, title_match, body_match, kind, literal_query in rows:
            note.matched_in_title = title_match
            note.matched_in_body = body_match
            note.match_kind = kind
            note.find_query = literal_query
            notes.append(note)

        folder_paths = NotesFolderService.get_folders_path_map(db, user_id)
        for note in notes:
            note.folders_path = folder_paths.get(note.folder_id, [])

        return notes

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
        db.flush()
        db_note.body = cls._clean_html(NotesAttachmentsService.synchronize_body(
            db, db_note, db_note.body or '', previous_body='',
        ))
        db.commit()

        db.refresh(db_note)
        return db_note

    @classmethod
    def update_note(cls, db: Session, note_id: int, user_id: int, update_data: NoteUpdateSchema) -> Note | None:
        db_note = cls.get_base_query(db, user_id=user_id).filter(
            Note.id == note_id,
        ).populate_existing().with_for_update().first()
        if not db_note:
            return None

        update_data_dict = update_data.model_dump(exclude_unset=True)
        if update_data_dict.get('is_pinned') is True and not db_note.is_pinned:
            pinned_notes = cls.get_base_query(db, user_id=user_id).filter(
                Note.is_pinned.is_(True),
            ).order_by(
                Note.pin_index.asc().nulls_last(),
                Note.updated_dt.desc(),
            ).all()
            set_sequential_indexes([db_note, *pinned_notes], index_field='pin_index')
        elif update_data_dict.get('is_pinned') is False:
            db_note.pin_index = None
        if 'body' in update_data_dict:
            update_data_dict['body'] = cls._clean_html(update_data_dict['body']) if update_data_dict['body'] else ''
            NotesAttachmentsService.get_note(db, note_id, user_id, editable=True)
            update_data_dict['body'] = cls._clean_html(NotesAttachmentsService.synchronize_body(
                db,
                db_note,
                update_data_dict['body'],
            ))
            update_data_dict['body_plain_text'] = cls.extract_plain_text(update_data_dict['body'])

        for field, value in update_data_dict.items():
            setattr(db_note, field, value)
        db.commit()

        db.refresh(db_note)
        return db_note

    @classmethod
    def reorder_pinned_notes(cls, db: Session, user_id: int, note_ids: list[int]) -> list[Note] | None:
        if len(note_ids) != len(set(note_ids)):
            return None

        notes = (
            cls.get_base_query(db, user_id=user_id)
            .filter(
                Note.id.in_(note_ids),
                Note.is_pinned.is_(True),
            )
            .all()
        )
        notes_by_id = {note.id: note for note in notes}
        if len(notes_by_id) != len(note_ids):
            return None

        ordered_notes = [notes_by_id[note_id] for note_id in note_ids]
        set_sequential_indexes(ordered_notes, index_field='pin_index')

        db.commit()
        return ordered_notes

    @classmethod
    def delete_note(cls, db: Session, note_id: int, user_id: int) -> bool:
        db_note = cls.get_note(db, note_id, user_id)
        if not db_note:
            return False
        db_note.mark_as_deleted()
        db.commit()
        return True
