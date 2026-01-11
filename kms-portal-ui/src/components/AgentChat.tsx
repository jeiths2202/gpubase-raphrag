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
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './AgentChat.css';
import { type AgentType } from '../api/agent.api';
import { useArtifactStore, createArtifactFromChunk } from '../store/artifactStore';
import { useConversationStore } from '../store/conversationStore';
import { ArtifactPanel } from './ArtifactPanel';
import { ConversationSidebar } from './ConversationSidebar';

// Import from refactored modules
import {
  MessageBubble,
  IMSCredentialsModal,
  useFileAttachment,
  useUrlAttachment,
  useStreamingChat,
  AGENT_CONFIGS,
  SUGGESTED_QUESTIONS,
  SUPPORTED_EXTENSIONS,
  type ChatMessage,
} from './AgentChat/index';

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

  // Get active conversation ID for current agent
  const agentState = agentStates[selectedAgent] || { activeConversationId: null };
  const activeConversationId = agentState.activeConversationId;

  // Get artifacts for current agent
  const artifacts = getCurrentArtifacts();

  // IMS Credentials modal state
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  // File attachment (using custom hook)
  const {
    attachedFiles,
    fileError,
    fileInputRef,
    handleFileAttach,
    handleFileChange,
    handleRemoveFile,
    handleClearAllFiles,
    getFileContext,
    clearFileError,
  } = useFileAttachment();

  // URL attachment (using custom hook)
  const {
    attachedUrls,
    detectedUrl,
    handleUrlDetect,
    handleFetchUrl,
    handleRemoveUrl,
    getUrlContext,
    dismissDetectedUrl,
  } = useUrlAttachment();

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
  } = useStreamingChat(selectedAgentRef, {
    t,
    userLanguage,
    agentStates,
    createConversation,
    loadConversations,
    addArtifact,
    createArtifactFromChunk,
    getFileContext,
    getUrlContext,
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

  // Restore agent state and load conversations when agent type changes
  useEffect(() => {
    // Sync streaming chat state for the selected agent
    syncAgentState(selectedAgent);

    // Update artifact store to show this agent's artifacts
    setArtifactAgentType(selectedAgent);

    // Load conversations for the new agent type
    loadConversations(selectedAgent);
  }, [selectedAgent, loadConversations, setArtifactAgentType, syncAgentState]);

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

  // Handle send message (wrapper for streaming hook)
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;
    const currentInput = inputValue;
    setInputValue('');
    await streamingHandleSend(currentInput);
  }, [inputValue, isLoading, streamingHandleSend]);

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
                <div key={urlItem.url} className={`agent-attached-url ${urlItem.isLoading ? 'loading' : ''} ${urlItem.error ? 'error' : ''}`}>
                  {urlItem.isLoading ? (
                    <Loader2 size={14} className="spin" />
                  ) : urlItem.error ? (
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
    </div>

    {/* Artifact Panel */}
    <ArtifactPanel />
    </div>
  );
};

export default AgentChat;
