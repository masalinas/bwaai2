import React from 'react';
import { AlertCircle, FileSearch, RefreshCw } from 'lucide-react';
import type { DocumentStatus } from '../api/types';
import { DocumentListItem, type DocumentSummaryItem } from './DocumentListItem';

interface DocumentListProps {
  documents: DocumentSummaryItem[];
  selectedDocumentId: string | null;
  onSelectDocument: (doc: DocumentSummaryItem) => void;
  onStatusUpdated?: (docId: string, newStatus: DocumentStatus) => void;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry?: () => void;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
}

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  selectedDocumentId,
  onSelectDocument,
  onStatusUpdated,
  isLoading,
  isError,
  error,
  onRetry,
  hasMore,
  isLoadingMore,
  onLoadMore,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
          <FileSearch className="w-5 h-5 text-indigo-600" />
          Processed Documents
        </h2>
        <span className="text-xs text-slate-500">{documents.length} loaded</span>
      </div>

      {/* Network Error State */}
      {isError && (
        <div
          role="alert"
          className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-sm flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error?.message || 'Failed to load document list.'}</span>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="text-xs font-semibold px-2.5 py-1 bg-white border border-rose-300 rounded hover:bg-rose-50 text-rose-700 flex items-center gap-1 shadow-xs"
            >
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          )}
        </div>
      )}

      {/* Initial Loading Skeleton */}
      {isLoading && documents.length === 0 && (
        <div className="space-y-2.5 animate-pulse" data-testid="document-list-loading">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-slate-200 rounded-lg" />
                <div className="space-y-1.5">
                  <div className="w-32 h-4 bg-slate-200 rounded" />
                  <div className="w-20 h-3 bg-slate-200 rounded" />
                </div>
              </div>
              <div className="w-16 h-5 bg-slate-200 rounded-full" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && documents.length === 0 && !isError && (
        <div className="text-center py-10 px-4 border-2 border-dashed border-slate-200 rounded-lg bg-slate-50/50">
          <FileSearch className="w-8 h-8 text-slate-400 mx-auto mb-2" />
          <h3 className="text-sm font-medium text-slate-700">No documents yet</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto">
            Upload one or more PDF files using the box above to start parsing and
            summarization.
          </p>
        </div>
      )}

      {/* Documents List */}
      {documents.length > 0 && (
        <div className="space-y-2" aria-live="polite">
          {documents.map((doc) => (
            <DocumentListItem
              key={doc.document_id}
              document={doc}
              isSelected={selectedDocumentId === doc.document_id}
              onSelect={onSelectDocument}
              onStatusUpdated={onStatusUpdated}
            />
          ))}
        </div>
      )}

      {/* Load More Pagination Button */}
      {hasMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={isLoadingMore}
          className="w-full py-2 px-3 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors flex items-center justify-center gap-1.5 shadow-xs"
        >
          {isLoadingMore ? (
            <>
              <RefreshCw className="w-3 h-3 animate-spin text-slate-500" />
              Loading older documents...
            </>
          ) : (
            'Load More Documents'
          )}
        </button>
      )}
    </div>
  );
};
