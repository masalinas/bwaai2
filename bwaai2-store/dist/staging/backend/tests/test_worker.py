import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core import constants
from app.core.config import settings
from app.core.exceptions import (
    ParserFailedError,
    ParserRateLimitedError,
    SummaryRateLimitedError,
)
from app.models.documents import ContentFormat, DocumentPage
from app.services.parsers.pypdf_parser import PyPDFParser
from app.services.summarizer import DocumentSummarizer
from app.worker.autoclaim import AutoClaimer
from app.worker.consumer import StreamConsumer
from tests.conftest import create_sample_encrypted_pdf, create_sample_pdf


@pytest.mark.asyncio
async def test_worker_happy_path(client: AsyncClient, fake_redis) -> None:
    # 1. Upload valid PDF
    pdf_bytes = create_sample_pdf(num_pages=2)
    files = [("files", ("annual_report.pdf", pdf_bytes, "application/pdf"))]
    post_resp = await client.post("/documents", files=files)
    assert post_resp.status_code == 202
    doc_id = post_resp.json()[0]["document_id"]

    # 2. Mock summarizer so test runs offline
    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-1")
    await consumer.init_group()

    with patch.object(
        consumer.processor.summarizer,
        "summarize_document",
        new_callable=AsyncMock,
        return_value="Executive summary of the annual report.",
    ):
        processed_count = await consumer.read_and_process_batch()
        assert processed_count == 1
        await consumer.drain_in_flight()

    # 3. Verify document transitioned to done with both pages and summary
    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["status"] == "done"
    assert doc_data["pages"] is not None
    assert len(doc_data["pages"]) == 2
    assert doc_data["summary"] == "Executive summary of the annual report."
    assert doc_data["error"] is None

    # 4. Verify message was acknowledged in stream
    pending = await fake_redis.xpending(
        constants.STREAM_DOCUMENTS_JOBS, constants.GROUP_DOCUMENTS_WORKERS
    )
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_worker_gemini_parser_happy_path(client: AsyncClient, fake_redis) -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    files = [("files", ("multimodal.pdf", pdf_bytes, "application/pdf"))]
    post_resp = await client.post("/documents", files=files, data={"parser": "gemini"})
    assert post_resp.status_code == 202
    doc_id = post_resp.json()[0]["document_id"]

    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-gemini")
    await consumer.init_group()

    mock_pages = [
        DocumentPage(
            page_number=1, content="# Heading 1\n\nContent", format=ContentFormat.markdown
        ),
        DocumentPage(page_number=2, content="# Heading 2\n\nTables", format=ContentFormat.markdown),
    ]

    with (
        patch.object(
            consumer.processor.gemini_parser,
            "parse",
            new_callable=AsyncMock,
            return_value=mock_pages,
        ),
        patch.object(
            consumer.processor.summarizer,
            "summarize_document",
            new_callable=AsyncMock,
            return_value="Summary from Gemini markdown pages.",
        ),
    ):
        await consumer.read_and_process_batch()
        await consumer.drain_in_flight()

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["status"] == "done"
    assert doc_data["parser"] == "gemini"
    assert len(doc_data["pages"]) == 2
    assert doc_data["pages"][0]["format"] == "markdown"
    assert doc_data["summary"] == "Summary from Gemini markdown pages."


@pytest.mark.asyncio
async def test_worker_mistral_parser_happy_path(client: AsyncClient, fake_redis) -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    files = [("files", ("multimodal_mistral.pdf", pdf_bytes, "application/pdf"))]
    with patch.object(settings, "MISTRAL_API_KEY", "valid-key"):
        post_resp = await client.post("/documents", files=files, data={"parser": "mistral"})
        assert post_resp.status_code == 202
        doc_id = post_resp.json()[0]["document_id"]

    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-mistral")
    await consumer.init_group()

    mock_pages = [
        DocumentPage(
            page_number=1, content="# Mistral Page 1\n\nContent", format=ContentFormat.markdown
        ),
        DocumentPage(
            page_number=2, content="# Mistral Page 2\n\nTables", format=ContentFormat.markdown
        ),
    ]

    with (
        patch.object(
            consumer.processor.mistral_parser,
            "parse",
            new_callable=AsyncMock,
            return_value=mock_pages,
        ),
        patch.object(
            consumer.processor.summarizer,
            "summarize_document",
            new_callable=AsyncMock,
            return_value="Summary from Mistral OCR pages.",
        ),
    ):
        await consumer.read_and_process_batch()
        await consumer.drain_in_flight()

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["status"] == "done"
    assert doc_data["parser"] == "mistral"
    assert len(doc_data["pages"]) == 2
    assert doc_data["pages"][0]["format"] == "markdown"
    assert doc_data["summary"] == "Summary from Mistral OCR pages."


