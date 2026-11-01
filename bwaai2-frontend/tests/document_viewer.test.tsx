import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { DocumentDetailResponse } from '../src/api/types';
import { DocumentViewer } from '../src/components/DocumentViewer';
import { renderWithProviders } from './test_utils';

describe('DocumentViewer Component', () => {
  it('renders failed document displaying error details while retaining extracted pages', () => {
    const failedDetailWithPages: DocumentDetailResponse = {
      document_id: 'doc_failed_preserved',
      filename: 'contract_error.pdf',
      parser: 'gemini',
      status: 'failed',
      created_at: '2026-10-31T00:00:00Z',
      updated_at: '2026-10-31T00:01:00Z',
      error: {
        code: 'SUMMARY_FAILED',
        message: 'Gemini rate limit exhausted during map-reduce step.',
      },
      summary: null,
      pages: [
        {
          page_number: 1,
          content: '# Page 1 Preserved\n\nContract text remains readable.',
          format: 'markdown',
        },
      ],
    };

    renderWithProviders(
      <DocumentViewer
        documentDetail={failedDetailWithPages}
        isLoading={false}
        isError={false}
      />
    );

    // Verify error code and message are visible
    expect(screen.getByText(/Processing Error: SUMMARY_FAILED/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Gemini rate limit exhausted during map-reduce step/i)
    ).toBeInTheDocument();

    // Verify preserved page text is still rendered
    expect(screen.getByText(/Contract text remains readable/i)).toBeInTheDocument();
  });

  it('renders early pages during summarizing status with pending summary indicator', () => {
    const summarizingDetail: DocumentDetailResponse = {
      document_id: 'doc_summarizing_early',
      filename: 'early_preview.pdf',
      parser: 'gemini',
      status: 'summarizing',
      created_at: '2026-10-31T00:00:00Z',
      updated_at: '2026-10-31T00:00:02Z',
      error: null,
      summary: null,
      pages: [
        {
          page_number: 1,
          content: '# Early Page Content\n\nPages are accessible before summary completes.',
          format: 'markdown',
        },
      ],
    };

    renderWithProviders(
      <DocumentViewer
        documentDetail={summarizingDetail}
        isLoading={false}
        isError={false}
      />
    );

    // Pending summary placeholder
    expect(
      screen.getByText(/Generating executive summary with Gemini/i)
    ).toBeInTheDocument();

    // Pages are already visible!
    expect(
      screen.getByText(/Pages are accessible before summary completes/i)
    ).toBeInTheDocument();
  });

  it('navigates between multiple pages and respects plain text vs markdown formats', () => {
    const multiPageDetail: DocumentDetailResponse = {
      document_id: 'doc_multipage',
      filename: 'multi.pdf',
      parser: 'pypdf',
      status: 'done',
      created_at: '2026-10-31T00:00:00Z',
      updated_at: '2026-10-31T00:01:00Z',
      summary: 'Executive Summary.',
      pages: [
        {
          page_number: 1,
          content: 'Plain text line 1\nPlain text line 2',
          format: 'text',
        },
        {
          page_number: 2,
          content: 'Second page plain text content.',
          format: 'text',
        },
      ],
      error: null,
    };

    renderWithProviders(
      <DocumentViewer
        documentDetail={multiPageDetail}
        isLoading={false}
        isError={false}
      />
    );

    // Initial page: Page 1
    expect(screen.getByText(/Page 1 of 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Plain text line 1/i)).toBeInTheDocument();

    // Click Next
    const nextBtn = screen.getByRole('button', { name: /Next page/i });
    fireEvent.click(nextBtn);

    // Switch to Page 2
    expect(screen.getByText(/Page 2 of 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Second page plain text content/i)).toBeInTheDocument();
  });

  it('triggers copy summary and download markdown actions', async () => {
    const docWithSummary: DocumentDetailResponse = {
      document_id: 'doc_export_test',
      filename: 'annual_report.pdf',
      parser: 'gemini',
      status: 'done',
      created_at: '2026-10-31T00:00:00Z',
      updated_at: '2026-10-31T00:01:00Z',
      summary: 'Full executive summary text to copy.',
      pages: [
        {
          page_number: 1,
          content: '# Page 1',
          format: 'markdown',
        },
      ],
      error: null,
    };

    // Mock clipboard
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderWithProviders(
      <DocumentViewer
        documentDetail={docWithSummary}
        isLoading={false}
        isError={false}
      />
    );

    // Copy Summary button
    const copyBtn = screen.getByRole('button', { name: /Copy/i });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('Full executive summary text to copy.');
      expect(screen.getByText(/Copied!/i)).toBeInTheDocument();
    });

    // Download .md button
    const downloadBtn = screen.getByRole('button', { name: /Download \.md/i });
    expect(downloadBtn).toBeEnabled();
  });
});
