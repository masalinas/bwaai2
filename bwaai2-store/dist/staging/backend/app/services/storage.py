import base64
import json
from datetime import UTC, datetime

from redis.asyncio import ConnectionPool, Redis

from app.core import constants
from app.core.config import settings
from app.core.exceptions import DocumentNotFoundError
from app.core.logging import logger
from app.models.documents import (
    DocumentDetailResponse,
    DocumentListItem,
    DocumentPage,
    DocumentStatus,
    DocumentStatusResponse,
    ParserType,
)
from app.models.errors import Error

# Global connection pool
_redis_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=False,  # We handle binary vs text explicitly
        )
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connection pool closed.")


def get_redis_client() -> Redis:
    pool = get_redis_pool()
    return Redis(connection_pool=pool)


class StorageService:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis or get_redis_client()

    async def save_document(
        self,
        document_id: str,
        filename: str,
        parser: ParserType,
        pdf_bytes: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else settings.PDF_TTL_SECONDS
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        now_epoch = now.timestamp()

        pipe = self.redis.pipeline(transaction=True)

        # 1. Store raw PDF binary bytes with TTL
        pipe.set(constants.doc_file_key(document_id), pdf_bytes, ex=ttl)

        # 2. Store metadata hash
        meta = {
            b"document_id": document_id.encode("utf-8"),
            b"filename": filename.encode("utf-8"),
            b"parser": parser.value.encode("utf-8"),
            b"status": DocumentStatus.queued.value.encode("utf-8"),
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        }
        pipe.hset(constants.doc_key(document_id), mapping=meta)

        # 3. Add to sorted set index ordered by score (epoch timestamp)
        pipe.zadd(constants.INDEX_DOCS, {document_id.encode("utf-8"): now_epoch})

        await pipe.execute()
        logger.info(
            "Saved document %s (%s, %d bytes) in Redis", document_id, filename, len(pdf_bytes)
        )

    async def get_raw_metadata(self, document_id: str) -> dict[str, str] | None:
        data = await self.redis.hgetall(constants.doc_key(document_id))
        if not data:
            return None
        return {k.decode("utf-8"): v.decode("utf-8") for k, v in data.items()}

    async def get_document_status(self, document_id: str) -> DocumentStatusResponse:
        meta = await self.get_raw_metadata(document_id)
        if not meta:
            raise DocumentNotFoundError(
                message=f"Document with ID '{document_id}' was not found.",
                details={"document_id": document_id},
            )

        error_obj: Error | None = None
        if meta.get("error"):
            try:
                error_dict = json.loads(meta["error"])
                error_obj = Error(**error_dict)
            except Exception:
                pass

        return DocumentStatusResponse(
            document_id=meta["document_id"],
            status=DocumentStatus(meta["status"]),
            created_at=datetime.fromisoformat(meta["created_at"]),
            updated_at=datetime.fromisoformat(meta["updated_at"]),
            error=error_obj,
        )

    async def get_document_detail(self, document_id: str) -> DocumentDetailResponse:
        meta = await self.get_raw_metadata(document_id)
        if not meta:
            raise DocumentNotFoundError(
                message=f"Document with ID '{document_id}' was not found.",
                details={"document_id": document_id},
            )

        pages_list: list[DocumentPage] | None = None
        summary_val: str | None = None
        error_obj: Error | None = None

        current_status = meta.get("status")

        # Expose pages as soon as they exist (summarizing, done, or failed after parsing)
        if current_status in (
            DocumentStatus.summarizing.value,
            DocumentStatus.done.value,
            DocumentStatus.failed.value,
        ):
            pages_raw = await self.redis.get(constants.doc_pages_key(document_id))
            if pages_raw:
                try:
                    pages_data = json.loads(pages_raw.decode("utf-8"))
                    pages_list = [DocumentPage(**p) for p in pages_data]
                except Exception as ex:
                    logger.warning("Failed to deserialize pages for %s: %s", document_id, ex)

        # Summary is populated only when status is done
        if current_status == DocumentStatus.done.value:
            summary_raw = await self.redis.get(constants.doc_summary_key(document_id))
            if summary_raw:
                summary_val = summary_raw.decode("utf-8")

        elif current_status == DocumentStatus.failed.value and meta.get("error"):
            try:
                error_dict = json.loads(meta["error"])
                error_obj = Error(**error_dict)
            except Exception:
                pass

        return DocumentDetailResponse(
            document_id=meta["document_id"],
            filename=meta["filename"],
            parser=ParserType(meta["parser"]),
            status=DocumentStatus(meta["status"]),
            created_at=datetime.fromisoformat(meta["created_at"]),
            updated_at=datetime.fromisoformat(meta["updated_at"]),
            pages=pages_list,
            summary=summary_val,
            error=error_obj,
        )

    async def list_documents(
        self,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[DocumentListItem], str | None, bool]:
        max_score = "+inf"
        offset = 0

        if cursor:
            try:
                decoded = json.loads(base64.b64decode(cursor.encode("ascii")).decode("utf-8"))
                max_score = str(decoded["ts"])
                offset = 1  # Skip the item with max_score itself
            except Exception:
                # If invalid cursor, default to start from beginning
                max_score = "+inf"
                offset = 0

        # Fetch limit + 1 to know if there is a next page
        doc_ids_with_scores = await self.redis.zrevrangebyscore(
            constants.INDEX_DOCS,
            max=max_score,
            min="-inf",
            start=offset,
            num=limit + 1,
            withscores=True,
        )

        has_more = len(doc_ids_with_scores) > limit
        selected_entries = doc_ids_with_scores[:limit]

        items: list[DocumentListItem] = []
        for raw_id, _ in selected_entries:
            doc_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
            meta = await self.get_raw_metadata(doc_id)
            if meta:
                items.append(
                    DocumentListItem(
                        document_id=meta["document_id"],
                        filename=meta["filename"],
                        parser=ParserType(meta["parser"]),
                        status=DocumentStatus(meta["status"]),
                        created_at=datetime.fromisoformat(meta["created_at"]),
                        updated_at=datetime.fromisoformat(meta["updated_at"]),
                    )
                )

        next_cursor: str | None = None
        if has_more and selected_entries:
            last_id, last_score = selected_entries[-1]
            last_id_str = last_id.decode("utf-8") if isinstance(last_id, bytes) else str(last_id)
            cursor_payload = {"ts": last_score, "id": last_id_str}
            next_cursor = base64.b64encode(json.dumps(cursor_payload).encode("utf-8")).decode(
                "ascii"
            )

        return items, next_cursor, has_more

    async def get_raw_file(self, document_id: str) -> bytes | None:
        data = await self.redis.get(constants.doc_file_key(document_id))
        return data

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception as ex:
            logger.error("Redis ping check failed: %s", ex)
            return False
