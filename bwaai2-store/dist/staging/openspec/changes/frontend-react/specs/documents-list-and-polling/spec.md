# Spec: Documents List and Polling

## Purpose

Defines user interface behaviors for listing uploaded documents, managing cursor pagination, and polling non-terminal jobs using TanStack Query.

## ADDED Requirements

### Requirement: Document Listing and Ordering
The UI SHALL query `GET /documents` to display the history of uploaded documents, ordered with the newest documents first. Each item SHALL display its filename, parser badge, status badge, and creation timestamp.

#### Scenario: Displaying document list
- **WHEN** the document list loads
- **THEN** it renders all documents with their filename, parser tag, status badge, and formatted timestamp

### Requirement: Pagination (Load More)
The UI SHALL support cursor-based pagination matching the contract (`cursor` and `has_more` fields). If `has_more` is true, a "Load More" button SHALL be rendered.

#### Scenario: Loading additional documents
- **WHEN** the user clicks "Load More"
- **THEN** the UI requests the next page using the `cursor` parameter and appends the new items to the list

### Requirement: Status Lifecycle Badges
The UI SHALL display distinct, accessible visual badges for each status:
- `queued`: Amber badge
- `processing`: Blue badge with activity indicator
- `summarizing`: Purple badge with pulse indicator
- `done`: Emerald badge with checkmark icon
- `failed`: Rose/Crimson badge with alert icon

#### Scenario: Visual status differentiation
- **WHEN** a document transitions from `processing` to `summarizing` to `done`
- **THEN** the badge color, icon, and text update accordingly with an `aria-live` announcement

### Requirement: TanStack Query Polling
For each document with a non-terminal status (`queued`, `processing`, `summarizing`), the UI SHALL poll `GET /documents/{document_id}/status` periodically:
1. Default interval is 2,000 milliseconds.
2. If the API response includes a `Retry-After` header, that duration SHALL be used for the next poll.
3. Polling SHALL stop immediately when status reaches `done` or `failed`.
4. Polling SHALL pause when the browser tab is hidden.

#### Scenario: Transition through status lifecycle
- **WHEN** a newly uploaded document is polled
- **THEN** status updates from `queued` to `processing` to `summarizing` and finally stops at `done`

#### Scenario: Polling halts on terminal state
- **WHEN** a document status becomes `done` or `failed`
- **THEN** polling for that document ceases
