/**
 * useStreamingChat Hook
 * Handles streaming chat logic for multi-agent conversations.
 *
 * Features:
 * - Per-agent message state management
 * - Streaming response processing
 * - Tool call tracking
 * - Source document handling
 * - Abort/cancel functionality
 * - Database persistence
 */

import { useState, useRef, useCallback } from 'react';
import { streamAgent, type AgentType } from '../../../api/agent.api';
import { conversationApi } from '../../../api/conversation.api';
import type { ChatMessage, ToolCallInfo, AgentLocalState, AgentSource } from '../types';

// ============================================================================
// Types
// ============================================================================

// Language type for API requests
type SupportedLanguage = 'en' | 'ko' | 'ja' | 'auto';

export interface StreamingChatDependencies {
  // Translation
  t: (key: string) => string;
  userLanguage: string;

  // Conversation store operations
  agentStates: Record<AgentType, { activeConversationId: string | null }>;
  createConversation: (agentType: AgentType, title: string) => Promise<{ id: string }>;
  loadConversations: (agentType: AgentType) => void;

  // Artifact operations (using any for flexibility with store types)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addArtifact: (agentType: AgentType, artifact: any) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createArtifactFromChunk: (chunk: any) => any;

  // Context getters
  getFileContext: () => string | undefined;
  getUrlContext: () => string | undefined;

  // IMS credentials callback
  onCredentialsRequired: (query: string) => void;

  // URL cleanup callback
  onMessageSent: () => void;
}

export interface UseStreamingChatReturn {
  // Current agent state (synced with selectedAgent)
  messages: ChatMessage[];
  streamingMessage: ChatMessage | null;
  isLoading: boolean;
  abortController: AbortController | null;

