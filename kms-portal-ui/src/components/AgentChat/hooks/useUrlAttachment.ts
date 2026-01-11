/**
 * useUrlAttachment Hook
 * Handles URL detection, fetching, and attachment logic for the AgentChat component.
 */

import { useState, useCallback } from 'react';
import { fetchUrlContent, type FetchUrlResponse } from '../../../api/agent.api';
import type { AttachedUrl } from '../types';
import { URL_REGEX } from '../constants';

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
}

export function useUrlAttachment(): UseUrlAttachmentReturn {
  const [attachedUrls, setAttachedUrls] = useState<AttachedUrl[]>([]);
  const [detectedUrl, setDetectedUrl] = useState<string | null>(null);

  // Detect URLs in input text
  const handleUrlDetect = useCallback((text: string) => {
    const matches = text.match(URL_REGEX);
    if (matches && matches.length > 0) {
      // Find the first URL that isn't already attached
      const newUrl = matches.find(url => !attachedUrls.some(au => au.url === url));
      setDetectedUrl(newUrl || null);
    } else {
      setDetectedUrl(null);
    }
  }, [attachedUrls]);

  // Fetch and attach URL content
  const handleFetchUrl = useCallback(async (url: string) => {
    // Check if already attached
    if (attachedUrls.some(au => au.url === url)) {
      setDetectedUrl(null);
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
    };
    setAttachedUrls(prev => [...prev, placeholder]);
    setDetectedUrl(null);

    try {
      const result: FetchUrlResponse = await fetchUrlContent(url);

      if (result.success) {
        setAttachedUrls(prev => prev.map(au =>
          au.url === url
            ? { ...au, title: result.title, content: result.content, charCount: result.char_count, isLoading: false }
            : au
        ));
      } else {
        setAttachedUrls(prev => prev.map(au =>
          au.url === url
            ? { ...au, isLoading: false, error: result.error || 'Failed to fetch URL' }
            : au
        ));
      }
    } catch (error) {
      console.error('Failed to fetch URL:', error);
      setAttachedUrls(prev => prev.map(au =>
        au.url === url
          ? { ...au, isLoading: false, error: error instanceof Error ? error.message : 'Unknown error' }
          : au
      ));
    }
  }, [attachedUrls]);

  // Remove attached URL
  const handleRemoveUrl = useCallback((url: string) => {
    setAttachedUrls(prev => prev.filter(au => au.url !== url));
  }, []);

  // Get URL context for API request (returns first successful URL)
  const getUrlContext = useCallback((): string | undefined => {
    const successfulUrls = attachedUrls.filter(au => au.content && !au.error);
    if (successfulUrls.length === 0) return undefined;
    // Return the first URL's content (usually we only have one URL at a time)
    // If multiple URLs, just use the first one as url_context (server-side handles truncation)
    return successfulUrls[0].url;
  }, [attachedUrls]);

  // Dismiss detected URL (without clearing attached URLs)
  const dismissDetectedUrl = useCallback(() => {
    setDetectedUrl(null);
  }, []);

  // Clear all attached URLs (for use after sending message)
  const clearAllUrls = useCallback(() => {
    setAttachedUrls([]);
    setDetectedUrl(null);
  }, []);

  return {
    attachedUrls,
    detectedUrl,
    handleUrlDetect,
    handleFetchUrl,
    handleRemoveUrl,
    getUrlContext,
    dismissDetectedUrl,
    clearAllUrls,
  };
}

export default useUrlAttachment;