@pytest.mark.asyncio
async def test_worker_corrupt_or_encrypted_pdf(client: AsyncClient, fake_redis) -> None:
    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-err")
    await consumer.init_group()

    doc_id = "doc_test_encrypted"
    encrypted_bytes = create_sample_encrypted_pdf("secret")
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), encrypted_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"secret.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    pipe.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"pypdf"},
    )
    await pipe.execute()

    await consumer.read_and_process_batch()
    await consumer.drain_in_flight()

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["status"] == "failed"
    assert doc_data["error"]["code"] == "ENCRYPTED_PDF"

    # Verify routed to DLQ stream
    dlq_entries = await fake_redis.xrange(constants.STREAM_DOCUMENTS_DEAD)
    assert len(dlq_entries) == 1
    assert dlq_entries[0][1][b"error_code"] == b"ENCRYPTED_PDF"


@pytest.mark.asyncio
async def test_worker_unsupported_parser_rejection(client: AsyncClient, fake_redis) -> None:
    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-mistral")
    await consumer.init_group()

    doc_id = "doc_test_mistral"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"doc.pdf",
            b"parser": b"mistral",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    pipe.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"mistral"},
    )
    await pipe.execute()

    await consumer.read_and_process_batch()
    await consumer.drain_in_flight()

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["status"] == "failed"
    assert doc_data["error"]["code"] == "PARSER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_worker_mistral_parser_rate_limit_and_exhaustion(
    client: AsyncClient, fake_redis
) -> None:
    doc_id = "doc_mistral_429"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"doc.pdf",
            b"parser": b"mistral",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    pipe.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"mistral"},
    )
    await pipe.execute()

    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-mistral-429")
    processor = consumer.processor

    with patch.object(
        processor.mistral_parser,
        "parse",
        side_effect=ParserRateLimitedError("Mistral rate limit 429"),
    ):
        # Attempt 1: Transient -> left unacknowledged
        await processor.process_message(
            msg_id="1-0",
            fields={"document_id": doc_id, "parser": "mistral"},
            consumer_name="worker-1",
            delivery_count=1,
        )
        get_mid = await client.get(f"/documents/{doc_id}")
        assert get_mid.json()["status"] == "processing"

        # Attempt 3: Exhausted -> marks failed with PARSER_FAILED
        await processor.process_message(
            msg_id="1-0",
            fields={"document_id": doc_id, "parser": "mistral"},
            consumer_name="worker-1",
            delivery_count=settings.MAX_ATTEMPTS,
        )

        get_final = await client.get(f"/documents/{doc_id}")
        assert get_final.json()["status"] == "failed"
        assert get_final.json()["error"]["code"] == "PARSER_FAILED"

        dlq_entries = await fake_redis.xrange(constants.STREAM_DOCUMENTS_DEAD)
        assert len(dlq_entries) == 1
        assert dlq_entries[0][1][b"error_code"] == b"PARSER_FAILED"


