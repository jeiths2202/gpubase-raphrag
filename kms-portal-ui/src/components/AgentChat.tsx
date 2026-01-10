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
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './AgentChat.css';
import {
  streamAgent,
  type AgentType,
  type AgentSource,
} from '../api/agent.api';
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
  const { t } = useTranslation();

  // Artifact store
  const {
    artifacts,
    panel: artifactPanel,
    addArtifact,
    clearArtifacts,
    togglePanel: toggleArtifactPanel,
  } = useArtifactStore();

  // Conversation store
  const {
    currentConversation,
    loadConversations,
    createConversation,
    selectConversation,
    startNewConversation,
  } = useConversationStore();

  // State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentType>('auto');
  const [showAgentSelector, setShowAgentSelector] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState<ChatMessage | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [showHistorySidebar, setShowHistorySidebar] = useState(false);

  // IMS Credentials modal state
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);
  const [imsUsername, setImsUsername] = useState('');
  const [imsPassword, setImsPassword] = useState('');
  const [isSubmittingCredentials, setIsSubmittingCredentials] = useState(false);
  const [credentialsError, setCredentialsError] = useState<string | null>(null);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const agentSelectorRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

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

  // Handle send message
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

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
      agentType: selectedAgent,
      toolCalls: [],
      sources: [],
      isStreaming: true,
    };
    setStreamingMessage(streamingMsg);

    // Create abort controller for cancellation
    const controller = new AbortController();
    setAbortController(controller);

    try {
      let accumulatedContent = '';
      const toolCalls: ToolCallInfo[] = [];
      let sources: AgentSource[] = [];
      let receivedAnyChunk = false;

      console.log('[AgentChat] Starting stream for task:', userMessage.content, 'agent:', selectedAgent);

      // When 'auto' is selected, don't send agent_type to let backend classify
      const requestPayload = selectedAgent === 'auto'
        ? { task: userMessage.content }
        : { task: userMessage.content, agent_type: selectedAgent };

      for await (const chunk of streamAgent(
        requestPayload,
        controller.signal
      )) {
        receivedAnyChunk = true;
        console.log('[AgentChat] Received chunk:', chunk.chunk_type, chunk);
        switch (chunk.chunk_type) {
          case 'thinking':
            // Update with thinking status
            setStreamingMessage((prev) =>
              prev ? { ...prev, content: chunk.content || 'Analyzing...' } : prev
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
              setStreamingMessage((prev) =>
                prev ? { ...prev, toolCalls: [...toolCalls] } : prev
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
                setStreamingMessage((prev) =>
                  prev ? { ...prev, toolCalls: [...toolCalls] } : prev
                );
              }
            }
            break;

          case 'text':
            // Accumulate text content
            accumulatedContent += chunk.content || '';
            setStreamingMessage((prev) =>
              prev ? { ...prev, content: accumulatedContent } : prev
            );
            break;

          case 'sources':
            // Update sources
            sources = chunk.sources || [];
            setStreamingMessage((prev) =>
              prev ? { ...prev, sources } : prev
            );
            break;

          case 'artifact':
            // Handle artifact chunk - add to artifact store
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
                addArtifact(artifact);
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
                setIsLoading(false);
                setStreamingMessage(null);
                return; // Stop processing, user needs to enter credentials
              }

              const statusMsg: ChatMessage = {
                id: `status-${Date.now()}`,
                role: 'status',
                content: statusKey, // Store the key, translate in render
                timestamp: new Date(),
                statusType: statusKey === 'crawling' ? 'crawling' : 'ready',
              };
              setMessages((prev) => [...prev, statusMsg]);
            }
            break;

          case 'error':
            // Handle error
            setStreamingMessage((prev) =>
              prev
                ? {
                    ...prev,
                    content: chunk.content || 'An error occurred',
                    error: chunk.content || 'Unknown error',
                    isStreaming: false,
                  }
                : prev
            );
            break;

          case 'done':
            // Streaming complete - remove processing status messages
            setMessages((prev) => prev.filter(msg =>
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
        agentType: selectedAgent,
        toolCalls,
        sources,
        isStreaming: false,
      };

      console.log('[AgentChat] Final message:', finalMessage);
      setMessages((prev) => [
        ...prev.filter(msg =>
          !(msg.role === 'status' &&
            (msg.content === 'processing' || msg.content === 'crawling' || msg.content === 'searching'))
        ),
        finalMessage
      ]);
      setStreamingMessage(null);
    } catch (error) {
      console.error('[AgentChat] Stream error:', error);
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was cancelled
        setStreamingMessage(null);
      } else {
        console.error('Agent chat error:', error);
        const errorMessage: ChatMessage = {
          id: assistantMessageId,
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
          agentType: selectedAgent,
          error: error instanceof Error ? error.message : 'Unknown error',
          isStreaming: false,
        };
        setMessages((prev) => [...prev, errorMessage]);
        setStreamingMessage(null);
      }
    } finally {
      setIsLoading(false);
      setAbortController(null);
    }
  }, [inputValue, isLoading, selectedAgent]);

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
    clearArtifacts(); // Also clear artifacts
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

  // Handle select conversation from sidebar
  const handleSelectConversation = useCallback(async (conversationId: string) => {
    try {
      await selectConversation(selectedAgent, conversationId);
      // Load messages from current conversation
      if (currentConversation) {
        const loadedMessages: ChatMessage[] = currentConversation.messages.map((msg) => ({
          id: msg.id,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(msg.created_at),
          agentType: selectedAgent,
          sources: msg.sources,
        }));
        setMessages(loadedMessages);
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  }, [selectedAgent, selectConversation, currentConversation]);

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
        <div className="agent-chat-input-wrapper">
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
// Message Content Renderer
// =============================================================================

interface MessageContentProps {
  content: string;
}

const MessageContent: React.FC<MessageContentProps> = ({ content }) => {
  if (!content) return null;

  // Simple markdown-like rendering
  const parts: React.ReactNode[] = [];
  let key = 0;

  // Code block regex
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before code block
    if (match.index > lastIndex) {
      const textBefore = content.substring(lastIndex, match.index);
      parts.push(
        <span key={key++}>
          {textBefore.split('\n').map((line, i) => (
            <React.Fragment key={i}>
              {i > 0 && <br />}
              {line}
            </React.Fragment>
          ))}
        </span>
      );
    }

    // Add code block
    const language = match[1] || 'text';
    const code = match[2].trim();
    parts.push(
      <pre key={key++} className="agent-code-block">
        <div className="agent-code-header">
          <span className="agent-code-lang">{language}</span>
          <button
            className="agent-code-copy"
            onClick={() => navigator.clipboard.writeText(code)}
            title="Copy code"
          >
            <Copy size={12} />
          </button>
        </div>
        <code>{code}</code>
      </pre>
    );

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < content.length) {
    const textAfter = content.substring(lastIndex);
    parts.push(
      <span key={key++}>
        {textAfter.split('\n').map((line, i) => (
          <React.Fragment key={i}>
            {i > 0 && <br />}
            {line}
          </React.Fragment>
        ))}
      </span>
    );
  }

  return <>{parts.length > 0 ? parts : content}</>;
};

export default AgentChat;
