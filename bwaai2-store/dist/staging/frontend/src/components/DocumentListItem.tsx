import React, { useEffect, useState } from 'react';
import { ChevronRight, FileText } from 'lucide-react';
import type { DocumentStatus, ParserType } from '../api/types';
import { useDocumentStatus } from '../hooks/useDocumentStatus';
import { formatDateTime } from '../utils/format';
import { StatusBadge } from './StatusBadge';

export interface DocumentSummaryItem {
  document_id: string;
  filename: string;
  parser: ParserType;
  status: DocumentStatus;
  created_at: string;
  updated_at?: string;
  error?: { code: string; message: string } | null;
}

interface DocumentListItemProps {
  document: DocumentSummaryItem;
  isSelected: boolean;
  onSelect: (doc: DocumentSummaryItem) => void;
  onStatusUpdated?: (docId: string, newStatus: DocumentStatus) => void;
}

export const DocumentListItem: React.FC<DocumentListItemProps> = ({
  document,
  isSelected,
  onSelect,
  onStatusUpdated,
}) => {
  const [currentStatus, setCurrentStatus] = useState<DocumentStatus>(document.status);

  // Sync if prop changes
  useEffect(() => {
    setCurrentStatus(document.status);
  }, [document.status]);

  const isTerminal = currentStatus === 'done' || currentStatus === 'failed';

  // TanStack Query polling hook for non-terminal statuses
  const { data: statusQueryData } = useDocumentStatus(document.document_id, {
    enabled: !isTerminal,
    onStatusChange: (newStatus) => {
      if (newStatus !== currentStatus) {
        setCurrentStatus(newStatus);
        if (onStatusUpdated) {
          onStatusUpdated(document.document_id, newStatus);
        }
      }
    },
  });

  // Sync if query returned updated status
  useEffect(() => {
    if (statusQueryData?.data?.status && statusQueryData.data.status !== currentStatus) {
      setCurrentStatus(statusQueryData.data.status);
      if (onStatusUpdated) {
        onStatusUpdated(document.document_id, statusQueryData.data.status);
      }
    }
  }, [statusQueryData, currentStatus, document.document_id, onStatusUpdated]);

  return (
    <div
      onClick={() => onSelect({ ...document, status: currentStatus })}
      role="button"
      tabIndex={0}
      aria-selected={isSelected}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onSelect({ ...document, status: currentStatus });
        }
      }}
      className={`p-3.5 rounded-lg border transition-all text-left flex items-center justify-between gap-3 cursor-pointer ${
        isSelected
          ? 'bg-indigo-50/70 border-indigo-400 ring-1 ring-indigo-400 shadow-sm'
          : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 shadow-xs'
      }`}
    >
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
            isSelected ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'
          }`}
        >
          <FileText className="w-5 h-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-slate-900 truncate">
              {document.filename}
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap text-xs text-slate-500">
            <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-[11px] text-slate-600">
              {document.parser}
            </span>
            <span>·</span>
            <span>{formatDateTime(document.created_at)}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <StatusBadge status={currentStatus} />
        <ChevronRight
          className={`w-4 h-4 transition-colors ${
            isSelected ? 'text-indigo-600' : 'text-slate-400'
          }`}
        />
      </div>
    </div>
  );
};