@pytest.mark.asyncio
async def test_worker_mistral_permanent_4xx_no_retries(client: AsyncClient, fake_redis) -> None:
    doc_id = "doc_mistral_4xx"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"doc.pdf",
            b"parser": b"mistral",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    pipe.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"mistral"},
    )
    await pipe.execute()

    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-mistral-4xx")
    processor = consumer.processor

    with patch.object(
        processor.mistral_parser,
        "parse",
        side_effect=ParserFailedError("Invalid document (422)"),
    ):
        await processor.process_message(
            msg_id="1-0",
            fields={"document_id": doc_id, "parser": "mistral"},
            consumer_name="worker-1",
            delivery_count=1,
        )

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.json()["status"] == "failed"
    assert get_resp.json()["error"]["code"] == "PARSER_FAILED"

    dlq_entries = await fake_redis.xrange(constants.STREAM_DOCUMENTS_DEAD)
    assert len(dlq_entries) == 1


@pytest.mark.asyncio
async def test_worker_summarization_rate_limit_retry_and_exhaustion(
    client: AsyncClient, fake_redis
) -> None:
    consumer = StreamConsumer(redis=fake_redis, consumer_name="test-worker-429")
    await consumer.init_group()

    doc_id = "doc_rate_limit_test"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"doc.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    pipe.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"pypdf"},
    )
    await pipe.execute()

    processor = consumer.processor

    # Mock summarizer raising 429 rate limit
    with patch.object(
        processor.summarizer,
        "summarize_document",
        side_effect=SummaryRateLimitedError("Rate limit 429"),
    ):
        # Attempt 1: Transient -> leaves unacked
        await processor.process_message(
            msg_id="1-0",
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-1",
            delivery_count=1,
        )
        # Verify status reached summarizing and pages were preserved
        get_mid = await client.get(f"/documents/{doc_id}")
        assert get_mid.json()["status"] == "summarizing"
        assert get_mid.json()["pages"] is not None
        assert len(get_mid.json()["pages"]) == 1

        # Attempt 3: Exhausted -> marks failed with SUMMARY_RATE_LIMITED
        await processor.process_message(
            msg_id="1-0",
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-1",
            delivery_count=settings.MAX_ATTEMPTS,
        )

        get_final = await client.get(f"/documents/{doc_id}")
        assert get_final.json()["status"] == "failed"
        assert get_final.json()["error"]["code"] == "SUMMARY_RATE_LIMITED"
        # PAGES MUST BE PRESERVED!
        assert get_final.json()["pages"] is not None
        assert len(get_final.json()["pages"]) == 1

        dlq_entries = await fake_redis.xrange(constants.STREAM_DOCUMENTS_DEAD)
        assert len(dlq_entries) == 1
        assert dlq_entries[0][1][b"error_code"] == b"SUMMARY_RATE_LIMITED"


@pytest.mark.asyncio
async def test_worker_retry_skips_parsing_stage(client: AsyncClient, fake_redis) -> None:
    doc_id = "doc_resume_test"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"resume.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    await pipe.execute()

    consumer = StreamConsumer(redis=fake_redis, consumer_name="worker-resume")
    processor = consumer.processor

    # Attempt 1: Parser succeeds, summarizer fails transiently
    with patch.object(
        processor.summarizer,
        "summarize_document",
        side_effect=SummaryRateLimitedError("429 rate limit"),
    ):
        await processor.process_message(
            msg_id="2-0",
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-resume",
            delivery_count=1,
        )

    # Verify pages are saved in Redis
    assert await fake_redis.get(constants.doc_pages_key(doc_id)) is not None

    # Attempt 2: If parser is called, raise an error to prove it was skipped!
    with (
        patch.object(
            PyPDFParser, "parse", side_effect=AssertionError("Parser should not be re-run!")
        ),
        patch.object(
            processor.summarizer,
            "summarize_document",
            new_callable=AsyncMock,
            return_value="Resumed summary",
        ),
    ):
        await processor.process_message(
            msg_id="2-0",
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-resume",
            delivery_count=2,
        )

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.json()["status"] == "done"
    assert get_resp.json()["summary"] == "Resumed summary"


