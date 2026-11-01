from app.core.config import settings
from app.core.exceptions import SummaryFailedError
from app.core.logging import logger
from app.models.documents import DocumentPage
from app.services.gemini import GeminiService

CHUNK_SIZE_CHARS = 50_000


class DocumentSummarizer:
    def __init__(self, gemini_service: GeminiService | None = None) -> None:
        self.gemini_service = gemini_service or GeminiService()

    async def summarize_document(self, pages: list[DocumentPage]) -> str:
        # Pre-flight check for API key configuration
        if type(self.gemini_service) is GeminiService and not self.gemini_service.api_key:
            raise SummaryFailedError(
                message="Gemini summarizer is not configured: GEMINI_API_KEY is not set.",
                details={"service": "gemini_summarizer"},
            )

        # 1. Inspect combined text across all pages
        valid_sections = [
            f"--- Page {p.page_number} ---\n{p.content.strip()}"
            for p in pages
            if p.content and p.content.strip()
        ]

        if not valid_sections:
            logger.warning("Document contains 0 characters of text; rejecting summarization")
            raise SummaryFailedError(
                message="Document contains no extractable text. Please re-upload using the 'gemini' multimodal parser.",
                details={"reason": "empty_extracted_text"},
            )

        full_text = "\n\n".join(valid_sections)
        total_chars = len(full_text)
        max_budget = settings.SUMMARY_MAX_INPUT_CHARS

        logger.info(
            "Summarizing document (%d pages, %d characters, budget: %d)",
            len(pages),
            total_chars,
            max_budget,
        )

        # 2. Check if text fits in single-pass context budget
        if total_chars <= max_budget:
            return await self._single_pass_summary(full_text)
        else:
            return await self._map_reduce_summary(valid_sections)

    async def _single_pass_summary(self, full_text: str) -> str:
        prompt = (
            "You are an expert executive summarizer. Analyze the following document text and produce a concise, "
            "comprehensive summary highlighting key points, decisions, metrics, and takeaways.\n"
            "CRITICAL LANGUAGE RULE: Write the summary in the PRIMARY LANGUAGE of the document itself "
            "(e.g., if the document is in Spanish, output Spanish; if English, output English).\n\n"
            f"DOCUMENT CONTENT:\n{full_text}"
        )
        response = await self.gemini_service.generate_content(contents=prompt)
        summary = (response.text or "").strip()
        if not summary:
            raise SummaryFailedError(message="Gemini returned an empty summary response.")
        return summary

    async def _map_reduce_summary(self, sections: list[str]) -> str:
        logger.info("Document exceeds single-pass budget; executing map-reduce summarization")

        # Group sections into chunks of ~50,000 characters
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_length = 0

        for section in sections:
            sec_len = len(section)
            if current_length + sec_len > CHUNK_SIZE_CHARS and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [section]
                current_length = sec_len
            else:
                current_chunk.append(section)
                current_length += sec_len

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        logger.info("Split document into %d map-reduce chunks", len(chunks))

        # Map phase: summarize each chunk
        intermediate_summaries: list[str] = []
        for idx, chunk in enumerate(chunks):
            map_prompt = (
                f"You are summarizing section {idx + 1} of {len(chunks)} of a large document. "
                "Synthesize the key points and findings concisely in the document's primary language:\n\n"
                f"{chunk}"
            )
            resp = await self.gemini_service.generate_content(contents=map_prompt)
            intermediate_summaries.append((resp.text or "").strip())

        # Reduce phase: synthesize final summary
        combined_intermediates = "\n\n".join(
            f"--- Section {i + 1} Summary ---\n{s}" for i, s in enumerate(intermediate_summaries)
        )
        reduce_prompt = (
            "You are synthesizing multiple section summaries of a document into one final, coherent, "
            "executive summary. Remove redundancies, unify tone, and highlight the most vital findings.\n"
            "CRITICAL LANGUAGE RULE: Output the final summary in the primary language of the document.\n\n"
            f"INTERMEDIATE SUMMARIES:\n{combined_intermediates}"
        )
        final_resp = await self.gemini_service.generate_content(contents=reduce_prompt)
        final_summary = (final_resp.text or "").strip()

        if not final_summary:
            raise SummaryFailedError(
                message="Map-reduce summarization produced empty final summary."
            )
        return final_summary
