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
import type {
  ChatMessage,
  ToolCallInfo,
  AgentLocalState,
  AgentSource,
  ImageReference,
  SearchToolResult,
  SearchResultItem,
  RagAnalysis,
  ChunkStructure,
  EmbeddingInfo,
  GenerationProgress,
  ExpandableSearchResult
} from '../types';

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
  // Optional callback to clear invalid conversation (called on 403/404)
  clearActiveConversation?: (agentType: AgentType) => void;

  // Artifact operations (using any for flexibility with store types)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addArtifact: (agentType: AgentType, artifact: any) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createArtifactFromChunk: (chunk: any) => any;

  // Context getters
  getFileContext: () => string | undefined;
  getUrlContext: () => string | undefined;
  // External resources context from connected services (Notion, Confluence, etc.)
  getExternalResourcesContext?: () => string | undefined;
  // UI context for context-aware AI (optional, from contextStore)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getUIContext?: () => any;

  // IMS credentials callback
  onCredentialsRequired: (query: string) => void;

  // URL cleanup callback
  onMessageSent: () => void;

  // Trace data callback for visualization (accepts any shape, store will validate)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onTraceData?: (traceData: any) => void;
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

  // Search progress state for RAG knowledge search visualization
  searchProgress: {
    isOpen: boolean;
    currentQuery: string;
    toolResults: SearchToolResult[];
  };
  setSearchProgressOpen: (open: boolean) => void;

  // RAG detailed progress state (5 sections)
  ragProgress: {
    ragAnalysis: RagAnalysis | null;
    chunkStructures: ChunkStructure[];
    embeddingInfos: EmbeddingInfo[];
    generationProgress: GenerationProgress | null;
    isGenerating: boolean;
  };
}

// Initial state for each agent
const createInitialAgentState = (): AgentLocalState => ({
  messages: [],
  streamingMessage: null,
  isLoading: false,
  abortController: null,
});

// Search tools to track for progress visualization
const SEARCH_TOOLS = ['adaptive_search', 'vector_search', 'graph_query', 'document_read'];

