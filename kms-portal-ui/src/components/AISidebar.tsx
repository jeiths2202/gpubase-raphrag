/**
 * AI Sidebar Component (Right Panel)
 *
 * NotebookLM-style AI assistant sidebar with chat interface
 * Features:
 * - Streaming responses with typing effect
 * - Conversation history management
 * - Source documents with relevance scores
 * - Notes with localStorage persistence
 * - Markdown rendering for code blocks
 * - Message copy and feedback buttons
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  MessageSquare,
  FileText,
  Link2,
  StickyNote,
  Send,
  Loader2,
  X,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Copy,
  RefreshCw,
  Plus,
  Trash2,
  Check,
  History,
  Edit2,
  Save,
  ExternalLink,
  GripHorizontal,
  Minimize2,
  Maximize2,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useUIStore } from '../store/uiStore';

// Storage key for AI sidebar position
const AI_SIDEBAR_POSITION_KEY = 'kms-portal-ai-sidebar-position';

// Default panel position (right side)
const DEFAULT_SIDEBAR_POSITION = { x: -420, y: 80 }; // Relative to right edge

interface SidebarPosition {
  x: number;
  y: number;
}

// Load saved panel position from localStorage
const loadSidebarPosition = (): SidebarPosition => {
  try {
    const saved = localStorage.getItem(AI_SIDEBAR_POSITION_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.warn('Failed to load sidebar position:', e);
  }
  return DEFAULT_SIDEBAR_POSITION;
};

// Save panel position to localStorage
const saveSidebarPosition = (position: SidebarPosition) => {
  try {
    localStorage.setItem(AI_SIDEBAR_POSITION_KEY, JSON.stringify(position));
  } catch (e) {
    console.warn('Failed to save sidebar position:', e);
  }
};

// Tab type
type TabId = 'chat' | 'conversations' | 'sources' | 'notes';

// Chat message interface
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceDocument[];
  timestamp: Date;
  isStreaming?: boolean;
}

// Source document interface
interface SourceDocument {
  id: string;
  title: string;
  relevance: number;
  snippet?: string;
  url?: string;
}

// Conversation interface
interface Conversation {
  id: string;
  title: string;
  lastMessage: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
}

// Note interface
interface Note {
  id: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

// Feedback state
interface FeedbackState {
  [messageId: string]: 'up' | 'down' | null;
}

// Suggested questions
const SUGGESTED_QUESTIONS = [
  'How do I get started?',
  'What is RAG technology?',
  'How to configure IMS Crawler?',
];

// Local storage keys
const STORAGE_KEYS = {
  NOTES: 'kms-portal-ai-notes',
  CURRENT_CONVERSATION: 'kms-portal-current-conversation',
};

// Markdown-like renderer for code blocks
const renderMessageContent = (content: string): React.ReactNode => {
  const parts: React.ReactNode[] = [];
  let key = 0;

  // Simple markdown parsing for code blocks
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
              {renderInlineMarkdown(line)}
            </React.Fragment>
          ))}
        </span>
      );
    }

    // Add code block
    const language = match[1] || 'text';
    const code = match[2].trim();
    parts.push(
      <pre key={key++} className="ai-chat-code-block">
        <div className="ai-chat-code-header">
          <span className="ai-chat-code-lang">{language}</span>
          <button
            className="ai-chat-code-copy"
            onClick={() => navigator.clipboard.writeText(code)}
            title="Copy code"
          >
            <Copy size={12} />
          </button>
        </div>
        <code className={`language-${language}`}>{code}</code>
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
            {renderInlineMarkdown(line)}
          </React.Fragment>
        ))}
      </span>
    );
  }

  return parts.length > 0 ? parts : content;
};

// Render inline markdown (bold, italic, inline code)
const renderInlineMarkdown = (text: string): React.ReactNode => {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  // Bold: **text**
  const boldRegex = /\*\*(.*?)\*\*/g;
  // Inline code: `code`
  const inlineCodeRegex = /`([^`]+)`/g;

  // Simple replacement - bold
  remaining = remaining.replace(boldRegex, (_, content) => `<strong>${content}</strong>`);
  // Inline code
  remaining = remaining.replace(inlineCodeRegex, (_, content) => `<code class="ai-chat-inline-code">${content}</code>`);

  // Parse HTML-like tags we created
  const htmlRegex = /<(strong|code[^>]*)>([^<]*)<\/\1>/g;
  let lastIndex = 0;
  let match;

  while ((match = htmlRegex.exec(remaining)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={key++}>{remaining.substring(lastIndex, match.index)}</span>);
    }

    if (match[1] === 'strong') {
      parts.push(<strong key={key++}>{match[2]}</strong>);
    } else if (match[1].startsWith('code')) {
      parts.push(
        <code key={key++} className="ai-chat-inline-code">
          {match[2]}
        </code>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < remaining.length) {
    parts.push(<span key={key++}>{remaining.substring(lastIndex)}</span>);
  }

  return parts.length > 0 ? <>{parts}</> : text;
};

export const AISidebar: React.FC = () => {
  const { t } = useTranslation();
  const { rightSidebarOpen, toggleRightSidebar } = useUIStore();

  // Floating panel state
  const [sidebarPosition, setSidebarPosition] = useState<SidebarPosition>(loadSidebarPosition);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // State
  const [activeTab, setActiveTab] = useState<TabId>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [streamingContent, setStreamingContent] = useState('');

  // Conversation state
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);

  // Source documents state (collected from all messages)
  const [allSources, setAllSources] = useState<SourceDocument[]>([]);

  // Notes state
  const [notes, setNotes] = useState<Note[]>([]);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteContent, setNoteContent] = useState('');

  // Feedback state
  const [feedback, setFeedback] = useState<FeedbackState>({});

  // Copy state
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const noteInputRef = useRef<HTMLTextAreaElement>(null);

  // Load notes from localStorage
  useEffect(() => {
    try {
      const savedNotes = localStorage.getItem(STORAGE_KEYS.NOTES);
      if (savedNotes) {
        setNotes(JSON.parse(savedNotes));
      }
    } catch (error) {
      console.error('Failed to load notes:', error);
    }
  }, []);

  // Save notes to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.NOTES, JSON.stringify(notes));
    } catch (error) {
      console.error('Failed to save notes:', error);
    }
  }, [notes]);

  // Fetch conversations on mount
  useEffect(() => {
    fetchConversations();
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  // Update all sources when messages change
  useEffect(() => {
    const sources: SourceDocument[] = [];
    const seenIds = new Set<string>();

    messages.forEach((msg) => {
      if (msg.sources) {
        msg.sources.forEach((source) => {
          if (!seenIds.has(source.id)) {
            seenIds.add(source.id);
            sources.push(source);
          }
        });
      }
    });

    // Sort by relevance
    sources.sort((a, b) => b.relevance - a.relevance);
    setAllSources(sources);
  }, [messages]);

  // Drag handlers for floating panel
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
    setDragStart({
      x: e.clientX - sidebarPosition.x,
      y: e.clientY - sidebarPosition.y
    });
  }, [sidebarPosition]);

  const handleDragMove = useCallback((e: MouseEvent) => {
    if (isDragging) {
      const newX = e.clientX - dragStart.x;
      const newY = e.clientY - dragStart.y;

      // Constrain to viewport with padding
      const constrainedX = Math.max(-window.innerWidth + 100, Math.min(newX, window.innerWidth - 100));
      const constrainedY = Math.max(60, Math.min(newY, window.innerHeight - 100));

      setSidebarPosition({ x: constrainedX, y: constrainedY });
    }
  }, [isDragging, dragStart]);

  const handleDragEnd = useCallback(() => {
    if (isDragging) {
      setIsDragging(false);
      saveSidebarPosition(sidebarPosition);
    }
  }, [isDragging, sidebarPosition]);

  // Drag event listeners
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleDragMove);
      window.addEventListener('mouseup', handleDragEnd);
      return () => {
        window.removeEventListener('mousemove', handleDragMove);
        window.removeEventListener('mouseup', handleDragEnd);
      };
    }
  }, [isDragging, handleDragMove, handleDragEnd]);

  // Toggle minimize
  const toggleMinimize = useCallback(() => {
    setIsMinimized(prev => !prev);
  }, []);

  // Fetch conversations
  const fetchConversations = async () => {
    setIsLoadingConversations(true);
    try {
      const response = await fetch('/api/v1/conversations');
      const data = await response.json();
      setConversations(data.conversations || []);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    } finally {
      setIsLoadingConversations(false);
    }
  };

  // Fetch conversation messages
  const fetchConversationMessages = async (conversationId: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/v1/conversations/${conversationId}/messages`);
      const data = await response.json();

      if (data.messages) {
        setMessages(
          data.messages.map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
          }))
        );
        setCurrentConversationId(conversationId);
        setShowSuggestions(false);
        setActiveTab('chat');
      }
    } catch (error) {
      console.error('Failed to fetch conversation messages:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Delete conversation
  const deleteConversation = async (conversationId: string) => {
    try {
      await fetch(`/api/v1/conversations/${conversationId}`, {
        method: 'DELETE',
      });

      setConversations((prev) => prev.filter((c) => c.id !== conversationId));

      if (currentConversationId === conversationId) {
        handleNewConversation();
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  // Start new conversation
  const handleNewConversation = () => {
    setMessages([]);
    setCurrentConversationId(null);
    setShowSuggestions(true);
    setActiveTab('chat');
    setAllSources([]);
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  // Handle send message with streaming
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setShowSuggestions(false);
    setIsLoading(true);
    setStreamingContent('');

    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    try {
      // Use streaming endpoint
      const response = await fetch('/api/v1/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage.content,
          conversationId: currentConversationId,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let accumulatedContent = '';
      let sources: SourceDocument[] = [];

      // Create placeholder assistant message
      const assistantMessageId = `msg-${Date.now()}-assistant`;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter((line) => line.startsWith('data: '));

        for (const line of lines) {
          const data = line.replace('data: ', '').trim();

          if (data === '[DONE]') {
            // Streaming complete
            break;
          }

          try {
            const parsed = JSON.parse(data);

            if (parsed.type === 'content') {
              accumulatedContent += parsed.content;
              setStreamingContent(accumulatedContent);
            } else if (parsed.type === 'sources') {
              sources = parsed.sources || [];
            }
          } catch (e) {
            // Ignore parse errors for incomplete chunks
          }
        }
      }

      // Create final assistant message
      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: accumulatedContent,
        sources: sources,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setStreamingContent('');

      // Update conversation ID if new
      if (!currentConversationId) {
        setCurrentConversationId(`conv-${Date.now()}`);
      }
    } catch (error) {
      console.error('Chat error:', error);
      // Fallback to non-streaming
      try {
        const fallbackResponse = await fetch('/api/v1/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: userMessage.content }),
        });

        const data = await fallbackResponse.json();

        const assistantMessage: ChatMessage = {
          id: data.id,
          role: 'assistant',
          content: data.response,
          sources: data.sources,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } catch (fallbackError) {
        // Add error message
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: t('knowledge.chat.errorMessage') || 'Sorry, I encountered an error. Please try again.',
            timestamp: new Date(),
          },
        ]);
      }
    } finally {
      setIsLoading(false);
      setStreamingContent('');
    }
  };

  // Handle key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Handle suggested question click
  const handleSuggestionClick = (question: string) => {
    setInputValue(question);
    inputRef.current?.focus();
  };

  // Clear chat
  const handleClearChat = () => {
    setMessages([]);
    setShowSuggestions(true);
    setCurrentConversationId(null);
    setAllSources([]);
  };

  // Copy message to clipboard with feedback
  const handleCopyMessage = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  // Handle feedback
  const handleFeedback = (messageId: string, type: 'up' | 'down') => {
    setFeedback((prev) => ({
      ...prev,
      [messageId]: prev[messageId] === type ? null : type,
    }));
  };

  // Navigate to source document
  const handleSourceClick = (source: SourceDocument) => {
    // In real implementation, this would navigate to the document
    console.log('Navigate to source:', source);
    // Could emit event or use router
  };

  // Notes CRUD operations
  const handleAddNote = () => {
    if (!noteContent.trim()) return;

    const newNote: Note = {
      id: `note-${Date.now()}`,
      content: noteContent.trim(),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    setNotes((prev) => [newNote, ...prev]);
    setNoteContent('');
    setEditingNoteId(null);
  };

  const handleEditNote = (note: Note) => {
    setEditingNoteId(note.id);
    setNoteContent(note.content);
    noteInputRef.current?.focus();
  };

  const handleUpdateNote = () => {
    if (!editingNoteId || !noteContent.trim()) return;

    setNotes((prev) =>
      prev.map((note) =>
        note.id === editingNoteId
          ? { ...note, content: noteContent.trim(), updatedAt: new Date().toISOString() }
          : note
      )
    );
    setNoteContent('');
    setEditingNoteId(null);
  };

  const handleDeleteNote = (noteId: string) => {
    setNotes((prev) => prev.filter((note) => note.id !== noteId));
    if (editingNoteId === noteId) {
      setEditingNoteId(null);
      setNoteContent('');
    }
  };

  const handleCancelNoteEdit = () => {
    setEditingNoteId(null);
    setNoteContent('');
  };

  // Tabs configuration
  const tabs: { id: TabId; icon: React.ReactNode; label: string }[] = [
    { id: 'chat', icon: <MessageSquare size={16} />, label: t('knowledge.sidebar.chat') },
    { id: 'conversations', icon: <History size={16} />, label: t('knowledge.conversationHistory') },
    { id: 'sources', icon: <Link2 size={16} />, label: t('knowledge.sidebar.sources') },
    { id: 'notes', icon: <StickyNote size={16} />, label: t('knowledge.sidebar.notes') },
  ];

  // FAB button when sidebar is closed
  if (!rightSidebarOpen) {
    return (
      <button
        className="ai-sidebar-fab"
        onClick={toggleRightSidebar}
        title={t('knowledge.chat.title')}
      >
        <Sparkles size={24} />
      </button>
    );
  }

  return (
    <aside
      className={`portal-ai-sidebar floating ${isMinimized ? 'minimized' : ''} ${isDragging ? 'dragging' : ''}`}
      style={{
        left: sidebarPosition.x < 0 ? 'auto' : sidebarPosition.x,
        right: sidebarPosition.x < 0 ? Math.abs(sidebarPosition.x) : 'auto',
        top: sidebarPosition.y,
      }}
    >
      {/* Draggable Header */}
      <div
        className="ai-sidebar-header ai-sidebar-drag-handle"
        onMouseDown={handleDragStart}
      >
        <div className="ai-sidebar-drag-indicator">
          <GripHorizontal size={16} />
        </div>
        <div className="ai-sidebar-title">
          <Sparkles size={18} className="ai-sidebar-icon" />
          <span>{t('knowledge.chat.title')}</span>
        </div>
        <div className="ai-sidebar-header-actions">
          <button
            className="btn btn-ghost btn-xs"
            onClick={toggleMinimize}
            title={isMinimized ? 'Expand' : 'Minimize'}
          >
            {isMinimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
          </button>
          <button
            className="btn btn-ghost btn-xs"
            onClick={toggleRightSidebar}
            aria-label="Close AI sidebar"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Collapsible Content */}
      {!isMinimized && (
        <>
          {/* Tabs */}
          <div className="ai-sidebar-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`ai-sidebar-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="ai-sidebar-content">
        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <>
            {/* Messages area */}
            <div className="ai-chat-messages">
              {messages.length === 0 && showSuggestions ? (
                <div className="ai-chat-empty">
                  <div className="ai-chat-empty-icon">
                    <Sparkles size={32} />
                  </div>
                  <h3>{t('knowledge.chat.title')}</h3>
                  <p>{t('knowledge.chat.subtitle')}</p>

                  {/* Suggestions */}
                  <div className="ai-chat-suggestions">
                    <span className="ai-chat-suggestions-label">
                      {t('knowledge.chat.suggestions')}:
                    </span>
                    {SUGGESTED_QUESTIONS.map((q, i) => (
                      <button
                        key={i}
                        className="ai-chat-suggestion"
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
                    <div key={msg.id} className={`ai-chat-message ${msg.role}`}>
                      <div className="ai-chat-message-content">
                        {msg.role === 'assistant' ? (
                          renderMessageContent(msg.content)
                        ) : (
                          msg.content.split('\n').map((line, i) => (
                            <p key={i}>{line}</p>
                          ))
                        )}
                      </div>

                      {/* Sources */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="ai-chat-sources">
                          <span className="ai-chat-sources-label">{t('knowledge.sources')}:</span>
                          {msg.sources.map((source) => (
                            <button
                              key={source.id}
                              className="ai-chat-source"
                              onClick={() => handleSourceClick(source)}
                            >
                              <FileText size={12} />
                              <span>{source.title}</span>
                              <span className="ai-chat-source-relevance">
                                {Math.round(source.relevance * 100)}%
                              </span>
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Actions for assistant messages */}
                      {msg.role === 'assistant' && (
                        <div className="ai-chat-message-actions">
                          <button
                            className={`ai-chat-action ${copiedMessageId === msg.id ? 'copied' : ''}`}
                            onClick={() => handleCopyMessage(msg.content, msg.id)}
                            title={t('common.copy') || 'Copy'}
                          >
                            {copiedMessageId === msg.id ? (
                              <Check size={14} />
                            ) : (
                              <Copy size={14} />
                            )}
                          </button>
                          <button
                            className={`ai-chat-action ${feedback[msg.id] === 'up' ? 'active' : ''}`}
                            onClick={() => handleFeedback(msg.id, 'up')}
                            title={t('knowledge.article.helpful') || 'Helpful'}
                          >
                            <ThumbsUp size={14} />
                          </button>
                          <button
                            className={`ai-chat-action ${feedback[msg.id] === 'down' ? 'active' : ''}`}
                            onClick={() => handleFeedback(msg.id, 'down')}
                            title={t('knowledge.article.notHelpful') || 'Not helpful'}
                          >
                            <ThumbsDown size={14} />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Streaming indicator */}
                  {isLoading && streamingContent && (
                    <div className="ai-chat-message assistant streaming">
                      <div className="ai-chat-message-content">
                        {renderMessageContent(streamingContent)}
                        <span className="ai-chat-cursor" />
                      </div>
                    </div>
                  )}

                  {/* Loading indicator (when not streaming) */}
                  {isLoading && !streamingContent && (
                    <div className="ai-chat-message assistant loading">
                      <div className="ai-chat-loading">
                        <div className="ai-chat-thinking">
                          <span className="ai-chat-thinking-dot" />
                          <span className="ai-chat-thinking-dot" />
                          <span className="ai-chat-thinking-dot" />
                        </div>
                        <span>{t('knowledge.chat.thinking')}</span>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* Input area */}
            <div className="ai-chat-input-container">
              {messages.length > 0 && (
                <div className="ai-chat-actions-bar">
                  <button className="ai-chat-clear" onClick={handleClearChat}>
                    <RefreshCw size={14} />
                    <span>{t('knowledge.chat.clearHistory')}</span>
                  </button>
                  <button className="ai-chat-new" onClick={handleNewConversation}>
                    <Plus size={14} />
                    <span>{t('knowledge.newConversation')}</span>
                  </button>
                </div>
              )}
              <div className="ai-chat-input-wrapper">
                <textarea
                  ref={inputRef}
                  className="ai-chat-input"
                  placeholder={t('knowledge.chat.inputPlaceholder')}
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyPress}
                  rows={1}
                />
                <button
                  className="ai-chat-send"
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isLoading}
                >
                  {isLoading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
                </button>
              </div>
            </div>
          </>
        )}

        {/* Conversations Tab */}
        {activeTab === 'conversations' && (
          <div className="ai-conversations">
            <div className="ai-conversations-header">
              <button className="btn btn-primary btn-sm" onClick={handleNewConversation}>
                <Plus size={16} />
                <span>{t('knowledge.newConversation')}</span>
              </button>
            </div>

            {isLoadingConversations ? (
              <div className="ai-conversations-loading">
                <Loader2 size={24} className="spin" />
              </div>
            ) : conversations.length === 0 ? (
              <div className="ai-conversations-empty">
                <History size={32} />
                <p>{t('knowledge.chat.noConversations') || 'No conversations yet'}</p>
                <span>{t('knowledge.chat.startNewConversation') || 'Start a new conversation'}</span>
              </div>
            ) : (
              <div className="ai-conversations-list">
                {conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`ai-conversation-item ${currentConversationId === conv.id ? 'active' : ''}`}
                  >
                    <button
                      className="ai-conversation-content"
                      onClick={() => fetchConversationMessages(conv.id)}
                    >
                      <div className="ai-conversation-title">{conv.title}</div>
                      <div className="ai-conversation-preview">{conv.lastMessage}</div>
                      <div className="ai-conversation-meta">
                        <span>{conv.messageCount} messages</span>
                        <span>{new Date(conv.updatedAt).toLocaleDateString()}</span>
                      </div>
                    </button>
                    <button
                      className="ai-conversation-delete"
                      onClick={() => deleteConversation(conv.id)}
                      title="Delete conversation"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Sources Tab */}
        {activeTab === 'sources' && (
          <div className="ai-sources">
            {allSources.length === 0 ? (
              <div className="ai-sources-empty">
                <Link2 size={32} />
                <p>{t('knowledge.sidebar.sources')}</p>
                <span>{t('knowledge.chat.noSourcesYet') || 'Referenced sources will appear here after chatting'}</span>
              </div>
            ) : (
              <div className="ai-sources-list">
                {allSources.map((source) => (
                  <button
                    key={source.id}
                    className="ai-source-item"
                    onClick={() => handleSourceClick(source)}
                  >
                    <div className="ai-source-icon">
                      <FileText size={16} />
                    </div>
                    <div className="ai-source-content">
                      <div className="ai-source-title">{source.title}</div>
                      {source.snippet && (
                        <div className="ai-source-snippet">{source.snippet}</div>
                      )}
                      <div className="ai-source-meta">
                        <span className="ai-source-relevance-badge">
                          {t('knowledge.relevance')}: {Math.round(source.relevance * 100)}%
                        </span>
                      </div>
                    </div>
                    <div className="ai-source-arrow">
                      <ExternalLink size={14} />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Notes Tab */}
        {activeTab === 'notes' && (
          <div className="ai-notes">
            <div className="ai-notes-input">
              <textarea
                ref={noteInputRef}
                className="ai-notes-textarea"
                placeholder={t('knowledge.chat.addNote') || 'Add a note...'}
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                rows={3}
              />
              <div className="ai-notes-input-actions">
                {editingNoteId ? (
                  <>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={handleCancelNoteEdit}
                    >
                      {t('common.cancel') || 'Cancel'}
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleUpdateNote}
                      disabled={!noteContent.trim()}
                    >
                      <Save size={14} />
                      <span>{t('common.save') || 'Save'}</span>
                    </button>
                  </>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleAddNote}
                    disabled={!noteContent.trim()}
                  >
                    <Plus size={14} />
                    <span>{t('knowledge.chat.addNote') || 'Add Note'}</span>
                  </button>
                )}
              </div>
            </div>

            {notes.length === 0 ? (
              <div className="ai-notes-empty">
                <StickyNote size={32} />
                <p>{t('knowledge.sidebar.notes')}</p>
                <span>{t('knowledge.chat.noNotesYet') || 'Your notes will appear here'}</span>
              </div>
            ) : (
              <div className="ai-notes-list">
                {notes.map((note) => (
                  <div
                    key={note.id}
                    className={`ai-note-item ${editingNoteId === note.id ? 'editing' : ''}`}
                  >
                    <div className="ai-note-content">{note.content}</div>
                    <div className="ai-note-meta">
                      <span>{new Date(note.updatedAt).toLocaleDateString()}</span>
                    </div>
                    <div className="ai-note-actions">
                      <button
                        className="ai-note-action"
                        onClick={() => handleEditNote(note)}
                        title={t('common.edit') || 'Edit'}
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        className="ai-note-action"
                        onClick={() => handleDeleteNote(note.id)}
                        title={t('common.delete') || 'Delete'}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
        </>
      )}
    </aside>
  );
};

export default AISidebar;
