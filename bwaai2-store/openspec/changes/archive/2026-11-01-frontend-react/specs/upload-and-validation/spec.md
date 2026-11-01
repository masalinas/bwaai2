# Spec: Upload and Validation

## Purpose

Defines user interface behaviors for uploading PDF files, selecting a parser, and performing client-side validation against contract-mandated constraints.

## ADDED Requirements

### Requirement: Drag-and-Drop and File Picker Upload
The UI SHALL provide an upload zone supporting drag-and-drop and standard file picker input for 1 to 10 files.

#### Scenario: User drops valid PDF files
- **WHEN** the user drops one or more valid PDF files (`.pdf` extension, MIME type `application/pdf`)
- **THEN** the files are added to the pending upload queue and displayed with name and file size

### Requirement: Client-Side Validation
The UI SHALL validate files before submission against contract constraints:
1. File type MUST be `application/pdf`.
2. File size MUST NOT exceed 25 MB (26,214,400 bytes).
3. Batch count MUST NOT exceed 10 files.

#### Scenario: Non-PDF file rejected
- **WHEN** the user attempts to upload a non-PDF file (e.g. `report.docx` or `image.png`)
- **THEN** the UI rejects the file and displays an error message indicating that only PDF files are supported

#### Scenario: File exceeding maximum size rejected
- **WHEN** the user attempts to upload a PDF file exceeding 25 MB
- **THEN** the UI rejects the file and displays an error message showing the 25 MB limit

#### Scenario: More than 10 files rejected
- **WHEN** the user attempts to upload more than 10 files simultaneously
- **THEN** the UI warns the user and restricts the batch to a maximum of 10 files

### Requirement: Parser Selection
The UI SHALL offer a parser selector containing the options defined in the contract (`pypdf`, `gemini`, `mistral`), defaulting to `pypdf`. Parsers designated in `DISABLED_PARSERS` SHALL be visually disabled with an explanatory tooltip or badge.

#### Scenario: Default parser selection
- **WHEN** the user views the upload interface
- **THEN** `pypdf` is selected by default

#### Scenario: Disabled parser cannot be submitted
- **WHEN** a parser is listed in `DISABLED_PARSERS` (such as `mistral`)
- **THEN** the option cannot be selected or submitted

### Requirement: Submission and Optimistic List Addition
Upon clicking Submit, the UI SHALL issue `POST /documents` with `multipart/form-data` containing `files[]` and `parser`. On a `202 Accepted` response, the returned items SHALL be added immediately to the document list in `queued` status.

#### Scenario: Successful upload batch submission
- **WHEN** the user submits 2 valid PDF files
- **THEN** the API returns 202 with 2 document records, which immediately appear in the document list as "Queued"

#### Scenario: Graceful handling of PARSER_UNAVAILABLE
- **WHEN** the upload request fails due to `PARSER_UNAVAILABLE`
- **THEN** the UI displays the server error message and remains fully usable without crashing
