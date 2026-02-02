/**
 * OpenAgent Page
 *
 * Chat interface for vLLM-based AI agent with multiple modes:
 * - RAG: Summary-based retrieval augmented generation
 * - Direct: Direct LLM response without retrieval
 * - OpenCode: 5-step mandatory workflow with hallucination detection
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
  Shield,
  Eye,
  RotateCcw,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './OpenAgentPage.css';

// Agent mode type
type AgentMode = 'rag' | 'direct' | 'opencode';

// OpenCode step progress interface
interface OpenCodeStep {
  step_number: number;
  step_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  latency_ms?: number;
}

// OpenCode progress state
interface OpenCodeProgress {
  currentStep: number;
  steps: OpenCodeStep[];
  attempt: number;
  maxAttempts: number;
  hallucinationDetected: boolean;
  hallucinationReasons: string[];
  verificationStatus: 'pending' | 'passed' | 'failed';
}

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
  id?: string;
  chunk_id?: string;
  content: string;
  page_start?: number;
  page_end?: number;
  doc_filename?: string;
  image_url?: string;
  // Figure image data (base64)
  figure_reference?: string;
  figure_caption?: string;
  data?: string;  // base64 data URL e.g. "data:image/png;base64,..."
  width?: number;
  height?: number;
  page_number?: number;
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
  const [agentMode, setAgentMode] = useState<AgentMode>('rag'); // Default to RAG mode

  // OpenCode progress state
  const [openCodeProgress, setOpenCodeProgress] = useState<OpenCodeProgress | null>(null);

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

  // Initialize OpenCode progress with default steps
  const initOpenCodeProgress = (): OpenCodeProgress => ({
    currentStep: 0,
    steps: [
      { step_number: 1, step_name: 'keyword_extraction', status: 'pending' },
      { step_number: 2, step_name: 'summary_search', status: 'pending' },
      { step_number: 3, step_name: 'pdf_verification', status: 'pending' },
      { step_number: 4, step_name: 'tool_selection', status: 'pending' },
      { step_number: 5, step_name: 'answer_generation', status: 'pending' },
    ],
    attempt: 1,
    maxAttempts: 4,
    hallucinationDetected: false,
    hallucinationReasons: [],
    verificationStatus: 'pending',
  });

  // Get display name for step
  const getStepDisplayName = (stepName: string): string => {
    const stepNames: Record<string, Record<string, string>> = {
      keyword_extraction: { en: 'Keyword Extraction', ko: '키워드 추출', ja: 'キーワード抽出' },
      summary_search: { en: 'Summary Search', ko: '요약 검색', ja: '要約検索' },
      pdf_verification: { en: 'PDF Verification', ko: 'PDF 검증', ja: 'PDF検証' },
      tool_selection: { en: 'Tool Selection', ko: '도구 선택', ja: 'ツール選択' },
      answer_generation: { en: 'Answer Generation', ko: '답변 생성', ja: '回答生成' },
    };
    return stepNames[stepName]?.[language] || stepName;
  };

  // Handle OpenCode SSE streaming
  const handleOpenCodeStream = async (userMessage: Message) => {
    const progress = initOpenCodeProgress();
    setOpenCodeProgress(progress);

    // baseURL is already '/api/v1', so just append the endpoint path
    const baseUrl = client.defaults.baseURL || '/api/v1';
    const url = `${baseUrl}/agents/stream`;

    console.log('[OpenCode] Starting SSE stream to:', url);
    console.log('[OpenCode] Request body:', { task: userMessage.content, agent_type: 'opencode', language });

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // HttpOnly cookies are sent automatically with credentials: 'include'
        },
        credentials: 'include',
        body: JSON.stringify({
          task: userMessage.content,
          agent_type: 'opencode',
          language: language,
        }),
      });

      console.log('[OpenCode] Response status:', response.status);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedContent = '';
      let sources: Array<{ type: string; file: string }> = [];
      let images: ImageContent[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (!data) continue;

          try {
            const chunk = JSON.parse(data);

            if (chunk.chunk_type === 'status') {
              const metadata = chunk.metadata || {};

              // Update step progress
              if (metadata.step_number) {
                setOpenCodeProgress((prev) => {
                  if (!prev) return prev;
                  const newSteps = [...prev.steps];
                  const stepIdx = metadata.step_number - 1;
                  if (stepIdx >= 0 && stepIdx < newSteps.length) {
                    newSteps[stepIdx] = {
                      ...newSteps[stepIdx],
                      status: metadata.status === 'running' ? 'running' :
                              metadata.status === 'completed' ? 'completed' :
                              metadata.status === 'failed' ? 'failed' : 'pending',
                      latency_ms: metadata.latency_ms,
                    };
                  }
                  return {
                    ...prev,
                    currentStep: metadata.step_number,
                    steps: newSteps,
                    attempt: metadata.attempt || prev.attempt,
                    maxAttempts: metadata.max_attempts || prev.maxAttempts,
                  };
                });
              }

              // Handle hallucination detection
              if (metadata.hallucination_detected) {
                setOpenCodeProgress((prev) => {
                  if (!prev) return prev;
                  // Reset steps for retry
                  const resetSteps = prev.steps.map((s) => ({ ...s, status: 'pending' as const }));
                  return {
                    ...prev,
                    steps: resetSteps,
                    currentStep: 0,
                    hallucinationDetected: true,
                    hallucinationReasons: metadata.reasons || [],
                    attempt: (metadata.attempt || 0) + 1,
                    verificationStatus: 'pending',
                  };
                });
              }

              // Handle verification status
              if (metadata.verification_status) {
                setOpenCodeProgress((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    verificationStatus: metadata.verification_status.toLowerCase() as 'passed' | 'failed',
                    hallucinationDetected: metadata.verification_status === 'FAILED',
                  };
                });
              }
            } else if (chunk.chunk_type === 'text') {
              accumulatedContent += chunk.content || '';
            } else if (chunk.chunk_type === 'sources') {
              sources = (chunk.sources || []).map((s: any) => ({
                type: s.type || 'pdf',
                file: s.doc_filename || s.file || s.source || 'Unknown',
              }));
            } else if (chunk.chunk_type === 'images') {
              // Handle figure images from backend
              images = (chunk.images || []).map((img: any) => ({
                id: img.id,
                content: img.figure_caption || img.description || '',
                figure_reference: img.figure_reference,
                figure_caption: img.figure_caption,
                data: img.data,  // base64 data URL
                width: img.width,
                height: img.height,
                page_number: img.page_number,
                doc_filename: img.document_id,
              }));
            } else if (chunk.chunk_type === 'error') {
              setError(chunk.content || 'Unknown error');
            } else if (chunk.chunk_type === 'done') {
              // Streaming complete
            }
          } catch (parseError) {
            console.error('Failed to parse SSE chunk:', parseError);
          }
        }
      }

      // Create assistant message with accumulated content
      if (accumulatedContent) {
        const assistantMessage: Message = {
          id: generateId(),
          role: 'assistant',
          content: accumulatedContent,
          timestamp: new Date(),
          sources: sources.length > 0 ? sources : undefined,
          images: images.length > 0 ? images : undefined,
          confidence: openCodeProgress?.verificationStatus === 'passed' ? 'HIGH' : 'MEDIUM',
        };
        setMessages((prev) => [...prev, assistantMessage]);
      }
    } catch (err: any) {
      console.error('OpenCode streaming error:', err);
      setError(err.message || 'Failed to get response from OpenCode agent');
    } finally {
      setIsLoading(false);
      // Keep progress visible for a moment before clearing
      setTimeout(() => setOpenCodeProgress(null), 3000);
    }
  };

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
      // Handle OpenCode mode with SSE streaming
      if (agentMode === 'opencode' && !selectedFile) {
        await handleOpenCodeStream(userMessage);
        return;
      }

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
        const endpoint = agentMode === 'rag' ? '/openagent/rag/chat' : '/openagent/chat';

        response = await client.post(endpoint, {
          message: userMessage.content,
          history: history.length > 0 ? history : undefined,
          use_summaries: agentMode === 'rag',
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
  }, [input, selectedFile, isLoading, messages, agentMode, language]);

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
          {/* Agent Mode Selector */}
          <div className="openagent-mode-selector">
            <button
              className={`openagent-btn-mode ${agentMode === 'rag' ? 'active' : ''}`}
              onClick={() => setAgentMode('rag')}
              title="RAG Mode: Summary-based retrieval augmented generation"
            >
              <BookOpen size={16} />
              <span>RAG</span>
            </button>
            <button
              className={`openagent-btn-mode ${agentMode === 'direct' ? 'active' : ''}`}
              onClick={() => setAgentMode('direct')}
              title="Direct Mode: Direct LLM response without retrieval"
            >
              <Zap size={16} />
              <span>Direct</span>
            </button>
            <button
              className={`openagent-btn-mode opencode ${agentMode === 'opencode' ? 'active' : ''}`}
              onClick={() => setAgentMode('opencode')}
              title="OpenCode Mode: 5-step workflow with hallucination detection"
            >
              <Shield size={16} />
              <span>OpenCode</span>
            </button>
          </div>
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

                {/* Image Gallery */}
                {message.images && message.images.length > 0 && (
                  <div className="openagent-images">
                    <div className="openagent-images-header">
                      <span>関連図表 ({message.images.length})</span>
                    </div>
                    <div className="openagent-images-grid">
                      {message.images.map((img, idx) => (
                        <div key={img.id || idx} className="openagent-image-item">
                          {img.data ? (
                            <img
                              src={img.data}
                              alt={img.figure_caption || img.figure_reference || `Image ${idx + 1}`}
                              loading="lazy"
                              onClick={() => window.open(img.data, '_blank')}
                              style={{ cursor: 'pointer' }}
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
                            />
                          ) : (
                            <div className="openagent-image-placeholder">
                              {img.figure_reference || 'Image'}
                            </div>
                          )}
                          {(img.figure_caption || img.figure_reference) && (
                            <div className="openagent-image-caption">
                              {img.figure_caption || img.figure_reference}
                              {img.page_number && <span className="page-num"> (p.{img.page_number})</span>}
                            </div>
                          )}
                        </div>
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

        {/* OpenCode Progress Panel */}
        {openCodeProgress && (
          <div className="opencode-progress-panel">
            <div className="opencode-progress-header">
              <Shield size={18} />
              <span>OpenCode Agent</span>
              {openCodeProgress.attempt > 1 && (
                <span className="opencode-retry-badge">
                  <RotateCcw size={14} />
                  Attempt {openCodeProgress.attempt}/{openCodeProgress.maxAttempts}
                </span>
              )}
            </div>

            <div className="opencode-steps">
              {openCodeProgress.steps.map((step) => (
                <div
                  key={step.step_number}
                  className={`opencode-step ${step.status}`}
                >
                  <div className="opencode-step-number">
                    {step.status === 'completed' ? (
                      <CheckCircle2 size={18} />
                    ) : step.status === 'running' ? (
                      <Loader2 size={18} className="spin" />
                    ) : step.status === 'failed' ? (
                      <AlertCircle size={18} />
                    ) : (
                      <span>{step.step_number}</span>
                    )}
                  </div>
                  <div className="opencode-step-content">
                    <span className="opencode-step-name">
                      {getStepDisplayName(step.step_name)}
                    </span>
                    {step.latency_ms && (
                      <span className="opencode-step-time">
                        {(step.latency_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Hallucination Detection Status */}
            {openCodeProgress.hallucinationDetected && (
              <div className="opencode-hallucination-alert">
                <Eye size={16} />
                <div className="opencode-hallucination-content">
                  <span className="opencode-hallucination-title">
                    Hallucination Detected - Retrying...
                  </span>
                  {openCodeProgress.hallucinationReasons.length > 0 && (
                    <ul className="opencode-hallucination-reasons">
                      {openCodeProgress.hallucinationReasons.map((reason, idx) => (
                        <li key={idx}>{reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {/* Verification Status */}
            {openCodeProgress.verificationStatus !== 'pending' && (
              <div className={`opencode-verification ${openCodeProgress.verificationStatus}`}>
                {openCodeProgress.verificationStatus === 'passed' ? (
                  <>
                    <CheckCircle2 size={16} />
                    <span>Verification Passed</span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={16} />
                    <span>Verification Failed</span>
                  </>
                )}
              </div>
            )}
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
