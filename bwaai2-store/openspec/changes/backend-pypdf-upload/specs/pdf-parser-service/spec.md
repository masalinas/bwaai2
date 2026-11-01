# Spec Delta

## Purpose

Defines the pluggable `Parser` abstraction and the CPU-offloaded PyPDF extraction service for page-by-page text parsing.

## ADDED Requirements

### Requirement: Pluggable Parser Interface
The backend SHALL implement a unified `Parser` interface with an asynchronous `parse(pdf_bytes: bytes) -> list[Page]` method, allowing multiple parser engines to be substituted transparently.

#### Scenario: Interface contract adherence
- **WHEN** a parser implementation executes its parse method
- **THEN** it returns a list of Page objects with 1-indexed page_number, content string, and format indicator

### Requirement: PyPDF Text Extraction Off Event Loop
The `PyPDFParser` service SHALL execute PDF reading and page text extraction off the main asyncio event loop using `asyncio.to_thread`, detecting encrypted PDFs and emitting structured page results with `format: "text"`.

#### Scenario: Successful multi-page text parsing
- **WHEN** valid PDF bytes are provided to `PyPDFParser.parse()`
- **THEN** it returns Page objects for each page with extracted text and format "text"

#### Scenario: Encrypted PDF encountered during parsing
- **WHEN** password-protected PDF bytes are passed to `PyPDFParser.parse()`
- **THEN** it raises an `EncryptedPDFError` indicating password protection
