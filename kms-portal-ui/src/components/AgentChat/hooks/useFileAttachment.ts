/**
 * useFileAttachment Hook
 * Handles file attachment logic for the AgentChat component.
 */

import { useState, useRef, useCallback } from 'react';
import type { AttachedFile } from '../types';
import {
  BINARY_EXTENSIONS,
  SUPPORTED_EXTENSIONS,
  MAX_TEXT_FILE_SIZE,
  MAX_BINARY_FILE_SIZE,
} from '../constants';

export interface UseFileAttachmentReturn {
  // State
  attachedFiles: AttachedFile[];
  fileError: string | null;
  fileInputRef: React.RefObject<HTMLInputElement>;

  // Actions
  handleFileAttach: () => void;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  handleRemoveFile: (fileName: string) => void;
  handleClearAllFiles: () => void;
  getFileContext: () => string | undefined;
  clearFileError: () => void;
}

export function useFileAttachment(): UseFileAttachmentReturn {
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Trigger file input click
  const handleFileAttach = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // Handle file selection
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setFileError(null);

    for (const file of Array.from(files)) {
      // Check extension
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        setFileError(`Unsupported file type: ${ext}. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}`);
        continue;
      }

      // Check size based on file type
      const isBinaryFile = BINARY_EXTENSIONS.includes(ext);
      const maxSize = isBinaryFile ? MAX_BINARY_FILE_SIZE : MAX_TEXT_FILE_SIZE;
      const maxSizeLabel = isBinaryFile ? '2MB' : '500KB';

      if (file.size > maxSize) {
        setFileError(`File too large: ${file.name} (max ${maxSizeLabel})`);
        continue;
      }

      // Check if already attached
      if (attachedFiles.some(f => f.name === file.name)) {
        setFileError(`File already attached: ${file.name}`);
        continue;
      }

      // Handle file based on type
      try {
        let content: string;

        if (isBinaryFile) {
          // PDF/DOCX: Send to server for text extraction
          const formData = new FormData();
          formData.append('file', file);

          const response = await fetch('/api/v1/agents/extract-text', {
            method: 'POST',
            body: formData,
            credentials: 'include',
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail?.message || 'Failed to extract text');
          }

          const result = await response.json();
          content = result.content;
        } else {
          // Text files: Read directly
          content = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsText(file);
          });
        }

        setAttachedFiles(prev => [...prev, {
          name: file.name,
          content,
          size: content.length  // Use extracted content size
        }]);
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        setFileError(`Failed to process file ${file.name}: ${errorMsg}`);
      }
    }

    // Reset input to allow re-selecting the same file
    if (e.target) e.target.value = '';
  }, [attachedFiles]);

  // Remove a single file
  const handleRemoveFile = useCallback((fileName: string) => {
    setAttachedFiles(prev => prev.filter(f => f.name !== fileName));
    setFileError(null);
  }, []);

  // Clear all files
  const handleClearAllFiles = useCallback(() => {
    setAttachedFiles([]);
    setFileError(null);
  }, []);

  // Get combined file context for API request
  const getFileContext = useCallback((): string | undefined => {
    if (attachedFiles.length === 0) return undefined;
    return attachedFiles.map(f => `=== File: ${f.name} ===\n${f.content}\n`).join('\n');
  }, [attachedFiles]);

  // Clear file error
  const clearFileError = useCallback(() => {
    setFileError(null);
  }, []);

  return {
    attachedFiles,
    fileError,
    fileInputRef,
    handleFileAttach,
    handleFileChange,
    handleRemoveFile,
    handleClearAllFiles,
    getFileContext,
    clearFileError,
  };
}

export default useFileAttachment;
