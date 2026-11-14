import datetime as dt
import logging
import warnings
from bs4 import BeautifulSoup
from collections import Counter
from fastapi import HTTPException
from io import BytesIO
from pathlib import PurePath
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typing import BinaryIO
from uuid import uuid4

from app.const.notes import NotesFolderType
from app.core.config import settings
from app.core.file_storage import FileStorage, StorageError
from app.models.notes import Note, NotesAttachment, NotesFolder
from app.models.user import User

logger = logging.getLogger(__name__)

FORMATS = {'PNG': ('image/png', 'png'), 'JPEG': ('image/jpeg', 'jpg'), 'WEBP': ('image/webp', 'webp')}
FILE_EXTENSIONS = {'pdf', 'txt', 'md', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip'}
FILE_CONTENT_TYPE = 'application/octet-stream'
INCOMPLETE_UPLOAD_TTL_DAYS = 1
IMAGE_PREVIEW_MAX_EDGE = 1600
IMAGE_PREVIEW_QUALITY = 82
IMAGE_PREVIEW_ENCODING_METHOD = 1
IMAGE_PREVIEW_CONTENT_TYPE = 'image/webp'


def attachment_url(note_id: int, attachment_id: int) -> str:
    return f'{settings.API_V1_STR}/notes/{note_id}/attachments/{attachment_id}/content/'


class NotesAttachmentsService:
    @staticmethod
    def generate_preview_image(stream: BinaryIO) -> bytes | None:
        """ Creates a smaller WebP preview image from original """
        try:
            with Image.open(stream) as source:
                # let JPEG decode at reduced resolution before applying EXIF orientation
                source.draft('RGB', (IMAGE_PREVIEW_MAX_EDGE, IMAGE_PREVIEW_MAX_EDGE))
                image = ImageOps.exif_transpose(source)
                image.thumbnail((IMAGE_PREVIEW_MAX_EDGE, IMAGE_PREVIEW_MAX_EDGE), Image.Resampling.LANCZOS)
                mode = 'RGBA' if image.has_transparency_data else 'RGB'
                with BytesIO() as output:
                    image.convert(mode).save(
                        output, format='WEBP', quality=IMAGE_PREVIEW_QUALITY, method=IMAGE_PREVIEW_ENCODING_METHOD,
                    )
                    return output.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError):
            logger.warning('Cannot generate attachment preview', exc_info=True)
            return None
        finally:
            stream.seek(0)

    @staticmethod
    def delete_files(storage: FileStorage, attachment: NotesAttachment) -> None:
        if attachment.preview_storage_key is not None:
            storage.delete(attachment.preview_storage_key)
        storage.delete(attachment.storage_key)

    @staticmethod
    def has_deleted_folder(db: Session, folder_id: int) -> bool:
        seen = set()
        while folder_id and folder_id not in seen:
            seen.add(folder_id)
            folder = db.query(NotesFolder).filter(NotesFolder.id == folder_id).first()
            if not folder or folder.is_deleted:
                return True
            folder_id = folder.parent_id
        return False

    @staticmethod
    def get_note(db: Session, note_id: int, user_id: int, *, lock=False, editable=False) -> Note:
        query = db.query(Note).filter(Note.id == note_id, Note.user_id == user_id, Note.is_deleted.is_(False))
        if lock:
            query = query.populate_existing().with_for_update()

        note = query.first()
        if not note:
            raise HTTPException(404, 'Note not found')

        folder = db.query(NotesFolder).filter(NotesFolder.id == note.folder_id).first()
        seen = set()
        while folder and folder.id not in seen:
            seen.add(folder.id)

            if folder.is_deleted:
                raise HTTPException(404, 'Note not found')

            if editable and folder.folder_type == NotesFolderType.TRASH:
                raise HTTPException(409, 'Notes in trash cannot be edited')

            folder = (
                db.query(NotesFolder).filter(NotesFolder.id == folder.parent_id).first() if folder.parent_id else None
            )

        return note

    @staticmethod
    def metadata(attachment: NotesAttachment) -> dict:
        fields = ('id', 'note_id', 'original_filename', 'content_type', 'attachment_type',
                  'size_bytes', 'width', 'height', 'created_dt')
        return {
            **{field: getattr(attachment, field) for field in fields},
            'url': attachment_url(attachment.note_id, attachment.id),
        }

    @staticmethod
    def measure_file(file: BinaryIO) -> int:
        limit = settings.ATTACHMENTS_MAX_FILE_SIZE_MB * 1024 * 1024
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > limit:
            raise HTTPException(413, 'Attachment exceeds file size limit')
        return size

    @classmethod
    def validate_image(cls, file: BinaryIO) -> tuple[int, str, str, int, int]:
        size = cls.measure_file(file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)

                with Image.open(file) as image:
                    if image.format not in FORMATS:
                        raise HTTPException(415, 'Only PNG, JPEG and WebP images are supported')

                    width, height = image.size
                    if width * height > settings.ATTACHMENTS_MAX_IMAGE_PIXELS:
                        raise HTTPException(413, 'Image exceeds pixel limit')

                    if getattr(image, 'is_animated', False):
                        raise HTTPException(415, 'Animated images are not supported')

                    content_type, extension = FORMATS[image.format]
                    image.verify()

                file.seek(0)
                with Image.open(file) as image:
                    image.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise HTTPException(413, 'Image exceeds pixel limit') from exc
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            raise HTTPException(415, 'Invalid image') from exc
        finally:
            file.seek(0)

        return size, content_type, extension, width, height

    @classmethod
    def upload(
        cls, db: Session, storage: FileStorage, note_id: int, user_id: int, file: BinaryIO, filename: str
    ) -> NotesAttachment:
        # validate note and image
        cls.get_note(db, note_id, user_id, editable=True)
        filename = PurePath(filename.replace('\\', '/')).name
        extension = PurePath(filename).suffix.lower().lstrip('.')
        if extension in FILE_EXTENSIONS:
            attachment_type = 'file'
            size, content_type = cls.measure_file(file), FILE_CONTENT_TYPE
            width = height = preview = None
        else:
            attachment_type = 'image'
            size, content_type, extension, width, height = cls.validate_image(file)
            preview = cls.generate_preview_image(file) if max(width, height) > IMAGE_PREVIEW_MAX_EDGE else None

        # lock user and note, and count total attachments size
        db.query(User).filter(User.id == user_id).with_for_update().one()
        cls.get_note(db, note_id, user_id, lock=True, editable=True)
        usage = db.query(func.coalesce(func.sum(NotesAttachment.size_bytes), 0)).join(
            Note, Note.id == NotesAttachment.note_id,
        ).filter(Note.user_id == user_id).scalar()
        count = db.query(NotesAttachment).filter(NotesAttachment.note_id == note_id).count()
        if usage + size > settings.ATTACHMENTS_MAX_USER_STORAGE_MB * 1024 * 1024:
            raise HTTPException(413, 'User attachment storage limit exceeded')
        if count >= settings.ATTACHMENTS_MAX_PER_NOTE:
            raise HTTPException(413, 'Note attachment count limit exceeded')

        storage_path = f'notes/{note_id}/{uuid4()}'
        attachment = NotesAttachment(
            note_id=note_id,
            content_type=content_type, size_bytes=size, width=width, height=height,
            status='uploading',
            original_filename=filename[:256] or f'image.{extension}',
            attachment_type=attachment_type,
            storage_key=f'{storage_path}.{extension}',
            preview_storage_key=f'{storage_path}-preview.webp' if preview else None,
        )
        db.add(attachment)
        db.commit()

        attachment_id = attachment.id
        try:
            # keep the note locked during I/O so cleanup cannot reclaim a live upload
            cls.get_note(db, note_id, user_id, lock=True, editable=True)
            attachment = db.query(NotesAttachment).filter(NotesAttachment.id == attachment_id).with_for_update().one()
            storage.put(attachment.storage_key, file, content_type)
            if preview is not None:
                storage.put(attachment.preview_storage_key, BytesIO(preview), IMAGE_PREVIEW_CONTENT_TYPE)
                attachment.preview_size_bytes = len(preview)
            attachment.status = 'ready'
            attachment.mark_as_deleted()
            db.commit()
        except Exception:
            db.rollback()
            # the persisted uploading reservation allows retries after a crash or failed compensation
            try:
                db.query(Note).filter(Note.id == note_id).with_for_update().one()
                attachment = db.query(NotesAttachment).filter(
                    NotesAttachment.id == attachment_id,
                ).with_for_update().first()
                if attachment:
                    cls.delete_files(storage, attachment)
                    db.delete(attachment)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception('Attachment upload compensation failed for %s', attachment_id)
            raise

        db.refresh(attachment)
        return attachment

    @staticmethod
    def retention_cutoff() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=settings.ATTACHMENTS_UNUSED_TTL_DAYS)

    @classmethod
    def available_filter(cls):
        # recently soft-deleted uploads remain available for insertion and undo
        return NotesAttachment.is_deleted.is_(False) | (NotesAttachment.deleted_dt > cls.retention_cutoff())

    @classmethod
    def list_attachments(cls, db: Session, note_id: int, user_id: int) -> list[NotesAttachment]:
        cls.get_note(db, note_id, user_id)
        return db.query(NotesAttachment).filter(
            NotesAttachment.note_id == note_id, NotesAttachment.status == 'ready',
            cls.available_filter(),
        ).order_by(NotesAttachment.created_dt, NotesAttachment.id).all()

    @classmethod
    def get_attachment(cls, db: Session, note_id: int, attachment_id: int, user_id: int) -> NotesAttachment:
        cls.get_note(db, note_id, user_id)
        attachment = db.query(NotesAttachment).filter(
            NotesAttachment.id == attachment_id, NotesAttachment.note_id == note_id,
            NotesAttachment.status == 'ready', cls.available_filter(),
        ).first()
        if not attachment:
            raise HTTPException(404, 'Attachment not found')
        return attachment

    @classmethod
    def synchronize_body(cls, db: Session, note: Note, body: str, *, previous_body: str | None = None) -> str:
        """ Validates attachment references, normalizes their URLs and marks unused attachments as deleted. """
        soup = BeautifulSoup(body, 'html.parser')
        old = BeautifulSoup((note.body or '') if previous_body is None else previous_body, 'html.parser')

        # preserve existing external images, but do not introduce new external URLs
        legacy = Counter(str(image) for image in old.find_all('img') if not image.has_attr('data-attachment-id'))

        attachments = db.query(NotesAttachment).filter(NotesAttachment.note_id == note.id).order_by(
            NotesAttachment.id,
        ).populate_existing().with_for_update().all()
        by_id = {str(item.id): item for item in attachments}

        referenced = set()
        links_by_url = {attachment_url(note.id, item.id): str(item.id) for item in attachments}
        for image in soup.find_all(['img', 'a']):
            url_attr = 'src' if image.name == 'img' else 'href'
            raw_id = image.get('data-attachment-id')
            if raw_id is None:
                # recognize stable URLs even when another editor strips the data attribute
                raw_id = links_by_url.get(image.get(url_attr))
                if raw_id is None and image.name == 'a':
                    continue
                if raw_id is None and legacy[str(image)] > 0:
                    legacy[str(image)] -= 1
                    continue
                if raw_id is None:
                    raise HTTPException(422, 'Images must reference an uploaded attachment')

            try:
                normalized_id = str(int(raw_id))
                if int(normalized_id) <= 0:
                    raise ValueError('Attachment id must be positive')
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(422, 'Invalid attachment id') from exc

            attachment = by_id.get(normalized_id)
            if (not attachment or attachment.status != 'ready' or
                    (attachment.is_deleted and (attachment.deleted_dt is None or
                                                attachment.deleted_dt <= cls.retention_cutoff()))):
                raise HTTPException(422, 'Attachment does not belong to this note or is unavailable')

            expected_type = 'image' if image.name == 'img' else 'file'
            if attachment.attachment_type != expected_type:
                raise HTTPException(422, 'Attachment type does not match its reference')

            image['data-attachment-id'] = normalized_id
            image[url_attr] = attachment_url(note.id, attachment.id)
            referenced.add(normalized_id)

        for attachment in attachments:
            if attachment.status == 'ready':
                if str(attachment.id) in referenced:
                    attachment.is_deleted = False
                    attachment.deleted_dt = None
                elif not attachment.is_deleted:
                    attachment.mark_as_deleted()

        return str(soup) if referenced else body

    @classmethod
    def cleanup(cls, db: Session, storage: FileStorage, *, limit: int = 100) -> int:
        """ Deletes unused attachments, attachments of deleted notes or folders, and stale uploads. """
        cutoff = cls.retention_cutoff()
        stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=INCOMPLETE_UPLOAD_TTL_DAYS)

        deleted_folders = select(NotesFolder.id).where(NotesFolder.is_deleted.is_(True)).cte(
            'deleted_attachment_folders', recursive=True,
        )
        deleted_folders = deleted_folders.union(
            select(NotesFolder.id).where(NotesFolder.parent_id == deleted_folders.c.id),
        )
        candidates = db.query(NotesAttachment.id, NotesAttachment.note_id).join(Note).filter(
            ((NotesAttachment.status == 'uploading') & (NotesAttachment.created_dt < stale)) |
            ((NotesAttachment.status == 'ready') & (
                    (NotesAttachment.is_deleted.is_(True) & (NotesAttachment.deleted_dt < cutoff)) |
                    Note.is_deleted.is_(True) | Note.folder_id.in_(select(deleted_folders.c.id))
            )),
        ).order_by(NotesAttachment.created_dt).limit(limit).all()
        db.rollback()

        removed = 0
        for attachment_id, note_id in candidates:
            note = db.query(Note).filter(Note.id == note_id).populate_existing().with_for_update(
                skip_locked=True,
            ).first()
            if not note:
                db.rollback()
                continue

            attachment = db.query(NotesAttachment).filter(
                NotesAttachment.id == attachment_id,
            ).populate_existing().with_for_update().first()
            if not attachment:
                db.rollback()
                continue

            if (
                attachment.status == 'ready' and not note.is_deleted and not cls.has_deleted_folder(db, note.folder_id)
            ):
                tag, url_attr = ('img', 'src') if attachment.attachment_type == 'image' else ('a', 'href')
                images = BeautifulSoup(note.body or '', 'html.parser').find_all(tag)
                referenced = any(
                    image.get('data-attachment-id') == str(attachment.id) or
                    image.get(url_attr) == attachment_url(note.id, attachment.id)
                    for image in images
                )
                if referenced:
                    attachment.is_deleted = False
                    attachment.deleted_dt = None
                    db.commit()
                    continue
                if not attachment.is_deleted:
                    attachment.mark_as_deleted()
                if attachment.deleted_dt is None or attachment.deleted_dt >= cutoff:
                    db.commit()
                    continue
            elif attachment.status == 'uploading' and attachment.created_dt >= stale:
                db.rollback()
                continue

            if not attachment.is_deleted:
                attachment.mark_as_deleted()

            try:
                # keep both locks until deletion commits so saves cannot restore a file being removed
                cls.delete_files(storage, attachment)
            except StorageError:
                db.commit()
                logger.exception('Attachment cleanup failed for %s', attachment_id)
                continue

            db.delete(attachment)
            db.commit()
            removed += 1

        return removed
