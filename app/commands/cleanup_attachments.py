""" Run with python -m app.commands.cleanup_attachments --limit 100 """
import argparse
import logging

from app.core.database import SessionLocal
from app.core.file_storage import get_file_storage
from app.services.notes_attachments_service import NotesAttachmentsService


def main() -> None:
    parser = argparse.ArgumentParser(description='Remove unused note attachments and retry failed deletions')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of items per run')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        removed = NotesAttachmentsService.cleanup(db, get_file_storage(), limit=args.limit)

    print(f'Removed {removed} attachments')


if __name__ == '__main__':
    main()
