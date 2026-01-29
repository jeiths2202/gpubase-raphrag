/**
 * OpenAgent Page
 *
 * Chat interface for vLLM-based AI agent.
 * Uses Qwen2.5-7B-Instruct model via vLLM server.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import client from '../api/client';
import {
  Send,
  Paperclip,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Settings,
  RefreshCw,
  Sparkles,
  X,
  BookOpen,
  Zap,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './OpenAgentPage.css';

// Helper function to extract filename from path
const getFilename = (path: string): string => {
  if (!path) return '';
  // Handle both forward and backward slashes
  const parts = path.split(/[/\\]/);
  return parts[parts.length - 1] || path;
};

// Helper function to check if content is markdown table
const isMarkdownTable = (content: string): boolean => {
  return content.includes('|') && content.includes('---');
};

// Helper function to convert plain text table to markdown table
const formatTableContent = (content: string): string => {
  if (!content) return '';

  // If already markdown table, return as-is
  if (isMarkdownTable(content)) {
    return content;
  }

  // Try to detect key-value pairs pattern (Japanese table format)
  // Pattern: "キー1 値1 キー2 値2 ..."
  const lines = content.split(/\n/).filter(line => line.trim());

  if (lines.length === 1) {
    // Single line - try to parse as key-value pairs
    // Common patterns: "表記 意味" style tables
    // Split by common delimiters and try to pair them
    const tokens = content.split(/\s{2,}|\t/).filter(t => t.trim());

    if (tokens.length >= 2) {
      // Create markdown table
      let markdown = '| 項目 | 内容 |\n|---|---|\n';
      for (let i = 0; i < tokens.length; i += 2) {
        const key = tokens[i]?.trim() || '';
        const value = tokens[i + 1]?.trim() || '';
        if (key) {
          markdown += `| ${key} | ${value} |\n`;
        }
      }
      return markdown;
    }
  }

  // Fallback: return as code block for better formatting
  return '```\n' + content + '\n```';
};

interface TableContent {
  chunk_id?: string;
  content: string;
  page_start?: number;
  page_end?: number;
  doc_filename?: string;
}

interface ImageContent {
  chunk_id?: string;
  content: string;
  page_start?: number;
  page_end?: number;
  doc_filename?: string;
  image_url?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  fileInfo?: {
    name: string;
    size: number;
  };
  sources?: Array<{
    type: string;
    file: string;
  }>;
  confidence?: string;
  tables?: TableContent[];
  images?: ImageContent[];
}

interface HealthStatus {
  available: boolean;
  message: string;
  model?: string;
  base_url?: string;
}

export const OpenAgentPage: React.FC = () => {
  const { t, language } = useTranslation();

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [ragMode, setRagMode] = useState(true); // RAG mode enabled by default

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check health on mount
  useEffect(() => {
    checkHealth();
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const checkHealth = async () => {
    try {
      const response = await client.get<HealthStatus>('/openagent/health');
      setHealthStatus(response.data);
    } catch (err) {
      setHealthStatus({
        available: false,
        message: 'Failed to connect to OpenAgent service',
      });
    }
  };

  const generateId = () => `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const handleSend = useCallback(async () => {
    if ((!input.trim() && !selectedFile) || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      fileInfo: selectedFile ? { name: selectedFile.name, size: selectedFile.size } : undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      let response;

      if (selectedFile) {
        // Chat with file
        const formData = new FormData();
        formData.append('message', userMessage.content || `Analyze this file: ${selectedFile.name}`);
        formData.append('file', selectedFile);

        response = await client.post('/openagent/chat-with-file', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } else {
        // Build history for context
        const history = messages.slice(-10).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        // Use RAG endpoint if RAG mode is enabled
        const endpoint = ragMode ? '/openagent/rag/chat' : '/openagent/chat';

        response = await client.post(endpoint, {
          message: userMessage.content,
          history: history.length > 0 ? history : undefined,
          use_summaries: ragMode,
          language: language,  // Pass UI language for response language
        });
      }

      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: response.data.response,
        timestamp: new Date(),
        sources: response.data.sources,
        confidence: response.data.confidence,
        tables: response.data.tables,
        images: response.data.images,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setSelectedFile(null);
    } catch (err: any) {
      console.error('OpenAgent error:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to get response');
    } finally {
      setIsLoading(false);
    }
  }, [input, selectedFile, isLoading, messages, ragMode, language]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      // Validate file size (max 1MB for text files)
      if (file.size > 1024 * 1024) {
        setError('File too large. Maximum size is 1MB.');
        return;
      }
      setSelectedFile(file);
      setError(null);
    }
  };

  const clearMessages = () => {
    setMessages([]);
    setError(null);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="openagent-page">
      {/* Header */}
      <header className="openagent-header">
        <div className="openagent-header-left">
          <Sparkles size={24} className="openagent-icon" />
          <div>
            <h1>{t('common.openAgent.title')}</h1>
          </div>
        </div>
        <div className="openagent-header-right">
          {/* RAG Mode Toggle */}
          <button
            className={`openagent-btn-rag ${ragMode ? 'active' : ''}`}
            onClick={() => setRagMode(!ragMode)}
            title={ragMode ? 'RAG Mode: ON (Summary-based retrieval)' : 'RAG Mode: OFF (Direct LLM)'}
          >
            {ragMode ? <BookOpen size={18} /> : <Zap size={18} />}
            <span className="openagent-btn-label">
              {ragMode ? 'RAG' : 'Direct'}
            </span>
          </button>
          {healthStatus && (
            <span className={`openagent-status ${healthStatus.available ? 'available' : 'unavailable'}`}>
              {healthStatus.available ? (
                <CheckCircle2 size={16} />
              ) : (
                <AlertCircle size={16} />
              )}
              {healthStatus.available ? t('common.openAgent.connected') : t('common.openAgent.disconnected')}
            </span>
          )}
          <button
            className="openagent-btn-icon"
            onClick={checkHealth}
            title={t('common.refresh')}
          >
            <RefreshCw size={18} />
          </button>
          <button
            className="openagent-btn-icon"
            onClick={() => setShowSettings(!showSettings)}
            title={t('common.nav.settings')}
          >
            <Settings size={18} />
          </button>
          <button
            className="openagent-btn-icon"
            onClick={clearMessages}
            title={t('common.openAgent.clearChat')}
          >
            <Trash2 size={18} />
          </button>
        </div>
      </header>

      {/* Settings Panel */}
      {showSettings && healthStatus && (
        <div className="openagent-settings">
          <h3>{t('common.openAgent.configuration')}</h3>
          <div className="openagent-settings-grid">
            <div className="openagent-setting">
              <label>Model</label>
              <span>{healthStatus.model || 'N/A'}</span>
            </div>
            <div className="openagent-setting">
              <label>Server</label>
              <span>{healthStatus.base_url || 'N/A'}</span>
            </div>
            <div className="openagent-setting">
              <label>Status</label>
              <span>{healthStatus.available ? 'Online' : 'Offline'}</span>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="openagent-messages">
        {messages.length === 0 ? (
          <div className="openagent-empty">
            <Sparkles size={48} className="openagent-empty-icon" />
            <h2>{t('common.openAgent.welcomeTitle')}</h2>
            <p>{t('common.openAgent.welcomeMessage')}</p>
            <div className="openagent-suggestions">
              <button onClick={() => setInput(t('common.openAgent.suggestion1'))}>
                {t('common.openAgent.suggestion1')}
              </button>
              <button onClick={() => setInput(t('common.openAgent.suggestion2'))}>
                {t('common.openAgent.suggestion2')}
              </button>
              <button onClick={() => setInput(t('common.openAgent.suggestion3'))}>
                {t('common.openAgent.suggestion3')}
              </button>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`openagent-message ${message.role}`}
            >
              <div className="openagent-message-content">
                {message.fileInfo && (
                  <div className="openagent-file-badge">
                    <Paperclip size={14} />
                    <span>{message.fileInfo.name}</span>
                    <span className="openagent-file-size">
                      ({formatFileSize(message.fileInfo.size)})
                    </span>
                  </div>
                )}
                {message.role === 'assistant' ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                ) : (
                  <p>{message.content}</p>
                )}
                {/* Show tables from RAG responses */}
                {message.tables && message.tables.length > 0 && (
                  <div className="openagent-tables">
                    <div className="openagent-tables-header">
                      <BookOpen size={14} />
                      <span>관련 테이블 ({message.tables.length})</span>
                    </div>
                    {message.tables.map((table, idx) => (
                      <div key={idx} className="openagent-table-item">
                        {table.doc_filename && (
                          <div className="openagent-table-source">
                            📄 {getFilename(table.doc_filename)}
                            {table.page_start && ` (p.${table.page_start}${table.page_end && table.page_end !== table.page_start ? `-${table.page_end}` : ''})`}
                          </div>
                        )}
                        <div className="openagent-table-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {formatTableContent(table.content)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {/* Show images from RAG responses */}
                {message.images && message.images.length > 0 && (
                  <div className="openagent-images">
                    <div className="openagent-images-header">
                      <BookOpen size={14} />
                      <span>관련 이미지 ({message.images.length})</span>
                    </div>
                    {message.images.map((image, idx) => (
                      <div key={idx} className="openagent-image-item">
                        {image.doc_filename && (
                          <div className="openagent-image-source">
                            📄 {getFilename(image.doc_filename)}
                            {image.page_start && ` (p.${image.page_start}${image.page_end && image.page_end !== image.page_start ? `-${image.page_end}` : ''})`}
                          </div>
                        )}
                        {image.image_url && (
                          <img
                            src={image.image_url}
                            alt={image.content || 'Related image'}
                            className="openagent-image"
                          />
                        )}
                        <div className="openagent-image-caption">
                          {image.content}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {/* Show sources for RAG responses */}
                {message.sources && message.sources.length > 0 && (
                  <div className="openagent-sources">
                    <div className="openagent-sources-header">
                      <BookOpen size={14} />
                      <span>참조 소스 ({message.confidence})</span>
                    </div>
                    <div className="openagent-sources-list">
                      {message.sources.map((source, idx) => (
                        <span key={idx} className="openagent-source-tag">
                          {source.type}: {source.file}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <span className="openagent-message-time">
                {message.timestamp.toLocaleTimeString()}
              </span>
            </div>
          ))
        )}

        {isLoading && (
          <div className="openagent-message assistant loading">
            <div className="openagent-message-content">
              <Loader2 size={20} className="spin" />
              <span>{t('common.openAgent.thinking')}</span>
            </div>
          </div>
        )}

        {error && (
          <div className="openagent-error">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>
              <X size={16} />
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="openagent-input-area">
        {selectedFile && (
          <div className="openagent-selected-file">
            <Paperclip size={16} />
            <span>{selectedFile.name}</span>
            <span className="openagent-file-size">
              ({formatFileSize(selectedFile.size)})
            </span>
            <button onClick={() => setSelectedFile(null)}>
              <X size={16} />
            </button>
          </div>
        )}
        <div className="openagent-input-row">
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.py,.js,.ts,.json,.yaml,.yml,.xml,.html,.css,.java,.go,.rs,.c,.cpp,.h"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          <button
            className="openagent-btn-attach"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            title={t('common.openAgent.attachFile')}
          >
            <Paperclip size={20} />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('common.openAgent.placeholder')}
            disabled={isLoading}
            rows={1}
          />
          <button
            className="openagent-btn-send"
            onClick={handleSend}
            disabled={(!input.trim() && !selectedFile) || isLoading}
          >
            {isLoading ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OpenAgentPage;
