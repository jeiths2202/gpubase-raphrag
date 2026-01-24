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
  RefreshCw,
  Sparkles,
  ChevronDown,
  AlertCircle,
  X,
  PanelRightOpen,
  PanelRightClose,
  History,
  Plus,
  Paperclip,
  FileText,
  Globe,
  Link,
  ExternalLink,
  GitBranch,
  Link2,
  Search,
  Layers,
  MessageSquare,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './AgentChat.css';
import { type AgentType } from '../api/agent.api';
import { useArtifactStore, createArtifactFromChunk } from '../store/artifactStore';
import { useConversationStore } from '../store/conversationStore';
import { useTraceStore } from '../store/traceStore';
import { useContextStore } from '../store/contextStore';
import { ArtifactPanel } from './ArtifactPanel';
import { ConversationSidebar } from './ConversationSidebar';
import { TracePanel } from './TracePanel';

// Import from refactored modules
import {
  MessageBubble,
  IMSCredentialsModal,
  ExternalConnectorsModal,
  SearchProgressModal,
  FAQRegistrationModal,
  ScopeSelectionModal,
  ClarificationModal,
  useFileAttachment,
  useUrlAttachment,
  useStreamingChat,
  useClarification,
  AGENT_CONFIGS,
  SUPPORTED_EXTENSIONS,
  type ChatMessage,
} from './AgentChat/index';
import type { SearchScope } from '../api/agent-navigation.api';

// Feedback API
import { submitQuickFeedback, cancelFeedback } from '../api/feedback.api';
import type { FeedbackType } from './AgentChat/MessageBubble';

// External connectors store
import { useExternalConnectorsStore } from '../store/externalConnectorsStore';

// Auth store for user ID
import { useAuthStore } from '../store/authStore';

// Preferences store for display mode
import { usePreferencesStore } from '../store/preferencesStore';

// Floating panel store
import { useFloatingPanelStore } from '../store/floatingPanelStore';

// Floating panel component
import { DirectModeFloatingPanel } from './AgentChat/DirectModeFloatingPanel';

// =============================================================================
// Component
// =============================================================================

interface AgentChatProps {
  windowId?: string;  // For floating window mode
  isFloatingWindow?: boolean;  // Whether this is inside a floating window
}