// Parse tool output to extract result items
const parseToolOutput = (toolName: string, output: string): { resultCount: number; results: SearchResultItem[] } => {
  const results: SearchResultItem[] = [];
  let resultCount = 0;

  try {
    // Try to parse as JSON first
    const parsed = JSON.parse(output);
    if (Array.isArray(parsed)) {
      resultCount = parsed.length;
      results.push(...parsed.slice(0, 10).map((item: Record<string, unknown>) => ({
        title: (item.title as string) || (item.chunk_type as string) || toolName,
        content: (item.content as string) || (item.text as string) || '',
        similarity: item.similarity as number | undefined,
        source: (item.source as string) || (item.document_name as string),
        page: item.page_number as number | undefined,
        chunkType: item.chunk_type as string | undefined,
      })));
    } else if (parsed.results && Array.isArray(parsed.results)) {
      resultCount = parsed.results.length;
      results.push(...parsed.results.slice(0, 10).map((item: Record<string, unknown>) => ({
        title: (item.title as string) || (item.chunk_type as string) || toolName,
        content: (item.content as string) || (item.text as string) || '',
        similarity: item.similarity as number | undefined,
        source: (item.source as string) || (item.document_name as string),
        page: item.page_number as number | undefined,
        chunkType: item.chunk_type as string | undefined,
      })));
    }
  } catch {
    // If not JSON, try to count results from text
    const matches = output.match(/found\s+(\d+)\s+results?/i);
    if (matches) {
      resultCount = parseInt(matches[1], 10);
    }
    // Also check for "N건" Korean format or "N results" pattern
    const countMatches = output.match(/(\d+)\s*(건|results?|개)/i);
    if (countMatches) {
      resultCount = parseInt(countMatches[1], 10);
    }
  }

  return { resultCount, results };
};

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
    clearActiveConversation,
    addArtifact,
    createArtifactFromChunk,
    getFileContext,
    getUrlContext,
    getExternalResourcesContext,
    getUIContext,
    onCredentialsRequired,
    onMessageSent,
    onTraceData,
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

  // Search progress state for RAG knowledge search visualization
  const [searchProgressOpen, setSearchProgressOpen] = useState(false);
  const [searchCurrentQuery, setSearchCurrentQuery] = useState('');
  const [searchToolResults, setSearchToolResults] = useState<SearchToolResult[]>([]);
  const searchToolResultsRef = useRef<SearchToolResult[]>([]);

  // RAG detailed progress state (5 sections)
  const [ragAnalysis, setRagAnalysis] = useState<RagAnalysis | null>(null);
  const [chunkStructures, setChunkStructures] = useState<ChunkStructure[]>([]);
  const [embeddingInfos, setEmbeddingInfos] = useState<EmbeddingInfo[]>([]);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

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
    content: string,
    agentType?: AgentType
  ) => {
    try {
      await conversationApi.addMessage(conversationId, { role, content });
      console.log('[useStreamingChat] Message saved to conversation:', conversationId);
    } catch (error) {
      // Check if error is 403/404 (conversation not found or access denied)
      const axiosError = error as { response?: { status?: number } };
      const status = axiosError.response?.status;

      if ((status === 403 || status === 404) && agentType && clearActiveConversation) {
        console.warn('[useStreamingChat] Conversation not found or access denied, clearing active conversation');
        clearActiveConversation(agentType);
      } else {
        console.error('[useStreamingChat] Failed to save message:', error);
      }
    }
  }, [clearActiveConversation]);

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
      saveMessageToDb(conversationId, 'user', userMessage.content, requestingAgent);
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

    // Reset search progress state for new request
    searchToolResultsRef.current = [];
    setSearchToolResults([]);
    setSearchCurrentQuery(userMessage.content);
    // Don't auto-open yet, will open when first search tool is called

    // Reset RAG detailed progress state
    setRagAnalysis(null);
    setChunkStructures([]);
    setEmbeddingInfos([]);
    setGenerationProgress(null);
    setIsGenerating(false);

    try {
      let accumulatedContent = '';
      const toolCalls: ToolCallInfo[] = [];
      let sources: AgentSource[] = [];
      const images: ImageReference[] = [];
      const searchResults: ExpandableSearchResult[] = [];
      let receivedAnyChunk = false;

      console.log('[useStreamingChat] Starting stream for task:', userMessage.content, 'agent:', requestingAgent);

      // Build request payload
      const fileContext = getFileContext();
      const urlContext = getUrlContext();
      const externalContext = getExternalResourcesContext ? getExternalResourcesContext() : undefined;
      // Combine file, URL, and external resource contexts into file_context
      // (url_context field is for URLs that backend will fetch, but we already have content)
      const combinedContext = [fileContext, urlContext, externalContext].filter(Boolean).join('\n\n') || undefined;

      // Get UI context for context-aware AI (if available)
      const uiContext = getUIContext ? getUIContext() : undefined;

      // Cast language to supported type (validated by UI)
      const language = userLanguage as SupportedLanguage;
      // 모든 에이전트에서 Deep Agents 사용
      const useDeepAgent = true;
      const requestPayload = requestingAgent === 'auto'
        ? { task: userMessage.content, language, file_context: combinedContext, ui_context: uiContext, use_deep_agent: useDeepAgent }
        : { task: userMessage.content, agent_type: requestingAgent, language, file_context: combinedContext, ui_context: uiContext, use_deep_agent: useDeepAgent };

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

              // Track search tool progress
              if (SEARCH_TOOLS.includes(chunk.tool_name)) {
                const newToolResult: SearchToolResult = {
                  toolName: chunk.tool_name,
                  status: 'running',
                  startTime: Date.now(),
                  input: chunk.tool_input || {},
                };
                searchToolResultsRef.current = [...searchToolResultsRef.current, newToolResult];
                setSearchToolResults([...searchToolResultsRef.current]);
                // Auto-open progress modal when search starts
                if (!searchProgressOpen) {
                  setSearchProgressOpen(true);
                }
              }
            }
            break;

          case 'tool_result':
            if (chunk.tool_name) {
              // Extract query correction info from metadata (shared by both blocks)
              const metadata = chunk.metadata as { query_corrected?: boolean; original_llm_query?: string; corrected_query?: string } | undefined;

              const toolIndex = toolCalls.findIndex((tc) => tc.name === chunk.tool_name && tc.status === 'pending');
              if (toolIndex !== -1) {
                toolCalls[toolIndex] = {
                  ...toolCalls[toolIndex],
                  output: chunk.tool_output || '',
                  status: chunk.tool_output?.includes('error') || chunk.tool_output?.includes('Error')
                    ? 'error'
                    : 'success',
                  // Add query correction info if present
                  queryCorrected: metadata?.query_corrected,
                  originalLlmQuery: metadata?.original_llm_query,
                  correctedQuery: metadata?.corrected_query,
                };
                updateAgentStreamingMessage(requestingAgent,
                  agentLocalStatesRef.current[requestingAgent].streamingMessage
                    ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, toolCalls: [...toolCalls] }
                    : null
                );
              }

              // Update search tool progress
              if (SEARCH_TOOLS.includes(chunk.tool_name)) {
                const searchToolIndex = searchToolResultsRef.current.findIndex(
                  (st) => st.toolName === chunk.tool_name && st.status === 'running'
                );
                if (searchToolIndex !== -1) {
                  const output = chunk.tool_output || '';
                  const hasError = output.includes('error') || output.includes('Error');
                  const { resultCount, results } = parseToolOutput(chunk.tool_name, output);

                  searchToolResultsRef.current[searchToolIndex] = {
                    ...searchToolResultsRef.current[searchToolIndex],
                    status: hasError ? 'error' : 'success',
                    endTime: Date.now(),
                    output: output,
                    resultCount,
                    results,
                    error: hasError ? output : undefined,
                    queryCorrected: metadata?.query_corrected,
                    originalQuery: metadata?.original_llm_query,
                    correctedQuery: metadata?.corrected_query,
                  };
                  setSearchToolResults([...searchToolResultsRef.current]);
                }
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
            console.log('[useStreamingChat] Sources chunk received:', chunk);
            console.log('[useStreamingChat] Sources data:', chunk.sources);
            sources = chunk.sources || [];
            console.log('[useStreamingChat] Sources assigned:', sources.length, 'items');
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

          case 'image':
            // Handle figure reference images from document
            if (chunk.metadata) {
              const meta = chunk.metadata as Record<string, string | number | undefined>;
              const imageId = (meta.image_id as string) || `img-${Date.now()}`;

              // Skip duplicate images (check by imageId)
              if (images.some(img => img.imageId === imageId)) {
                console.log('[useStreamingChat] Skipping duplicate image:', imageId);
                break;
              }

              const imageRef: ImageReference = {
                imageId,
                documentId: (meta.document_id as string) || '',
                pageNumber: meta.page_number as number | undefined,
                description: (meta.figure_caption as string) || (meta.description as string),
                figureReference: meta.figure_reference as string | undefined,
                figureCaption: meta.figure_caption as string | undefined,
                imageBase64: meta.data as string | undefined,  // Already in data:mime;base64,xxx format
                mimeType: meta.mime_type as string | undefined,
                width: meta.width as number | undefined,
                height: meta.height as number | undefined,
              };
              images.push(imageRef);
              console.log('[useStreamingChat] Received image:', imageRef.figureReference);

              // Update streaming message with new images array
              updateAgentStreamingMessage(requestingAgent,
                agentLocalStatesRef.current[requestingAgent].streamingMessage
                  ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, images: [...images] }
                  : null
              );
            }
            break;

          case 'search_result':
            // Individual search result for expandable card display
            {
              // Parse source data from snake_case to camelCase
              const sourceData = chunk.result_source as Record<string, unknown> | undefined;
              const searchResult: ExpandableSearchResult = {
                index: chunk.result_index || searchResults.length + 1,
                total: chunk.result_total || 0,
                title: chunk.result_title || '',
                content: chunk.result_content || '',
                images: (chunk.result_images || []).map((img: Record<string, unknown>) => ({
                  imageId: img.image_id as string,
                  documentId: img.document_id as string | undefined,
                  pageNumber: img.page_number as number | undefined,
                  similarity: img.similarity as number | undefined,
                  url: img.url as string,
                })),
                tables: (chunk.result_tables || []).map((tbl: Record<string, unknown>) => ({
                  markdown: tbl.markdown as string,
                })),
                source: {
                  documentName: (sourceData?.document_name as string) || '',
                  pageStart: sourceData?.page_start as number | undefined,
                  pageEnd: sourceData?.page_end as number | undefined,
                  sectionPath: sourceData?.section_path as string | undefined,
                  sectionTitle: sourceData?.section_title as string | undefined,
                  docId: sourceData?.doc_id as string | undefined,
                },
                score: chunk.result_score || 0,
                chunkId: (chunk.metadata as Record<string, unknown>)?.chunk_id as string | undefined,
                chunkType: (chunk.metadata as Record<string, unknown>)?.chunk_type as string | undefined,
                relations: (chunk.metadata as Record<string, unknown>)?.relations as Record<string, unknown> | undefined,
              };

              searchResults.push(searchResult);
              console.log('[useStreamingChat] Received search result:', searchResult.index, '/', searchResult.total);

              // Update streaming message with search results
              updateAgentStreamingMessage(requestingAgent,
                agentLocalStatesRef.current[requestingAgent].streamingMessage
                  ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, searchResults: [...searchResults] }
                  : null
              );
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
            // Mark generation as complete
            setIsGenerating(false);
            break;

          // RAG Analysis chunk types (for detailed progress modal)
          case 'rag_analysis':
            // Query analysis with keywords, intent, strategy
            if (chunk.metadata) {
              const analysis = chunk.metadata as unknown as RagAnalysis;
              setRagAnalysis(analysis);
              console.log('[useStreamingChat] RAG analysis received:', analysis);
              // Auto-open progress modal when analysis starts
              if (!searchProgressOpen) {
                setSearchProgressOpen(true);
              }
            }
            break;

          case 'chunk_structure':
            // Document chunk structure info
            if (chunk.metadata && chunk.tool_name) {
              const structure = chunk.metadata as unknown as ChunkStructure;
              setChunkStructures(prev => [...prev.filter(s => s.tool_name !== chunk.tool_name), structure]);
              console.log('[useStreamingChat] Chunk structure received:', structure);
            }
            break;

          case 'embedding_info':
            // Embedding/similarity info
            if (chunk.metadata && chunk.tool_name) {
              const embedding = chunk.metadata as unknown as EmbeddingInfo;
              setEmbeddingInfos(prev => [...prev.filter(e => e.tool_name !== chunk.tool_name), embedding]);
              console.log('[useStreamingChat] Embedding info received:', embedding);
            }
            break;

          case 'generation_start':
            // Answer generation started
            setIsGenerating(true);
            if (chunk.metadata) {
              setGenerationProgress({
                current_chunk: 0,
                total_chunks: 0,
                progress_pct: 0,
                ...(chunk.metadata as unknown as Partial<GenerationProgress>)
              });
            }
            console.log('[useStreamingChat] Generation started:', chunk.metadata);
            break;

          case 'generation_progress':
            // Answer generation progress update
            if (chunk.metadata) {
              setGenerationProgress(chunk.metadata as unknown as GenerationProgress);
            }
            break;

          // Enterprise multi-agent chunk types
          case 'agent_chunk':
            // Extract text content from nested agent chunk
            console.log('[useStreamingChat] agent_chunk handler:', {
              hasAgentChunk: !!chunk.agent_chunk,
              nestedType: chunk.agent_chunk?.chunk_type,
              nestedContent: chunk.agent_chunk?.content?.substring(0, 50),
              currentAccumulated: accumulatedContent.length,
            });
            if (chunk.agent_chunk?.chunk_type === 'text' && chunk.agent_chunk?.content) {
              accumulatedContent += chunk.agent_chunk.content;
              console.log('[useStreamingChat] Accumulated content updated, length:', accumulatedContent.length);
              updateAgentStreamingMessage(requestingAgent,
                agentLocalStatesRef.current[requestingAgent].streamingMessage
                  ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: accumulatedContent }
                  : null
              );
            }
            break;

          case 'synthesis':
            // Synthesis contains the final combined answer
            console.log('[useStreamingChat] synthesis chunk:', {
              hasContent: !!chunk.content,
              contentPreview: chunk.content?.substring(0, 100),
            });
            if (chunk.content) {
              accumulatedContent += chunk.content;
              console.log('[useStreamingChat] Synthesis added, total length:', accumulatedContent.length);
              updateAgentStreamingMessage(requestingAgent,
                agentLocalStatesRef.current[requestingAgent].streamingMessage
                  ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: accumulatedContent }
                  : null
              );
            }
            break;

          // Other enterprise chunk types (for trace visualization only)
          case 'orchestration_start':
          case 'dag_created':
          case 'batch_start':
          case 'agent_start':
          case 'agent_done':
          case 'batch_done':
          case 'evaluation':
          case 'retry':
          case 'next_actions':
            // These are handled by trace_data processing below
            break;

          default:
            console.log('[useStreamingChat] Unhandled chunk type:', chunk.chunk_type);
            break;
        }

        // Process trace_data if present (for agent execution visualization)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const chunkWithTrace = chunk as any;
        if (chunkWithTrace.trace_data && onTraceData) {
          onTraceData(chunkWithTrace.trace_data);
        }
      }

      if (!receivedAnyChunk) {
        console.warn('[useStreamingChat] No chunks received from stream');
      }

      // Debug: show final accumulated content before finalization
      console.log('[useStreamingChat] Stream complete. Final accumulated content length:', accumulatedContent.length);
      console.log('[useStreamingChat] Final content preview:', accumulatedContent.substring(0, 200));

      // Finalize message
      const finalMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: accumulatedContent || (receivedAnyChunk ? 'No content in response.' : 'Failed to get response from server.'),
        timestamp: new Date(),
        agentType: requestingAgent,
        toolCalls,
        sources,
        images: images.length > 0 ? images : undefined,
        searchResults: searchResults.length > 0 ? searchResults : undefined,
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
        saveMessageToDb(conversationId, 'assistant', accumulatedContent, requestingAgent);
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
    getExternalResourcesContext,
    getUIContext,
    onCredentialsRequired,
    onMessageSent,
    onTraceData,
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

    // Search progress state for RAG knowledge search visualization
    searchProgress: {
      isOpen: searchProgressOpen,
      currentQuery: searchCurrentQuery,
      toolResults: searchToolResults,
    },
    setSearchProgressOpen,

    // RAG detailed progress state (5 sections)
    ragProgress: {
      ragAnalysis,
      chunkStructures,
      embeddingInfos,
      generationProgress,
      isGenerating,
    },
  };
}

export default useStreamingChat;
