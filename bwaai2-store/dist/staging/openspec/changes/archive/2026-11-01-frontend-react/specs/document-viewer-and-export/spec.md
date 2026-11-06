# Spec: Document Viewer and Export

## Purpose

Defines user interface behaviors for inspecting document details, rendering per-page text or markdown, displaying the executive summary, and exporting content.

## ADDED Requirements

### Requirement: Document Selection and Detail Fetching
When a user selects a document from the list, the UI SHALL fetch `GET /documents/{document_id}` and render its details.

#### Scenario: User selects a completed document
- **WHEN** the user selects a document with status `done`
- **THEN** the viewer loads the executive summary and parsed pages

### Requirement: Early Page Display During Summarization
When a document has status `summarizing`, the UI SHALL display the extracted pages immediately, alongside a placeholder indicating that the summary is being generated.

#### Scenario: Viewing document in summarizing status
- **WHEN** the user inspects a document currently in `summarizing` status
- **THEN** the viewer renders the extracted pages and displays a loading card for the pending summary

### Requirement: Content Rendering (Markdown vs Text)
The UI SHALL render each page according to its `format` property:
- If format is `markdown`, content SHALL be rendered via `react-markdown` with GFM support.
- If format is `text`, content SHALL be rendered in a preformatted monospace block preserving whitespace.

#### Scenario: Gemini markdown page rendering
- **WHEN** viewing a page produced by Gemini (`format: markdown`)
- **THEN** headings, tables, bold text, and lists are formatted as HTML

#### Scenario: PyPDF plain text page rendering
- **WHEN** viewing a page produced by PyPDF (`format: text`)
- **THEN** plain text is rendered preserving line breaks and spacing

### Requirement: Page Navigation
When a document contains multiple pages, the UI SHALL provide page navigation controls (previous page, next page, and current page / total pages indicator).

#### Scenario: Navigating between pages
- **WHEN** the user clicks "Next Page"
- **THEN** the viewer switches from page 1 to page 2

### Requirement: Error Display with Page Retention
When a document has status `failed`, the UI SHALL render an error message containing the `code` and `message`. If `pages` are present in the response (e.g., failure occurred during summarization), the pages SHALL remain viewable.

#### Scenario: Failed summarization keeps pages
- **WHEN** a document failed with code `SUMMARY_FAILED` after parsing completed
- **THEN** the error is prominently displayed, and the extracted pages are still readable

### Requirement: Copy and Export Actions
The UI SHALL provide action buttons:
1. **Copy Summary**: Copies the executive summary text to the clipboard with visual confirmation.
2. **Download Markdown**: Generates and downloads a `.md` file containing the summary and all pages.

#### Scenario: Copy summary to clipboard
- **WHEN** the user clicks "Copy Summary"
- **THEN** the text is copied to clipboard and a brief confirmation state is shown

#### Scenario: Download full markdown
- **WHEN** the user clicks "Download Markdown"
- **THEN** the browser downloads `{document_id}_{filename}.md` containing the summary and all pages
