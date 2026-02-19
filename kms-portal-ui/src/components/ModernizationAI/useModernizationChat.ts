/**
 * useModernizationChat - SSE streaming hook for Modernization AI chat.
 *
 * Integrates with PostgreSQL conversation persistence:
 * - Receives conversation_id from SSE stream
 * - Loads past conversations via conversation API
 * - Supports "new conversation" flow
 */

import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../../config/constants';
import { conversationApi } from '../../api/conversation.api';
import type { ConversationListItem, ConversationMessage } from '../../api/conversation.api';
import type {
  ChatMessage,
  ChatSource,
  ChatSection,
  SystemType,
  SSEEvent,
  AnalysisContextInfo,
} from './types';

let messageCounter = 0;
function generateId(): string {
  return `mod-msg-${Date.now()}-${++messageCounter}`;
}

const AGENT_TYPE = 'modernization';

export function useModernizationChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sources, setSources] = useState<ChatSource[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  /**
   * Load conversation list from DB
   */
  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const result = await conversationApi.list({
        agent_type: AGENT_TYPE as never,
        limit: 50,
      });
      setConversations(result.conversations);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  /**
   * Load a specific conversation's messages from DB
   */
  const loadConversation = useCallback(async (convId: string) => {
    try {
      const detail = await conversationApi.get(convId);
      setConversationId(convId);

      // Convert DB messages to ChatMessage format
      const chatMessages: ChatMessage[] = detail.messages.map(
        (m: ConversationMessage) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: new Date(m.created_at).getTime(),
          systemType: 'host' as SystemType, // Default; metadata could refine this
          sources: m.sources
            ? m.sources.map((s: { content?: string; source?: string; title?: string; url?: string }) => ({
                title: s.title || s.source || 'Source',
                url: s.url,
                snippet: s.content,
              }))
            : undefined,
        })
      );

      setMessages(chatMessages);

      // Collect sources
      const allSources: ChatSource[] = [];
      for (const m of detail.messages) {
        if (m.sources) {
          for (const s of m.sources) {
            allSources.push({
              title: (s as { title?: string; source?: string }).title || (s as { source?: string }).source || 'Source',
              url: (s as { url?: string }).url,
              snippet: (s as { content?: string }).content,
            });
          }
        }
      }
      setSources(allSources);
    } catch (err) {
      console.error('Failed to load conversation:', err);
    }
  }, []);

  /**
   * Start a new conversation (clear current state)
   */
  const newConversation = useCallback(() => {
    setMessages([]);
    setSources([]);
    setConversationId(null);
  }, []);

  /**
   * Delete a conversation
   */
  const deleteConversation = useCallback(async (convId: string) => {
    try {
      await conversationApi.delete(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (conversationId === convId) {
        newConversation();
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  }, [conversationId, newConversation]);

  const sendMessage = useCallback(
    async (
      text: string,
      systemType: SystemType,
      language: string,
      analysisContext?: AnalysisContextInfo
    ) => {
      if (!text.trim() || isStreaming) return;

      // Add user message
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: text.trim(),
        timestamp: Date.now(),
        systemType,
      };

      // Prepare assistant message placeholder
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        systemType,
        sources: [],
        sections: systemType === 'all' ? [] : undefined,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const body: Record<string, unknown> = {
          message: text.trim(),
          system_type: systemType,
          language,
        };
        // Include conversation_id for continuation
        if (conversationId) {
          body.conversation_id = conversationId;
        }
        if (analysisContext) {
          body.analysis_context = {
            analysis_id: analysisContext.analysisId,
            file_name: analysisContext.fileName,
            asset_type: analysisContext.assetType,
            source_code_snippet: analysisContext.sourceCodeSnippet,
            target_product: analysisContext.targetProduct,
          };
        }

        const response = await fetch(`${API_BASE_URL}/legacy/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        let currentSectionContent = '';
        let currentSectionSystem = '';
        let currentSectionLabel = '';
        const accumulatedSources: ChatSource[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;

            try {
              const event: SSEEvent = JSON.parse(trimmed.slice(6));

              // Handle conversation_id event from backend
              if (event.type === 'conversation_id' && event.conversation_id) {
                setConversationId(event.conversation_id as string);
                continue;
              }

              handleSSEEvent(
                event,
                assistantMsg.id,
                systemType,
                accumulatedSources,
                { currentSectionContent, currentSectionSystem, currentSectionLabel },
                (content) => { currentSectionContent = content; },
                (system) => { currentSectionSystem = system; },
                (label) => { currentSectionLabel = label; },
              );
            } catch {
              // skip malformed lines
            }
          }
        }

        // Update aggregated sources
        if (accumulatedSources.length > 0) {
          setSources((prev) => [...prev, ...accumulatedSources]);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          // User cancelled
        } else {
          const errorMsg = err instanceof Error ? err.message : 'Unknown error';
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content || `Error: ${errorMsg}` }
                : m
            )
          );
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming, conversationId]
  );

  function handleSSEEvent(
    event: SSEEvent,
    assistantId: string,
    systemType: SystemType,
    accumulatedSources: ChatSource[],
    sectionState: {
      currentSectionContent: string;
      currentSectionSystem: string;
      currentSectionLabel: string;
    },
    setSectionContent: (v: string) => void,
    setSectionSystem: (v: string) => void,
    setSectionLabel: (v: string) => void,
  ) {
    switch (event.type) {
      case 'llm_token':
        if (systemType === 'all' && sectionState.currentSectionSystem) {
          // In ALL mode, accumulate per section
          setSectionContent(sectionState.currentSectionContent + (event.token || ''));
          // Also update the message content for display
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + (event.token || '') }
                : m
            )
          );
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + (event.token || '') }
                : m
            )
          );
        }
        break;

      case 'section_start':
        setSectionSystem(event.source_system || '');
        setSectionLabel(event.label || '');
        setSectionContent('');
        // Add section marker to content
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: m.content + `\n\n### ${event.label || event.source_system}\n\n`,
                }
              : m
          )
        );
        break;

      case 'section_end': {
        const section: ChatSection = {
          sourceSystem: (sectionState.currentSectionSystem as 'host' | 'openframe') || 'host',
          label: sectionState.currentSectionLabel,
          content: sectionState.currentSectionContent,
        };
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, sections: [...(m.sections || []), section] }
              : m
          )
        );
        setSectionSystem('');
        setSectionLabel('');
        setSectionContent('');
        break;
      }

      case 'sources':
        if (event.sources) {
          accumulatedSources.push(...event.sources);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, sources: [...(m.sources || []), ...event.sources!] }
                : m
            )
          );
        }
        break;

      case 'error':
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: m.content + `\n\n**Error:** ${event.message || 'Unknown error'}` }
              : m
          )
        );
        break;

      // system_info, done, conversation_id - no visible action needed
    }
  }

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSources([]);
    setConversationId(null);
  }, []);

  return {
    messages,
    isStreaming,
    sources,
    conversationId,
    conversations,
    loadingConversations,
    sendMessage,
    cancelStream,
    clearMessages,
    loadConversations,
    loadConversation,
    newConversation,
    deleteConversation,
  };
}
