/**
 * useUrlAttachment Hook
 * Handles URL detection, fetching, and attachment logic for the AgentChat component.
 * Supports per-agent URL attachment state.
 */

import { useState, useRef, useCallback } from 'react';
import { fetchUrlContent, type FetchUrlResponse, type AgentType } from '../../../api/agent.api';
import type { AttachedUrl } from '../types';
import { URL_REGEX } from '../constants';

// Per-agent URL state
interface AgentUrlState {
  attachedUrls: AttachedUrl[];
  detectedUrl: string | null;
}

// Initialize empty state for an agent
const createInitialAgentUrlState = (): AgentUrlState => ({
  attachedUrls: [],
  detectedUrl: null,
});

export interface UseUrlAttachmentReturn {
  // State
  attachedUrls: AttachedUrl[];
  detectedUrl: string | null;

  // Actions
  handleUrlDetect: (text: string) => void;
  handleFetchUrl: (url: string) => Promise<void>;
  handleRemoveUrl: (url: string) => void;
  getUrlContext: () => string | undefined;
  dismissDetectedUrl: () => void;
  clearAllUrls: () => void;

  // Sync function (call when selectedAgent changes)
  syncAgentUrlState: (selectedAgent: AgentType) => void;
}

export function useUrlAttachment(
  selectedAgentRef: React.MutableRefObject<AgentType>
): UseUrlAttachmentReturn {
  // Per-agent state storage (persists across agent switches)
  const agentUrlStatesRef = useRef<Record<AgentType, AgentUrlState>>({
    auto: createInitialAgentUrlState(),
    rag: createInitialAgentUrlState(),
    ims: createInitialAgentUrlState(),
    vision: createInitialAgentUrlState(),
    code: createInitialAgentUrlState(),
    planner: createInitialAgentUrlState(),
  });

  // Current agent's state (React state for UI updates)
  const [attachedUrls, setAttachedUrlsState] = useState<AttachedUrl[]>([]);
  const [detectedUrl, setDetectedUrlState] = useState<string | null>(null);

  // Helper to update a specific agent's URLs
  const updateAgentUrls = useCallback((agent: AgentType, urls: AttachedUrl[]) => {
    agentUrlStatesRef.current[agent].attachedUrls = urls;
    if (agent === selectedAgentRef.current) {
      setAttachedUrlsState(urls);
    }
  }, [selectedAgentRef]);

  const updateAgentDetectedUrl = useCallback((agent: AgentType, url: string | null) => {
    agentUrlStatesRef.current[agent].detectedUrl = url;
    if (agent === selectedAgentRef.current) {
      setDetectedUrlState(url);
    }
  }, [selectedAgentRef]);

  // Sync function to call when agent changes
  const syncAgentUrlState = useCallback((selectedAgent: AgentType) => {
    const savedState = agentUrlStatesRef.current[selectedAgent];
    setAttachedUrlsState(savedState.attachedUrls);
    setDetectedUrlState(savedState.detectedUrl);
  }, []);

  // Detect URLs in input text
  const handleUrlDetect = useCallback((text: string) => {
    const currentAgent = selectedAgentRef.current;
    const currentUrls = agentUrlStatesRef.current[currentAgent].attachedUrls;

    const matches = text.match(URL_REGEX);
    if (matches && matches.length > 0) {
      // Find the first URL that isn't already attached
      const newUrl = matches.find(url => !currentUrls.some(au => au.url === url));
      updateAgentDetectedUrl(currentAgent, newUrl || null);
    } else {
      updateAgentDetectedUrl(currentAgent, null);
    }
  }, [selectedAgentRef, updateAgentDetectedUrl]);

  // Fetch and attach URL content
  const handleFetchUrl = useCallback(async (url: string) => {
    const currentAgent = selectedAgentRef.current;
    const currentUrls = agentUrlStatesRef.current[currentAgent].attachedUrls;

    // Check if already attached
    if (currentUrls.some(au => au.url === url)) {
      updateAgentDetectedUrl(currentAgent, null);
      return;
    }

    // Add placeholder with loading state
    const placeholder: AttachedUrl = {
      url,
      title: null,
      content: '',
      charCount: 0,
      isLoading: true,
      error: null,
      warning: null,
    };
    updateAgentUrls(currentAgent, [...currentUrls, placeholder]);
    updateAgentDetectedUrl(currentAgent, null);

    try {
      const result: FetchUrlResponse = await fetchUrlContent(url);

      // Get fresh state in case it changed
      const latestUrls = agentUrlStatesRef.current[currentAgent].attachedUrls;

      if (result.success) {
        const updatedUrls = latestUrls.map(au =>
          au.url === url
            ? {
                ...au,
                title: result.title,
                content: result.content,
                charCount: result.char_count,
                isLoading: false,
                warning: result.warning
              }
            : au
        );
        updateAgentUrls(currentAgent, updatedUrls);
      } else {
        const updatedUrls = latestUrls.map(au =>
          au.url === url
            ? { ...au, isLoading: false, error: result.error || 'Failed to fetch URL', warning: result.warning }
            : au
        );
        updateAgentUrls(currentAgent, updatedUrls);
      }
    } catch (error) {
      console.error('Failed to fetch URL:', error);
      const latestUrls = agentUrlStatesRef.current[currentAgent].attachedUrls;
      const updatedUrls = latestUrls.map(au =>
        au.url === url
          ? { ...au, isLoading: false, error: error instanceof Error ? error.message : 'Unknown error' }
          : au
      );
      updateAgentUrls(currentAgent, updatedUrls);
    }
  }, [selectedAgentRef, updateAgentUrls, updateAgentDetectedUrl]);

  // Remove attached URL
  const handleRemoveUrl = useCallback((url: string) => {
    const currentAgent = selectedAgentRef.current;
    const updatedUrls = agentUrlStatesRef.current[currentAgent].attachedUrls.filter(au => au.url !== url);
    updateAgentUrls(currentAgent, updatedUrls);
  }, [selectedAgentRef, updateAgentUrls]);

  // Get URL context for API request (returns combined content from all successful URLs)
  const getUrlContext = useCallback((): string | undefined => {
    const currentAgent = selectedAgentRef.current;
    const urls = agentUrlStatesRef.current[currentAgent].attachedUrls;
    const successfulUrls = urls.filter(au => au.content && !au.error);
    if (successfulUrls.length === 0) return undefined;

    // Combine all URL contents with headers (similar to file attachments)
    const contextParts = successfulUrls.map(au => {
      const title = au.title || au.url;
      return `=== URL: ${title} (${au.url}) ===\n${au.content}`;
    });

    return contextParts.join('\n\n');
  }, [selectedAgentRef]);

  // Dismiss detected URL (without clearing attached URLs)
  const dismissDetectedUrl = useCallback(() => {
    const currentAgent = selectedAgentRef.current;
    updateAgentDetectedUrl(currentAgent, null);
  }, [selectedAgentRef, updateAgentDetectedUrl]);

  // Clear all attached URLs (for use after sending message)
  const clearAllUrls = useCallback(() => {
    const currentAgent = selectedAgentRef.current;
    updateAgentUrls(currentAgent, []);
    updateAgentDetectedUrl(currentAgent, null);
  }, [selectedAgentRef, updateAgentUrls, updateAgentDetectedUrl]);

  return {
    attachedUrls,
    detectedUrl,
    handleUrlDetect,
    handleFetchUrl,
    handleRemoveUrl,
    getUrlContext,
    dismissDetectedUrl,
    clearAllUrls,
    syncAgentUrlState,
  };
}

export default useUrlAttachment;
