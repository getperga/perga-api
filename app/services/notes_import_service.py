import html
import io
import markdown
import os
import re
import zipfile
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.notes import Note
from app.schemas.notes import NoteCreateSchema
from app.schemas.notes_folders import NotesFolderCreateSchema
from app.services.notes_service import NoteService
from app.services.notes_folders_service import NotesFolderService


class NotesImportService:
    IGNORE_FOLDER_NAMES = ('__macosx', '.ds_store', 'thumbs.db', 'desktop.ini')

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
        body_html = markdown.markdown(body_md)
        # to avoid losing line breaks, replace \n with empty paragraph tags
        # but not in between of lists
        body_html = re.sub(r'\n(?=<(?!li|/ul|/ol))', '<p></p>', body_html)
        return title, body_html

    @classmethod
    def _parse_txt(cls, content: str, default_title: str) -> tuple[str, str]:
        title = default_title
        body_html = f'<p>{html.escape(content)}</p>'
        return title, body_html

    @classmethod
    def import_file(
        cls, db: Session, user_id: int, filename: str, content: bytes, folder_id: int
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

        return NoteService.create_note(
            db,
            user_id,
            NoteCreateSchema(folder_id=folder_id, title=title, body=body)
        )

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
    def import_zip(
        cls, db: Session, user_id: int, zip_content: bytes, folder_id: int
    ) -> list[Note]:
        imported_notes = []

        zip_buffer = io.BytesIO(zip_content)
        with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
            # keep track of created folders to reuse them: { <path>: <folder_id> }
            created_folders_map = {'': folder_id}
            
            for file_info in zip_ref.infolist():
                filename = cls._check_zipped_filename(file_info.filename, file_info)

                # skip special folders and files
                if cls._is_special_path(filename):
                    continue

                if file_info.is_dir():
                    path_parts = [part for part in filename.strip('/').split('/') if part]
                    current_path = ''
                    current_parent_id = folder_id
                    
                    for part in path_parts:
                        full_part_path = f'{current_path}/{part}'.strip('/')
                        if full_part_path not in created_folders_map:
                            new_folder = NotesFolderService.create_folder(
                                db,
                                user_id,
                                NotesFolderCreateSchema(parent_id=current_parent_id, name=part)
                            )
                            created_folders_map[full_part_path] = new_folder.id
                        
                        current_path = full_part_path
                        current_parent_id = created_folders_map[full_part_path]
                    continue
                
                # Handle file entry
                path_parts = filename.split('/')
                
                if len(path_parts) > 1:
                    # File is in a subfolder
                    base_filename = path_parts[-1]
                    
                    # Ensure all parent folders exist
                    current_path = ''
                    current_parent_id = folder_id
                    for part in path_parts[:-1]:
                        full_part_path = f'{current_path}/{part}'.strip('/')
                        if full_part_path not in created_folders_map:
                            new_folder = NotesFolderService.create_folder(
                                db,
                                user_id,
                                NotesFolderCreateSchema(parent_id=current_parent_id, name=part)
                            )
                            created_folders_map[full_part_path] = new_folder.id
                        current_path = full_part_path
                        current_parent_id = created_folders_map[full_part_path]
                    
                    target_folder_id = current_parent_id
                else:
                    base_filename = filename
                    target_folder_id = folder_id
                
                # import the file
                with zip_ref.open(file_info) as f:
                    content = f.read()
                    note = cls.import_file(db, user_id, base_filename, content, target_folder_id)
                    if note:
                        imported_notes.append(note)
                        
        return imported_notes
