import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import App from '../src/App';
import { server } from './mocks/server';
import { renderWithProviders } from './test_utils';

describe('Upload & Validation Flow', () => {
  it('rejects non-PDF files with client validation error', async () => {
    renderWithProviders(<App />);
    const fileInput = screen.getByTestId('file-input');

    const invalidFile = new File(['dummy content'], 'report.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    fireEvent.change(fileInput, { target: { files: [invalidFile] } });

    await waitFor(() => {
      expect(
        screen.getByText(/Only application\/pdf files are accepted/i)
      ).toBeInTheDocument();
    });
  });

  it('rejects files exceeding 25 MB limit', async () => {
    renderWithProviders(<App />);
    const fileInput = screen.getByTestId('file-input');

    // 26 MB dummy file
    const oversizedBytes = new Uint8Array(26 * 1024 * 1024);
    const oversizedFile = new File([oversizedBytes], 'huge.pdf', {
      type: 'application/pdf',
    });

    fireEvent.change(fileInput, { target: { files: [oversizedFile] } });

    await waitFor(() => {
      expect(screen.getByText(/exceeds the 25 MB limit/i)).toBeInTheDocument();
    });
  });

  it('rejects more than 10 files in a single batch', async () => {
    renderWithProviders(<App />);
    const fileInput = screen.getByTestId('file-input');

    const elevenFiles = Array.from({ length: 11 }, (_, i) =>
      new File(['%PDF-1.4'], `doc_${i + 1}.pdf`, { type: 'application/pdf' })
    );

    fireEvent.change(fileInput, { target: { files: elevenFiles } });

    await waitFor(() => {
      expect(screen.getByText(/Maximum batch limit is 10 files/i)).toBeInTheDocument();
    });
  });

  it('allows selecting Mistral OCR when enabled', () => {
    renderWithProviders(<App />);
    const mistralBtn = screen.getByRole('button', { name: /Mistral OCR/i });
    expect(mistralBtn).not.toBeDisabled();
    fireEvent.click(mistralBtn);
    expect(mistralBtn).toHaveClass('border-indigo-600');
  });

  it('handles PARSER_UNAVAILABLE gracefully without breaking the app', async () => {
    server.use(
      http.post('*/api/documents', () => {
        return HttpResponse.json(
          {
            code: 'PARSER_UNAVAILABLE',
            message: "The requested parser service is temporarily unavailable.",
            details: { service: 'parser' },
          },
          { status: 500 }
        );
      })
    );

    renderWithProviders(<App />);

    const fileInput = screen.getByTestId('file-input');
    const validFile = new File(['%PDF-1.4'], 'valid.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    const submitBtn = screen.getByRole('button', { name: /Upload & Process/i });
    await waitFor(() => expect(submitBtn).not.toBeDisabled());
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/temporarily unavailable/i)
      ).toBeInTheDocument();
    });

    // Verify app remains usable
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Upload & Process/i })).toBeInTheDocument();
    });
  });

  it('completes upload happy path, moves through polling states, and renders detail', async () => {
    let statusCallCount = 0;
    const documentId = 'doc_test_happy_1';

    server.use(
      http.post('*/api/documents', async () => {
        return HttpResponse.json(
          [
            {
              document_id: documentId,
              filename: 'financial_2026.pdf',
              status: 'queued',
            },
          ],
          { status: 202 }
        );
      }),

      http.get(`*/api/documents/${documentId}/status`, () => {
        statusCallCount++;
        let status = 'queued';
        if (statusCallCount === 2) status = 'processing';
        else if (statusCallCount === 3) status = 'summarizing';
        else if (statusCallCount >= 4) status = 'done';

        return HttpResponse.json({
          document_id: documentId,
          status,
          created_at: '2026-10-31T00:00:00Z',
          updated_at: '2026-10-31T00:00:02Z',
          error: null,
        });
      }),

      http.get(`*/api/documents/${documentId}`, () => {
        return HttpResponse.json({
          document_id: documentId,
          filename: 'financial_2026.pdf',
          parser: 'gemini',
          status: 'done',
          created_at: '2026-10-31T00:00:00Z',
          updated_at: '2026-10-31T00:00:05Z',
          summary: 'Executive summary for financial report 2026.',
          pages: [
            {
              page_number: 1,
              content: '# Financial Summary\n\nRevenue up 20%.',
              format: 'markdown',
            },
          ],
          error: null,
        });
      })
    );

    renderWithProviders(<App />);

    // 1. Upload file
    const fileInput = screen.getByTestId('file-input');
    const validFile = new File(['%PDF-1.4'], 'financial_2026.pdf', {
      type: 'application/pdf',
    });
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    const submitBtn = screen.getByRole('button', { name: /Upload & Process/i });
    await waitFor(() => expect(submitBtn).not.toBeDisabled());
    fireEvent.click(submitBtn);

    // 2. Newly uploaded document appears in list immediately
    await waitFor(() => {
      expect(screen.getByText('financial_2026.pdf')).toBeInTheDocument();
    });

    // 3. Document detail renders final summary and markdown pages
    await waitFor(
      () => {
        expect(
          screen.getByText(/Executive summary for financial report 2026/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/Revenue up 20%/i)).toBeInTheDocument();
      },
      { timeout: 4000 }
    );
  });
});
