# Spec Delta

## Purpose

Enables multimodal Gemini PDF-to-Markdown document parsing using structured JSON schema extraction and page-count verification against PyPDF.

## ADDED Requirements

### Requirement: Structured Multimodal Gemini Parsing
The `GeminiParser` SHALL send PDF binary bytes to Gemini using structured output schemas returning a list of page objects with 1-indexed `page_number`, markdown `content`, and format set to `markdown`.

#### Scenario: Successful Gemini Markdown parsing
- **WHEN** valid PDF bytes are processed by GeminiParser
- **THEN** it returns structured DocumentPage objects containing page numbers and markdown formatting

### Requirement: Page Count Validation and Retry
The parser SHALL compare the number of pages returned by Gemini against the ground-truth page count obtained via PyPDF. If the count differs, it MUST retry the extraction once; if the mismatch persists, it SHALL raise `ParserFailedError`.

#### Scenario: Page count matches on first attempt
- **WHEN** Gemini returns the exact number of pages detected by PyPDF
- **THEN** the parsed pages are accepted without retry

#### Scenario: Page count mismatch retried and resolved
- **WHEN** Gemini initially returns fewer pages than PyPDF detects, but matches on the second attempt
- **THEN** the second result is accepted

#### Scenario: Persistent page count mismatch
- **WHEN** Gemini returns mismatched page counts on both attempts
- **THEN** the parser raises `ParserFailedError` with error code "PARSER_FAILED"