@pytest.mark.asyncio
async def test_worker_empty_text_fails_with_summary_failed(client: AsyncClient, fake_redis) -> None:
    doc_id = "doc_empty_text"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    pipe = fake_redis.pipeline(transaction=True)
    pipe.set(constants.doc_file_key(doc_id), pdf_bytes)
    pipe.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"scanned.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    await pipe.execute()

    consumer = StreamConsumer(redis=fake_redis, consumer_name="worker-empty")
    processor = consumer.processor

    # Mock empty text pages
    empty_pages = [DocumentPage(page_number=1, content="", format=ContentFormat.text)]
    with patch.object(
        processor.pypdf_parser, "parse", new_callable=AsyncMock, return_value=empty_pages
    ):
        await processor.process_message(
            msg_id="3-0",
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-empty",
            delivery_count=1,
        )

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.json()["status"] == "failed"
    assert get_resp.json()["error"]["code"] == "SUMMARY_FAILED"
    assert "gemini" in get_resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_worker_autoclaim_crashed_worker(fake_redis) -> None:
    consumer_crashed = StreamConsumer(redis=fake_redis, consumer_name="crashed-worker")
    await consumer_crashed.init_group()

    doc_id = "doc_autoclaim_test"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    await fake_redis.set(constants.doc_file_key(doc_id), pdf_bytes)
    await fake_redis.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"claim.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    await fake_redis.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"pypdf"},
    )

    # Crashed worker reads message but crashes
    await fake_redis.xreadgroup(
        groupname=constants.GROUP_DOCUMENTS_WORKERS,
        consumername="crashed-worker",
        streams={constants.STREAM_DOCUMENTS_JOBS: ">"},
        count=1,
    )

    # Live worker runs autoclaim
    with (
        patch.object(settings, "CLAIM_IDLE_MS", 0),
        patch.object(
            DocumentSummarizer,
            "summarize_document",
            new_callable=AsyncMock,
            return_value="Claimed summary",
        ),
    ):
        consumer_healthy = StreamConsumer(redis=fake_redis, consumer_name="healthy-worker")
        autoclaimer = AutoClaimer(
            redis=fake_redis,
            consumer_name="healthy-worker",
            processor=consumer_healthy.processor,
            semaphore=consumer_healthy.semaphore,
        )

        claimed_count = await autoclaimer.sweep_once()
        assert claimed_count == 1

        await asyncio.sleep(0.05)
        meta = await fake_redis.hgetall(constants.doc_key(doc_id))
        assert meta[b"status"] == b"done"


@pytest.mark.asyncio
async def test_two_workers_parallel_consumption(client: AsyncClient, fake_redis) -> None:
    consumer_1 = StreamConsumer(redis=fake_redis, consumer_name="worker-alpha")
    consumer_2 = StreamConsumer(redis=fake_redis, consumer_name="worker-beta")
    await consumer_1.init_group()

    pdf_bytes = create_sample_pdf(1)
    files = [("files", (f"multi_{i}.pdf", pdf_bytes, "application/pdf")) for i in range(4)]
    resp = await client.post("/documents", files=files)
    assert resp.status_code == 202
    doc_ids = [item["document_id"] for item in resp.json()]

    with patch.object(
        DocumentSummarizer,
        "summarize_document",
        new_callable=AsyncMock,
        return_value="Concurrent summary",
    ):
        results = await asyncio.gather(
            consumer_1.read_and_process_batch(),
            consumer_2.read_and_process_batch(),
        )
        await asyncio.gather(
            consumer_1.drain_in_flight(),
            consumer_2.drain_in_flight(),
        )

    assert sum(results) == 4

    for doc_id in doc_ids:
        meta = await fake_redis.hgetall(constants.doc_key(doc_id))
        assert meta[b"status"] == b"done"


