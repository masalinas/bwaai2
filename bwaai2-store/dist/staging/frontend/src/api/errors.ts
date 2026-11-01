import type { ApiErrorSchema, ErrorCode } from './types';

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: ErrorCode | string;
  public readonly details?: unknown;

  constructor(
    status: number,
    code: ErrorCode | string,
    message: string,
    details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  static fromResponse(status: number, body: unknown): ApiError {
    if (
      typeof body === 'object' &&
      body !== null &&
      'code' in body &&
      'message' in body
    ) {
      const err = body as ApiErrorSchema;
      return new ApiError(status, err.code, err.message, err.details);
    }
    return new ApiError(
      status,
      'UNKNOWN_ERROR',
      typeof body === 'string' && body.trim()
        ? body
        : `Request failed with status ${status}`
    );
  }
}
