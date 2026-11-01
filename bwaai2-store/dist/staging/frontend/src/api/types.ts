import type { components, operations, paths } from './schema';

export type Paths = paths;
export type Operations = operations;

// Schema Component Types
export type DocumentStatus = components['schemas']['DocumentStatus'];
export type ParserType = components['schemas']['ParserType'];
export type ContentFormat = components['schemas']['ContentFormat'];
export type DocumentUploadItem = components['schemas']['DocumentUploadItem'];
export type DocumentDetailResponse = components['schemas']['DocumentDetailResponse'];
export type DocumentStatusResponse = components['schemas']['DocumentStatusResponse'];
export type DocumentListResponse = components['schemas']['DocumentListResponse'];
export type DocumentPage = components['schemas']['DocumentPage'];
export type ApiErrorSchema = components['schemas']['Error'];
export type ErrorCode = components['schemas']['ErrorCode'];
export type HealthResponse = components['schemas']['HealthResponse'];
