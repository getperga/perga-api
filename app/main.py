import logging
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette import status
from starlette.responses import RedirectResponse, Response, JSONResponse

from app.core.config import settings
from app.core.file_storage import StorageError, get_file_storage
from app.core.middlewares.attachment_upload_limit import AttachmentUploadLimitMiddleware
from app.api.v1 import (
    auth,
    planner_days, planner_agendas,
    notes, notes_folders, notes_export, notes_import, notes_attachments,
)

# Ensure logs directory exists
logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    level=settings.LOGGING_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(logs_dir, "app.log"), mode="a", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"Application starting in {'development' if settings.IS_DEV else 'production'} mode")

router_prefix = f'{settings.API_V1_STR}/'


@asynccontextmanager
async def lifespan(app):
    get_file_storage()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f'{router_prefix}openapi.json',
    lifespan=lifespan,
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=['Content-Disposition'],
)

# Attachments storage
app.add_middleware(AttachmentUploadLimitMiddleware)
@app.exception_handler(StorageError)
async def storage_error_handler(request, exc):
    logger.error('Attachment storage operation failed', exc_info=exc)
    return JSONResponse({'detail': 'Attachment storage is temporarily unavailable'}, status_code=503)

# Include routers

app.include_router(auth.router, prefix=f'{router_prefix}auth', tags=['auth'])

app.include_router(planner_days.router, prefix=f'{router_prefix}planner/days', tags=['planner_days'])
app.include_router(planner_agendas.router, prefix=f'{router_prefix}planner/agendas', tags=['planner_agendas'])

app.include_router(notes_folders.router, prefix=f"{router_prefix}notes/folders", tags=['notes_folders'])
app.include_router(notes_export.router, prefix=f"{router_prefix}notes/export", tags=['notes_export'])
app.include_router(notes_import.router, prefix=f"{router_prefix}notes/import", tags=['notes_import'])
app.include_router(notes.router, prefix=f'{router_prefix}notes', tags=['notes'])
app.include_router(notes_attachments.router, prefix=f'{router_prefix}notes', tags=['notes_attachments'])

@app.get('/')
def root():
    if settings.ROOT_URL_REDIRECT:
        return RedirectResponse(url=settings.ROOT_URL_REDIRECT)
    return Response(content='OK', status_code=status.HTTP_200_OK)

@app.get('/health/')
def health():
    return Response(content='OK', status_code=status.HTTP_200_OK)
