import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Note
from app.schemas.notes import NoteAppendSchema
from app.services.notes_service import NoteService


WAIT_TIMEOUT_SECONDS = 10
LOCK_POLL_INTERVAL_SECONDS = 0.01


def test_concurrent_appends_wait_for_lock_and_refresh_stale_body(test_engine, committed_note):
    user_id, note_id = committed_note
    backend_pids = Queue()

    def append_second_fragment():
        with Session(test_engine) as db:
            db.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {'timeout': f'{WAIT_TIMEOUT_SECONDS}s'},
            )
            stale_note = db.get(Note, note_id)
            assert stale_note.body == '<p>Original</p>'
            backend_pids.put(db.scalar(select(func.pg_backend_pid())))
            result = NoteService.append_to_note(db, note_id, user_id, NoteAppendSchema(body='<p>Second</p>'))
            return result.body

    with ThreadPoolExecutor(max_workers=1) as executor:
        with Session(test_engine) as first:
            first.query(Note).filter(Note.id == note_id).with_for_update().one()
            first_pid = first.scalar(select(func.pg_backend_pid()))
            future = executor.submit(append_second_fragment)
            second_pid = backend_pids.get(timeout=WAIT_TIMEOUT_SECONDS)
            deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS

            with Session(test_engine) as observer:
                while first_pid not in observer.scalar(select(func.pg_blocking_pids(second_pid))):
                    assert not future.done(), 'append must wait for the locked note'
                    assert time.monotonic() < deadline, 'append did not acquire a PostgreSQL row lock'
                    time.sleep(LOCK_POLL_INTERVAL_SECONDS)

            NoteService.append_to_note(first, note_id, user_id, NoteAppendSchema(body='<p>First</p>'))

        assert future.result(timeout=WAIT_TIMEOUT_SECONDS) == '<p>Original</p><p>First</p><p>Second</p>'

    with Session(test_engine) as db:
        note = db.get(Note, note_id)
        assert note.body == '<p>Original</p><p>First</p><p>Second</p>'
        assert note.body_plain_text == 'Original First Second'