  // State updaters for specific agent
  updateAgentMessages: (agent: AgentType, updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  updateAgentStreamingMessage: (agent: AgentType, msg: ChatMessage | null) => void;
  updateAgentIsLoading: (agent: AgentType, loading: boolean) => void;
  updateAgentAbortController: (agent: AgentType, controller: AbortController | null) => void;

  // Wrapper functions for current agent
  setMessages: (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  setStreamingMessage: (msg: ChatMessage | null) => void;
  setIsLoading: (loading: boolean) => void;

  // Agent state ref (for accessing background agent states)
  agentLocalStatesRef: React.MutableRefObject<Record<AgentType, AgentLocalState>>;

  // Actions
  handleSend: (inputValue: string) => Promise<void>;
  handleCancelStreaming: () => void;
  handleClearChat: (clearArtifacts: (agent: AgentType) => void) => void;
  saveMessageToDb: (conversationId: string, role: 'user' | 'assistant', content: string) => Promise<void>;

  // Sync function (call when selectedAgent changes)
  syncAgentState: (selectedAgent: AgentType) => void;
}

// Initial state for each agent
const createInitialAgentState = (): AgentLocalState => ({
  messages: [],
  streamingMessage: null,
  isLoading: false,
  abortController: null,
});

// ============================================================================
// Hook
// ============================================================================

export function useStreamingChat(
  selectedAgentRef: React.MutableRefObject<AgentType>,
  deps: StreamingChatDependencies
): UseStreamingChatReturn {
  const {
    t,
    userLanguage,
    agentStates,
    createConversation,
    loadConversations,
    addArtifact,
    createArtifactFromChunk,
    getFileContext,
    getUrlContext,
    onCredentialsRequired,
    onMessageSent,
  } = deps;

  // Per-agent state storage (persists across agent switches)
  const agentLocalStatesRef = useRef<Record<AgentType, AgentLocalState>>({
    auto: createInitialAgentState(),
    rag: createInitialAgentState(),
    ims: createInitialAgentState(),
    vision: createInitialAgentState(),
    code: createInitialAgentState(),
    planner: createInitialAgentState(),
  });

  // Current agent's state (React state for UI updates)
  const [messages, setMessagesState] = useState<ChatMessage[]>([]);
  const [streamingMessage, setStreamingMessageState] = useState<ChatMessage | null>(null);
  const [isLoading, setIsLoadingState] = useState(false);
  const [abortController, setAbortControllerState] = useState<AbortController | null>(null);

  // ============================================================================
  // State Updaters (update specific agent's state)
  // ============================================================================

  const updateAgentMessages = useCallback((targetAgent: AgentType, updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    const prev = agentLocalStatesRef.current[targetAgent].messages;
    const newValue = typeof updater === 'function' ? updater(prev) : updater;
    agentLocalStatesRef.current[targetAgent].messages = newValue;
    // Only update React state if this is the currently selected agent
    if (targetAgent === selectedAgentRef.current) {
      setMessagesState(newValue);
    }
  }, [selectedAgentRef]);

  const updateAgentStreamingMessage = useCallback((targetAgent: AgentType, msg: ChatMessage | null) => {
    agentLocalStatesRef.current[targetAgent].streamingMessage = msg;
    if (targetAgent === selectedAgentRef.current) {
      setStreamingMessageState(msg);
    }
  }, [selectedAgentRef]);

  const updateAgentIsLoading = useCallback((targetAgent: AgentType, loading: boolean) => {
    agentLocalStatesRef.current[targetAgent].isLoading = loading;
    if (targetAgent === selectedAgentRef.current) {
      setIsLoadingState(loading);
    }
  }, [selectedAgentRef]);

  const updateAgentAbortController = useCallback((targetAgent: AgentType, controller: AbortController | null) => {
    agentLocalStatesRef.current[targetAgent].abortController = controller;
    if (targetAgent === selectedAgentRef.current) {
      setAbortControllerState(controller);
    }
  }, [selectedAgentRef]);

  // ============================================================================
  // Wrapper functions (operate on current selected agent)
  // ============================================================================

  const setMessages = useCallback((updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    updateAgentMessages(selectedAgentRef.current, updater);
  }, [selectedAgentRef, updateAgentMessages]);

  const setStreamingMessage = useCallback((msg: ChatMessage | null) => {
    updateAgentStreamingMessage(selectedAgentRef.current, msg);
  }, [selectedAgentRef, updateAgentStreamingMessage]);

  const setIsLoading = useCallback((loading: boolean) => {
    updateAgentIsLoading(selectedAgentRef.current, loading);
  }, [selectedAgentRef, updateAgentIsLoading]);

  // ============================================================================
  // Sync function (call when selectedAgent changes)
  // ============================================================================

  const syncAgentState = useCallback((selectedAgent: AgentType) => {
    const savedState = agentLocalStatesRef.current[selectedAgent];
    setMessagesState(savedState.messages);
    setStreamingMessageState(savedState.streamingMessage);
    setIsLoadingState(savedState.isLoading);
    setAbortControllerState(savedState.abortController);
  }, []);

  // ============================================================================
  // Database Operations
  // ============================================================================

  const saveMessageToDb = useCallback(async (
    conversationId: string,
    role: 'user' | 'assistant',
    content: string
  ) => {
    try {
      await conversationApi.addMessage(conversationId, { role, content });
      console.log('[useStreamingChat] Message saved to conversation:', conversationId);
    } catch (error) {
      console.error('[useStreamingChat] Failed to save message:', error);
    }
  }, []);

  // ============================================================================
  // Stream Processing
  // ============================================================================

  const handleSend = useCallback(async (inputValue: string) => {
    if (!inputValue.trim() || agentLocalStatesRef.current[selectedAgentRef.current].isLoading) return;

    // Capture agent type at start (won't change during streaming)
    const requestingAgent = selectedAgentRef.current;
    const requestingAgentConversationId = agentStates[requestingAgent]?.activeConversationId || null;

    // Create user message
    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    updateAgentMessages(requestingAgent, (prev) => [...prev, userMessage]);
    updateAgentIsLoading(requestingAgent, true);

    // Notify parent to clear URLs
    onMessageSent();

    // Get or create conversation for auto-save
    let conversationId = requestingAgentConversationId;
    if (!conversationId) {
      try {
        const title = userMessage.content.slice(0, 50) + (userMessage.content.length > 50 ? '...' : '');
        const conversation = await createConversation(requestingAgent, title);
        conversationId = conversation.id;
        console.log('[useStreamingChat] Created new conversation:', conversationId);
      } catch (error) {
        console.error('[useStreamingChat] Failed to create conversation:', error);
      }
    }

    // Save user message to database
    if (conversationId) {
      saveMessageToDb(conversationId, 'user', userMessage.content);
    }

    // Create streaming message placeholder
    const assistantMessageId = `msg-${Date.now()}-assistant`;
    const streamingMsg: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: t('common.agent.status.analyzing') || 'Analyzing your request...',
      timestamp: new Date(),
      agentType: requestingAgent,
      toolCalls: [],
      sources: [],
      isStreaming: true,
    };
    updateAgentStreamingMessage(requestingAgent, streamingMsg);

    // Create abort controller
    const controller = new AbortController();
    updateAgentAbortController(requestingAgent, controller);

    try {
      let accumulatedContent = '';
      const toolCalls: ToolCallInfo[] = [];
      let sources: AgentSource[] = [];
      let receivedAnyChunk = false;

      console.log('[useStreamingChat] Starting stream for task:', userMessage.content, 'agent:', requestingAgent);

      // Build request payload
      const fileContext = getFileContext();
      const urlContext = getUrlContext();
      // Combine file and URL contexts into file_context
      // (url_context field is for URLs that backend will fetch, but we already have content)
      const combinedContext = [fileContext, urlContext].filter(Boolean).join('\n\n') || undefined;

      // Cast language to supported type (validated by UI)
      const language = userLanguage as SupportedLanguage;
      const requestPayload = requestingAgent === 'auto'
        ? { task: userMessage.content, language, file_context: combinedContext }
        : { task: userMessage.content, agent_type: requestingAgent, language, file_context: combinedContext };

      // Process stream
      for await (const chunk of streamAgent(requestPayload, controller.signal)) {
        receivedAnyChunk = true;
        console.log('[useStreamingChat] Received chunk:', chunk.chunk_type, chunk);

        switch (chunk.chunk_type) {
          case 'thinking':
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: chunk.content || 'Analyzing...' }
                : null
            );
            break;

          case 'tool_call':
            if (chunk.tool_name) {
              toolCalls.push({
                name: chunk.tool_name,
                input: chunk.tool_input || {},
                status: 'pending',
              });
              updateAgentStreamingMessage(requestingAgent,
                agentLocalStatesRef.current[requestingAgent].streamingMessage
                  ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, toolCalls: [...toolCalls] }
                  : null
              );
            }
            break;

          case 'tool_result':
            if (chunk.tool_name) {
              const toolIndex = toolCalls.findIndex((tc) => tc.name === chunk.tool_name && tc.status === 'pending');
              if (toolIndex !== -1) {
                toolCalls[toolIndex] = {
                  ...toolCalls[toolIndex],
                  output: chunk.tool_output || '',
                  status: chunk.tool_output?.includes('error') || chunk.tool_output?.includes('Error')
                    ? 'error'
                    : 'success',
                };
                updateAgentStreamingMessage(requestingAgent,
                  agentLocalStatesRef.current[requestingAgent].streamingMessage
                    ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, toolCalls: [...toolCalls] }
                    : null
                );
              }
            }
            break;

          case 'text':
            accumulatedContent += chunk.content || '';
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: accumulatedContent }
                : null
            );
            break;