@pytest.mark.asyncio
async def test_worker_repeated_crashes_route_to_dlq(fake_redis) -> None:
    """Test that 3 successive worker crashes cause the 4th delivery to immediately route to DLQ."""
    consumer = StreamConsumer(redis=fake_redis, consumer_name="worker-crash-test")
    await consumer.init_group()

    doc_id = "doc_poison_pill"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    await fake_redis.set(constants.doc_file_key(doc_id), pdf_bytes)
    await fake_redis.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"poison.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    msg_id = await fake_redis.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"pypdf"},
    )
    msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

    # 1st attempt: worker 1 reads message from stream, then crashes abruptly
    await fake_redis.xreadgroup(
        groupname=constants.GROUP_DOCUMENTS_WORKERS,
        consumername="crashed-worker-1",
        streams={constants.STREAM_DOCUMENTS_JOBS: ">"},
        count=1,
    )
    p = await fake_redis.xpending_range(
        constants.STREAM_DOCUMENTS_JOBS,
        constants.GROUP_DOCUMENTS_WORKERS,
        min=msg_id_str,
        max=msg_id_str,
        count=1,
    )
    assert p[0]["times_delivered"] == 1

    # 2nd attempt: worker 2 autoclaims message, then crashes abruptly
    await fake_redis.xautoclaim(
        name=constants.STREAM_DOCUMENTS_JOBS,
        groupname=constants.GROUP_DOCUMENTS_WORKERS,
        consumername="crashed-worker-2",
        min_idle_time=0,
        start_id="0-0",
        count=1,
    )
    p = await fake_redis.xpending_range(
        constants.STREAM_DOCUMENTS_JOBS,
        constants.GROUP_DOCUMENTS_WORKERS,
        min=msg_id_str,
        max=msg_id_str,
        count=1,
    )
    assert p[0]["times_delivered"] == 2

    # 3rd attempt: worker 3 autoclaims message, then crashes abruptly
    await fake_redis.xautoclaim(
        name=constants.STREAM_DOCUMENTS_JOBS,
        groupname=constants.GROUP_DOCUMENTS_WORKERS,
        consumername="crashed-worker-3",
        min_idle_time=0,
        start_id="0-0",
        count=1,
    )
    p = await fake_redis.xpending_range(
        constants.STREAM_DOCUMENTS_JOBS,
        constants.GROUP_DOCUMENTS_WORKERS,
        min=msg_id_str,
        max=msg_id_str,
        count=1,
    )
    assert p[0]["times_delivered"] == 3

    # 4th attempt: live worker autoclaims and processes with delivery_count > MAX_ATTEMPTS (3)
    live_consumer = StreamConsumer(redis=fake_redis, consumer_name="live-worker")
    autoclaimer = AutoClaimer(
        redis=fake_redis,
        consumer_name="live-worker",
        processor=live_consumer.processor,
        semaphore=live_consumer.semaphore,
    )

    mock_parse = AsyncMock()
    with patch.object(live_consumer.processor.pypdf_parser, "parse", mock_parse):
        with patch.object(settings, "CLAIM_IDLE_MS", 0):
            claimed = await autoclaimer.sweep_once()
            assert claimed == 1

        # Give async task time to run
        await asyncio.sleep(0.05)

        # Verify parser was NEVER called on the 4th attempt
        mock_parse.assert_not_called()

        # Verify document status is failed with PARSER_FAILED
        meta = await fake_redis.hgetall(constants.doc_key(doc_id))
        assert meta[b"status"] == b"failed"
        error_data = meta[b"error"].decode("utf-8")
        assert "PARSER_FAILED" in error_data
        assert "3 attempts" in error_data

        # Verify DLQ received the poison pill message
        dlq_entries = await fake_redis.xrange(constants.STREAM_DOCUMENTS_DEAD)
        assert len(dlq_entries) == 1
        dlq_fields = dlq_entries[0][1]
        assert dlq_fields[b"document_id"] == doc_id.encode("utf-8")
        assert dlq_fields[b"error_code"] == b"PARSER_FAILED"
        assert dlq_fields[b"attempts"] == b"4"

        # Verify message was acknowledged in the jobs stream
        pending_after = await fake_redis.xpending_range(
            constants.STREAM_DOCUMENTS_JOBS,
            constants.GROUP_DOCUMENTS_WORKERS,
            min=msg_id_str,
            max=msg_id_str,
            count=1,
        )
        assert len(pending_after) == 0


