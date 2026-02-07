/**
 * Agentic RAG Page
 *
 * 제품별 Agent 기반 RAG 채팅 인터페이스
 * - 동적 제품 발견 (uploads/manuals/)
 * - 트리 드롭다운 (패밀리 > 버전)
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
  ChevronRight,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Search,
  FolderOpen,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import client from '../api/client';
import type {
  AgenticRAGRequest,
  ClarificationCandidate,
  VerifiedSentence,
  SSEEvent,
  ProductGroup,
} from '../api/agentic-rag.api';
import './OpenAgentPage.css';

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
  const [selectedProductLabel, setSelectedProductLabel] = useState('Auto');
  const [showProductSelector, setShowProductSelector] = useState(false);
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load product tree from API
  useEffect(() => {
    if (!isAuthenticated) return;
    client.get('/agentic-rag/products')
      .then(res => {
        const data = res.data;
        if (data.success && data.products) {
          setProductGroups(data.products);
        }
      })
      .catch(() => {
        // Fallback: empty groups
      });
  }, [isAuthenticated]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowProductSelector(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Get display label for a product_id
  const getProductLabel = useCallback((productId: string): string => {
    if (productId === 'auto') return 'Auto';
    for (const group of productGroups) {
      for (const v of group.versions) {
        if (v.product_id === productId) {
          return group.versions.length > 1
            ? `${group.name} ${v.version}`
            : group.name;
        }
      }
    }
    return productId;
  }, [productGroups]);

  // Toggle family expansion
  const toggleFamily = (family: string) => {
    setExpandedFamilies(prev => {
      const next = new Set(prev);
      if (next.has(family)) {
        next.delete(family);
      } else {
        next.add(family);
      }
      return next;
    });
  };

  // Select product
  const selectProduct = (productId: string, label: string) => {
    setSelectedProduct(productId);
    setSelectedProductLabel(label);
    setShowProductSelector(false);
  };

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
                      {getProductLabel(candidate.product)}
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
                  <span>{getProductLabel(msg.product)}</span>
                  {msg.queryType && (
                    <span className="message-query-type">{msg.queryType}</span>
                  )}
                </div>
              )}
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children, ...props }: React.HTMLAttributes<HTMLTableElement>) => (
                    <div className="markdown-table-wrapper">
                      <table {...props}>{children}</table>
                    </div>
                  ),
                  img: ({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) => (
                    <div className="markdown-image-wrapper">
                      <img
                        src={src}
                        alt={alt || ''}
                        loading="lazy"
                        onClick={() => src && window.open(src, '_blank')}
                        {...props}
                      />
                      {alt && <span className="markdown-image-caption">{alt}</span>}
                    </div>
                  ),
                }}
              >
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

  // Render product tree dropdown
  const renderProductTree = () => (
    <div className="product-tree-dropdown">
      {/* Auto option */}
      <button
        className={`product-tree-item ${selectedProduct === 'auto' ? 'active' : ''}`}
        onClick={() => selectProduct('auto', 'Auto')}
      >
        <Search size={14} />
        <span>{t('common.agenticRag.autoProduct') || 'Auto'}</span>
      </button>
      <div className="product-tree-separator" />
      {/* Product families */}
      {productGroups.map(group => (
        <div key={group.name} className="product-tree-family">
          {group.versions.length === 1 ? (
            // Single version: click selects directly
            <button
              className={`product-tree-item ${selectedProduct === group.versions[0].product_id ? 'active' : ''}`}
              onClick={() => selectProduct(
                group.versions[0].product_id,
                group.name,
              )}
            >
              <FolderOpen size={14} />
              <span>{group.name}</span>
              <span className="product-tree-meta">
                {group.versions[0].pdf_count} PDFs
              </span>
            </button>
          ) : (
            // Multiple versions: expandable
            <>
              <button
                className="product-tree-item product-tree-group"
                onClick={() => toggleFamily(group.name)}
              >
                {expandedFamilies.has(group.name)
                  ? <ChevronDown size={14} />
                  : <ChevronRight size={14} />
                }
                <span>{group.name}</span>
                <span className="product-tree-meta">
                  {group.versions.length} {t('common.agenticRag.version') || 'ver'}
                </span>
              </button>
              {expandedFamilies.has(group.name) && (
                <div className="product-tree-versions">
                  {group.versions.map(v => (
                    <button
                      key={v.product_id}
                      className={`product-tree-item product-tree-version ${selectedProduct === v.product_id ? 'active' : ''}`}
                      onClick={() => selectProduct(
                        v.product_id,
                        `${group.name} ${v.version}`,
                      )}
                    >
                      <span className="product-tree-version-label">
                        {v.version}
                        {v.doc_version && <span className="product-tree-doc-ver">(v{v.doc_version})</span>}
                      </span>
                      <span className="product-tree-meta">
                        {v.language} · {v.pdf_count} PDFs
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );

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
              {t('common.agenticRag.subtitle') || '製品別エージェント基盤のRAGシステム'}
            </p>
          </div>
        </div>
        <div className="openagent-header-right">
          {/* Product Selector */}
          <div className="product-selector-wrapper" ref={dropdownRef}>
            <button
              className="product-selector-button"
              onClick={() => setShowProductSelector(!showProductSelector)}
            >
              <span>{selectedProductLabel}</span>
              <ChevronDown size={16} />
            </button>
            {showProductSelector && renderProductTree()}
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
            <p>{t('common.agenticRag.emptyState') || '製品に関する技術的な質問を入力してください'}</p>
            <p style={{ fontSize: '0.85rem', opacity: 0.6 }}>
              {t('common.agenticRag.emptyHint') || 'コマンド使用法、エラーコード、設定方法など'}
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
            placeholder={t('common.agenticRag.inputPlaceholder') || '質問を入力してください...'}
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
