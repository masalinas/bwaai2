import { ApiError } from './errors';
import type {
  DocumentDetailResponse,
  DocumentListResponse,
  DocumentStatusResponse,
  DocumentUploadItem,
  HealthResponse,
  ParserType,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      try {
        body = await response.text();
      } catch {
        body = null;
      }
    }
    throw ApiError.fromResponse(response.status, body);
  }
  return response.json() as Promise<T>;
}

export async function uploadDocuments(
  files: File[],
  parser: ParserType = 'pypdf'
): Promise<DocumentUploadItem[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file, file.name);
  }
  formData.append('parser', parser);

  const response = await fetch(`${API_BASE_URL}/documents`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<DocumentUploadItem[]>(response);
}

export async function listDocuments(
  limit: number = 20,
  cursor?: string | null
): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  if (limit) params.set('limit', limit.toString());
  if (cursor) params.set('cursor', cursor);

  const query = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(`${API_BASE_URL}/documents${query}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  return handleResponse<DocumentListResponse>(response);
}

export async function getDocumentDetail(
  documentId: string
): Promise<DocumentDetailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`,
    {
      method: 'GET',
      headers: { Accept: 'application/json' },
    }
  );

  return handleResponse<DocumentDetailResponse>(response);
}

export async function getDocumentStatus(
  documentId: string
): Promise<{ data: DocumentStatusResponse; retryAfter?: number }> {
  const response = await fetch(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/status`,
    {
      method: 'GET',
      headers: { Accept: 'application/json' },
    }
  );

  const data = await handleResponse<DocumentStatusResponse>(response);
  const retryAfterHeader = response.headers.get('Retry-After');
  let retryAfter: number | undefined;

  if (retryAfterHeader) {
    const parsed = parseInt(retryAfterHeader, 10);
    if (!isNaN(parsed) && parsed > 0) {
      retryAfter = parsed;
    }
  }

  return { data, retryAfter };
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  return handleResponse<HealthResponse>(response);
}
