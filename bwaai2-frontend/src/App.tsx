import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Layers } from 'lucide-react';
import { listDocuments } from './api/client';
import type {
  DocumentDetailResponse,
  DocumentStatus,
  DocumentUploadItem,
} from './api/types';
import type { DocumentSummaryItem } from './components/DocumentListItem';
import { DocumentList } from './components/DocumentList';
import { DocumentViewer } from './components/DocumentViewer';
import { UploadArea } from './components/UploadArea';
import { useDocumentDetail } from './hooks/useDocumentDetail';

export const App: React.FC = () => {
  const queryClient = useQueryClient();
  const [documents, setDocuments] = useState<DocumentSummaryItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [listError, setListError] = useState<Error | null>(null);

  // Fetch initial documents list
  const fetchInitialDocuments = React.useCallback(async () => {
    setIsInitialLoading(true);
    setListError(null);
    try {
      const data = await listDocuments(20);
      setDocuments(data.items);
      setCursor(data.next_cursor || null);
      setHasMore(data.has_more);
      if (data.items.length > 0 && !selectedDocId) {
        setSelectedDocId(data.items[0].document_id);
      }
    } catch (err) {
      setListError(err instanceof Error ? err : new Error('Failed to load documents'));
    } finally {
      setIsInitialLoading(false);
    }
  }, [selectedDocId]);

  React.useEffect(() => {
    fetchInitialDocuments();
  }, [fetchInitialDocuments]);

  // Load more documents for cursor pagination
  const handleLoadMore = async () => {
    if (!cursor || isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const data = await listDocuments(20, cursor);
      setDocuments((prev) => {
        // Deduplicate against existing items
        const existingIds = new Set(prev.map((d) => d.document_id));
        const newItems = data.items.filter((d) => !existingIds.has(d.document_id));
        return [...prev, ...newItems];
      });
      setCursor(data.next_cursor || null);
      setHasMore(data.has_more);
    } catch (err) {
      setListError(
        err instanceof Error ? err : new Error('Failed to load more documents')
      );
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Upload callback: prepend new documents and select the first one
  const handleUploadSuccess = (items: DocumentUploadItem[]) => {
    const nowIso = new Date().toISOString();
    const newDocs: DocumentSummaryItem[] = items.map((item) => ({
      document_id: item.document_id,
      filename: item.filename,
      parser: 'pypdf', // default unless overrode in selection
      status: item.status,
      created_at: nowIso,
      updated_at: nowIso,
    }));

    setDocuments((prev) => [...newDocs, ...prev]);
    if (newDocs.length > 0) {
      setSelectedDocId(newDocs[0].document_id);
    }
  };

  // Status update from polling: update list item and invalidate detail if active
  const handleStatusUpdated = (docId: string, newStatus: DocumentStatus) => {
    setDocuments((prev) =>
      prev.map((doc) => (doc.document_id === docId ? { ...doc, status: newStatus } : doc))
    );

    if (docId === selectedDocId) {
      // Invalidate detail query so freshly extracted pages or summary load immediately
      queryClient.invalidateQueries({ queryKey: ['document-detail', docId] });
    }
  };

  // Fetch detail query for selected document
  const {
    data: detailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
    error: detailError,
  } = useDocumentDetail(selectedDocId);

  // If detailData has latest status, sync with documents list
  React.useEffect(() => {
    if (detailData?.document_id && detailData.status) {
      setDocuments((prev) =>
        prev.map((doc) =>
          doc.document_id === detailData.document_id && doc.status !== detailData.status
            ? { ...doc, status: detailData.status }
            : doc
        )
      );
    }
  }, [detailData]);

  // Selected document object
  const activeDocDetail: DocumentDetailResponse | null = detailData || null;

  return (
    <div className="min-h-screen bg-slate-100/60 pb-12">
      {/* Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-xs">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">
                PDF Processor & Summarizer
              </h1>
              <p className="text-xs text-slate-500">
                Async multimodal parsing & Gemini executive summaries
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs px-2.5 py-1 bg-slate-100 text-slate-700 font-mono rounded-md border border-slate-200">
              API v1.0.0
            </span>
          </div>
        </div>
      </header>

      {/* Main Grid Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Upload & Documents List */}
          <div className="lg:col-span-5 space-y-6">
            <UploadArea onUploadSuccess={handleUploadSuccess} />
            <DocumentList
              documents={documents}
              selectedDocumentId={selectedDocId}
              onSelectDocument={(doc) => setSelectedDocId(doc.document_id)}
              onStatusUpdated={handleStatusUpdated}
              isLoading={isInitialLoading}
              isError={Boolean(listError)}
              error={listError}
              onRetry={fetchInitialDocuments}
              hasMore={hasMore}
              isLoadingMore={isLoadingMore}
              onLoadMore={handleLoadMore}
            />
          </div>

          {/* Right Column: Document Details & Extracted Pages */}
          <div className="lg:col-span-7 sticky top-22">
            <DocumentViewer
              documentDetail={activeDocDetail}
              isLoading={isDetailLoading}
              isError={isDetailError}
              error={detailError}
            />
          </div>
        </div>
      </main>
    </div>
  );
};
export default App;
