import type { ParserType } from '../api/types';

export interface ParserOption {
  id: ParserType;
  name: string;
  badge: string;
  description: string;
}

export const AVAILABLE_PARSERS: ParserOption[] = [
  {
    id: 'pypdf',
    name: 'PyPDF',
    badge: 'Text',
    description: 'Fast CPU-based plain text extraction',
  },
  {
    id: 'gemini',
    name: 'Gemini 3.8 Flash',
    badge: 'Multimodal Markdown',
    description: 'High-fidelity multimodal markdown extraction & formatting',
  },
  {
    id: 'mistral',
    name: 'Mistral OCR',
    badge: 'OCR',
    description: 'High-accuracy document OCR markdown extraction',
  },
];

/**
 * Parsers listed here are visually disabled in the selector.
 * Removing an entry enables it immediately across the UI.
 */
export const DISABLED_PARSERS: ParserType[] = [];