          case 'sources':
            sources = chunk.sources || [];
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, sources }
                : null
            );
            break;

          case 'artifact':
            if (chunk.artifact_id && chunk.artifact_type && chunk.content) {
              const artifact = createArtifactFromChunk({
                artifact_id: chunk.artifact_id,
                artifact_type: chunk.artifact_type,
                artifact_title: chunk.artifact_title,
                artifact_language: chunk.artifact_language,
                content: chunk.content,
                metadata: chunk.metadata,
                messageId: assistantMessageId,
              });

              if (artifact) {
                addArtifact(requestingAgent, artifact);
              }
            }
            break;

          case 'status':
            if (chunk.content) {
              const statusKey = chunk.content as 'crawling' | 'ready' | 'searching' | 'processing' | 'credentials_required';

              if (statusKey === 'credentials_required') {
                onCredentialsRequired(userMessage.content);
                updateAgentIsLoading(requestingAgent, false);
                updateAgentStreamingMessage(requestingAgent, null);
                return;
              }

              const statusMsg: ChatMessage = {
                id: `status-${Date.now()}`,
                role: 'status',
                content: statusKey,
                timestamp: new Date(),
                statusType: statusKey === 'crawling' ? 'crawling' : 'ready',
              };
              updateAgentMessages(requestingAgent, (prev) => [...prev, statusMsg]);
            }
            break;

          case 'error':
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? {
                    ...agentLocalStatesRef.current[requestingAgent].streamingMessage!,
                    content: chunk.content || 'An error occurred',
                    error: chunk.content || 'Unknown error',
                    isStreaming: false,
                  }
                : null
            );
            break;

          case 'done':
            updateAgentMessages(requestingAgent, (prev) => prev.filter(msg =>
              !(msg.role === 'status' &&
                (msg.content === 'processing' || msg.content === 'crawling' || msg.content === 'searching'))
            ));
            break;
        }
      }

      if (!receivedAnyChunk) {
        console.warn('[useStreamingChat] No chunks received from stream');
      }

      // Finalize message
      const finalMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: accumulatedContent || (receivedAnyChunk ? 'No content in response.' : 'Failed to get response from server.'),
        timestamp: new Date(),
        agentType: requestingAgent,
        toolCalls,
        sources,
        isStreaming: false,
      };

      console.log('[useStreamingChat] Final message:', finalMessage);
      updateAgentMessages(requestingAgent, (prev) => [
        ...prev.filter(msg =>
          !(msg.role === 'status' &&
            (msg.content === 'processing' || msg.content === 'crawling' || msg.content === 'searching'))
        ),
        finalMessage
      ]);
      updateAgentStreamingMessage(requestingAgent, null);

      // Save assistant response to database
      if (conversationId && accumulatedContent) {
        saveMessageToDb(conversationId, 'assistant', accumulatedContent);
        loadConversations(requestingAgent);
      }
    } catch (error) {
      console.error('[useStreamingChat] Stream error:', error);
      if (error instanceof Error && error.name === 'AbortError') {
        updateAgentStreamingMessage(requestingAgent, null);
      } else {
        console.error('Agent chat error:', error);
        const errorMessage: ChatMessage = {
          id: assistantMessageId,
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
          agentType: requestingAgent,
          error: error instanceof Error ? error.message : 'Unknown error',
          isStreaming: false,
        };
        updateAgentMessages(requestingAgent, (prev) => [...prev, errorMessage]);
        updateAgentStreamingMessage(requestingAgent, null);
      }
    } finally {
      updateAgentIsLoading(requestingAgent, false);
      updateAgentAbortController(requestingAgent, null);
    }
  }, [
    selectedAgentRef,
    agentStates,
    createConversation,
    loadConversations,
    saveMessageToDb,
    t,
    userLanguage,
    addArtifact,
    createArtifactFromChunk,
    getFileContext,
    getUrlContext,
    onCredentialsRequired,
    onMessageSent,
    updateAgentMessages,
    updateAgentStreamingMessage,
    updateAgentIsLoading,
    updateAgentAbortController,
  ]);

  // ============================================================================
  // Cancel Streaming
  // ============================================================================

  const handleCancelStreaming = useCallback(() => {
    const currentAbortController = agentLocalStatesRef.current[selectedAgentRef.current].abortController;
    if (currentAbortController) {
      currentAbortController.abort();
      updateAgentIsLoading(selectedAgentRef.current, false);
      updateAgentStreamingMessage(selectedAgentRef.current, null);
    }
  }, [selectedAgentRef, updateAgentIsLoading, updateAgentStreamingMessage]);

  // ============================================================================
  // Clear Chat
  // ============================================================================

  const handleClearChat = useCallback((clearArtifacts: (agent: AgentType) => void) => {
    const currentAbortController = agentLocalStatesRef.current[selectedAgentRef.current].abortController;
    if (currentAbortController) {
      currentAbortController.abort();
    }
    setMessages([]);
    setStreamingMessage(null);
    clearArtifacts(selectedAgentRef.current);
  }, [selectedAgentRef, setMessages, setStreamingMessage]);

  // ============================================================================
  // Return
  // ============================================================================

  return {
    // Current agent state
    messages,
    streamingMessage,
    isLoading,
    abortController,

    // State updaters for specific agent
    updateAgentMessages,
    updateAgentStreamingMessage,
    updateAgentIsLoading,
    updateAgentAbortController,

    // Wrapper functions for current agent
    setMessages,
    setStreamingMessage,
    setIsLoading,

    // Agent state ref
    agentLocalStatesRef,

    // Actions
    handleSend,
    handleCancelStreaming,
    handleClearChat,
    saveMessageToDb,

    // Sync function
    syncAgentState,
  };
}

export default useStreamingChat;
