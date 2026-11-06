# Stream and Queue Constants
STREAM_DOCUMENTS_JOBS = "documents:jobs"
GROUP_DOCUMENTS_WORKERS = "documents:workers"
STREAM_DOCUMENTS_DEAD = "documents:dead"

# Redis Key Patterns
PREFIX_DOC = "doc:"
INDEX_DOCS = "docs:index"
PREFIX_WORKER_HEARTBEAT = "worker:heartbeat:"


def doc_key(doc_id: str) -> str:
    """Return the hash key for document metadata."""
    return f"doc:{doc_id}"


def doc_file_key(doc_id: str) -> str:
    """Return the key storing raw PDF binary bytes."""
    return f"doc:{doc_id}:file"


def doc_pages_key(doc_id: str) -> str:
    """Return the key storing extracted pages JSON."""
    return f"doc:{doc_id}:pages"


def doc_summary_key(doc_id: str) -> str:
    """Return the key storing the consolidated summary."""
    return f"doc:{doc_id}:summary"


def doc_lock_key(doc_id: str) -> str:
    """Return the distributed lock key for document processing."""
    return f"doc:lock:{doc_id}"


def worker_heartbeat_key(consumer_name: str) -> str:
    """Return the key storing worker heartbeat."""
    return f"worker:heartbeat:{consumer_name}"


# Header and Protocol Constants
RETRY_AFTER_HEADER = "Retry-After"
ALLOWED_MIME_TYPE = "application/pdf"
PDF_MAGIC_BYTES = b"%PDF-"