export const AgentChat: React.FC<AgentChatProps> = ({
  windowId: _windowId,
  isFloatingWindow: _isFloatingWindow = false,
}) => {
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

  // Trace store
  const {
    panel: tracePanel,
    currentTrace,
    togglePanel: toggleTracePanel,
    updateFromTraceData,
  } = useTraceStore();

  // Context store for UI context-aware AI
  const { getUIContext } = useContextStore();

  // State - Initialize selectedAgent from store's lastSelectedAgent
  const [selectedAgent, setSelectedAgentState] = useState<AgentType>(lastSelectedAgent);
  const [inputValue, setInputValue] = useState('');
  const [showAgentSelector, setShowAgentSelector] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [showHistorySidebar, setShowHistorySidebar] = useState(false);

  // Ref to track current selectedAgent (for async callbacks to check current value)
  const selectedAgentRef = useRef<AgentType>(selectedAgent);
  selectedAgentRef.current = selectedAgent;

  // Get active conversation ID for current agent
  const agentState = agentStates[selectedAgent] || { activeConversationId: null };
  const activeConversationId = agentState.activeConversationId;

  // Get artifacts for current agent
  const artifacts = getCurrentArtifacts();

  // IMS Credentials modal state
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  // Feedback state (per message)
  const [feedbackState, setFeedbackState] = useState<Record<string, FeedbackType>>({});

  // FAQ Registration modal state
  const [showFAQModal, setShowFAQModal] = useState(false);
  const [faqData, setFaqData] = useState<{
    question: string;
    answer: string;
    agentType?: AgentType;
  } | null>(null);

  // Scope Selection modal state (Agent-Driven RAG)
  const [showScopeModal, setShowScopeModal] = useState(false);
  const [scopePendingQuery, setScopePendingQuery] = useState<string | null>(null);

  // Auth store - get current user ID
  const { user } = useAuthStore();

  // Preferences store - display mode for Direct mode results
  const { directModeDisplay, setDirectModeDisplay } = usePreferencesStore();

  // Floating panel store - manage multiple floating panels
  const {
    panels: floatingPanels,
    createPanel: _createPanel, // Will be used when Direct mode response is received
    closePanel,
    closeAllPanels,
    minimizePanel,
    restorePanel,
    bringToFront,
    updatePosition,
    updateSize,
  } = useFloatingPanelStore();

  // Export createPanel for external use (e.g., from streaming chat hook)
  const createPanel = _createPanel;

  // External connectors store and modal state (must be before setSelectedAgent callback)
  const {
    isModalOpen: showConnectorsModal,
    openModal: openConnectorsModal,
    closeModal: closeConnectorsModal,
    activeResourcesByAgent,
    currentAgentType,
    getConnectedCount,
    getActiveResourcesContext,
    setCurrentUserId,
    setCurrentAgentType,
    loadConnections,
    toggleResourceActive,
    clearActiveResources,
  } = useExternalConnectorsStore();

  // Compute activeResources from activeResourcesByAgent and currentAgentType
  // (Zustand doesn't support object getters, so we compute it here)
  const activeResources = activeResourcesByAgent[currentAgentType] || [];

  // Wrapper to update selectedAgent and persist to store
  const setSelectedAgent = useCallback((agentType: AgentType) => {
    setSelectedAgentState(agentType);
    setLastSelectedAgent(agentType);
    // Update external connectors store to scope resources by agent type
    setCurrentAgentType(agentType);
  }, [setLastSelectedAgent, setCurrentAgentType]);

  // File attachment (using custom hook with per-agent state)
  const {
    attachedFiles,
    fileError,
    fileInputRef,
    handleFileAttach,
    handleFileChange,
    handleFileDrop,
    handleRemoveFile,
    handleClearAllFiles,
    getFileContext,
    clearFileError,
    syncAgentFileState,
  } = useFileAttachment(selectedAgentRef);

  // Drag and drop state
  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  // URL attachment (using custom hook with per-agent state)
  const {
    attachedUrls,
    detectedUrl,
    handleUrlDetect,
    handleFetchUrl,
    handleRemoveUrl,
    getUrlContext,
    dismissDetectedUrl,
    syncAgentUrlState,
  } = useUrlAttachment(selectedAgentRef);

  // Set user ID in external connectors store when user is available
  useEffect(() => {
    if (user?.id) {
      setCurrentUserId(user.id);
      // Load existing connections for this user
      loadConnections();
    }
  }, [user?.id, setCurrentUserId, loadConnections]);

  // Set current agent type for external connectors scoping
  useEffect(() => {
    setCurrentAgentType(selectedAgent);
  }, [selectedAgent, setCurrentAgentType]);

  // Streaming chat (using custom hook)
  const {
    messages,
    streamingMessage,
    isLoading,
    setMessages,
    handleSend: streamingHandleSend,
    handleCancelStreaming,
    handleClearChat: streamingClearChat,
    syncAgentState,
    searchProgress,
    setSearchProgressOpen,
    ragProgress,
  } = useStreamingChat(selectedAgentRef, {
    t,
    userLanguage,
    agentStates,
    createConversation,
    loadConversations,
    clearActiveConversation: startNewConversation,
    addArtifact,
    createArtifactFromChunk,
    getFileContext,
    getUrlContext,
    getExternalResourcesContext: () => {
      const context = getActiveResourcesContext();
      return context || undefined;
    },
    getUIContext,
    onCredentialsRequired: (query: string) => {
      setPendingQuery(query);
      setShowCredentialsModal(true);
    },
    onMessageSent: () => {
      // URL context is preserved until user explicitly removes it
      // Reset textarea height
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
      }
    },
    onTraceData: updateFromTraceData,
  });

  // Query clarification hook (for ambiguous terms like MFS, WebAdmin)
  const {
    isModalOpen: isClarificationModalOpen,
    detectedTerms,
    pendingQuery: clarificationPendingQuery,
    checkQueryClarification,
    handleClarificationConfirm,
    closeClarificationModal,
    autoResolvedMessage,
    clearAutoResolvedMessage,
  } = useClarification(async (resolvedQuery: string) => {
    // After clarification, proceed with scope selection or direct send
    if (selectedAgent === 'rag' || selectedAgent === 'auto') {
      setScopePendingQuery(resolvedQuery);
      setShowScopeModal(true);
    } else {
      await streamingHandleSend(resolvedQuery);
    }
  });

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

  // Track previous messages length for floating panel creation
  const prevMessagesLengthRef = useRef(messages.length);

  // Auto-create floating panel when assistant message is added in floating mode
  useEffect(() => {
    // Only process if floating mode is active and messages increased
    if (directModeDisplay !== 'floating' || messages.length <= prevMessagesLengthRef.current) {
      prevMessagesLengthRef.current = messages.length;
      return;
    }

    // Get the newly added message
    const lastMessage = messages[messages.length - 1];

    // Only process assistant messages
    if (lastMessage && lastMessage.role === 'assistant' && !lastMessage.isStreaming) {
      // Find the corresponding user message (second to last or earlier)
      const userMessage = [...messages].reverse().find(m => m.role === 'user');

      // Create floating panel with the response
      createPanel({
        title: userMessage?.content.slice(0, 50) || 'Search Result',
        query: userMessage?.content || '',
        content: lastMessage.content,
        searchResults: lastMessage.searchResults,
        sourceReliability: lastMessage.sourceReliability,
        timestamp: lastMessage.timestamp,
      });

      // Clear chat after creating panel (keep empty for new conversations)
      setMessages([]);
    }

    prevMessagesLengthRef.current = messages.length;
  }, [messages, directModeDisplay, createPanel, setMessages]);

  // Restore agent state and load conversations when agent type changes
  useEffect(() => {
    // Sync streaming chat state for the selected agent
    syncAgentState(selectedAgent);

    // Sync file and URL attachment states for the selected agent
    syncAgentFileState(selectedAgent);
    syncAgentUrlState(selectedAgent);

    // Update artifact store to show this agent's artifacts
    setArtifactAgentType(selectedAgent);

    // Load conversations for the new agent type
    loadConversations(selectedAgent);
  }, [selectedAgent, loadConversations, setArtifactAgentType, syncAgentState, syncAgentFileState, syncAgentUrlState]);

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

  // Auto-resize textarea with URL detection
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInputValue(value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
    // Detect URLs in input
    handleUrlDetect(value);
  };

  // Handle paste event explicitly to ensure URL detection works
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    // Get pasted text
    const pastedText = e.clipboardData.getData('text');
    if (pastedText) {
      // Use setTimeout to ensure the input value is updated before detection
      setTimeout(() => {
        const currentValue = inputRef.current?.value || '';
        handleUrlDetect(currentValue);
      }, 0);
    }
  }, [handleUrlDetect]);

  // Drag and drop handlers
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileDrop(files);
    }
  }, [handleFileDrop]);

  // Handle send message (wrapper for streaming hook)
  // Flow: Check Clarification → Scope Selection (RAG/Auto) → Send
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;
    const currentInput = inputValue;
    setInputValue('');

    // Step 1: Check for ambiguous terms that need clarification
    const clarificationResult = await checkQueryClarification(currentInput);

    if (!clarificationResult.canProceed) {
      // Clarification modal is now open, wait for user selection
      return;
    }

    // Use resolved query (may have auto-resolved terms)
    const queryToSend = clarificationResult.resolvedQuery;

    // Step 2: For RAG or Auto agent, show scope selection modal
    if (selectedAgent === 'rag' || selectedAgent === 'auto') {
      setScopePendingQuery(queryToSend);
      setShowScopeModal(true);
      return;
    }

    // Step 3: Send directly for other agents
    await streamingHandleSend(queryToSend);
  }, [inputValue, isLoading, selectedAgent, streamingHandleSend, checkQueryClarification]);

  // Handle scope selection callback (Agent-Driven RAG)
  const handleScopeSelect = useCallback(async (scope: SearchScope | null) => {
    if (!scopePendingQuery) return;
    const query = scopePendingQuery;
    setScopePendingQuery(null);
    setShowScopeModal(false);
    await streamingHandleSend(query, scope);
  }, [scopePendingQuery, streamingHandleSend]);

  // Handle scope modal close (cancel)
  const handleScopeModalClose = useCallback(() => {
    setShowScopeModal(false);
    // Restore input if user cancels
    if (scopePendingQuery) {
      setInputValue(scopePendingQuery);
    }
    setScopePendingQuery(null);
  }, [scopePendingQuery]);

  // Handle key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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

  // Handle feedback (thumbs up/down) with toggle support
  const handleFeedback = useCallback(async (messageId: string, type: 'thumbs_up' | 'thumbs_down') => {
    try {
      const currentFeedback = feedbackState[messageId];

      // If clicking the same button, cancel the feedback (toggle off)
      if (currentFeedback === type) {
        await cancelFeedback(messageId);
        setFeedbackState(prev => {
          const newState = { ...prev };
          delete newState[messageId];
          return newState;
        });
      }
      // If clicking a different button, switch the feedback
      else if (currentFeedback) {
        // First cancel the old feedback, then submit the new one
        await cancelFeedback(messageId);
        await submitQuickFeedback({ message_id: messageId, feedback_type: type });
        setFeedbackState(prev => ({ ...prev, [messageId]: type }));
      }
      // If no existing feedback, submit new one
      else {
        await submitQuickFeedback({ message_id: messageId, feedback_type: type });
        setFeedbackState(prev => ({ ...prev, [messageId]: type }));
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    }
  }, [feedbackState]);

  // Handle FAQ registration modal open
  const handleRegisterFAQ = useCallback((question: string, answer: string, agentType?: AgentType) => {
    setFaqData({ question, answer, agentType });
    setShowFAQModal(true);
  }, []);

  // Handle FAQ modal close
  const handleFAQModalClose = useCallback(() => {
    setShowFAQModal(false);
    setFaqData(null);
  }, []);

  // Handle FAQ registration success
  const handleFAQSuccess = useCallback(() => {
    // Could show a toast notification here
    console.log('FAQ registered successfully');
  }, []);

  // Handle regenerate response
  const handleRegenerate = useCallback((messageId: string) => {
    // Find the assistant message and its preceding user message
    const messageIndex = messages.findIndex(m => m.id === messageId);
    if (messageIndex === -1) return;

    // Find the most recent user message before this assistant message
    let userMessageContent = '';
    for (let i = messageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userMessageContent = messages[i].content;
        break;
      }
    }

    if (userMessageContent) {
      // Remove the current assistant message and any after it (for re-streaming)
      const newMessages = messages.slice(0, messageIndex);
      setMessages(newMessages);

      // Re-send the user's question
      setInputValue(userMessageContent);
      // Trigger send after state update
      setTimeout(() => {
        streamingHandleSend(userMessageContent);
      }, 100);
    }
  }, [messages, setMessages, streamingHandleSend]);

  // Find the user message for a given assistant message (for FAQ registration)
  const findUserMessageForAssistant = useCallback((assistantIndex: number): string => {
    for (let i = assistantIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        return messages[i].content;
      }
    }
    return '';
  }, [messages]);

  // Clear chat (wrapper for streaming hook)
  const handleClearChat = useCallback(() => {
    streamingClearChat(clearArtifacts);
  }, [streamingClearChat, clearArtifacts]);

  // IMS credentials modal handlers
  const handleCredentialsClose = useCallback(() => {
    setShowCredentialsModal(false);
    setPendingQuery(null);
  }, []);

  const handleCredentialsSuccess = useCallback(() => {
    setShowCredentialsModal(false);
    // Retry the pending query with credentials now stored
    if (pendingQuery) {
      setInputValue(pendingQuery);
      setPendingQuery(null);
      // Trigger send after a short delay to let state update
      setTimeout(() => {
        handleSend();
      }, 100);
    }
  }, [pendingQuery, handleSend]);

  // Get agent icon
  const AgentIcon = AGENT_CONFIGS[selectedAgent].icon;

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    // If in floating mode and there are existing messages, create a floating panel first
    if (directModeDisplay === 'floating' && messages.length > 0) {
      const lastAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant');
      if (lastAssistantMessage) {
        createPanel({
          title: lastAssistantMessage.content.slice(0, 50) + '...',
          query: messages.find(m => m.role === 'user')?.content || '',
          content: lastAssistantMessage.content,
          searchResults: lastAssistantMessage.searchResults,
          sourceReliability: lastAssistantMessage.sourceReliability,
          timestamp: lastAssistantMessage.timestamp,
        });
      }
    }
    startNewConversation(selectedAgent);
    handleClearChat();
  }, [selectedAgent, startNewConversation, handleClearChat, directModeDisplay, messages, createPanel]);

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

  const isEmpty = messages.length === 0 && !streamingMessage;

  return (
    <div className={`agent-chat-wrapper ${isEmpty ? 'is-empty' : ''} ${artifactPanel.isOpen ? 'with-artifact-panel' : ''} ${tracePanel.isOpen ? 'with-trace-panel' : ''} ${showHistorySidebar ? 'with-history-sidebar' : ''}`}>
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

          {/* Display mode toggle */}
          <button
            className={`agent-chat-display-mode-toggle ${directModeDisplay === 'floating' ? 'active' : ''}`}
            onClick={() => {
              const newMode = directModeDisplay === 'inline' ? 'floating' : 'inline';
              console.log('[AgentChat] Display mode toggle clicked:', directModeDisplay, '->', newMode);
              setDirectModeDisplay(newMode);
            }}
            title={directModeDisplay === 'floating'
              ? (t('common.displayMode.inline') || 'Switch to inline mode')
              : (t('common.displayMode.floating') || 'Switch to floating mode')}
          >
            {directModeDisplay === 'floating' ? <MessageSquare size={16} /> : <Layers size={16} />}
          </button>

          {/* External connectors button */}
          <button
            className={`agent-chat-connectors-toggle ${activeResources.length > 0 ? 'has-active' : ''}`}
            onClick={openConnectorsModal}
            title={t('externalConnectors.title') || 'External Connectors'}
          >
            <Link2 size={16} />
            {(getConnectedCount() > 0 || activeResources.length > 0) && (
              <span className="connectors-count">
                {activeResources.length > 0 ? activeResources.length : getConnectedCount()}
              </span>
            )}
          </button>

          {/* Search progress toggle button - show when there are search results */}
          {searchProgress.toolResults.length > 0 && (
            <button
              className={`agent-chat-search-toggle ${searchProgress.isOpen ? 'active' : ''}`}
              onClick={() => setSearchProgressOpen(!searchProgress.isOpen)}
              title={t('searchProgress.title') || 'Search Progress'}
            >
              <Search size={16} />
              <span className="search-results-count">
                {searchProgress.toolResults.reduce((sum, t) => sum + (t.resultCount || 0), 0)}
              </span>
            </button>
          )}

          {/* Trace panel toggle button - Planner only */}
          {selectedAgent === 'planner' && currentTrace.dag && (
            <button
              className={`agent-chat-trace-toggle ${tracePanel.isOpen ? 'active' : ''}`}
              onClick={toggleTracePanel}
              title={tracePanel.isOpen ? 'Close trace' : 'Open trace'}
            >
              <GitBranch size={16} />
            </button>
          )}

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

            {/* Search Syntax Help */}
            <div className="agent-chat-search-syntax">
              <span className="agent-chat-search-syntax-title">
                {t('knowledge.chat.searchSyntax.title')}
              </span>
              <p className="agent-chat-search-syntax-description">
                {t('knowledge.chat.searchSyntax.description')}
              </p>
              <div className="agent-chat-search-syntax-table">
                <div className="agent-chat-search-syntax-row">
                  <code className="agent-chat-search-syntax-code">{t('knowledge.chat.searchSyntax.examples.0.syntax')}</code>
                  <span className="agent-chat-search-syntax-desc">{t('knowledge.chat.searchSyntax.examples.0.description')}</span>
                </div>
                <div className="agent-chat-search-syntax-row">
                  <code className="agent-chat-search-syntax-code">{t('knowledge.chat.searchSyntax.examples.1.syntax')}</code>
                  <span className="agent-chat-search-syntax-desc">{t('knowledge.chat.searchSyntax.examples.1.description')}</span>
                </div>
                <div className="agent-chat-search-syntax-row">
                  <code className="agent-chat-search-syntax-code">{t('knowledge.chat.searchSyntax.examples.2.syntax')}</code>
                  <span className="agent-chat-search-syntax-desc">{t('knowledge.chat.searchSyntax.examples.2.description')}</span>
                </div>
                <div className="agent-chat-search-syntax-row">
                  <code className="agent-chat-search-syntax-code">{t('knowledge.chat.searchSyntax.examples.3.syntax')}</code>
                  <span className="agent-chat-search-syntax-desc">{t('knowledge.chat.searchSyntax.examples.3.description')}</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, index) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onCopy={handleCopyMessage}
                copiedMessageId={copiedMessageId}
                onFeedback={handleFeedback}
                onRegisterFAQ={handleRegisterFAQ}
                onRegenerate={handleRegenerate}
                feedbackState={feedbackState}
                userMessage={msg.role === 'assistant' ? findUserMessageForAssistant(index) : undefined}
                userRole={user?.role as 'user' | 'admin' | 'leader' | undefined}
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

      {/* Input area with drag & drop support */}
      <div
        className={`agent-chat-input-container ${isDragging ? 'dragging' : ''}`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
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

        {/* Attached URLs display */}
        {attachedUrls.length > 0 && (
          <div className="agent-attached-urls">
            <div className="agent-attached-urls-header">
              <span className="agent-attached-urls-label">
                <Link size={14} />
                {attachedUrls.length} URL{attachedUrls.length > 1 ? 's' : ''} attached
              </span>
            </div>
            <div className="agent-attached-urls-list">
              {attachedUrls.map(urlItem => (
                <div key={urlItem.url} className={`agent-attached-url ${urlItem.isLoading ? 'loading' : ''} ${urlItem.error ? 'error' : ''} ${urlItem.warning ? 'warning' : ''}`}>
                  {urlItem.isLoading ? (
                    <Loader2 size={14} className="spin" />
                  ) : urlItem.error ? (
                    <AlertCircle size={14} />
                  ) : urlItem.warning ? (
                    <AlertCircle size={14} />
                  ) : (
                    <Globe size={14} />
                  )}
                  <div className="agent-attached-url-info">
                    <span className="agent-attached-url-title">
                      {urlItem.isLoading ? 'Fetching...' : urlItem.error ? 'Failed to fetch' : (urlItem.title || urlItem.url)}
                    </span>
                    {!urlItem.isLoading && !urlItem.error && (
                      <span className="agent-attached-url-meta">
                        {urlItem.charCount < 1024 ? `${urlItem.charCount} chars` : `${Math.round(urlItem.charCount / 1024)}KB`}
                      </span>
                    )}
                    {urlItem.error && (
                      <span className="agent-attached-url-error">{urlItem.error}</span>
                    )}
                    {urlItem.warning && !urlItem.error && (
                      <span className="agent-attached-url-warning">{urlItem.warning}</span>
                    )}
                  </div>
                  <button
                    className="agent-attached-url-remove"
                    onClick={() => handleRemoveUrl(urlItem.url)}
                    title="Remove"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Selected External Resources display */}
        {activeResources.length > 0 && (
          <div className="agent-external-resources">
            <div className="agent-external-resources-header">
              <span className="agent-external-resources-label">
                <Link2 size={14} />
                {activeResources.length} {t('externalConnectors.selected') || 'external resource(s) selected'}
              </span>
              <div className="agent-external-resources-actions">
                <button
                  className="agent-external-resources-add"
                  onClick={openConnectorsModal}
                  title={t('externalConnectors.title') || 'Manage connectors'}
                >
                  <Plus size={12} />
                </button>
                <button
                  className="agent-external-resources-clear"
                  onClick={clearActiveResources}
                  title={t('common.delete') || 'Clear all'}
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="agent-external-resources-list">
              {activeResources.map(resource => (
                <div
                  key={resource.id}
                  className={`agent-external-resource ${resource.status === 'ready' ? 'ready' : ''} ${resource.status === 'error' ? 'error' : ''}`}
                >
                  {resource.status === 'ready' ? (
                    <GitBranch size={14} />
                  ) : resource.status === 'error' ? (
                    <AlertCircle size={14} />
                  ) : (
                    <Loader2 size={14} className="spin" />
                  )}
                  <div className="agent-external-resource-info">
                    <span className="agent-external-resource-title" title={resource.title}>
                      {resource.title.length > 30 ? resource.title.slice(0, 30) + '...' : resource.title}
                    </span>
                    <span className="agent-external-resource-meta">
                      {resource.status === 'ready' && resource.content ? (
                        <>
                          {resource.content.length < 1024
                            ? `${resource.content.length} chars`
                            : `${Math.round(resource.content.length / 1024)}KB`}
                        </>
                      ) : resource.status === 'error' ? (
                        <span className="error-text">{resource.errorMessage || 'Error'}</span>
                      ) : (
                        <span>{t(`externalConnectors.docStatus.${resource.status}`) || resource.status}</span>
                      )}
                    </span>
                  </div>
                  <button
                    className="agent-external-resource-remove"
                    onClick={() => toggleResourceActive(resource)}
                    title={t('common.delete') || 'Remove'}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* URL detection prompt */}
        {detectedUrl && (
          <div className="agent-url-detected">
            <Link size={14} />
            <span className="agent-url-detected-text">
              URL detected: <strong>{detectedUrl.length > 50 ? detectedUrl.slice(0, 50) + '...' : detectedUrl}</strong>
            </span>
            <button
              className="agent-url-fetch-btn"
              onClick={() => handleFetchUrl(detectedUrl)}
              title="Fetch content for RAG context"
            >
              <ExternalLink size={12} />
              Fetch content
            </button>
            <button
              className="agent-url-dismiss-btn"
              onClick={dismissDetectedUrl}
              title="Dismiss"
            >
              <X size={12} />
            </button>
          </div>
        )}

        {/* File error display */}
        {fileError && (
          <div className="agent-file-error">
            <AlertCircle size={14} />
            <span>{fileError}</span>
            <button onClick={() => clearFileError()}><X size={12} /></button>
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
            onPaste={handlePaste}
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
      <IMSCredentialsModal
        isOpen={showCredentialsModal}
        onClose={handleCredentialsClose}
        onSuccess={handleCredentialsSuccess}
        t={t}
      />

      {/* External Connectors Modal */}
      <ExternalConnectorsModal
        isOpen={showConnectorsModal}
        onClose={closeConnectorsModal}
        t={t}
      />

      {/* FAQ Registration Modal */}
      <FAQRegistrationModal
        isOpen={showFAQModal}
        onClose={handleFAQModalClose}
        onSuccess={handleFAQSuccess}
        t={t}
        question={faqData?.question || ''}
        answer={faqData?.answer || ''}
        agentType={faqData?.agentType}
      />

      {/* Search Progress Modal */}
      <SearchProgressModal
        isOpen={searchProgress.isOpen}
        onClose={() => setSearchProgressOpen(false)}
        query={searchProgress.currentQuery}
        toolResults={searchProgress.toolResults}
        isSearching={searchProgress.toolResults.some(t => t.status === 'running') || ragProgress.isGenerating}
        ragProgress={ragProgress}
        t={t}
      />

      {/* Scope Selection Modal (Agent-Driven RAG) */}
      <ScopeSelectionModal
        isOpen={showScopeModal}
        onClose={handleScopeModalClose}
        onSelectScope={handleScopeSelect}
        query={scopePendingQuery || ''}
        t={t}
        language={userLanguage}
      />

      {/* Query Clarification Modal (for ambiguous terms like MFS, WebAdmin) */}
      <ClarificationModal
        isOpen={isClarificationModalOpen}
        detectedTerms={detectedTerms}
        query={clarificationPendingQuery}
        onConfirm={handleClarificationConfirm}
        onClose={closeClarificationModal}
        t={t}
      />

      {/* Auto-resolved notification */}
      {autoResolvedMessage && (
        <div className="auto-resolved-notification" onClick={clearAutoResolvedMessage}>
          <span>{autoResolvedMessage}</span>
          <X size={14} />
        </div>
      )}
    </div>

    {/* Artifact Panel */}
    <ArtifactPanel />

    {/* Trace Panel */}
    <TracePanel t={t} />

    {/* Floating Panels for Direct Mode Results */}
    {directModeDisplay === 'floating' && floatingPanels.length > 0 && (
      <div className="floating-panels-container">
        {floatingPanels.map((panel) => (
          <DirectModeFloatingPanel
            key={panel.id}
            panel={panel}
            onClose={closePanel}
            onMinimize={minimizePanel}
            onRestore={restorePanel}
            onBringToFront={bringToFront}
            onUpdatePosition={updatePosition}
            onUpdateSize={updateSize}
            t={t}
          />
        ))}
      </div>
    )}

    {/* Minimized panels bar */}
    {directModeDisplay === 'floating' && floatingPanels.filter(p => p.isMinimized).length > 0 && (
      <div className="minimized-panels-bar">
        {floatingPanels.filter(p => p.isMinimized).map((panel) => (
          <button
            key={panel.id}
            className="minimized-panel-item"
            onClick={() => restorePanel(panel.id)}
            title={panel.title}
          >
            <MessageSquare size={14} />
            <span>{panel.title.length > 15 ? panel.title.slice(0, 15) + '...' : panel.title}</span>
          </button>
        ))}
        {floatingPanels.filter(p => p.isMinimized).length > 1 && (
          <button
            className="minimized-panel-close-all"
            onClick={closeAllPanels}
            title={t('common.closeAll') || 'Close all'}
          >
            <X size={14} />
          </button>
        )}
      </div>
    )}
    </div>
  );
};

export default AgentChat;
