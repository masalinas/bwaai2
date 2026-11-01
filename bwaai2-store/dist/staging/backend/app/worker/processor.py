import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core import constants
from app.core.config import settings
from app.core.exceptions import (
    EncryptedPDFError,
    ErrorCode,
    InvalidFileTypeError,
    ParserFailedError,
    ParserRateLimitedError,
    ParserTransientError,
    ParserUnavailableError,
    SummaryFailedError,
    SummaryRateLimitedError,
)
from app.core.logging import logger
from app.models.documents import DocumentPage
from app.models.errors import Error
from app.services.parsers.base import BaseParser
from app.services.parsers.gemini_parser import GeminiParser
from app.services.parsers.mistral_parser import MistralParser
from app.services.parsers.pypdf_parser import PyPDFParser
from app.services.summarizer import DocumentSummarizer


class JobProcessor:
    def __init__(
        self,
        redis: Redis,
        pypdf_parser: PyPDFParser | None = None,
        gemini_parser: GeminiParser | None = None,
        mistral_parser: MistralParser | None = None,
        summarizer: DocumentSummarizer | None = None,
    ) -> None:
        self.redis = redis
        self.pypdf_parser = pypdf_parser or PyPDFParser()
        self.gemini_parser = gemini_parser or GeminiParser()
        self.mistral_parser = mistral_parser or MistralParser()
        self.summarizer = summarizer or DocumentSummarizer()

    def _get_parser_for(self, parser_name: str) -> BaseParser | None:
        if parser_name == "pypdf":
            return self.pypdf_parser
        if parser_name == "gemini":
            return self.gemini_parser
        if parser_name == "mistral":
            return self.mistral_parser
        return None

    async def process_message(
        self,
        msg_id: str,
        fields: dict[str | bytes, str | bytes],
        consumer_name: str,
        delivery_count: int = 1,
    ) -> None:
        normalized: dict[str, str] = {}
        for k, v in fields.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            val = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            normalized[key] = val

        doc_id = normalized.get("document_id")
        parser_name = normalized.get("parser", "pypdf")

        if not doc_id:
            logger.warning(
                "[%s] Missing document_id in msg %s, acknowledging", consumer_name, msg_id
            )
            await self.redis.xack(
                constants.STREAM_DOCUMENTS_JOBS, constants.GROUP_DOCUMENTS_WORKERS, msg_id
            )
            return

        logger.info(
            "[%s] [%s] [attempt_%d] Processing message %s (parser: %s)",
            consumer_name,
            doc_id,
            delivery_count,
            msg_id,
            parser_name,
        )

        # 1. Fetch document metadata
        meta = await self.redis.hgetall(constants.doc_key(doc_id))
        if not meta:
            logger.warning("[%s] [%s] Document metadata not found in Redis", consumer_name, doc_id)
            await self._handle_permanent_error(
                doc_id=doc_id,
                parser=parser_name,
                msg_id=msg_id,
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message=f"Document with ID '{doc_id}' not found.",
                consumer_name=consumer_name,
                attempts=delivery_count,
            )
            return

        current_status = meta.get(b"status", b"").decode("utf-8")

        # Idempotency check: if already completed, acknowledge immediately
        if current_status == "done":
            logger.info(
                "[%s] [%s] Document already done, acknowledging duplicate", consumer_name, doc_id
            )
            await self.redis.xack(
                constants.STREAM_DOCUMENTS_JOBS, constants.GROUP_DOCUMENTS_WORKERS, msg_id
            )
            return

        parser = self._get_parser_for(parser_name)
        if not parser:
            await self._handle_permanent_error(
                doc_id=doc_id,
                parser=parser_name,
                msg_id=msg_id,
                code=ErrorCode.PARSER_UNAVAILABLE,
                message=f"Parser '{parser_name}' is not recognized.",
                consumer_name=consumer_name,
                attempts=delivery_count,
            )
            return

        # -------------------------------------------------------------
        # STAGE 1: PARSING (Resumable)
        # -------------------------------------------------------------
        pages_raw = await self.redis.get(constants.doc_pages_key(doc_id))
        pages: list[DocumentPage]

        if pages_raw:
            logger.info(
                "[%s] [%s] Pages already parsed in Redis; skipping Stage 1", consumer_name, doc_id
            )
            pages_data = json.loads(pages_raw.decode("utf-8"))
            pages = [DocumentPage(**p) for p in pages_data]
        else:
            # Mark processing
            now_iso = datetime.now(UTC).isoformat()
            await self.redis.hset(
                constants.doc_key(doc_id),
                mapping={
                    b"status": b"processing",
                    b"started_at": now_iso.encode("utf-8"),
                    b"updated_at": now_iso.encode("utf-8"),
                },
            )

            # Load raw PDF bytes
            pdf_bytes = await self.redis.get(constants.doc_file_key(doc_id))
            if not pdf_bytes:
                logger.error(
                    "[%s] [%s] PDF bytes missing or expired from Redis", consumer_name, doc_id
                )
                await self._handle_permanent_error(
                    doc_id=doc_id,
                    parser=parser_name,
                    msg_id=msg_id,
                    code=ErrorCode.DOCUMENT_NOT_FOUND,
                    message="PDF file bytes have expired or were not found.",
                    consumer_name=consumer_name,
                    attempts=delivery_count,
                )
                return

            try:
                pages = await parser.parse(pdf_bytes)
                pages_json = json.dumps([p.model_dump() for p in pages])
                # Store pages in Redis
                await self.redis.set(constants.doc_pages_key(doc_id), pages_json.encode("utf-8"))
                logger.info(
                    "[%s] [%s] Stage 1 (Parsing) completed: %d pages saved",
                    consumer_name,
                    doc_id,
                    len(pages),
                )
            except EncryptedPDFError as ex:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.ENCRYPTED_PDF,
                    ex.message,
                    consumer_name,
                    delivery_count,
                )
                return
            except InvalidFileTypeError as ex:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.INVALID_FILE_TYPE,
                    ex.message,
                    consumer_name,
                    delivery_count,
                )
                return
            except ParserUnavailableError as ex:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.PARSER_UNAVAILABLE,
                    ex.message,
                    consumer_name,
                    delivery_count,
                )
                return
            except (ParserRateLimitedError, ParserTransientError) as ex:
                await self._handle_transient_error(
                    doc_id, parser_name, msg_id, ex.message, consumer_name, delivery_count
                )
                return
            except ParserFailedError as ex:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.PARSER_FAILED,
                    ex.message,
                    consumer_name,
                    delivery_count,
                )
                return
            except (ConnectionError, TimeoutError, RedisError) as ex:
                await self._handle_transient_error(
                    doc_id, parser_name, msg_id, str(ex), consumer_name, delivery_count
                )
                return
            except Exception as ex:
                logger.error(
                    "[%s] [%s] Unexpected error during parsing: %s",
                    consumer_name,
                    doc_id,
                    ex,
                    exc_info=True,
                )
                if delivery_count >= settings.MAX_ATTEMPTS:
                    await self._handle_permanent_error(
                        doc_id,
                        parser_name,
                        msg_id,
                        ErrorCode.PARSER_FAILED,
                        f"Parsing crashed: {str(ex)}",
                        consumer_name,
                        delivery_count,
                    )
                else:
                    await self._handle_transient_error(
                        doc_id, parser_name, msg_id, str(ex), consumer_name, delivery_count
                    )
                return

        # -------------------------------------------------------------
        # STAGE TRANSITION: SUMMARIZING
        # -------------------------------------------------------------
        now_iso = datetime.now(UTC).isoformat()
        await self.redis.hset(
            constants.doc_key(doc_id),
            mapping={
                b"status": b"summarizing",
                b"updated_at": now_iso.encode("utf-8"),
            },
        )
        logger.info("[%s] [%s] Transitioned to summarizing stage", consumer_name, doc_id)

        # -------------------------------------------------------------
        # STAGE 2: SUMMARIZATION
        # -------------------------------------------------------------
        try:
            summary = await self.summarizer.summarize_document(pages)
            finish_iso = datetime.now(UTC).isoformat()

            # Atomically save summary and transition to done
            pipe = self.redis.pipeline(transaction=True)
            pipe.set(constants.doc_summary_key(doc_id), summary.encode("utf-8"))
            pipe.hset(
                constants.doc_key(doc_id),
                mapping={
                    b"status": b"done",
                    b"finished_at": finish_iso.encode("utf-8"),
                    b"updated_at": finish_iso.encode("utf-8"),
                },
            )
            await pipe.execute()

            # Acknowledge strictly AFTER both stages succeed
            await self.redis.xack(
                constants.STREAM_DOCUMENTS_JOBS, constants.GROUP_DOCUMENTS_WORKERS, msg_id
            )
            logger.info(
                "[%s] [%s] [attempt_%d] Pipeline complete: status done with summary (%d chars)",
                consumer_name,
                doc_id,
                delivery_count,
                len(summary),
            )

        except SummaryFailedError as ex:
            # Permanent summarization failure (e.g. empty text, prompt blocked)
            await self._handle_permanent_error(
                doc_id,
                parser_name,
                msg_id,
                ErrorCode.SUMMARY_FAILED,
                ex.message,
                consumer_name,
                delivery_count,
            )
        except SummaryRateLimitedError as ex:
            # Rate limit is transient: retry up to MAX_ATTEMPTS
            if delivery_count >= settings.MAX_ATTEMPTS:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.SUMMARY_RATE_LIMITED,
                    ex.message,
                    consumer_name,
                    delivery_count,
                )
            else:
                await self._handle_transient_error(
                    doc_id, parser_name, msg_id, ex.message, consumer_name, delivery_count
                )
        except (ConnectionError, TimeoutError, RedisError) as ex:
            await self._handle_transient_error(
                doc_id, parser_name, msg_id, str(ex), consumer_name, delivery_count
            )
        except Exception as ex:
            logger.error(
                "[%s] [%s] Unexpected error during summarization: %s",
                consumer_name,
                doc_id,
                ex,
                exc_info=True,
            )
            if delivery_count >= settings.MAX_ATTEMPTS:
                await self._handle_permanent_error(
                    doc_id,
                    parser_name,
                    msg_id,
                    ErrorCode.SUMMARY_FAILED,
                    f"Summarization failed: {str(ex)}",
                    consumer_name,
                    delivery_count,
                )
            else:
                await self._handle_transient_error(
                    doc_id, parser_name, msg_id, str(ex), consumer_name, delivery_count
                )

    async def _handle_permanent_error(
        self,
        doc_id: str,
        parser: str,
        msg_id: str,
        code: ErrorCode,
        message: str,
        consumer_name: str,
        attempts: int,
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        err = Error(code=code, message=message)

        pipe = self.redis.pipeline(transaction=True)
        pipe.hset(
            constants.doc_key(doc_id),
            mapping={
                b"status": b"failed",
                b"error": err.model_dump_json().encode("utf-8"),
                b"finished_at": now_iso.encode("utf-8"),
                b"updated_at": now_iso.encode("utf-8"),
            },
        )
        await pipe.execute()

        # Route to DLQ and acknowledge original message
        await self._send_to_dlq(doc_id, parser, msg_id, code.value, message, attempts)
        await self.redis.xack(
            constants.STREAM_DOCUMENTS_JOBS, constants.GROUP_DOCUMENTS_WORKERS, msg_id
        )
        logger.error(
            "[%s] [%s] [attempt_%d] Marked failed (%s): %s",
            consumer_name,
            doc_id,
            attempts,
            code.value,
            message,
        )

    async def _handle_transient_error(
        self,
        doc_id: str,
        parser: str,
        msg_id: str,
        message: str,
        consumer_name: str,
        attempts: int,
    ) -> None:
        if attempts >= settings.MAX_ATTEMPTS:
            logger.error(
                "[%s] [%s] [attempt_%d] Exceeded max attempts (%d), routing to DLQ",
                consumer_name,
                doc_id,
                attempts,
                settings.MAX_ATTEMPTS,
            )
            await self._handle_permanent_error(
                doc_id=doc_id,
                parser=parser,
                msg_id=msg_id,
                code=ErrorCode.PARSER_FAILED,
                message=f"Exceeded maximum retry attempts: {message}",
                consumer_name=consumer_name,
                attempts=attempts,
            )
        else:
            logger.warning(
                "[%s] [%s] [attempt_%d] Transient error: %s. Leaving unacknowledged for redelivery.",
                consumer_name,
                doc_id,
                attempts,
                message,
            )

    async def _send_to_dlq(
        self,
        doc_id: str,
        parser: str,
        original_msg_id: str,
        error_code: str,
        error_message: str,
        attempts: int,
    ) -> str:
        now_iso = datetime.now(UTC).isoformat()
        dlq_payload = {
            b"document_id": doc_id.encode("utf-8"),
            b"parser": parser.encode("utf-8"),
            b"original_msg_id": original_msg_id.encode("utf-8"),
            b"error_code": error_code.encode("utf-8"),
            b"error_message": error_message.encode("utf-8"),
            b"attempts": str(attempts).encode("utf-8"),
            b"failed_at": now_iso.encode("utf-8"),
        }
        dlq_id = await self.redis.xadd(constants.STREAM_DOCUMENTS_DEAD, dlq_payload)
        dlq_id_str = dlq_id.decode("utf-8") if isinstance(dlq_id, bytes) else str(dlq_id)
        logger.info(
            "[%s] Published message %s to DLQ stream %s (id: %s)",
            doc_id,
            original_msg_id,
            constants.STREAM_DOCUMENTS_DEAD,
            dlq_id_str,
        )
        return dlq_id_str
