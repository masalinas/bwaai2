import { renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import App from '../src/App';
import { useDocumentStatus } from '../src/hooks/useDocumentStatus';
import { server } from './mocks/server';
import { createTestQueryClient, renderWithProviders } from './test_utils';
import { QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

describe('Polling and Pagination', () => {
  it('stops polling when status reaches terminal state (done)', async () => {
    let pollCount = 0;
    server.use(
      http.get('*/api/documents/doc_poll_terminal/status', () => {
        pollCount++;
        return HttpResponse.json({
          document_id: 'doc_poll_terminal',
          status: 'done', // Terminal state
          created_at: '2026-10-31T00:00:00Z',
          updated_at: '2026-10-31T00:00:01Z',
          error: null,
        });
      })
    );

    const queryClient = createTestQueryClient();
    const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useDocumentStatus('doc_poll_terminal'),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.data?.data.status).toBe('done');
    });

    const callsAfterFirst = pollCount;
    // Advance timers or wait to verify no new calls occur
    await new Promise((r) => setTimeout(r, 100));
    expect(pollCount).toBe(callsAfterFirst);
  });

  it('survives transient network errors during polling with query retry', async () => {
    let attempt = 0;
    server.use(
      http.get('*/api/documents/doc_transient/status', () => {
        attempt++;
        if (attempt === 1) {
          // First attempt fails with 503
          return new HttpResponse(null, { status: 503 });
        }
        // Second attempt succeeds
        return HttpResponse.json({
          document_id: 'doc_transient',
          status: 'processing',
          created_at: '2026-10-31T00:00:00Z',
          updated_at: '2026-10-31T00:00:02Z',
          error: null,
        });
      })
    );

    const queryClient = createTestQueryClient();
    const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useDocumentStatus('doc_transient'),
      { wrapper }
    );

    await waitFor(
      () => {
        expect(result.current.isSuccess).toBe(true);
        expect(result.current.data?.data.status).toBe('processing');
      },
      { timeout: 3000 }
    );

    expect(attempt).toBe(2);
  });

  it('loads more documents with cursor pagination upon clicking Load More', async () => {
    const user = userEvent.setup();
    renderWithProviders(<App />);

    // Initial page document
    await waitFor(() => {
      expect(screen.getByText('existing_document.pdf')).toBeInTheDocument();
    });

    // "Load More" button is rendered because has_more is true
    const loadMoreBtn = screen.getByRole('button', { name: /Load More Documents/i });
    expect(loadMoreBtn).toBeInTheDocument();

    await user.click(loadMoreBtn);

    // Second page document is appended
    await waitFor(() => {
      expect(screen.getByText('older_document.pdf')).toBeInTheDocument();
      // First page document is still retained
      expect(screen.getByText('existing_document.pdf')).toBeInTheDocument();
    });

    // has_more is now false, so Load More button disappears
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Load More Documents/i })).not.toBeInTheDocument();
    });
  });
});
