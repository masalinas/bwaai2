import React, { useRef, useState } from 'react';
import { AlertTriangle, FileText, Upload, X } from 'lucide-react';
import { uploadDocuments } from '../api/client';
import { ApiError } from '../api/errors';
import type { DocumentUploadItem, ParserType } from '../api/types';
import {
  ACCEPTED_MIME_TYPE,
  MAX_FILES_PER_REQUEST,
  MAX_FILE_SIZE_BYTES,
} from '../config/constants';
import { AVAILABLE_PARSERS, DISABLED_PARSERS } from '../config/parsers';
import { formatBytes } from '../utils/format';

interface UploadAreaProps {
  onUploadSuccess: (items: DocumentUploadItem[]) => void;
}

export const UploadArea: React.FC<UploadAreaProps> = ({ onUploadSuccess }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedParser, setSelectedParser] = useState<ParserType>('pypdf');
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndAddFiles = (newFiles: FileList | File[]) => {
    setValidationError(null);
    setApiError(null);

    const fileList = Array.from(newFiles);
    const combined = [...selectedFiles, ...fileList];

    if (combined.length > MAX_FILES_PER_REQUEST) {
      setValidationError(
        `Maximum batch limit is ${MAX_FILES_PER_REQUEST} files (you selected ${combined.length}).`
      );
      return;
    }

    for (const file of fileList) {
      if (file.type !== ACCEPTED_MIME_TYPE && !file.name.toLowerCase().endsWith('.pdf')) {
        setValidationError(
          `'${file.name}' is not a valid PDF. Only application/pdf files are accepted.`
        );
        return;
      }
      if (file.size > MAX_FILE_SIZE_BYTES) {
        setValidationError(
          `'${file.name}' exceeds the 25 MB limit (${formatBytes(file.size)}).`
        );
        return;
      }
    }

    // Deduplicate by name and size
    const unique = combined.filter(
      (f, idx, self) =>
        idx === self.findIndex((other) => other.name === f.name && other.size === f.size)
    );

    setSelectedFiles(unique);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndAddFiles(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setValidationError(null);
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setValidationError(null);
    setApiError(null);

    try {
      const items = await uploadDocuments(selectedFiles, selectedParser);
      setSelectedFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      onUploadSuccess(items);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'PARSER_UNAVAILABLE') {
          setApiError(`Parser '${selectedParser}' is unavailable: ${err.message}`);
        } else {
          setApiError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setApiError(err.message);
      } else {
        setApiError('An unexpected upload error occurred.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
          <Upload className="w-5 h-5 text-indigo-600" />
          Upload PDF Documents
        </h2>
        <span className="text-xs text-slate-500">Max 10 files · Up to 25MB each</span>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors duration-150 ${
          isDragging
            ? 'border-indigo-500 bg-indigo-50/50'
            : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
        }`}
        role="button"
        tabIndex={0}
        aria-label="Upload files dropzone"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            fileInputRef.current?.click();
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => e.target.files && validateAndAddFiles(e.target.files)}
          data-testid="file-input"
        />
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="w-10 h-10 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Upload className="w-5 h-5" />
          </div>
          <div>
            <span className="text-sm font-medium text-indigo-600 hover:underline">
              Choose files
            </span>{' '}
            <span className="text-sm text-slate-500">or drag & drop them here</span>
          </div>
          <p className="text-xs text-slate-400">Strictly PDF files up to 25 MB</p>
        </div>
      </div>

      {/* Client Validation Error */}
      {validationError && (
        <div
          role="alert"
          className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
          <span>{validationError}</span>
        </div>
      )}

      {/* API Error Display */}
      {apiError && (
        <div
          role="alert"
          className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-sm flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Selected Files List */}
      {selectedFiles.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Selected Files ({selectedFiles.length}/{MAX_FILES_PER_REQUEST})
          </div>
          <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
            {selectedFiles.map((file, idx) => (
              <div
                key={`${file.name}-${idx}`}
                className="flex items-center justify-between p-2 rounded-md bg-slate-50 border border-slate-200 text-xs"
              >
                <div className="flex items-center gap-2 truncate">
                  <FileText className="w-4 h-4 text-slate-400 shrink-0" />
                  <span className="font-medium text-slate-700 truncate">{file.name}</span>
                  <span className="text-slate-400 shrink-0">
                    ({formatBytes(file.size)})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(idx)}
                  className="text-slate-400 hover:text-rose-600 p-0.5 rounded transition-colors"
                  aria-label={`Remove ${file.name}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Parser Selection */}
      <div className="space-y-1.5 pt-2 border-t border-slate-100">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Parser Engine
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {AVAILABLE_PARSERS.map((parser) => {
            const isDisabled = DISABLED_PARSERS.includes(parser.id);
            const isSelected = selectedParser === parser.id;
            return (
              <button
                key={parser.id}
                type="button"
                disabled={isDisabled}
                onClick={() => setSelectedParser(parser.id)}
                className={`relative p-2.5 rounded-lg border text-left transition-all ${
                  isDisabled
                    ? 'opacity-50 cursor-not-allowed bg-slate-100 border-slate-200'
                    : isSelected
                      ? 'border-indigo-600 bg-indigo-50/40 ring-1 ring-indigo-600'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-semibold text-slate-800">
                    {parser.name}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded font-medium ${
                      isDisabled
                        ? 'bg-slate-200 text-slate-600'
                        : isSelected
                          ? 'bg-indigo-200 text-indigo-800'
                          : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {parser.badge}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 line-clamp-2">
                  {parser.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Submit Button */}
      <button
        type="button"
        disabled={selectedFiles.length === 0 || isUploading}
        onClick={handleUpload}
        className={`w-full py-2.5 px-4 rounded-lg text-sm font-medium text-white transition-all shadow-sm flex items-center justify-center gap-2 ${
          selectedFiles.length === 0 || isUploading
            ? 'bg-slate-300 cursor-not-allowed'
            : 'bg-indigo-600 hover:bg-indigo-700 active:scale-[0.99]'
        }`}
      >
        {isUploading ? (
          <>
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Uploading & Enqueuing...
          </>
        ) : (
          `Upload & Process ${selectedFiles.length > 0 ? `(${selectedFiles.length})` : ''}`
        )}
      </button>
    </div>
  );
};
