from redis.asyncio import Redis

from app.core import constants
from app.core.logging import logger
from app.models.documents import ParserType
from app.services.storage import get_redis_client


class QueueProducer:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis or get_redis_client()

    async def enqueue_document_job(self, document_id: str, parser: ParserType) -> str:
        """Publishes a document processing job to Redis Stream."""
        message = {
            b"document_id": document_id.encode("utf-8"),
            b"parser": parser.value.encode("utf-8"),
        }
        msg_id = await self.redis.xadd(
            constants.STREAM_DOCUMENTS_JOBS,
            message,
        )
        msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
        logger.info(
            "Enqueued job for document %s with parser %s to stream %s (id: %s)",
            document_id,
            parser.value,
            constants.STREAM_DOCUMENTS_JOBS,
            msg_id_str,
        )
        return msg_id_str
