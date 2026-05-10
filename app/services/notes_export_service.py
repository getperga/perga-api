import io
import re
import unicodedata
import urllib.parse
import zipfile
from markdownify import markdownify
from weasyprint import HTML
from sqlalchemy.orm import Session

from app.const.notes import ExportType, EXPORT_TYPE_EXTENSION_MAP
from app.models.notes import Note, NotesFolder
from app.services.notes_service import NoteService
from app.services.notes_folders_service import NotesFolderService


class NotesExportService:
    WINDOWS_RESERVED_FILENAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    WHITELIST_FILENAME_CHARS_RE = re.compile(r'[^A-Za-z0-9._()\- \u0400-\u04FF]')

    @classmethod
    def _generate_pdf_content(cls, note: Note) -> bytes:
        """ Generate PDF content from note body HTML. """
        html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; padding: 40px; }}
                    h1 {{ font-size: 24px; margin-bottom: 16px; }}
                </style>
            </head>
            <body>
                <h1>{note.title}</h1>
                {note.body}
            </body>
            </html>
        """
        return HTML(string=html_content).write_pdf()

    @classmethod
    def _get_note_content(cls, note: Note, export_type: ExportType) -> str | bytes:
        """ Notes body stored as HTML. Converts it to a specified format if needed and adds a title. """
        note_content: str | bytes
        if export_type == ExportType.MARKDOWN:
            title = f"# {note.title}\n\n"
            note_content = title + markdownify(note.body)
        elif export_type == ExportType.PDF:
            note_content = cls._generate_pdf_content(note)
        else:
            title = f"<h1>{note.title}</h1>"
            note_content = title + note.body
        return note_content

    @classmethod
    def _generate_export_filename(cls, note: Note, export_type: ExportType) -> str:
        extension = EXPORT_TYPE_EXTENSION_MAP[export_type]

        # collapse compatibility chars and combine decomposed sequences
        title = unicodedata.normalize('NFKC', note.title)

        # remove Unicode control and non-printable characters
        title = ''.join(
            title_char for title_char in title
            if not unicodedata.category(title_char).startswith('C')
        )

        # remove non-whitelisted characters
        title = cls.WHITELIST_FILENAME_CHARS_RE.sub('', title)

        # remove leading and trailing spaces and periods
        title = title.strip()
        title = title.lstrip('.')
        title = title.rstrip(' .')

        # fallback
        if not title or title.upper() in cls.WINDOWS_RESERVED_FILENAMES:
            title = f'note_{note.id}'

        # truncate utf-8 string (non-ASCII chars take 2-4 bytes in utf-8)
        encoded = title.encode('utf-8')
        if len(encoded) > 200:
            title = encoded[:200].decode('utf-8', errors='ignore').strip()

        return f'{title}.{extension}'

    @classmethod
    def generate_export_headers(cls, filename: str) -> dict:
        encoded_filename = urllib.parse.quote(filename)
        return {
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }

    @classmethod
    def _create_zip_archive(cls, items: list[Note | tuple[Note, str]], export_type: ExportType) -> io.BytesIO:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
            used_filenames = set()
            for item in items:
                if isinstance(item, tuple):
                    note, rel_path = item
                else:
                    note = item
                    rel_path = ''

                content = cls._get_note_content(note, export_type)
                base_filename = cls._generate_export_filename(note, export_type)
                
                if rel_path:
                    base_filename = f"{rel_path.strip('/')}/{base_filename}"

                # Handle duplicate filenames in ZIP
                filename = base_filename
                counter = 1
                while filename in used_filenames:
                    name_parts = base_filename.rsplit('.', 1)
                    filename = f'{name_parts[0]}_{counter}.{name_parts[1]}'
                    counter += 1

                used_filenames.add(filename)
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)
        return zip_buffer

    @classmethod
    def _get_notes_with_paths(cls, folder: NotesFolder, current_path: str = '') -> list[tuple[Note, str]]:
        items = []
        for note in folder.notes:
            if not note.is_deleted:
                items.append((note, current_path))
        
        for subfolder in folder.subfolders:
            if not subfolder.is_deleted:
                new_path = f"{current_path}/{subfolder.name}".strip('/')
                items.extend(cls._get_notes_with_paths(subfolder, new_path))
        return items

    @classmethod
    def _get_all_notes_in_folder(cls, folder: NotesFolder) -> list[Note]:
        notes = [note for note in folder.notes if not note.is_deleted]
        for subfolder in folder.subfolders:
            if not subfolder.is_deleted:
                notes.extend(cls._get_all_notes_in_folder(subfolder))
        return notes

    @classmethod
    def export_single_note(
        cls, db: Session, user_id: int, note_id: int, export_type: ExportType
    ) -> tuple[str | bytes, str] | tuple[None, None]:
        note = NoteService.get_note(db, note_id=note_id, user_id=user_id)
        if not note:
            return None, None

        content = cls._get_note_content(note, export_type)
        filename = cls._generate_export_filename(note, export_type)
        return content, filename

    @classmethod
    def export_folder(
        cls, db: Session, user_id: int, folder_id: int, export_type: ExportType
    ) -> tuple[io.BytesIO, str] | tuple[None, None]:
        folder = NotesFolderService.get_folder(db, folder_id=folder_id, user_id=user_id)
        if not folder:
            return None, None
        
        items = cls._get_notes_with_paths(folder)
        return cls._create_zip_archive(items, export_type), f'notes_folder_{folder.name}.zip'

    @classmethod
    def export_all_notes(
        cls, db: Session, user_id: int, export_type: ExportType
    ) -> tuple[io.BytesIO, str] | tuple[None, None]:
        notes = NoteService.get_base_query(db).filter(Note.user_id == user_id).all()
        if not notes:
            return None, None

        return cls._create_zip_archive(notes, export_type), 'all_notes.zip'
