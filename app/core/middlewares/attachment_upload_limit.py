import tempfile
from typing import BinaryIO

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import Message, Receive

from app.core.config import settings


MULTIPART_OVERHEAD_BYTES = 64 * 1024
READ_CHUNK_SIZE_BYTES = 64 * 1024


class _BufferedRequestReceive:
    """ Replays the buffered body, then forwards subsequent ASGI receive calls """

    def __init__(self, body: BinaryIO, size: int, receive: Receive):
        self.body = body
        self.remaining = size
        self.receive = receive
        self.delivered = False

    async def __call__(self) -> Message:
        if self.delivered:
            return await self.receive()

        chunk = await run_in_threadpool(self.body.read, READ_CHUNK_SIZE_BYTES)
        self.remaining -= len(chunk)
        self.delivered = self.remaining <= 0
        return {
            'type': 'http.request',
            'body': chunk,
            'more_body': self.remaining > 0,
        }


class AttachmentUploadLimitMiddleware:
    """ Checks and limits attachment requests before multipart parsing allocates temporary files """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '').rstrip('/')
        prefix = f'{settings.API_V1_STR}/notes/'
        if scope['type'] != 'http' or scope['method'] != 'POST' or not (
            path.startswith(prefix) and path.endswith('/attachments')
        ):
            await self.app(scope, receive, send)
            return

        # convert the file size limit to bytes and add space for multipart headers and boundaries
        limit = settings.ATTACHMENTS_MAX_FILE_SIZE_MB * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES

        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            declared = 0

        if declared > limit:
            await JSONResponse(
                {'detail': 'Attachment request is too large'},
                status_code=413
            )(scope, receive, send)
            return

        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
            total = 0

            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return

                chunk = message.get('body', b'')
                total += len(chunk)
                if total > limit:
                    response = JSONResponse({'detail': 'Attachment request is too large'}, status_code=413)
                    await response(scope, receive, send)
                    return

                await run_in_threadpool(body.write, chunk)
                if not message.get('more_body', False):
                    break

            await run_in_threadpool(body.seek, 0)
            replay = _BufferedRequestReceive(body, total, receive)
            await self.app(scope, replay, send)
