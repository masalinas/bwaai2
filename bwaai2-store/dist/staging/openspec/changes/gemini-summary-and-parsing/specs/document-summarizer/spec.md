# Spec Delta

## Purpose

Generates a single consolidated document summary from extracted pages using context budgeting, map-reduce chunking, and language preservation.

## ADDED Requirements

### Requirement: Consolidated Document Summarization
The summarizer service SHALL generate exactly one concise summary for a document using its extracted pages, preserving the primary language of the document.

#### Scenario: Single-pass summarization within context budget
- **WHEN** the combined text of all document pages is within the configured character budget
- **THEN** a single Gemini summarization request is made and the generated summary is returned

#### Scenario: Map-reduce summarization for large documents
- **WHEN** the combined text of all document pages exceeds the configured character budget
- **THEN** pages are summarized in chunks, and a final summary is generated from the intermediate summaries

### Requirement: Empty Extracted Text Rejection
When document pages contain no extractable text content (such as purely scanned PDFs parsed with PyPDF), the summarizer SHALL raise `SummaryFailedError` with a message advising the client to utilize the `gemini` multimodal parser.

#### Scenario: Empty text content detected
- **WHEN** all page contents in a document consist solely of whitespace
- **THEN** the summarizer raises an error with code "SUMMARY_FAILED" and suggestion to use parser "gemini"
