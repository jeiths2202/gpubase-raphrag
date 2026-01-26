/**
 * IMS AI Assistant Component
 *
 * Floating chat panel for AI-powered assistance with searched IMS issues.
 * Context is LIMITED to the currently searched issues only.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles,
  X,
  Send,
  Maximize2,
  Minimize2,
  MessageSquare,
  History,
  Link2,
  FileText,
  Loader2,
  AlertCircle,
  Trash2,
} from 'lucide-react';
import { streamChatMessage } from '../services/ims-api';
import type { ChatMessage, IMSIssue, IMSChatRequest } from '../types';
import './IMSAIAssistant.css';

interface IMSAIAssistantProps {
  issues: IMSIssue[];
  isOpen: boolean;
  onClose: () => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

type TabType = 'chat' | 'history' | 'sources' | 'notes';

const SUGGESTED_QUESTIONS = [
  'How do I get started?',
  'What is RAG technology?',
  'How to configure IMS Crawler?',
];

export const IMSAIAssistant: React.FC<IMSAIAssistantProps> = ({
  issues,
  isOpen,
  onClose,
  t,
}) => {
  // State
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState('');

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // Handle send message
  const handleSendMessage = useCallback(async (question?: string) => {
    const messageText = question || inputValue.trim();
    if (!messageText || isLoading) return;

    // Check if there are issues to use as context
    if (issues.length === 0) {
      setError(t('ims.chat.noIssuesContext'));
      return;
    }

    setError(null);
    setInputValue('');
    setIsLoading(true);

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      // Get issue IDs for context
      const issueIds = issues.map((issue) => issue.id);

      // Use streaming
      const request: IMSChatRequest = {
        question: messageText,
        issue_ids: issueIds,
        conversation_id: conversationId || undefined,
        stream: true,
        max_context_issues: 10,
      };

      // Stream response
      setStreamingContent('');
      let fullContent = '';
      let newConversationId = conversationId;

      for await (const event of streamChatMessage(request)) {
        const data = event.data;

        if (data.conversation_id && !newConversationId) {
          newConversationId = data.conversation_id as string;
          setConversationId(newConversationId);
        }

        if (data.content) {
          fullContent += data.content;
          setStreamingContent(fullContent);
        }

        if (data.is_final) {
          // Add assistant message
          const assistantMessage: ChatMessage = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: fullContent,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, assistantMessage]);
          setStreamingContent('');
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
      setError(err instanceof Error ? err.message : 'Failed to send message');

      // Remove user message on error
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, issues, conversationId, t]);

  // Handle key press (Enter to send)
  const handleKeyPress = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    },
    [handleSendMessage]
  );

  // Handle suggested question click
  const handleSuggestedQuestion = useCallback(
    (question: string) => {
      handleSendMessage(question);
    },
    [handleSendMessage]
  );

  // Clear chat
  const handleClearChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setStreamingContent('');
  }, []);

  if (!isOpen) return null;

  const tabs: { id: TabType; icon: React.ReactNode; label: string }[] = [
    { id: 'chat', icon: <MessageSquare size={16} />, label: t('ims.chat.tabs.chat') },
    { id: 'history', icon: <History size={16} />, label: t('ims.chat.tabs.history') },
    { id: 'sources', icon: <Link2 size={16} />, label: t('ims.chat.tabs.sources') },
    { id: 'notes', icon: <FileText size={16} />, label: t('ims.chat.tabs.notes') },
  ];

  return (
    <div className={`ims-ai-assistant ${isExpanded ? 'expanded' : ''}`}>
      {/* Header */}
      <header className="ims-ai-assistant__header">
        <div className="ims-ai-assistant__title">
          <Sparkles size={18} className="ims-ai-assistant__icon" />
          <span>{t('ims.chat.title')}</span>
        </div>
        <div className="ims-ai-assistant__actions">
          {messages.length > 0 && (
            <button
              className="ims-ai-assistant__btn"
              onClick={handleClearChat}
              title={t('ims.chat.clear')}
            >
              <Trash2 size={16} />
            </button>
          )}
          <button
            className="ims-ai-assistant__btn"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? t('ims.chat.minimize') : t('ims.chat.maximize')}
          >
            {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <button
            className="ims-ai-assistant__btn"
            onClick={onClose}
            title={t('ims.chat.close')}
          >
            <X size={16} />
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="ims-ai-assistant__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`ims-ai-assistant__tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* Content */}
      <div className="ims-ai-assistant__content">
        {activeTab === 'chat' && (
          <div className="ims-ai-assistant__chat">
            {/* Messages */}
            <div className="ims-ai-assistant__messages">
              {messages.length === 0 && !streamingContent ? (
                <div className="ims-ai-assistant__empty">
                  <Sparkles size={48} className="ims-ai-assistant__empty-icon" />
                  <h3>{t('ims.chat.title')}</h3>
                  <p>{t('ims.chat.description')}</p>

                  {/* Issue context info */}
                  {issues.length > 0 && (
                    <div className="ims-ai-assistant__context-info">
                      <span>{t('ims.chat.contextInfo', { count: issues.length })}</span>
                    </div>
                  )}

                  {/* Suggested questions */}
                  <div className="ims-ai-assistant__suggestions">
                    <span className="ims-ai-assistant__suggestions-label">
                      {t('ims.chat.suggestedQuestions')}
                    </span>
                    {SUGGESTED_QUESTIONS.map((question) => (
                      <button
                        key={question}
                        className="ims-ai-assistant__suggestion"
                        onClick={() => handleSuggestedQuestion(question)}
                        disabled={isLoading || issues.length === 0}
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={`ims-ai-assistant__message ims-ai-assistant__message--${message.role}`}
                    >
                      <div className="ims-ai-assistant__message-content">
                        {message.content}
                      </div>
                    </div>
                  ))}

                  {/* Streaming content */}
                  {streamingContent && (
                    <div className="ims-ai-assistant__message ims-ai-assistant__message--assistant">
                      <div className="ims-ai-assistant__message-content">
                        {streamingContent}
                        <span className="ims-ai-assistant__cursor" />
                      </div>
                    </div>
                  )}

                  {/* Loading indicator */}
                  {isLoading && !streamingContent && (
                    <div className="ims-ai-assistant__message ims-ai-assistant__message--assistant">
                      <div className="ims-ai-assistant__message-content">
                        <Loader2 size={16} className="ims-ai-assistant__loading" />
                        <span>{t('ims.chat.thinking')}</span>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* Error */}
            {error && (
              <div className="ims-ai-assistant__error">
                <AlertCircle size={14} />
                <span>{error}</span>
                <button onClick={() => setError(null)}>
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Input */}
            <div className="ims-ai-assistant__input-container">
              <textarea
                ref={inputRef}
                className="ims-ai-assistant__input"
                placeholder={
                  issues.length > 0
                    ? t('ims.chat.inputPlaceholder')
                    : t('ims.chat.noIssuesPlaceholder')
                }
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyPress}
                disabled={isLoading || issues.length === 0}
                rows={1}
              />
              <button
                className="ims-ai-assistant__send"
                onClick={() => handleSendMessage()}
                disabled={!inputValue.trim() || isLoading || issues.length === 0}
                title={t('ims.chat.send')}
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="ims-ai-assistant__history">
            <div className="ims-ai-assistant__placeholder">
              <History size={32} />
              <p>{t('ims.chat.historyPlaceholder')}</p>
            </div>
          </div>
        )}

        {activeTab === 'sources' && (
          <div className="ims-ai-assistant__sources">
            {issues.length > 0 ? (
              <div className="ims-ai-assistant__sources-list">
                <h4>{t('ims.chat.sourcesTitle', { count: issues.length })}</h4>
                {issues.slice(0, 10).map((issue) => (
                  <div key={issue.id} className="ims-ai-assistant__source-item">
                    <span className="ims-ai-assistant__source-id">{issue.ims_id}</span>
                    <span className="ims-ai-assistant__source-title">{issue.title}</span>
                  </div>
                ))}
                {issues.length > 10 && (
                  <div className="ims-ai-assistant__source-more">
                    +{issues.length - 10} {t('ims.chat.moreIssues')}
                  </div>
                )}
              </div>
            ) : (
              <div className="ims-ai-assistant__placeholder">
                <Link2 size={32} />
                <p>{t('ims.chat.noSourcesPlaceholder')}</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'notes' && (
          <div className="ims-ai-assistant__notes">
            <div className="ims-ai-assistant__placeholder">
              <FileText size={32} />
              <p>{t('ims.chat.notesPlaceholder')}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default IMSAIAssistant;
