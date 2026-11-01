import React from 'react';
import { AlertCircle, CheckCircle2, Clock, Loader2, Sparkles } from 'lucide-react';
import type { DocumentStatus } from '../api/types';

interface StatusBadgeProps {
  status: DocumentStatus;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  switch (status) {
    case 'queued':
      return (
        <span
          role="status"
          aria-label="Status: Queued"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 ${className}`}
        >
          <Clock className="w-3.5 h-3.5 text-amber-600" />
          Queued
        </span>
      );
    case 'processing':
      return (
        <span
          role="status"
          aria-label="Status: Processing PDF"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 ${className}`}
        >
          <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin" />
          Processing
        </span>
      );
    case 'summarizing':
      return (
        <span
          role="status"
          aria-label="Status: Summarizing document"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200 ${className}`}
        >
          <Sparkles className="w-3.5 h-3.5 text-purple-600 animate-pulse" />
          Summarizing
        </span>
      );
    case 'done':
      return (
        <span
          role="status"
          aria-label="Status: Done"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 ${className}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          Done
        </span>
      );
    case 'failed':
      return (
        <span
          role="status"
          aria-label="Status: Failed"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200 ${className}`}
        >
          <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
          Failed
        </span>
      );
    default:
      return (
        <span
          role="status"
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200 ${className}`}
        >
          {status}
        </span>
      );
  }
};
