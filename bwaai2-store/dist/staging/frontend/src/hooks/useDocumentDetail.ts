import { useQuery } from '@tanstack/react-query';
import { getDocumentDetail } from '../api/client';

export function useDocumentDetail(documentId: string | null) {
  return useQuery({
    queryKey: ['document-detail', documentId],
    queryFn: () => getDocumentDetail(documentId!),
    enabled: Boolean(documentId),
    retry: 2,
  });
}
