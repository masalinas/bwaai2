import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  FileText,
  Loader2,
  Sparkles,
} from 'lucide-react';
import type { DocumentDetailResponse } from '../api/types';
import { copyToClipboard, downloadMarkdown, formatDateTime } from '../utils/format';
import { StatusBadge } from './StatusBadge';

interface DocumentViewerProps {
  documentDetail: DocumentDetailResponse | null;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  documentDetail,
  isLoading,
  isError,
  error,
}) => {
  const [activePageIndex, setActivePageIndex] = useState<number>(0);
  const [hasCopied, setHasCopied] = useState<boolean>(false);

  // If new document is selected, reset to first page
  React.useEffect(() => {
    setActivePageIndex(0);
  }, [documentDetail?.document_id]);

  if (!documentDetail && !isLoading && !isError) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-10 text-center flex flex-col items-center justify-center min-h-[420px]">
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mb-3">
          <FileText className="w-6 h-6" />
        </div>
        <h3 className="text-base font-medium text-slate-700">No document selected</h3>
        <p className="text-sm text-slate-500 max-w-sm mt-1">
          Select a document from the list on the left to view its extracted pages and
          executive summary.
        </p>
      </div>
    );
  }

  if (isLoading && !documentDetail) {
    return (
      <div
        className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4 animate-pulse min-h-[420px]"
        data-testid="document-viewer-loading"
      >
        <div className="h-6 bg-slate-200 rounded w-1/3" />
        <div className="h-4 bg-slate-200 rounded w-1/4" />
        <div className="h-24 bg-slate-100 rounded-lg" />
        <div className="h-64 bg-slate-50 rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="bg-white rounded-xl border border-rose-200 shadow-sm p-6 text-center text-rose-800"
      >
        <AlertCircle className="w-8 h-8 text-rose-600 mx-auto mb-2" />
        <h3 className="text-sm font-semibold">Failed to load document details</h3>
        <p className="text-xs text-rose-600 mt-1">
          {error?.message || 'Network request failed'}
        </p>
      </div>
    );
  }

  if (!documentDetail) return null;

  const pages = documentDetail.pages || [];
  const activePage = pages[activePageIndex];
  const isSummarizing = documentDetail.status === 'summarizing';
  const isFailed = documentDetail.status === 'failed';
  const isDone = documentDetail.status === 'done';

  const handleCopySummary = async () => {
    if (documentDetail.summary) {
      const ok = await copyToClipboard(documentDetail.summary);
      if (ok) {
        setHasCopied(true);
        setTimeout(() => setHasCopied(false), 2000);
      }
    }
  };

  const handleDownloadFullMarkdown = () => {
    let md = `# ${documentDetail.filename}\n\n`;
    md += `**Document ID**: ${documentDetail.document_id}  \n`;
    md += `**Parser**: ${documentDetail.parser}  \n`;
    md += `**Status**: ${documentDetail.status}  \n`;
    md += `**Processed**: ${formatDateTime(documentDetail.updated_at)}  \n\n`;

    if (documentDetail.summary) {
      md += `## Executive Summary\n\n${documentDetail.summary}\n\n---\n\n`;
    }

    if (pages.length > 0) {
      md += `## Document Pages (${pages.length})\n\n`;
      pages.forEach((p) => {
        md += `### Page ${p.page_number}\n\n`;
        if (p.format === 'markdown') {
          md += `${p.content}\n\n`;
        } else {
          md += `\`\`\`text\n${p.content}\n\`\`\`\n\n`;
        }
      });
    }

    const safeFilename = `${documentDetail.document_id}_${documentDetail.filename.replace(/\.pdf$/i, '')}.md`;
    downloadMarkdown(safeFilename, md);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-bold text-slate-900 truncate">
              {documentDetail.filename}
            </h2>
            <StatusBadge status={documentDetail.status} />
          </div>
          <p className="text-xs text-slate-500 mt-1">
            ID:{' '}
            <span className="font-mono text-slate-600">{documentDetail.document_id}</span>{' '}
            · Parser:{' '}
            <span className="font-semibold text-slate-700">{documentDetail.parser}</span>{' '}
            · Created: {formatDateTime(documentDetail.created_at)}
          </p>
        </div>

        {/* Global Action: Full Download */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleDownloadFullMarkdown}
            disabled={!isDone && pages.length === 0}
            className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-xs"
          >
            <Download className="w-3.5 h-3.5" />
            Download .md
          </button>
        </div>
      </div>

      {/* Error Card if status is failed */}
      {isFailed && documentDetail.error && (
        <div
          role="alert"
          className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-900 text-xs space-y-1"
        >
          <div className="flex items-center gap-2 font-bold text-rose-800">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
            <span>Processing Error: {documentDetail.error.code}</span>
          </div>
          <p className="pl-6 text-rose-700">{documentDetail.error.message}</p>
          {pages.length > 0 && (
            <p className="pl-6 text-[11px] text-rose-600/90 italic pt-1">
              Note: Pages parsed prior to summarization failure have been preserved below.
            </p>
          )}
        </div>
      )}

      {/* Executive Summary Card */}
      <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            Executive Summary
          </h3>
          {documentDetail.summary && (
            <button
              type="button"
              onClick={handleCopySummary}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1 transition-colors px-2 py-0.5 rounded hover:bg-indigo-50"
            >
              {hasCopied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-700">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy
                </>
              )}
            </button>
          )}
        </div>

        {isSummarizing && (
          <div className="py-4 flex items-center gap-2.5 text-xs text-purple-700">
            <Loader2 className="w-4 h-4 animate-spin text-purple-600" />
            <span>Generating executive summary with Gemini 3.8 Flash...</span>
          </div>
        )}

        {isDone && documentDetail.summary && (
          <div className="prose prose-sm max-w-none text-slate-800 text-xs sm:text-sm bg-white p-3.5 rounded-md border border-slate-200 leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {documentDetail.summary}
            </ReactMarkdown>
          </div>
        )}

        {!isSummarizing && !documentDetail.summary && !isFailed && (
          <p className="text-xs text-slate-400 italic py-2">
            Summary will appear here once background processing completes.
          </p>
        )}
      </div>

      {/* Pages Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
            <FileText className="w-4 h-4 text-indigo-600" />
            Document Pages {pages.length > 0 ? `(${pages.length})` : ''}
          </h3>

          {/* Page Navigator */}
          {pages.length > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={activePageIndex === 0}
                onClick={() => setActivePageIndex((prev) => Math.max(0, prev - 1))}
                className="p-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-slate-600 transition-colors shadow-xs"
                aria-label="Previous page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs font-medium text-slate-600">
                Page {activePageIndex + 1} of {pages.length}
              </span>
              <button
                type="button"
                disabled={activePageIndex === pages.length - 1}
                onClick={() =>
                  setActivePageIndex((prev) => Math.min(pages.length - 1, prev + 1))
                }
                className="p-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-slate-600 transition-colors shadow-xs"
                aria-label="Next page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* Page Content Display */}
        {pages.length > 0 && activePage ? (
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/40 min-h-[220px]">
            <div className="flex items-center justify-between mb-2 pb-2 border-b border-slate-200 text-[11px] text-slate-500">
              <span className="font-semibold text-slate-700">
                Page {activePage.page_number}
              </span>
              <span className="font-mono uppercase bg-slate-200/70 px-1.5 py-0.2 rounded text-[10px]">
                {activePage.format}
              </span>
            </div>

            {activePage.format === 'markdown' ? (
              <div className="prose prose-sm max-w-none text-slate-800 text-xs sm:text-sm bg-white p-4 rounded border border-slate-200 leading-relaxed overflow-x-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {activePage.content}
                </ReactMarkdown>
              </div>
            ) : (
              <pre className="font-mono text-xs text-slate-800 bg-white p-4 rounded border border-slate-200 whitespace-pre-wrap leading-relaxed overflow-x-auto">
                {activePage.content || '(Page is blank)'}
              </pre>
            )}
          </div>
        ) : (
          <div className="border border-slate-200 rounded-lg p-8 text-center text-slate-400 bg-slate-50/40 text-xs">
            {documentDetail.status === 'queued' || documentDetail.status === 'processing'
              ? 'Parsing pages in background worker...'
              : 'No extracted page content available.'}
          </div>
        )}
      </div>
    </div>
  );
};
