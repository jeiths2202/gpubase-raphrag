/**
 * useFileAttachment Hook
 * Handles file attachment logic for the AgentChat component.
 * Supports per-agent file attachment state.
 */

import { useState, useRef, useCallback } from 'react';
import type { AttachedFile } from '../types';
import type { AgentType } from '../../../api/agent.api';
import {
  BINARY_EXTENSIONS,
  SUPPORTED_EXTENSIONS,
  MAX_TEXT_FILE_SIZE,
  MAX_BINARY_FILE_SIZE,
} from '../constants';

// Per-agent file state
interface AgentFileState {
  attachedFiles: AttachedFile[];
  fileError: string | null;
}

// Initialize empty state for an agent
const createInitialAgentFileState = (): AgentFileState => ({
  attachedFiles: [],
  fileError: null,
});

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

  // Sync function (call when selectedAgent changes)
  syncAgentFileState: (selectedAgent: AgentType) => void;
}

export function useFileAttachment(
  selectedAgentRef: React.MutableRefObject<AgentType>
): UseFileAttachmentReturn {
  // Per-agent state storage (persists across agent switches)
  const agentFileStatesRef = useRef<Record<AgentType, AgentFileState>>({
    auto: createInitialAgentFileState(),
    rag: createInitialAgentFileState(),
    ims: createInitialAgentFileState(),
    vision: createInitialAgentFileState(),
    code: createInitialAgentFileState(),
    planner: createInitialAgentFileState(),
  });

  // Current agent's state (React state for UI updates)
  const [attachedFiles, setAttachedFilesState] = useState<AttachedFile[]>([]);
  const [fileError, setFileErrorState] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Helper to update a specific agent's state
  const updateAgentFiles = useCallback((agent: AgentType, files: AttachedFile[]) => {
    agentFileStatesRef.current[agent].attachedFiles = files;
    if (agent === selectedAgentRef.current) {
      setAttachedFilesState(files);
    }
  }, [selectedAgentRef]);

  const updateAgentFileError = useCallback((agent: AgentType, error: string | null) => {
    agentFileStatesRef.current[agent].fileError = error;
    if (agent === selectedAgentRef.current) {
      setFileErrorState(error);
    }
  }, [selectedAgentRef]);

  // Sync function to call when agent changes
  const syncAgentFileState = useCallback((selectedAgent: AgentType) => {
    const savedState = agentFileStatesRef.current[selectedAgent];
    setAttachedFilesState(savedState.attachedFiles);
    setFileErrorState(savedState.fileError);
  }, []);

  // Trigger file input click
  const handleFileAttach = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // Handle file selection
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const currentAgent = selectedAgentRef.current;
    const currentFiles = agentFileStatesRef.current[currentAgent].attachedFiles;
    updateAgentFileError(currentAgent, null);

    for (const file of Array.from(files)) {
      // Check extension
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        updateAgentFileError(currentAgent, `Unsupported file type: ${ext}. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}`);
        continue;
      }

      // Check size based on file type
      const isBinaryFile = BINARY_EXTENSIONS.includes(ext);
      const maxSize = isBinaryFile ? MAX_BINARY_FILE_SIZE : MAX_TEXT_FILE_SIZE;
      const maxSizeLabel = isBinaryFile ? '2MB' : '500KB';

      if (file.size > maxSize) {
        updateAgentFileError(currentAgent, `File too large: ${file.name} (max ${maxSizeLabel})`);
        continue;
      }

      // Check if already attached
      if (currentFiles.some(f => f.name === file.name)) {
        updateAgentFileError(currentAgent, `File already attached: ${file.name}`);
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

        // Update state for the current agent
        const updatedFiles = [...agentFileStatesRef.current[currentAgent].attachedFiles, {
          name: file.name,
          content,
          size: content.length  // Use extracted content size
        }];
        updateAgentFiles(currentAgent, updatedFiles);
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        updateAgentFileError(currentAgent, `Failed to process file ${file.name}: ${errorMsg}`);
      }
    }

    // Reset input to allow re-selecting the same file
    if (e.target) e.target.value = '';
  }, [selectedAgentRef, updateAgentFiles, updateAgentFileError]);

  // Remove a single file
  const handleRemoveFile = useCallback((fileName: string) => {
    const currentAgent = selectedAgentRef.current;
    const updatedFiles = agentFileStatesRef.current[currentAgent].attachedFiles.filter(f => f.name !== fileName);
    updateAgentFiles(currentAgent, updatedFiles);
    updateAgentFileError(currentAgent, null);
  }, [selectedAgentRef, updateAgentFiles, updateAgentFileError]);

  // Clear all files
  const handleClearAllFiles = useCallback(() => {
    const currentAgent = selectedAgentRef.current;
    updateAgentFiles(currentAgent, []);
    updateAgentFileError(currentAgent, null);
  }, [selectedAgentRef, updateAgentFiles, updateAgentFileError]);

  // Get combined file context for API request
  const getFileContext = useCallback((): string | undefined => {
    const currentAgent = selectedAgentRef.current;
    const files = agentFileStatesRef.current[currentAgent].attachedFiles;
    if (files.length === 0) return undefined;
    return files.map(f => `=== File: ${f.name} ===\n${f.content}\n`).join('\n');
  }, [selectedAgentRef]);

  // Clear file error
  const clearFileError = useCallback(() => {
    const currentAgent = selectedAgentRef.current;
    updateAgentFileError(currentAgent, null);
  }, [selectedAgentRef, updateAgentFileError]);

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
    syncAgentFileState,
  };
}

export default useFileAttachment;
