/**
 * Agent Chat Component
 *
 * AI Agent chat interface with streaming support and tool visualization.
 * Features:
 * - Agent type selection (RAG, IMS, Vision, Code, Planner)
 * - Streaming responses with real-time tool calls
 * - Tool execution visualization
 * - Source document display
 * - Markdown rendering
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Loader2,
  Bot,
  User,
  Wrench,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  RefreshCw,
  Sparkles,
  Code,
  Search,
  FileText,
  Globe,
  Brain,
  ChevronDown,
  AlertCircle,
  Database,
  Lock,
  X,
  PanelRightOpen,
  PanelRightClose,
  History,
  Plus,
  Paperclip,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from '../hooks/useTranslation';
import './AgentChat.css';
import {
  streamAgent,
  type AgentType,
  type AgentSource,
} from '../api/agent.api';
import { conversationApi } from '../api/conversation.api';
import { useArtifactStore, createArtifactFromChunk } from '../store/artifactStore';
import { useConversationStore } from '../store/conversationStore';
import { ArtifactPanel } from './ArtifactPanel';
import { ConversationSidebar } from './ConversationSidebar';

// =============================================================================
// Types
// =============================================================================

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'status';
  content: string;
  timestamp: Date;
  agentType?: AgentType;
  toolCalls?: ToolCallInfo[];
  sources?: AgentSource[];
  isStreaming?: boolean;
  error?: string;
  statusType?: 'crawling' | 'ready' | 'credentials_required';
}

interface ToolCallInfo {
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: 'pending' | 'success' | 'error';
}

interface AttachedFile {
  name: string;
  content: string;
  size: number;
}

// Supported file extensions for attachment
// Note: PDF/DOCX are CLI-only (require server-side text extraction)
const SUPPORTED_EXTENSIONS = ['.txt', '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.xml', '.csv', '.log', '.sql', '.sh', '.bat', '.html', '.css'];
const MAX_FILE_SIZE = 500 * 1024; // 500KB

// Agent type configuration
const AGENT_CONFIGS: Record<AgentType, { icon: React.ElementType; label: string; description: string }> = {
  auto: {
    icon: Sparkles,
    label: 'Auto',
    description: 'Automatically detect the best agent',
  },
  rag: {
    icon: Search,
    label: 'RAG',
    description: 'Knowledge search and Q&A',
  },
  ims: {
    icon: FileText,
    label: 'IMS',
    description: 'Issue management search',
  },
  vision: {
    icon: Globe,
    label: 'Vision',
    description: 'Image and document analysis',
  },
  code: {
    icon: Code,
    label: 'Code',
    description: 'Code generation and analysis',
  },
  planner: {
    icon: Brain,
    label: 'Planner',
    description: 'Task planning and decomposition',
  },
};

// Suggested questions per agent type
const SUGGESTED_QUESTIONS: Record<AgentType, string[]> = {
  auto: [
    'osctdlupdate 이슈 찾아줘',
    'What is HybridRAG?',
    'Find authentication issues',
  ],
  rag: [
    'What is HybridRAG?',
    'How does vector search work?',
    'Explain knowledge graphs',
  ],
  ims: [
    'Find authentication issues',
    'Search for recent bug reports',
    'Show high priority issues',
  ],
  vision: [
    'Analyze this document',
    'Describe the image content',
    'Extract text from the file',
  ],
  code: [
    'Write a factorial function',
    'Explain this code snippet',
    'Generate a REST API endpoint',
  ],
  planner: [
    'Plan a new feature implementation',
    'Break down this complex task',
    'Create a project roadmap',
  ],
};

// =============================================================================
// Component
// =============================================================================

export const AgentChat: React.FC = () => {
  const { t, language: userLanguage } = useTranslation();

  // Artifact store
  const {
    panel: artifactPanel,
    addArtifact,
    clearArtifacts,
    togglePanel: toggleArtifactPanel,
    setCurrentAgentType: setArtifactAgentType,
    getCurrentArtifacts,
  } = useArtifactStore();

  // Conversation store
  const {
    currentConversation,
    agentStates,
    lastSelectedAgent,
    loadConversations,
    createConversation,
    selectConversation,
    startNewConversation,
    setLastSelectedAgent,
  } = useConversationStore();

  // State - Initialize selectedAgent from store's lastSelectedAgent
  const [selectedAgent, setSelectedAgentState] = useState<AgentType>(lastSelectedAgent);
  const [inputValue, setInputValue] = useState('');
  const [showAgentSelector, setShowAgentSelector] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [showHistorySidebar, setShowHistorySidebar] = useState(false);

  // Ref to track current selectedAgent (for async callbacks to check current value)
  const selectedAgentRef = useRef<AgentType>(selectedAgent);
  selectedAgentRef.current = selectedAgent;

  // Wrapper to update selectedAgent and persist to store
  const setSelectedAgent = useCallback((agentType: AgentType) => {
    setSelectedAgentState(agentType);
    setLastSelectedAgent(agentType);
  }, [setLastSelectedAgent]);

  // Per-agent local state structure
  interface AgentLocalState {
    messages: ChatMessage[];
    streamingMessage: ChatMessage | null;
    isLoading: boolean;
    abortController: AbortController | null;
  }

  // Ref to store state for each agent (persists across renders)
  const agentLocalStatesRef = useRef<Record<AgentType, AgentLocalState>>({
    auto: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
    rag: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
    ims: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
    vision: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
    code: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
    planner: { messages: [], streamingMessage: null, isLoading: false, abortController: null },
  });

  // Current agent's state (derived from ref)
  const [messages, setMessagesState] = useState<ChatMessage[]>([]);
  const [streamingMessage, setStreamingMessageState] = useState<ChatMessage | null>(null);
  const [isLoading, setIsLoadingState] = useState(false);
  const [abortController, setAbortControllerState] = useState<AbortController | null>(null);

  // Functions to update a SPECIFIC agent's state (for background streaming)
  // These use selectedAgentRef.current to always get the CURRENT selected agent,
  // not the one captured in the closure at function creation time
  const updateAgentMessages = useCallback((targetAgent: AgentType, updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    const prev = agentLocalStatesRef.current[targetAgent].messages;
    const newValue = typeof updater === 'function' ? updater(prev) : updater;
    agentLocalStatesRef.current[targetAgent].messages = newValue;
    // Only update React state if this is the currently selected agent
    if (targetAgent === selectedAgentRef.current) {
      setMessagesState(newValue);
    }
  }, []);

  const updateAgentStreamingMessage = useCallback((targetAgent: AgentType, msg: ChatMessage | null) => {
    agentLocalStatesRef.current[targetAgent].streamingMessage = msg;
    if (targetAgent === selectedAgentRef.current) {
      setStreamingMessageState(msg);
    }
  }, []);

  const updateAgentIsLoading = useCallback((targetAgent: AgentType, loading: boolean) => {
    agentLocalStatesRef.current[targetAgent].isLoading = loading;
    if (targetAgent === selectedAgentRef.current) {
      setIsLoadingState(loading);
    }
  }, []);

  const updateAgentAbortController = useCallback((targetAgent: AgentType, controller: AbortController | null) => {
    agentLocalStatesRef.current[targetAgent].abortController = controller;
    if (targetAgent === selectedAgentRef.current) {
      setAbortControllerState(controller);
    }
  }, []);

  // Wrapper functions to update CURRENT agent's state (for direct UI interactions)
  const setMessages = useCallback((updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    updateAgentMessages(selectedAgent, updater);
  }, [selectedAgent, updateAgentMessages]);

  const setStreamingMessage = useCallback((msg: ChatMessage | null) => {
    updateAgentStreamingMessage(selectedAgent, msg);
  }, [selectedAgent, updateAgentStreamingMessage]);

  const setIsLoading = useCallback((loading: boolean) => {
    updateAgentIsLoading(selectedAgent, loading);
  }, [selectedAgent, updateAgentIsLoading]);

  // Get active conversation ID for current agent
  const agentState = agentStates[selectedAgent] || { activeConversationId: null };
  const activeConversationId = agentState.activeConversationId;

  // Get artifacts for current agent
  const artifacts = getCurrentArtifacts();

  // IMS Credentials modal state
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);
  const [imsUsername, setImsUsername] = useState('');
  const [imsPassword, setImsPassword] = useState('');
  const [isSubmittingCredentials, setIsSubmittingCredentials] = useState(false);
  const [credentialsError, setCredentialsError] = useState<string | null>(null);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  // File attachment state
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const agentSelectorRef = useRef<HTMLDivElement>(null);
  const hasHydratedRef = useRef(false);

  // Sync selectedAgent with lastSelectedAgent after Zustand hydration
  useEffect(() => {
    // Only sync once on initial hydration (when lastSelectedAgent changes from default)
    if (!hasHydratedRef.current && lastSelectedAgent !== 'auto') {
      hasHydratedRef.current = true;
      setSelectedAgentState(lastSelectedAgent);
    }
    // Also sync if lastSelectedAgent becomes non-auto on first check
    if (!hasHydratedRef.current && lastSelectedAgent === 'auto') {
      hasHydratedRef.current = true;
    }
  }, [lastSelectedAgent]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

  // Restore agent state and load conversations when agent type changes
  useEffect(() => {
    // Restore state from ref for the selected agent
    const savedState = agentLocalStatesRef.current[selectedAgent];
    setMessagesState(savedState.messages);
    setStreamingMessageState(savedState.streamingMessage);
    setIsLoadingState(savedState.isLoading);
    setAbortControllerState(savedState.abortController);

    // Update artifact store to show this agent's artifacts
    setArtifactAgentType(selectedAgent);

    // Load conversations for the new agent type
    loadConversations(selectedAgent);
  }, [selectedAgent, loadConversations, setArtifactAgentType]);

  // Auto-load active conversation when agent type changes and there's an active conversation
  useEffect(() => {
    if (activeConversationId) {
      selectConversation(selectedAgent, activeConversationId).catch(err => {
        console.error('Failed to auto-load conversation:', err);
      });
    }
  }, [selectedAgent, activeConversationId, selectConversation]);

  // Close agent selector when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (agentSelectorRef.current && !agentSelectorRef.current.contains(event.target as Node)) {
        setShowAgentSelector(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
  };

  // File attachment handling
  const handleFileAttach = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

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

      // Check size
      if (file.size > MAX_FILE_SIZE) {
        setFileError(`File too large: ${file.name} (max 500KB)`);
        continue;
      }

      // Check if already attached
      if (attachedFiles.some(f => f.name === file.name)) {
        setFileError(`File already attached: ${file.name}`);
        continue;
      }

      // Read file content
      try {
        const content = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsText(file);
        });

        setAttachedFiles(prev => [...prev, {
          name: file.name,
          content,
          size: file.size
        }]);
      } catch (error) {
        setFileError(`Failed to read file: ${file.name}`);
      }
    }

    // Reset input to allow re-selecting the same file
    if (e.target) e.target.value = '';
  }, [attachedFiles]);

  const handleRemoveFile = useCallback((fileName: string) => {
    setAttachedFiles(prev => prev.filter(f => f.name !== fileName));
    setFileError(null);
  }, []);

  const handleClearAllFiles = useCallback(() => {
    setAttachedFiles([]);
    setFileError(null);
  }, []);

  // Get combined file context for API request
  const getFileContext = useCallback((): string | undefined => {
    if (attachedFiles.length === 0) return undefined;
    return attachedFiles.map(f => `=== File: ${f.name} ===\n${f.content}\n`).join('\n');
  }, [attachedFiles]);

  // Helper to save message to database
  const saveMessageToDb = useCallback(async (
    conversationId: string,
    role: 'user' | 'assistant',
    content: string
  ) => {
    try {
      await conversationApi.addMessage(conversationId, { role, content });
      console.log('[AgentChat] Message saved to conversation:', conversationId);
    } catch (error) {
      console.error('[AgentChat] Failed to save message:', error);
    }
  }, []);

  // Handle send message
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;

    // IMPORTANT: Capture the agent type at the start - this won't change during streaming
    const requestingAgent = selectedAgent;
    // Also capture the active conversation ID for THIS agent (not current render state)
    const requestingAgentConversationId = agentStates[requestingAgent]?.activeConversationId || null;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    updateAgentMessages(requestingAgent, (prev) => [...prev, userMessage]);
    setInputValue('');
    updateAgentIsLoading(requestingAgent, true);

    // Get or create conversation for auto-save
    let conversationId = requestingAgentConversationId;
    if (!conversationId) {
      try {
        // Create new conversation with first message as title
        const title = userMessage.content.slice(0, 50) + (userMessage.content.length > 50 ? '...' : '');
        const conversation = await createConversation(requestingAgent, title);
        conversationId = conversation.id;
        console.log('[AgentChat] Created new conversation:', conversationId);
      } catch (error) {
        console.error('[AgentChat] Failed to create conversation:', error);
        // Continue without persistence
      }
    }

    // Save user message to database
    if (conversationId) {
      saveMessageToDb(conversationId, 'user', userMessage.content);
    }

    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    // Create streaming message placeholder with initial thinking state
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

    // Create abort controller for cancellation
    const controller = new AbortController();
    updateAgentAbortController(requestingAgent, controller);

    try {
      let accumulatedContent = '';
      const toolCalls: ToolCallInfo[] = [];
      let sources: AgentSource[] = [];
      let receivedAnyChunk = false;

      console.log('[AgentChat] Starting stream for task:', userMessage.content, 'agent:', requestingAgent);

      // When 'auto' is selected, don't send agent_type to let backend classify
      // Always include user's preferred language for AI responses
      // Include attached file context for RAG priority
      const fileContext = getFileContext();
      const requestPayload = requestingAgent === 'auto'
        ? { task: userMessage.content, language: userLanguage, file_context: fileContext }
        : { task: userMessage.content, agent_type: requestingAgent, language: userLanguage, file_context: fileContext };

      for await (const chunk of streamAgent(
        requestPayload,
        controller.signal
      )) {
        receivedAnyChunk = true;
        console.log('[AgentChat] Received chunk:', chunk.chunk_type, chunk);
        switch (chunk.chunk_type) {
          case 'thinking':
            // Update with thinking status - use captured requestingAgent
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: chunk.content || 'Analyzing...' }
                : null
            );
            break;

          case 'tool_call':
            // Add new tool call
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
            // Update tool call status
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
            // Accumulate text content
            accumulatedContent += chunk.content || '';
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, content: accumulatedContent }
                : null
            );
            break;

          case 'sources':
            // Update sources
            sources = chunk.sources || [];
            updateAgentStreamingMessage(requestingAgent,
              agentLocalStatesRef.current[requestingAgent].streamingMessage
                ? { ...agentLocalStatesRef.current[requestingAgent].streamingMessage!, sources }
                : null
            );
            break;

          case 'artifact':
            // Handle artifact chunk - add to artifact store for the requesting agent
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
            // Handle status messages (crawl status, ready status, credentials_required)
            // Backend sends status keys: "crawling", "ready", "credentials_required", etc.
            if (chunk.content) {
              const statusKey = chunk.content as 'crawling' | 'ready' | 'searching' | 'processing' | 'credentials_required';

              // If credentials required, show the credentials modal
              if (statusKey === 'credentials_required') {
                setPendingQuery(userMessage.content);
                setShowCredentialsModal(true);
                updateAgentIsLoading(requestingAgent, false);
                updateAgentStreamingMessage(requestingAgent, null);
                return; // Stop processing, user needs to enter credentials
              }

              const statusMsg: ChatMessage = {
                id: `status-${Date.now()}`,
                role: 'status',
                content: statusKey, // Store the key, translate in render
                timestamp: new Date(),
                statusType: statusKey === 'crawling' ? 'crawling' : 'ready',
              };
              updateAgentMessages(requestingAgent, (prev) => [...prev, statusMsg]);
            }
            break;

          case 'error':
            // Handle error
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
            // Streaming complete - remove processing status messages
            updateAgentMessages(requestingAgent, (prev) => prev.filter(msg =>
              !(msg.role === 'status' &&
                (msg.content === 'processing' || msg.content === 'crawling' || msg.content === 'searching'))
            ));
            break;
        }
      }

      // Log if no chunks received
      if (!receivedAnyChunk) {
        console.warn('[AgentChat] No chunks received from stream');
      }

      // Finalize message - also filter out any remaining processing status messages
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

      console.log('[AgentChat] Final message:', finalMessage);
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
        // Reload conversation list to update counts
        loadConversations(requestingAgent);
      }
    } catch (error) {
      console.error('[AgentChat] Stream error:', error);
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was cancelled
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
  }, [inputValue, isLoading, selectedAgent, agentStates, createConversation, saveMessageToDb, loadConversations, t, addArtifact, updateAgentMessages, updateAgentStreamingMessage, updateAgentIsLoading, updateAgentAbortController, getFileContext]);

  // Handle key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Handle suggestion click
  const handleSuggestionClick = (question: string) => {
    setInputValue(question);
    inputRef.current?.focus();
  };

  // Copy message
  const handleCopyMessage = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  // Clear chat
  const handleClearChat = () => {
    if (abortController) {
      abortController.abort();
    }
    setMessages([]);
    setStreamingMessage(null);
    clearArtifacts(selectedAgent); // Also clear artifacts for this agent
  };

  // Cancel streaming
  const handleCancelStreaming = () => {
    if (abortController) {
      abortController.abort();
      setIsLoading(false);
      setStreamingMessage(null);
    }
  };

  // Submit IMS credentials
  const handleSubmitCredentials = async () => {
    if (!imsUsername.trim() || !imsPassword.trim()) {
      setCredentialsError(t('common.agent.credentials.emptyFields') || 'Please fill in all fields');
      return;
    }

    setIsSubmittingCredentials(true);
    setCredentialsError(null);

    try {
      const response = await fetch('/api/v1/ims-credentials/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          ims_url: 'https://ims.tmaxsoft.com',
          username: imsUsername,
          password: imsPassword,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to save credentials');
      }

      // Success - close modal and retry the query
      setShowCredentialsModal(false);
      setImsUsername('');
      setImsPassword('');

      // Retry the pending query with credentials now stored
      if (pendingQuery) {
        setInputValue(pendingQuery);
        setPendingQuery(null);
        // Trigger send after a short delay to let state update
        setTimeout(() => {
          handleSend();
        }, 100);
      }
    } catch (error) {
      console.error('Failed to save IMS credentials:', error);
      setCredentialsError(
        error instanceof Error ? error.message : t('common.agent.credentials.saveError') || 'Failed to save credentials'
      );
    } finally {
      setIsSubmittingCredentials(false);
    }
  };

  // Close credentials modal
  const handleCloseCredentialsModal = () => {
    setShowCredentialsModal(false);
    setImsUsername('');
    setImsPassword('');
    setCredentialsError(null);
    setPendingQuery(null);
  };

  // Get agent icon
  const AgentIcon = AGENT_CONFIGS[selectedAgent].icon;

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    startNewConversation(selectedAgent);
    handleClearChat();
  }, [selectedAgent, startNewConversation, handleClearChat]);

  // Track if we're manually selecting a conversation (to bypass agent_type check)
  const [manuallySelectedConversationId, setManuallySelectedConversationId] = useState<string | null>(null);

  // Handle select conversation from sidebar
  const handleSelectConversation = useCallback(async (conversationId: string) => {
    try {
      setManuallySelectedConversationId(conversationId);
      await selectConversation(selectedAgent, conversationId);
      // Messages will be loaded via useEffect when currentConversation changes
    } catch (error) {
      console.error('Failed to load conversation:', error);
      setManuallySelectedConversationId(null);
    }
  }, [selectedAgent, selectConversation]);

  // Load messages when currentConversation changes
  useEffect(() => {
    if (currentConversation && currentConversation.messages) {
      // Load messages ONLY if:
      // 1. The conversation was manually selected from sidebar, OR
      // 2. The conversation agent_type EXACTLY matches selectedAgent
      // NOTE: Do NOT load 'auto' conversations into other agents - each agent's state must be independent
      const isManuallySelected = manuallySelectedConversationId === currentConversation.id;
      const agentTypeMatches = currentConversation.agent_type === selectedAgent;

      if (isManuallySelected || agentTypeMatches) {
        const loadedMessages: ChatMessage[] = currentConversation.messages.map((msg) => ({
          id: msg.id,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(msg.created_at),
          agentType: selectedAgent,
          sources: msg.sources,
        }));
        setMessages(loadedMessages);

        // Clear manual selection flag after loading
        if (isManuallySelected) {
          setManuallySelectedConversationId(null);
        }
      }
    }
  }, [currentConversation, selectedAgent, manuallySelectedConversationId]);

  // Toggle history sidebar
  const toggleHistorySidebar = useCallback(() => {
    setShowHistorySidebar((prev) => !prev);
  }, []);

  return (
    <div className={`agent-chat-wrapper ${artifactPanel.isOpen ? 'with-artifact-panel' : ''} ${showHistorySidebar ? 'with-history-sidebar' : ''}`}>
    {/* Conversation History Sidebar */}
    <ConversationSidebar
      agentType={selectedAgent}
      isOpen={showHistorySidebar}
      onToggle={toggleHistorySidebar}
      onNewConversation={handleNewConversation}
      onSelectConversation={handleSelectConversation}
    />

    <div className="agent-chat">
      {/* Header with agent selector */}
      <div className="agent-chat-header">
        <div className="agent-selector-container" ref={agentSelectorRef}>
          <button
            className="agent-selector-button"
            onClick={() => setShowAgentSelector(!showAgentSelector)}
          >
            <AgentIcon size={18} />
            <span>{AGENT_CONFIGS[selectedAgent].label}</span>
            <ChevronDown size={16} className={showAgentSelector ? 'rotated' : ''} />
          </button>

          {showAgentSelector && (
            <div className="agent-selector-dropdown">
              {(Object.keys(AGENT_CONFIGS) as AgentType[]).map((type) => {
                const config = AGENT_CONFIGS[type];
                const Icon = config.icon;
                return (
                  <button
                    key={type}
                    className={`agent-selector-option ${selectedAgent === type ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedAgent(type);
                      setShowAgentSelector(false);
                    }}
                  >
                    <Icon size={18} />
                    <div className="agent-selector-option-info">
                      <span className="agent-selector-option-label">{config.label}</span>
                      <span className="agent-selector-option-description">{config.description}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="agent-chat-header-actions">
          {/* History sidebar toggle button */}
          <button
            className={`agent-chat-history-toggle ${showHistorySidebar ? 'active' : ''}`}
            onClick={toggleHistorySidebar}
            title={showHistorySidebar ? 'Close history' : 'Open history'}
          >
            <History size={16} />
          </button>

          {/* New conversation button */}
          <button
            className="agent-chat-new-conversation"
            onClick={handleNewConversation}
            title="New conversation"
          >
            <Plus size={16} />
          </button>

          {/* Artifact panel toggle button */}
          {artifacts.length > 0 && (
            <button
              className={`agent-chat-artifact-toggle ${artifactPanel.isOpen ? 'active' : ''}`}
              onClick={toggleArtifactPanel}
              title={artifactPanel.isOpen ? 'Close artifacts' : 'Open artifacts'}
            >
              {artifactPanel.isOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
              <span className="artifact-count">{artifacts.length}</span>
            </button>
          )}

          {messages.length > 0 && (
            <button className="agent-chat-clear" onClick={handleClearChat}>
              <RefreshCw size={16} />
              <span>{t('knowledge.chat.clearHistory') || 'Clear'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div className="agent-chat-messages">
        {messages.length === 0 && !streamingMessage ? (
          <div className="agent-chat-empty">
            <div className="agent-chat-empty-icon">
              <Sparkles size={40} />
            </div>
            <h3>{t('knowledge.chat.title') || 'AI Agent'}</h3>
            <p>{AGENT_CONFIGS[selectedAgent].description}</p>

            {/* Suggestions */}
            <div className="agent-chat-suggestions">
              <span className="agent-chat-suggestions-label">
                {t('knowledge.chat.suggestions') || 'Try asking'}:
              </span>
              {SUGGESTED_QUESTIONS[selectedAgent].map((q, i) => (
                <button
                  key={i}
                  className="agent-chat-suggestion"
                  onClick={() => handleSuggestionClick(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onCopy={handleCopyMessage}
                copiedMessageId={copiedMessageId}
              />
            ))}

            {/* Streaming message */}
            {streamingMessage && (
              <MessageBubble
                message={streamingMessage}
                onCopy={handleCopyMessage}
                copiedMessageId={copiedMessageId}
                onCancel={handleCancelStreaming}
              />
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input area */}
      <div className="agent-chat-input-container">
        {/* Attached files display */}
        {attachedFiles.length > 0 && (
          <div className="agent-attached-files">
            <div className="agent-attached-files-header">
              <span className="agent-attached-files-label">
                <Paperclip size={14} />
                {attachedFiles.length} {attachedFiles.length === 1 ? 'file' : 'files'} attached
              </span>
              <button
                className="agent-attached-files-clear"
                onClick={handleClearAllFiles}
                title="Clear all"
              >
                <X size={14} />
              </button>
            </div>
            <div className="agent-attached-files-list">
              {attachedFiles.map(file => (
                <div key={file.name} className="agent-attached-file">
                  <FileText size={14} />
                  <span className="agent-attached-file-name">{file.name}</span>
                  <span className="agent-attached-file-size">
                    {file.size < 1024 ? `${file.size}B` : `${Math.round(file.size / 1024)}KB`}
                  </span>
                  <button
                    className="agent-attached-file-remove"
                    onClick={() => handleRemoveFile(file.name)}
                    title="Remove"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* File error display */}
        {fileError && (
          <div className="agent-file-error">
            <AlertCircle size={14} />
            <span>{fileError}</span>
            <button onClick={() => setFileError(null)}><X size={12} /></button>
          </div>
        )}

        <div className="agent-chat-input-wrapper">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            className="agent-file-input-hidden"
            onChange={handleFileChange}
            accept={SUPPORTED_EXTENSIONS.join(',')}
            multiple
          />

          {/* Attach button */}
          <button
            className="agent-chat-attach"
            onClick={handleFileAttach}
            disabled={isLoading}
            title="Attach files"
          >
            <Paperclip size={18} />
          </button>

          <textarea
            ref={inputRef}
            className="agent-chat-input"
            placeholder={t('knowledge.chat.inputPlaceholder') || 'Ask anything...'}
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyPress}
            rows={1}
            disabled={isLoading}
          />
          <button
            className="agent-chat-send"
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
          >
            {isLoading ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
          </button>
        </div>
      </div>

      {/* IMS Credentials Modal */}
      {showCredentialsModal && (
        <div className="agent-credentials-modal-overlay" onClick={handleCloseCredentialsModal}>
          <div className="agent-credentials-modal" onClick={(e) => e.stopPropagation()}>
            <div className="agent-credentials-modal-header">
              <div className="agent-credentials-modal-title">
                <Lock size={20} />
                <h3>{t('common.agent.credentials.title') || 'IMS Login Required'}</h3>
              </div>
              <button className="agent-credentials-modal-close" onClick={handleCloseCredentialsModal}>
                <X size={20} />
              </button>
            </div>

            <div className="agent-credentials-modal-body">
              <p className="agent-credentials-modal-description">
                {t('common.agent.credentials.description') ||
                  'Please enter your IMS credentials to search the Issue Management System.'}
              </p>

              {credentialsError && (
                <div className="agent-credentials-error">
                  <AlertCircle size={16} />
                  <span>{credentialsError}</span>
                </div>
              )}

              <div className="agent-credentials-form">
                <div className="agent-credentials-field">
                  <label htmlFor="ims-username">
                    {t('common.agent.credentials.username') || 'Username'}
                  </label>
                  <input
                    id="ims-username"
                    type="text"
                    value={imsUsername}
                    onChange={(e) => setImsUsername(e.target.value)}
                    placeholder={t('common.agent.credentials.usernamePlaceholder') || 'Enter IMS username'}
                    disabled={isSubmittingCredentials}
                    autoFocus
                  />
                </div>

                <div className="agent-credentials-field">
                  <label htmlFor="ims-password">
                    {t('common.agent.credentials.password') || 'Password'}
                  </label>
                  <input
                    id="ims-password"
                    type="password"
                    value={imsPassword}
                    onChange={(e) => setImsPassword(e.target.value)}
                    placeholder={t('common.agent.credentials.passwordPlaceholder') || 'Enter IMS password'}
                    disabled={isSubmittingCredentials}
                    onKeyDown={(e) => e.key === 'Enter' && handleSubmitCredentials()}
                  />
                </div>
              </div>
            </div>

            <div className="agent-credentials-modal-footer">
              <button
                className="agent-credentials-cancel-btn"
                onClick={handleCloseCredentialsModal}
                disabled={isSubmittingCredentials}
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                className="agent-credentials-submit-btn"
                onClick={handleSubmitCredentials}
                disabled={isSubmittingCredentials || !imsUsername.trim() || !imsPassword.trim()}
              >
                {isSubmittingCredentials ? (
                  <>
                    <Loader2 size={16} className="spin" />
                    <span>{t('common.agent.credentials.saving') || 'Saving...'}</span>
                  </>
                ) : (
                  <>
                    <Lock size={16} />
                    <span>{t('common.agent.credentials.login') || 'Login'}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>

    {/* Artifact Panel */}
    <ArtifactPanel />
    </div>
  );
};

// =============================================================================
// Message Bubble Component
// =============================================================================

interface MessageBubbleProps {
  message: ChatMessage;
  onCopy: (content: string, messageId: string) => void;
  copiedMessageId: string | null;
  onCancel?: () => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onCopy,
  copiedMessageId,
  onCancel,
}) => {
  const { t } = useTranslation();
  const isUser = message.role === 'user';
  const isStatus = message.role === 'status';
  const agentConfig = message.agentType ? AGENT_CONFIGS[message.agentType] : null;
  const AgentIcon = agentConfig?.icon || Bot;

  // Render status message differently
  if (isStatus) {
    // Translate status key using i18n
    const statusKey = message.content as 'crawling' | 'ready' | 'searching' | 'processing';
    const translatedMessage = t(`common.agent.status.${statusKey}`) || message.content;

    // Get appropriate icon based on status
    const getStatusIcon = () => {
      switch (statusKey) {
        case 'crawling':
        case 'processing':
          return <Loader2 size={18} className="spin" />;
        case 'searching':
          return <Search size={18} className="pulse" />;
        case 'ready':
          return <CheckCircle2 size={18} />;
        default:
          return <Database size={18} />;
      }
    };

    return (
      <div className={`agent-status-message ${message.statusType || ''} ${statusKey}`}>
        <div className="agent-status-icon">
          {getStatusIcon()}
        </div>
        <div className="agent-status-content">
          <span>{translatedMessage}</span>
          {(statusKey === 'crawling' || statusKey === 'processing' || statusKey === 'searching') && (
            <span className="agent-status-dots">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`agent-message ${message.role} ${message.isStreaming ? 'streaming' : ''}`}>
      {/* Avatar */}
      <div className="agent-message-avatar">
        {isUser ? <User size={18} /> : <AgentIcon size={18} />}
      </div>

      {/* Content */}
      <div className="agent-message-content">
        {/* Agent type badge */}
        {!isUser && agentConfig && (
          <div className="agent-message-badge">
            <AgentIcon size={12} />
            <span>{agentConfig.label}</span>
          </div>
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="agent-tool-calls">
            {message.toolCalls.map((tool, idx) => (
              <div key={idx} className={`agent-tool-call ${tool.status}`}>
                <div className="agent-tool-call-header">
                  <Wrench size={14} />
                  <span className="agent-tool-call-name">{tool.name}</span>
                  {tool.status === 'pending' && <Loader2 size={14} className="spin" />}
                  {tool.status === 'success' && <CheckCircle2 size={14} />}
                  {tool.status === 'error' && <XCircle size={14} />}
                </div>
                {tool.input && Object.keys(tool.input).length > 0 && (
                  <div className="agent-tool-call-input">
                    <code>{JSON.stringify(tool.input, null, 2)}</code>
                  </div>
                )}
                {tool.output && (
                  <div className="agent-tool-call-output">
                    <span>{tool.output.substring(0, 200)}{tool.output.length > 200 ? '...' : ''}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message text */}
        <div className="agent-message-text">
          {message.error ? (
            <div className="agent-message-error">
              <AlertCircle size={16} />
              <span>{message.content}</span>
            </div>
          ) : (
            <MessageContent content={message.content} />
          )}
          {message.isStreaming && <span className="agent-typing-cursor" />}
        </div>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="agent-message-sources">
            <span className="agent-sources-label">Sources:</span>
            {message.sources.map((source, idx) => (
              <div key={idx} className="agent-source-item">
                <FileText size={12} />
                <span>{source.source}</span>
                <span className="agent-source-score">{Math.round(source.score * 100)}%</span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        {!isUser && !message.isStreaming && (
          <div className="agent-message-actions">
            <button
              className={`agent-message-action ${copiedMessageId === message.id ? 'copied' : ''}`}
              onClick={() => onCopy(message.content, message.id)}
              title="Copy"
            >
              {copiedMessageId === message.id ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        )}

        {/* Cancel button for streaming */}
        {message.isStreaming && onCancel && (
          <button className="agent-message-cancel" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
};

// =============================================================================
// Message Content Renderer with react-markdown
// =============================================================================

interface MessageContentProps {
  content: string;
}

const MessageContent: React.FC<MessageContentProps> = ({ content }) => {
  if (!content) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Custom table wrapper with horizontal scroll
        table: ({ children }) => (
          <div className="agent-table-wrapper">
            <table className="agent-markdown-table">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="agent-table-header">{children}</thead>
        ),
        tbody: ({ children }) => (
          <tbody className="agent-table-body">{children}</tbody>
        ),
        tr: ({ children }) => (
          <tr className="agent-table-row">{children}</tr>
        ),
        th: ({ children }) => (
          <th className="agent-table-th">{children}</th>
        ),
        td: ({ children }) => (
          <td className="agent-table-td">{children}</td>
        ),
        // Code blocks
        code: ({ className, children }) => {
          const match = /language-(\w+)/.exec(className || '');
          const isInline = !match && !String(children).includes('\n');

          if (isInline) {
            return <code className="agent-inline-code">{children}</code>;
          }

          const language = match ? match[1] : 'text';
          const codeString = String(children).replace(/\n$/, '');

          return (
            <pre className="agent-code-block">
              <div className="agent-code-header">
                <span className="agent-code-lang">{language}</span>
                <button
                  className="agent-code-copy"
                  onClick={() => navigator.clipboard.writeText(codeString)}
                  title="Copy code"
                >
                  <Copy size={12} />
                </button>
              </div>
              <code>{codeString}</code>
            </pre>
          );
        },
        // Links - open in new tab
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="agent-markdown-link">
            {children}
          </a>
        ),
        p: ({ children }) => <p className="agent-markdown-p">{children}</p>,
        h2: ({ children }) => <h2 className="agent-markdown-h2">{children}</h2>,
        h3: ({ children }) => <h3 className="agent-markdown-h3">{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

export default AgentChat;