@pytest.mark.asyncio
async def test_worker_long_running_job_lease_prevents_duplicate_processing(fake_redis) -> None:
    """Test that distributed locking and lease renewal prevent a secondary worker from duplicating a slow job."""
    consumer_1 = StreamConsumer(redis=fake_redis, consumer_name="worker-1")
    await consumer_1.init_group()

    doc_id = "doc_slow_processing"
    pdf_bytes = create_sample_pdf(1)
    now_iso = datetime.now(UTC).isoformat()

    await fake_redis.set(constants.doc_file_key(doc_id), pdf_bytes)
    await fake_redis.hset(
        constants.doc_key(doc_id),
        mapping={
            b"document_id": doc_id.encode("utf-8"),
            b"filename": b"slow.pdf",
            b"parser": b"pypdf",
            b"status": b"queued",
            b"created_at": now_iso.encode("utf-8"),
            b"updated_at": now_iso.encode("utf-8"),
            b"error": b"",
        },
    )
    msg_id = await fake_redis.xadd(
        constants.STREAM_DOCUMENTS_JOBS,
        {b"document_id": doc_id.encode("utf-8"), b"parser": b"pypdf"},
    )
    msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

    worker_1_started = asyncio.Event()
    worker_1_can_finish = asyncio.Event()
    parse_call_count = 0

    async def slow_parse(raw_bytes: bytes) -> list[DocumentPage]:
        nonlocal parse_call_count
        parse_call_count += 1
        worker_1_started.set()
        await worker_1_can_finish.wait()
        return [DocumentPage(page_number=1, content="Parsed text", format=ContentFormat.text)]

    consumer_2 = StreamConsumer(redis=fake_redis, consumer_name="worker-2")
    autoclaimer_2 = AutoClaimer(
        redis=fake_redis,
        consumer_name="worker-2",
        processor=consumer_2.processor,
        semaphore=consumer_2.semaphore,
    )

    with (
        patch.object(consumer_1.processor.pypdf_parser, "parse", side_effect=slow_parse),
        patch.object(
            DocumentSummarizer,
            "summarize_document",
            new_callable=AsyncMock,
            return_value="Summary of slow doc",
        ),
    ):
        # Worker 1 reads the message from stream into its PEL
        res = await fake_redis.xreadgroup(
            groupname=constants.GROUP_DOCUMENTS_WORKERS,
            consumername="worker-1",
            streams={constants.STREAM_DOCUMENTS_JOBS: ">"},
            count=1,
        )
        assert len(res[0][1]) == 1

        # Worker 1 starts processing
        task_1 = asyncio.create_task(
            consumer_1.processor.process_message(
                msg_id=msg_id_str,
                fields={"document_id": doc_id, "parser": "pypdf"},
                consumer_name="worker-1",
                delivery_count=1,
            )
        )

        # Wait until Worker 1 is actively inside slow_parse
        await worker_1_started.wait()

        # Verify Worker 1 actively holds the distributed lock
        lock_val = await fake_redis.get(constants.doc_lock_key(doc_id))
        assert lock_val == b"worker-1"

        # Worker 2 sweeps via AutoClaimer (with CLAIM_IDLE_MS = 0)
        with patch.object(settings, "CLAIM_IDLE_MS", 0):
            # AutoClaimer claims the message in PEL, but skips dispatching because lock is held
            claimed = await autoclaimer_2.sweep_once()
            assert claimed == 1

        # Also test direct process_message attempt by Worker 2: it should abort because lock is held
        await consumer_2.processor.process_message(
            msg_id=msg_id_str,
            fields={"document_id": doc_id, "parser": "pypdf"},
            consumer_name="worker-2",
            delivery_count=2,
        )

        # Worker 2 did NOT call parser
        assert parse_call_count == 1

        # Release Worker 1 to complete processing
        worker_1_can_finish.set()
        await task_1

        # Verify pipeline succeeded
        meta = await fake_redis.hgetall(constants.doc_key(doc_id))
        assert meta[b"status"] == b"done"
        assert parse_call_count == 1

        # Lock was safely released in finally block
        lock_after = await fake_redis.exists(constants.doc_lock_key(doc_id))
        assert lock_after == 0
