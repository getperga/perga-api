import html
import io
import markdown
import os
import posixpath
import re
import zipfile
from bs4 import BeautifulSoup
from fastapi import HTTPException
from sqlalchemy.orm import Session
from urllib.parse import unquote, urlsplit

from app.const.notes import IMPORT_SIZE_LIMIT
from app.core.config import settings
from app.core.file_storage import get_file_storage
from app.models.notes import Note
from app.schemas.notes import NoteCreateSchema, NoteUpdateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_service import NoteService
from app.services.notes_attachments_service import FILE_EXTENSIONS, NotesAttachmentsService, attachment_url
from app.services.notes_folders_service import NotesFolderService


class NotesImportService:
    IGNORE_FOLDER_NAMES = ('__macosx', '.ds_store', 'thumbs.db', 'desktop.ini')
    SUPPORTED_NOTE_EXTENSIONS = ('.md', '.html', '.htm', '.txt')
    ARCHIVE_ASSETS_FOLDER_NAME = 'assets'
    MAX_ARCHIVE_ENTRIES = 1000
    MAX_ARCHIVE_EXPANDED_SIZE = IMPORT_SIZE_LIMIT * 10
    ZIP_ENCRYPTED_FLAG = 1

    @classmethod
    def _parse_html(cls, content: str, default_title: str) -> tuple[str, str]:
        soup = BeautifulSoup(content, 'html.parser')
        
        # try to find a title
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif first_h1 := soup.find('h1'):
            title = first_h1.get_text().strip()
            first_h1.decompose() # remove the first title tag from the body to avoid duplication
        else:
            title = default_title or 'Untitled Note'

        # get body content as a string with HTML
        if soup.body:
            contents = soup.body.contents
        else:
            contents = soup.contents
        body = ''.join(str(tag) for tag in contents)

        return title, body

    @classmethod
    def _post_process_task_lists(cls, body_html: str):
        """ Post-process task lists from Markdown for TipTap compatibility """
        if 'task-list' not in body_html:
            return body_html

        soup = BeautifulSoup(body_html, 'html.parser')
        for ul in soup.find_all('ul', class_='task-list'):
            ul['data-type'] = 'taskList'
            # remove class to keep it clean
            del ul['class']

            for li in ul.find_all('li', class_='task-list-item'):
                li['data-type'] = 'taskItem'
                # find checkbox
                checkbox = li.find('input', type='checkbox')
                if checkbox:
                    li['data-checked'] = 'true' if checkbox.has_attr('checked') else 'false'
                    checkbox.decompose()

                # remove class
                del li['class']
        body_html = str(soup)

        return body_html

    @classmethod
    def _parse_markdown(cls, content: str, default_title: str) -> tuple[str, str]:
        lines = content.splitlines()
        title = None
        body_start_index = 0
        
        for index, line in enumerate(lines):
            if line.startswith('# '):
                title = line[2:].strip()
                body_start_index = index + 1
                break

        if not title:
            title = default_title or 'Untitled Note'
        
        body_md = '\n'.join(lines[body_start_index:]).strip()
        body_html = markdown.markdown(
            body_md,
            extensions=[
                'nl2br',  # converts newlines to <br> tags
                'sane_lists',  # handles ul and ol lists
                'tables',
                'fenced_code',  # handles ```code_blocks```
                'pymdownx.tasklist',  # handles [x] task list
                'pymdownx.tilde',  # handles ~~strikethrough~~
            ],
            extension_configs={
                'pymdownx.tilde': {
                    'subscript': False,
                }
            }
        )

        body_html = cls._post_process_task_lists(body_html)

        # to avoid losing line breaks, replace \n with empty paragraph tags but not in between of lists
        body_html = re.sub(r'\n(?=<(?!li|/ul|/ol))', '<p></p>', body_html)

        return title, body_html

    @classmethod
    def _parse_txt(cls, content: str, default_title: str) -> tuple[str, str]:
        title = default_title
        body_html = f'<p>{html.escape(content)}</p>'
        return title, body_html

    @classmethod
    def import_file(
        cls, db: Session, user_id: int, filename: str, content: bytes, folder_id: int,
        *, archive: zipfile.ZipFile | None = None, archive_path: str = '',
    ) -> Note | None:
        """ Import a single file as a note. """
        default_title = os.path.splitext(filename)[0]
        extension = os.path.splitext(filename)[1].lower()

        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            # skip non utf-8 files
            return None

        # parse file content and get the body as HTML
        if extension == '.md':
            title, body = cls._parse_markdown(text_content, default_title)
        elif extension in ('.html', '.htm'):
            title, body = cls._parse_html(text_content, default_title)
        elif extension == '.txt':
            title, body = cls._parse_txt(text_content, default_title)
        else:
            return None

        soup = BeautifulSoup(body, 'html.parser')
        references = [
            (element, 'src' if element.name == 'img' else 'href')
            for element in soup.select('img, a[href^="assets/files/"]')
        ]
        if not references:
            return NoteService.create_note(db, user_id, NoteCreateSchema(folder_id=folder_id, title=title, body=body))

        if archive is None:
            raise HTTPException(422, 'Attachments must be imported in a ZIP archive with their assets')

        prepared = {}
        for element, attr in references:
            path = cls._resolve_archive_asset_path(str(element.get(attr, '')), archive_path)
            if path not in prepared:
                prepared[path] = cls._read_archive_asset(archive, path)
            extension = posixpath.splitext(path)[1].lower().lstrip('.')
            if attr == 'src':
                NotesAttachmentsService.validate_image(io.BytesIO(prepared[path]))
                if extension in FILE_EXTENSIONS:
                    raise HTTPException(422, 'Image asset has a file attachment extension')
            elif extension not in FILE_EXTENSIONS:
                raise HTTPException(422, 'Unsupported file attachment extension')
            element[attr] = path
            element.attrs.pop('data-attachment-id', None)

        return cls._create_note_with_assets(db, user_id, folder_id, title, soup, references, prepared)

    @classmethod
    def _resolve_archive_asset_path(cls, source_url: str, archive_path: str) -> str:
        """ Resolves a relative attachment path within the ZIP root. """
        try:
            source = urlsplit(source_url)
        except ValueError as exc:
            raise HTTPException(422, 'Invalid attachment URL') from exc

        if source.scheme or source.netloc or not source.path or source.query or source.fragment:
            raise HTTPException(422, 'Only relative attachment paths inside the ZIP are supported')

        decoded_path = unquote(source.path)
        if decoded_path.startswith('/') or '\\' in decoded_path:
            raise HTTPException(422, 'Invalid attachment path')

        path = posixpath.normpath(posixpath.join(posixpath.dirname(archive_path), decoded_path))
        if path == '..' or path.startswith('../'):
            raise HTTPException(422, 'Attachment path escapes ZIP root')

        return path

    @classmethod
    def _read_archive_asset(cls, archive: zipfile.ZipFile, path: str) -> bytes:
        """ Reads an attachment from the archive before creating a note. """
        try:
            info = next(
                item for item in archive.infolist() if cls._check_zipped_filename(item.filename, item) == path
            )
        except StopIteration as exc:
            raise HTTPException(422, 'Attachment is missing from the ZIP archive') from exc

        if info.file_size > settings.ATTACHMENTS_MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(413, 'Imported attachment exceeds file size limit')

        try:
            data = archive.read(info)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
            raise HTTPException(422, 'Cannot read attachment from ZIP archive') from exc

        return data

    @classmethod
    def _create_note_with_assets(
        cls, db: Session, user_id: int, folder_id: int, title: str,
        soup: BeautifulSoup, references: list, prepared: dict[str, bytes],
    ) -> Note | None:
        """ Creates a note with uploaded assets and mark it deleted if import fails. """
        note = NoteService.create_note(db, user_id, NoteCreateSchema(folder_id=folder_id, title=title))
        note_id = note.id

        try:
            uploaded = {}
            for path, data in prepared.items():
                uploaded[path] = NotesAttachmentsService.upload(
                    db, get_file_storage(), note.id, user_id, io.BytesIO(data), posixpath.basename(path),
                )
            for element, attr in references:
                attachment = uploaded[element[attr]]
                element['data-attachment-id'] = str(attachment.id)
                element[attr] = attachment_url(note.id, attachment.id)
            note = NoteService.update_note(db, note.id, user_id, NoteUpdateSchema(body=str(soup)))
        except Exception:
            db.rollback()
            note = db.query(Note).filter(Note.id == note_id).with_for_update().one()
            note.mark_as_deleted()
            db.commit()
            raise

        return note

    @classmethod
    def _is_special_path(cls, path: str) -> bool:
        """ Check if the path should be ignored (special folders/files). """
        result = False

        parts = path.lower().replace('\\', '/').split('/')
        for part in parts:
            if part in cls.IGNORE_FOLDER_NAMES or part.startswith('._'):
                result = True

        return result

    @classmethod
    def _check_zipped_filename(cls, filename: str, file_info: zipfile.ZipInfo):
        """
        Handles potential issues with zipped filenames in different OS.
        1. Checks utf-8 bit
        2. If bit is set, returns the original filename
        3. If bit is not set, tries to re-encode the filename to CP437 and decode it as utf-8
        4. Returns the original filename if re-decoding fails. Some systems like macOS might use urf-8 names
           but not set the flag, so re-decoding fails.
        """
        if file_info.flag_bits & 0x800:
            return filename

        try:
            filename = filename.encode('cp437').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return filename

    @classmethod
    def _validate_archive(cls, entries: list[zipfile.ZipInfo]) -> None:
        """ Checks archive limits, encryption and unique safe entry paths. """
        if (
            len(entries) > cls.MAX_ARCHIVE_ENTRIES or
            sum(item.file_size for item in entries) > cls.MAX_ARCHIVE_EXPANDED_SIZE
        ):
            raise HTTPException(413, 'ZIP exceeds expanded size or entry count limit')

        names = set()
        for item in entries:
            if item.flag_bits & cls.ZIP_ENCRYPTED_FLAG:
                raise HTTPException(422, 'Encrypted ZIP archives are not supported')

            path = cls._check_zipped_filename(item.filename, item)
            if (
                path.startswith('/')
                or '\\' in path
                or '..' in path.split('/')
                or ':' in path.split('/')[0]
                or path in names
                or path.rstrip('/') != posixpath.normpath(path)
            ):
                raise HTTPException(422, 'Invalid or duplicate ZIP path')

            names.add(path)

    @classmethod
    def _should_skip_archive_entry(cls, filename: str, file_info: zipfile.ZipInfo) -> bool:
        """ Checks special paths, asset directories and unsupported note files. """
        if cls._is_special_path(filename):
            return True

        if cls.ARCHIVE_ASSETS_FOLDER_NAME in filename.rstrip('/').split('/')[:-1]:
            return True
        if file_info.is_dir():
            return filename.rstrip('/').split('/')[-1] == cls.ARCHIVE_ASSETS_FOLDER_NAME

        return os.path.splitext(filename)[1].lower() not in cls.SUPPORTED_NOTE_EXTENSIONS

    @classmethod
    def _ensure_archive_folder(
        cls, db: Session, user_id: int, folder_path: str, root_folder_id: int,
        created_folders_map: dict[str, int],
    ) -> int:
        """ Creates missing folders along an archive path and return the final folder ID. """
        current_path = ''
        current_parent_id = root_folder_id

        for part in folder_path.strip('/').split('/'):
            if not part:
                continue
            full_part_path = f'{current_path}/{part}'.strip('/')
            if full_part_path not in created_folders_map:
                new_folder = NotesFolderService.create_folder(
                    db,
                    user_id,
                    NotesFolderCreateSchema(parent_id=current_parent_id, name=part),
                )
                created_folders_map[full_part_path] = new_folder.id
            current_path = full_part_path
            current_parent_id = created_folders_map[full_part_path]

        return current_parent_id

    @classmethod
    def _import_archive_note(
        cls, db: Session, user_id: int, archive: zipfile.ZipFile, file_info: zipfile.ZipInfo,
        filename: str, folder_id: int,
    ) -> Note | None:
        """ Reads a note entry and import it with access to the archive assets. """
        with archive.open(file_info) as file:
            content = file.read()
            note = cls.import_file(
                db, user_id, posixpath.basename(filename), content, folder_id,
                archive=archive, archive_path=filename,
            )
        return note

    @classmethod
    def import_zip(
        cls, db: Session, user_id: int, zip_content: bytes, folder_id: int
    ) -> list[Note]:
        imported_notes = []
        created_folders_map = {'': folder_id}

        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as archive:
            entries = archive.infolist()
            cls._validate_archive(entries)

            for file_info in entries:
                filename = cls._check_zipped_filename(file_info.filename, file_info)
                if cls._should_skip_archive_entry(filename, file_info):
                    continue

                folder_path = filename if file_info.is_dir() else posixpath.dirname(filename)
                target_folder_id = cls._ensure_archive_folder(
                    db, user_id, folder_path, folder_id, created_folders_map,
                )
                if file_info.is_dir():
                    continue

                note = cls._import_archive_note(db, user_id, archive, file_info, filename, target_folder_id)
                if note:
                    imported_notes.append(note)

        return imported_notes
