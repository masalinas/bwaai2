import { useQuery } from '@tanstack/react-query';
import { getDocumentStatus } from '../api/client';
import type { DocumentStatus } from '../api/types';
import { DEFAULT_POLL_INTERVAL_MS } from '../config/constants';

interface UseDocumentStatusOptions {
  enabled?: boolean;
  onStatusChange?: (newStatus: DocumentStatus) => void;
}

export function useDocumentStatus(
  documentId: string,
  options: UseDocumentStatusOptions = {}
) {
  const { enabled = true } = options;

  return useQuery({
    queryKey: ['document-status', documentId],
    queryFn: async () => {
      const res = await getDocumentStatus(documentId);
      if (options.onStatusChange) {
        options.onStatusChange(res.data.status);
      }
      return res;
    },
    enabled: enabled && Boolean(documentId),
    refetchInterval: (query) => {
      const status = query.state.data?.data.status;
      if (status === 'done' || status === 'failed') {
        return false; // Terminal states halt polling
      }
      const retryAfter = query.state.data?.retryAfter;
      return retryAfter ? retryAfter * 1000 : DEFAULT_POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: false,
    retry: 3,
    retryDelay: (attempt) => Math.min(100 * 2 ** attempt, 1000),
  });
}
