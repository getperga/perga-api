from enum import Enum


class NotesFolderType(str, Enum):
    REGULAR = 'regular'
    ROOT = 'root'
    TRASH = 'trash'


class ExportType(str, Enum):
    MARKDOWN = 'markdown'
    HTML = 'html'
    PDF = 'pdf'


class ExportTarget(str, Enum):
    SINGLE_NOTE = 'single_note'
    FOLDER_NOTES = 'folder_notes'
    ALL_NOTES = 'all_notes'


EXPORT_TYPE_EXTENSION_MAP = {
    ExportType.MARKDOWN: 'md',
    ExportType.HTML: 'html',
    ExportType.PDF: 'pdf',
}


EXPORT_MEDIA_TYPE_MAP = {
    ExportType.MARKDOWN: 'text/markdown',
    ExportType.HTML: 'text/html',
    ExportType.PDF: 'application/pdf',
}

IMPORT_SIZE_LIMIT_MB = 10
IMPORT_SIZE_LIMIT = IMPORT_SIZE_LIMIT_MB * 1024 * 1024

# HTML sanitization settings
NOTE_BODY_ALLOWED_TAGS = {
    'p', 'br',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'u', 's', 'del',
    'sub', 'sup',
    'ul', 'ol', 'li',
    'blockquote', 'code', 'pre', 'hr',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'details', 'summary',
}
NOTE_BODY_ALLOWED_ATTRIBUTES = {
    'a': {'href', 'target', 'title'},
    'img': {'src', 'alt', 'title', 'width', 'height'},
    'ol': {'start', 'type'},
    'ul': {'data-type'},
    'li': {'data-type', 'data-checked'},
    'td': {'colspan', 'rowspan'},
    'th': {'colspan', 'rowspan'},
}
NOTE_BODY_ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}
