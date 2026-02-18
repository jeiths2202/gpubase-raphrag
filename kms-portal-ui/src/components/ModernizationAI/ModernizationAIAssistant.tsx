/**
 * ModernizationAIAssistant - Floating AI chat panel for Legacy Modernization.
 *
 * Features:
 * - FAB button with sparkles icon
 * - System selector: HOST / OpenFrame / ALL
 * - 4 tabs: Chat, History, Sources, Notes
 * - SSE streaming chat via fetch+ReadableStream
 * - Drag/resize with localStorage persistence
 * - Notes persistence in localStorage
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles,
  X,
  Minus,
  Send,
  StopCircle,
  MessageSquare,
  Clock,
  FileText,
  StickyNote,
  Plus,
  Trash2,
  Server,
  Database,
  Layers,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import { useFloatingPanel } from './useFloatingPanel';
import { useModernizationChat } from './useModernizationChat';
import type {
  SystemType,
  ChatTab,
  ChatNote,
  AnalysisContextInfo,
} from './types';
import './ModernizationAIAssistant.css';

// ============================================================================
// Markdown rendering helpers
// ============================================================================

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*(.+?)\*\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[1]) {
      parts.push(<strong key={key++}>{match[2]}</strong>);
    } else if (match[3]) {
      parts.push(<code key={key++} className="mod-ai-inline-code">{match[4]}</code>);
    } else if (match[5]) {
      parts.push(
        <a key={key++} href={match[7]} target="_blank" rel="noopener noreferrer">
          {match[6]}
        </a>
      );
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

function renderMessageContent(content: string): React.ReactNode {
  if (!content) return null;

  const blocks: React.ReactNode[] = [];
  const lines = content.split('\n');
  let inCode = false;
  let codeLines: string[] = [];
  let codeLang = '';
  let blockKey = 0;

  for (const line of lines) {
    if (line.startsWith('```') && !inCode) {
      inCode = true;
      codeLang = line.slice(3).trim();
      codeLines = [];
    } else if (line.startsWith('```') && inCode) {
      inCode = false;
      blocks.push(
        <div key={blockKey++} className="mod-ai-code-block">
          {codeLang && <div className="mod-ai-code-lang">{codeLang}</div>}
          <pre><code>{codeLines.join('\n')}</code></pre>
        </div>
      );
    } else if (inCode) {
      codeLines.push(line);
    } else if (line.startsWith('### ')) {
      blocks.push(<h4 key={blockKey++} className="mod-ai-heading">{line.slice(4)}</h4>);
    } else if (line.startsWith('## ')) {
      blocks.push(<h3 key={blockKey++} className="mod-ai-heading">{line.slice(3)}</h3>);
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      blocks.push(
        <div key={blockKey++} className="mod-ai-list-item">
          <span className="mod-ai-bullet" />
          <span>{renderInlineMarkdown(line.slice(2))}</span>
        </div>
      );
    } else if (line.trim() === '') {
      blocks.push(<div key={blockKey++} className="mod-ai-spacer" />);
    } else {
      blocks.push(<p key={blockKey++} className="mod-ai-paragraph">{renderInlineMarkdown(line)}</p>);
    }
  }

  return <>{blocks}</>;
}

// ============================================================================
// System type config
// ============================================================================

const SYSTEM_OPTIONS: { value: SystemType; icon: React.FC<{ size?: string | number }>; labelKey: string }[] = [
  { value: 'host', icon: Server, labelKey: 'legacy.ai.systemHost' },
  { value: 'openframe', icon: Database, labelKey: 'legacy.ai.systemOpenFrame' },
  { value: 'all', icon: Layers, labelKey: 'legacy.ai.systemAll' },
];

const SUGGESTIONS: Record<string, string[]> = {
  en: [
    'How to migrate EXEC CICS SEND MAP?',
    'Explain VSAM to TSAM migration steps',
    'What is the OpenFrame equivalent of JES2?',
  ],
  ja: [
    'EXEC CICS SEND MAPの移行方法は？',
    'VSAMからTSAMへの移行手順を説明してください',
    'JES2のOpenFrame相当は何ですか？',
  ],
  ko: [
    'EXEC CICS SEND MAP 마이그레이션 방법은?',
    'VSAM에서 TSAM으로의 마이그레이션 단계 설명',
    'JES2의 OpenFrame 대응은 무엇인가요?',
  ],
};

// ============================================================================
// Notes persistence
// ============================================================================

const NOTES_KEY = 'mod-ai-notes';

function loadNotes(): ChatNote[] {
  try {
    const stored = localStorage.getItem(NOTES_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return [];
}

function saveNotes(notes: ChatNote[]) {
  localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
}

// ============================================================================
// Component Props
// ============================================================================

interface ModernizationAIAssistantProps {
  analysisContext?: AnalysisContextInfo;
}

// ============================================================================
// Main Component
// ============================================================================

export const ModernizationAIAssistant: React.FC<ModernizationAIAssistantProps> = ({
  analysisContext,
}) => {
  const { t, language } = useTranslation();
  const { position, size, onDragStart, onResizeStart } = useFloatingPanel();
  const { messages, isStreaming, sources, sendMessage, cancelStream, clearMessages } =
    useModernizationChat();

  // Panel state
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [activeTab, setActiveTab] = useState<ChatTab>('chat');
  const [systemType, setSystemType] = useState<SystemType>('host');
  const [inputText, setInputText] = useState('');
  const [notes, setNotes] = useState<ChatNote[]>(loadNotes);
  const [noteInput, setNoteInput] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Save notes on change
  useEffect(() => {
    saveNotes(notes);
  }, [notes]);

  // Handle send
  const handleSend = useCallback(() => {
    if (!inputText.trim() || isStreaming) return;
    sendMessage(inputText, systemType, language, analysisContext);
    setInputText('');
  }, [inputText, isStreaming, sendMessage, systemType, language, analysisContext]);

  // Handle key press
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Add note
  const addNote = useCallback(() => {
    if (!noteInput.trim()) return;
    setNotes((prev) => [
      ...prev,
      { id: `note-${Date.now()}`, content: noteInput.trim(), createdAt: Date.now() },
    ]);
    setNoteInput('');
  }, [noteInput]);

  // Delete note
  const deleteNote = useCallback((id: string) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
  }, []);

  // Suggestion click
  const handleSuggestion = useCallback(
    (text: string) => {
      setInputText(text);
      inputRef.current?.focus();
    },
    []
  );

  // ========================================================================
  // Render
  // ========================================================================

  // FAB button
  if (!isOpen) {
    return (
      <button
        className="mod-ai-fab"
        onClick={() => setIsOpen(true)}
        title={t('legacy.ai.title')}
        aria-label={t('legacy.ai.title')}
      >
        <Sparkles size={22} />
      </button>
    );
  }

  // Minimized state
  if (isMinimized) {
    return (
      <div
        className="mod-ai-minimized"
        style={{ left: position.x, top: position.y }}
        onClick={() => setIsMinimized(false)}
      >
        <Sparkles size={16} />
        <span>{t('legacy.ai.title')}</span>
      </div>
    );
  }

  const lang = language || 'ja';
  const suggestionList = SUGGESTIONS[lang] || SUGGESTIONS.ja;

  return (
    <div
      className="mod-ai-panel"
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
      }}
    >
      {/* Header */}
      <div className="mod-ai-header" onMouseDown={onDragStart}>
        <div className="mod-ai-header-left">
          <Sparkles size={16} className="mod-ai-header-icon" />
          <span className="mod-ai-header-title">{t('legacy.ai.title')}</span>
        </div>
        <div className="mod-ai-header-actions">
          <button
            className="mod-ai-header-btn"
            onClick={() => setIsMinimized(true)}
            title="Minimize"
          >
            <Minus size={14} />
          </button>
          <button
            className="mod-ai-header-btn"
            onClick={() => setIsOpen(false)}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* System Selector */}
      <div className="mod-ai-system-selector">
        <span className="mod-ai-system-label">{t('legacy.ai.systemSelector')}:</span>
        <div className="mod-ai-system-buttons">
          {SYSTEM_OPTIONS.map(({ value, icon: Icon, labelKey }) => (
            <button
              key={value}
              className={`mod-ai-system-btn ${systemType === value ? 'active' : ''}`}
              onClick={() => setSystemType(value)}
              title={t(labelKey)}
            >
              <Icon size={14} />
              <span>{t(labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="mod-ai-tabs">
        {(
          [
            { key: 'chat' as ChatTab, icon: MessageSquare, labelKey: 'legacy.ai.tabChat' },
            { key: 'history' as ChatTab, icon: Clock, labelKey: 'legacy.ai.tabHistory' },
            { key: 'sources' as ChatTab, icon: FileText, labelKey: 'legacy.ai.tabSources' },
            { key: 'notes' as ChatTab, icon: StickyNote, labelKey: 'legacy.ai.tabNotes' },
          ] as const
        ).map(({ key, icon: Icon, labelKey }) => (
          <button
            key={key}
            className={`mod-ai-tab ${activeTab === key ? 'active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            <Icon size={14} />
            <span>{t(labelKey)}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="mod-ai-content">
        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="mod-ai-chat-container">
            <div className="mod-ai-messages">
              {messages.length === 0 && (
                <div className="mod-ai-welcome">
                  <Sparkles size={32} className="mod-ai-welcome-icon" />
                  <p className="mod-ai-welcome-text">{t('legacy.ai.welcomeMessage')}</p>
                  <div className="mod-ai-suggestions">
                    {suggestionList.map((s, i) => (
                      <button
                        key={i}
                        className="mod-ai-suggestion"
                        onClick={() => handleSuggestion(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`mod-ai-message mod-ai-message-${msg.role}`}
                >
                  {msg.role === 'assistant' && msg.sourceSystem && (
                    <span className={`mod-ai-source-badge mod-ai-badge-${msg.sourceSystem}`}>
                      {msg.sourceSystem === 'host' ? 'HOST' : 'OpenFrame'}
                    </span>
                  )}
                  <div className="mod-ai-message-content">
                    {msg.role === 'assistant'
                      ? renderMessageContent(msg.content)
                      : msg.content}
                  </div>
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mod-ai-message-sources">
                      {msg.sources.map((src, i) => (
                        <span key={i} className="mod-ai-source-tag">
                          {src.url ? (
                            <a href={src.url} target="_blank" rel="noopener noreferrer">
                              {src.title}
                            </a>
                          ) : (
                            src.title
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {isStreaming && (
                <div className="mod-ai-typing">
                  <div className="mod-ai-typing-dot" />
                  <div className="mod-ai-typing-dot" />
                  <div className="mod-ai-typing-dot" />
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="mod-ai-input-area">
              <textarea
                ref={inputRef}
                className="mod-ai-input"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('legacy.ai.inputPlaceholder')}
                rows={2}
                disabled={isStreaming}
              />
              <div className="mod-ai-input-actions">
                {isStreaming ? (
                  <button className="mod-ai-stop-btn" onClick={cancelStream}>
                    <StopCircle size={18} />
                  </button>
                ) : (
                  <button
                    className="mod-ai-send-btn"
                    onClick={handleSend}
                    disabled={!inputText.trim()}
                  >
                    <Send size={18} />
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <div className="mod-ai-history">
            {messages.length === 0 ? (
              <p className="mod-ai-empty">{t('legacy.ai.noHistory')}</p>
            ) : (
              <div className="mod-ai-history-list">
                <button className="mod-ai-clear-btn" onClick={clearMessages}>
                  {t('legacy.ai.clearHistory')}
                </button>
                {messages
                  .filter((m) => m.role === 'user')
                  .map((m) => (
                    <div key={m.id} className="mod-ai-history-item">
                      <span className="mod-ai-history-text">{m.content.slice(0, 80)}</span>
                      <span className="mod-ai-history-time">
                        {new Date(m.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {/* Sources Tab */}
        {activeTab === 'sources' && (
          <div className="mod-ai-sources-tab">
            {sources.length === 0 ? (
              <p className="mod-ai-empty">{t('legacy.ai.noSources')}</p>
            ) : (
              sources.map((src, i) => (
                <div key={i} className="mod-ai-source-item">
                  <span className="mod-ai-source-title">
                    {src.url ? (
                      <a href={src.url} target="_blank" rel="noopener noreferrer">
                        {src.title}
                      </a>
                    ) : (
                      src.title
                    )}
                  </span>
                  {src.snippet && (
                    <p className="mod-ai-source-snippet">{src.snippet}</p>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Notes Tab */}
        {activeTab === 'notes' && (
          <div className="mod-ai-notes-tab">
            <div className="mod-ai-note-input-row">
              <input
                className="mod-ai-note-input"
                value={noteInput}
                onChange={(e) => setNoteInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addNote()}
                placeholder={t('legacy.ai.notePlaceholder')}
              />
              <button
                className="mod-ai-note-add"
                onClick={addNote}
                disabled={!noteInput.trim()}
              >
                <Plus size={16} />
              </button>
            </div>
            {notes.length === 0 ? (
              <p className="mod-ai-empty">{t('legacy.ai.noNotes')}</p>
            ) : (
              notes.map((note) => (
                <div key={note.id} className="mod-ai-note-item">
                  <p className="mod-ai-note-content">{note.content}</p>
                  <div className="mod-ai-note-footer">
                    <span className="mod-ai-note-time">
                      {new Date(note.createdAt).toLocaleString()}
                    </span>
                    <button
                      className="mod-ai-note-delete"
                      onClick={() => deleteNote(note.id)}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Resize handle */}
      <div className="mod-ai-resize-handle" onMouseDown={onResizeStart} />
    </div>
  );
};

export default ModernizationAIAssistant;
