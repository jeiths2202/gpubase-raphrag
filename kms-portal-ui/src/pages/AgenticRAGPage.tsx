/**
 * Agentic RAG Page
 *
 * 제품별 Agent 기반 RAG 채팅 인터페이스
 * - 다단계 질문 라우터 (확정/되묻기/매칭없음)
 * - 정형 질문: 템플릿 기반 응답 (환각 0%)
 * - 비정형 질문: LLM 생성 + 사후 검증 (🟢🟡🔴)
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import {
  Send,
  Loader2,
  Trash2,
  Workflow,
  ChevronDown,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Search,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import client from '../api/client';
import type {
  AgenticRAGRequest,
  ClarificationCandidate,
  VerifiedSentence,
  SSEEvent,
} from '../api/agentic-rag.api';
import './OpenAgentPage.css';

// Product definitions
const PRODUCTS = [
  { id: 'auto', labelKey: 'Auto' },
  { id: 'openframe_mvs', labelKey: 'OpenFrame MVS' },
  { id: 'openframe_base', labelKey: 'OpenFrame Base' },
  { id: 'msp_openframe', labelKey: 'MSP' },
  { id: 'vos3_openframe', labelKey: 'VOS3' },
  { id: 'tibero7', labelKey: 'Tibero 7' },
  { id: 'ofasm', labelKey: 'OFASM' },
  { id: 'ofcobol', labelKey: 'OFCOBOL' },
  { id: 'xsp_openframe', labelKey: 'XSP' },
  { id: 'tmax', labelKey: 'Tmax' },
] as const;

// Verification badge config
const VERIFICATION_BADGE: Record<string, { icon: React.ReactNode; label: string; className: string }> = {
  verified: {
    icon: <CheckCircle2 size={14} />,
    label: '確認済み',
    className: 'badge-verified',
  },
  inferred: {
    icon: <AlertTriangle size={14} />,
    label: '推定',
    className: 'badge-inferred',
  },
  unverified: {
    icon: <XCircle size={14} />,
    label: '未確認',
    className: 'badge-unverified',
  },
};

// Message types
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'clarification';
  content: string;
  product?: string;
  queryType?: string;
  verification?: VerifiedSentence[];
  sources?: unknown;
  candidates?: ClarificationCandidate[];
  clarificationMessage?: string;
  timestamp: Date;
}

export const AgenticRAGPage: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuthStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState('auto');
  const [showProductSelector, setShowProductSelector] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Send message via SSE stream
  const sendMessage = useCallback(async (text: string, overrideProduct?: string) => {
    if (!text.trim() || isStreaming || !isAuthenticated) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);

    const request: AgenticRAGRequest = {
      message: text,
      product: overrideProduct || selectedProduct,
      selected_product: overrideProduct || undefined,
      language: 'ja',
      history: messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-10)
        .map(m => ({ role: m.role, content: m.content })),
    };

    const assistantId = `assistant-${Date.now()}`;
    let currentContent = '';
    let currentProduct = '';
    let currentQueryType = '';

    try {
      abortControllerRef.current = new AbortController();

      const authHeader = client.defaults.headers.common?.['Authorization'];
      const response = await fetch(`${client.defaults.baseURL}/agentic-rag/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authHeader ? { 'Authorization': String(authHeader) } : {}),
        },
        body: JSON.stringify(request),
        credentials: 'include',
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() || '';

        for (const chunk of chunks) {
          const trimmed = chunk.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          let event: SSEEvent;
          try {
            event = JSON.parse(trimmed.slice(6));
          } catch {
            continue;
          }

          switch (event.type) {
            case 'classification':
              currentProduct = (event as Record<string, unknown>).product as string || '';
              break;

            case 'clarification_needed': {
              // 되묻기 카드 표시
              const clarification: ChatMessage = {
                id: `clarify-${Date.now()}`,
                role: 'clarification',
                content: '',
                candidates: (event as Record<string, unknown>).candidates as ClarificationCandidate[],
                clarificationMessage: (event as Record<string, unknown>).message as string,
                timestamp: new Date(),
              };
              setMessages(prev => [...prev, clarification]);
              setIsStreaming(false);
              return;
            }

            case 'search_progress':
              // 검색 진행 상태 (UI 표시 가능)
              break;

            case 'template_response':
              currentContent = (event as Record<string, unknown>).content as string || '';
              currentQueryType = (event as Record<string, unknown>).query_type as string || '';
              setMessages(prev => [
                ...prev.filter(m => m.id !== assistantId),
                {
                  id: assistantId,
                  role: 'assistant',
                  content: currentContent,
                  product: currentProduct,
                  queryType: currentQueryType,
                  timestamp: new Date(),
                },
              ]);
              break;

            case 'llm_token':
              currentContent += (event as Record<string, unknown>).token as string || '';
              setMessages(prev => {
                const existing = prev.find(m => m.id === assistantId);
                if (existing) {
                  return prev.map(m =>
                    m.id === assistantId ? { ...m, content: currentContent } : m
                  );
                }
                return [
                  ...prev,
                  {
                    id: assistantId,
                    role: 'assistant',
                    content: currentContent,
                    product: currentProduct,
                    timestamp: new Date(),
                  },
                ];
              });
              break;

            case 'verification':
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, verification: (event as Record<string, unknown>).sentences as VerifiedSentence[] }
                    : m
                )
              );
              break;

            case 'sources':
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, sources: event } : m
                )
              );
              break;

            case 'done':
              currentQueryType = (event as Record<string, unknown>).query_type as string || currentQueryType;
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, queryType: currentQueryType } : m
                )
              );
              break;

            case 'error':
              currentContent = `エラーが発生しました: ${(event as Record<string, unknown>).message || 'Unknown error'}`;
              setMessages(prev => [
                ...prev.filter(m => m.id !== assistantId),
                {
                  id: assistantId,
                  role: 'assistant',
                  content: currentContent,
                  timestamp: new Date(),
                },
              ]);
              break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessages(prev => [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            content: `接続エラー: ${(err as Error).message}`,
            timestamp: new Date(),
          },
        ]);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [isStreaming, isAuthenticated, selectedProduct, messages]);

  // Handle clarification product selection
  const handleClarificationSelect = useCallback((product: string) => {
    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user');
    if (lastUserMessage) {
      sendMessage(lastUserMessage.content, product);
    }
  }, [messages, sendMessage]);

  // Handle submit
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  // Handle key press
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  // Clear messages
  const handleClear = () => {
    setMessages([]);
  };

  // Render verification badge
  const renderVerificationBadge = (level: string) => {
    const badge = VERIFICATION_BADGE[level];
    if (!badge) return null;
    return (
      <span className={`verification-badge ${badge.className}`} title={badge.label}>
        {badge.icon}
      </span>
    );
  };

  // Render message
  const renderMessage = (msg: ChatMessage) => {
    if (msg.role === 'clarification') {
      return (
        <div key={msg.id} className="openagent-message assistant">
          <div className="openagent-message-content assistant">
            <div className="clarification-card">
              <div className="clarification-header">
                <Info size={18} />
                <span>{msg.clarificationMessage || 'どの製品に関する質問ですか？'}</span>
              </div>
              <div className="clarification-options">
                {msg.candidates?.map(candidate => (
                  <button
                    key={candidate.product}
                    className="clarification-option"
                    onClick={() => handleClarificationSelect(candidate.product)}
                  >
                    <span className="clarification-product">
                      {PRODUCTS.find(p => p.id === candidate.product)?.labelKey || candidate.product}
                    </span>
                    <span className="clarification-confidence">
                      {Math.round(candidate.confidence * 100)}%
                    </span>
                    <span className="clarification-reason">{candidate.reason}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div key={msg.id} className={`openagent-message ${msg.role}`}>
        <div className={`openagent-message-content ${msg.role}`}>
          {msg.role === 'assistant' ? (
            <>
              {msg.product && (
                <div className="message-product-tag">
                  <Workflow size={14} />
                  <span>{PRODUCTS.find(p => p.id === msg.product)?.labelKey || msg.product}</span>
                  {msg.queryType && (
                    <span className="message-query-type">{msg.queryType}</span>
                  )}
                </div>
              )}
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
              {msg.verification && msg.verification.length > 0 && (
                <div className="verification-summary">
                  <div className="verification-title">
                    <Search size={14} />
                    <span>信頼度検証</span>
                  </div>
                  <div className="verification-badges">
                    {Object.entries(
                      msg.verification.reduce((acc, v) => {
                        acc[v.level] = (acc[v.level] || 0) + 1;
                        return acc;
                      }, {} as Record<string, number>)
                    ).map(([level, count]) => (
                      <span key={level} className={`verification-count ${level}`}>
                        {renderVerificationBadge(level)} {count}件
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {msg.sources && (
                <div className="message-sources">
                  <FileText size={14} />
                  <span>出典情報あり</span>
                </div>
              )}
            </>
          ) : (
            <p>{msg.content}</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="openagent-page">
      {/* Header */}
      <div className="openagent-header">
        <div className="openagent-header-left">
          <Workflow size={24} className="openagent-icon" />
          <div>
            <h1 className="openagent-title">
              {t('common.nav.agenticRag') || 'Agentic RAG'}
            </h1>
            <p className="openagent-subtitle">
              製品別エージェント基盤のRAGシステム
            </p>
          </div>
        </div>
        <div className="openagent-header-right">
          {/* Product Selector */}
          <div className="product-selector-wrapper">
            <button
              className="product-selector-button"
              onClick={() => setShowProductSelector(!showProductSelector)}
            >
              <span>{PRODUCTS.find(p => p.id === selectedProduct)?.labelKey || 'Auto'}</span>
              <ChevronDown size={16} />
            </button>
            {showProductSelector && (
              <div className="product-selector-dropdown">
                {PRODUCTS.map(product => (
                  <button
                    key={product.id}
                    className={`product-selector-item ${selectedProduct === product.id ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedProduct(product.id);
                      setShowProductSelector(false);
                    }}
                  >
                    {product.labelKey}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            className="openagent-btn-icon"
            onClick={handleClear}
            title="Clear"
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="openagent-messages">
        {messages.length === 0 ? (
          <div className="openagent-empty">
            <Workflow size={48} style={{ opacity: 0.3 }} />
            <p>製品に関する技術的な質問を入力してください</p>
            <p style={{ fontSize: '0.85rem', opacity: 0.6 }}>
              コマンド使用法、エラーコード、設定方法など
            </p>
          </div>
        ) : (
          messages.map(renderMessage)
        )}
        {isStreaming && (
          <div className="openagent-message assistant">
            <div className="openagent-message-content assistant">
              <Loader2 size={16} className="spinning" />
              <span style={{ marginLeft: 8 }}>検索中...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form className="openagent-input-area" onSubmit={handleSubmit}>
        <div className="openagent-input-row">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="質問を入力してください..."
            rows={1}
            disabled={isStreaming}
          />
          <button
            type="submit"
            className="openagent-btn-send"
            disabled={!input.trim() || isStreaming}
          >
            {isStreaming ? <Loader2 size={20} className="spinning" /> : <Send size={20} />}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AgenticRAGPage;
