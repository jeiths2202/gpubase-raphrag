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
  MessageCircle,
  Terminal,
  Settings,
  Zap,
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

// Source result from SSE
interface SourceResult {
  doc_name: string;
  source_page?: string;
  score: number;
  domain?: string;
  product?: string;
  url?: string;  // Web doc source URL (docs.tmaxsoft.com)
}

interface SourcesEvent {
  type: string;
  results: SourceResult[];
  total: number;
}

// Message types
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'clarification' | 'low_relevance';
  content: string;
  product?: string;
  products?: string[];
  queryType?: string;
  verification?: VerifiedSentence[];
  sources?: SourcesEvent;
  candidates?: ClarificationCandidate[];
  clarificationMessage?: string;
  lowRelevanceScore?: number;
  searchedProducts?: string[];
  timestamp: Date;
}

export const AgenticRAGPage: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuthStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);  // empty = auto
  const [isAutoMode, setIsAutoMode] = useState(true);
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

  // Selector display label
  const selectorLabel = isAutoMode
    ? (t('common.agenticRag.autoProduct') || 'Auto (All Products)')
    : selectedProducts.length === 1
      ? getProductLabel(selectedProducts[0])
      : `${selectedProducts.length} ${t('common.agenticRag.productsSelected') || 'products'}`;

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

  // Switch to auto mode
  const switchToAuto = () => {
    setIsAutoMode(true);
    setSelectedProducts([]);
  };

  // Toggle individual product checkbox
  const toggleProduct = (productId: string) => {
    setSelectedProducts(prev => {
      const next = prev.includes(productId)
        ? prev.filter(p => p !== productId)
        : [...prev, productId];
      if (next.length === 0) {
        setIsAutoMode(true);
      } else {
        setIsAutoMode(false);
      }
      return next;
    });
  };

  // Toggle all products in a family
  const toggleFamily_checkbox = (group: ProductGroup) => {
    const familyIds = group.versions.map(v => v.product_id);
    const allSelected = familyIds.every(id => selectedProducts.includes(id));
    setSelectedProducts(prev => {
      let next: string[];
      if (allSelected) {
        next = prev.filter(p => !familyIds.includes(p));
      } else {
        next = [...new Set([...prev, ...familyIds])];
      }
      setIsAutoMode(next.length === 0);
      return next;
    });
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
      product: isAutoMode ? 'auto' : (selectedProducts[0] || 'auto'),
      products: (!isAutoMode && selectedProducts.length > 0) ? selectedProducts : undefined,
      selected_product: overrideProduct || undefined,
      language: 'ja',
      history: messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-10)
        .map(m => ({ role: m.role, content: m.content, product: m.product })),
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

            case 'low_relevance_warning': {
              const warningMsg: ChatMessage = {
                id: `low-rel-${Date.now()}`,
                role: 'low_relevance',
                content: (event as Record<string, unknown>).message as string || '',
                lowRelevanceScore: (event as Record<string, unknown>).best_score as number,
                searchedProducts: (event as Record<string, unknown>).searched_products as string[],
                timestamp: new Date(),
              };
              setMessages(prev => [...prev, warningMsg]);
              break;
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

            case 'web_doc_match':
              // Web doc 매칭 알림 (score >= 0.9)
              break;

            case 'sources':
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, sources: event as unknown as SourcesEvent } : m
                )
              );
              break;

            case 'done':
              currentQueryType = (event as Record<string, unknown>).query_type as string || currentQueryType;
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? {
                        ...m,
                        queryType: currentQueryType,
                        products: (event as Record<string, unknown>).products as string[] || undefined,
                      }
                    : m
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
  }, [isStreaming, isAuthenticated, isAutoMode, selectedProducts, messages]);

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
    if (msg.role === 'low_relevance') {
      return (
        <div key={msg.id} className="openagent-message assistant">
          <div className="openagent-message-content assistant">
            <div className="low-relevance-warning">
              <AlertTriangle size={16} />
              <span>{msg.content || t('common.agenticRag.lowRelevance') || '検索結果の関連性が低い可能性があります'}</span>
              {msg.searchedProducts && msg.searchedProducts.length > 0 && (
                <span className="low-relevance-products">
                  ({msg.searchedProducts.map(p => getProductLabel(p)).join(', ')})
                </span>
              )}
            </div>
          </div>
        </div>
      );
    }

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
                    <span className="message-query-type" title={msg.queryType}>
                      {msg.queryType === 'command' && <Terminal size={12} />}
                      {msg.queryType === 'error_code' && <AlertTriangle size={12} />}
                      {msg.queryType === 'parameter' && <Settings size={12} />}
                      {msg.queryType === 'config' && <Settings size={12} />}
                      {msg.queryType === 'freeform' && <MessageCircle size={12} />}
                    </span>
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
                    <span className="markdown-image-wrapper" style={{ display: 'block' }}>
                      <img
                        src={src}
                        alt={alt || ''}
                        loading="lazy"
                        onClick={() => src && window.open(src, '_blank')}
                        {...props}
                      />
                      {alt && <span className="markdown-image-caption">{alt}</span>}
                    </span>
                  ),
                  p: ({ children, ...props }) => {
                    // Avoid nesting block elements inside <p>
                    const hasBlock = React.Children.toArray(children).some(
                      (child) => React.isValidElement(child) && typeof child.type === 'string' && ['div', 'table', 'pre'].includes(child.type)
                    );
                    if (hasBlock) return <div {...props}>{children}</div>;
                    return <p {...props}>{children}</p>;
                  },
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
              {msg.sources && msg.sources.results && msg.sources.results.length > 0 && (
                <details className="source-cards">
                  <summary className="source-cards-header">
                    <FileText size={14} />
                    <span>出典情報 ({msg.sources.results.length}件)</span>
                  </summary>
                  <div className="source-cards-list">
                    {msg.sources.results.slice(0, 5).map((src, i) => {
                      const scoreClass = src.score >= 0.7 ? 'high' : src.score >= 0.4 ? 'medium' : 'low';
                      const isWebDoc = src.domain === 'web_doc' && src.url;
                      return (
                        <div key={i} className="source-card-item">
                          {isWebDoc ? (
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="source-card-name source-card-link"
                              title={src.url}
                            >
                              {src.doc_name} ↗
                            </a>
                          ) : (
                            <span className="source-card-name">{src.doc_name}</span>
                          )}
                          {src.source_page && !isWebDoc && (
                            <span className="source-card-page">{src.source_page}</span>
                          )}
                          <span className={`source-card-score ${scoreClass}`}>
                            {src.score.toFixed(1)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </details>
              )}
            </>
          ) : (
            <p>{msg.content}</p>
          )}
        </div>
      </div>
    );
  };

  // Render product tree dropdown (checkbox multi-select)
  const renderProductTree = () => (
    <div className="product-tree-dropdown">
      {/* Auto option */}
      <button
        className={`product-tree-item ${isAutoMode ? 'active' : ''}`}
        onClick={switchToAuto}
      >
        <Zap size={14} />
        <span>{t('common.agenticRag.autoProduct') || 'Auto (All Products)'}</span>
      </button>
      <div className="product-tree-separator" />
      {/* Product families with checkboxes */}
      {productGroups.map(group => {
        const familyIds = group.versions.map(v => v.product_id);
        const allChecked = familyIds.every(id => selectedProducts.includes(id));
        const someChecked = familyIds.some(id => selectedProducts.includes(id));

        return (
          <div key={group.name} className="product-tree-family">
            {group.versions.length === 1 ? (
              // Single version: checkbox
              <label className={`product-tree-item product-tree-checkbox-row ${selectedProducts.includes(group.versions[0].product_id) ? 'active' : ''}`}>
                <input
                  type="checkbox"
                  className="product-tree-checkbox"
                  checked={selectedProducts.includes(group.versions[0].product_id)}
                  onChange={() => toggleProduct(group.versions[0].product_id)}
                />
                <FolderOpen size={14} />
                <span>{group.name}</span>
                <span className="product-tree-meta">
                  {group.versions[0].pdf_count} PDFs
                </span>
              </label>
            ) : (
              // Multiple versions: expandable with family checkbox
              <>
                <div className="product-tree-item product-tree-group">
                  <input
                    type="checkbox"
                    className="product-tree-checkbox"
                    checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked; }}
                    onChange={() => toggleFamily_checkbox(group)}
                  />
                  <button
                    className="product-tree-group-toggle"
                    onClick={() => toggleFamily(group.name)}
                  >
                    {expandedFamilies.has(group.name)
                      ? <ChevronDown size={14} />
                      : <ChevronRight size={14} />
                    }
                    <span>{group.name}</span>
                  </button>
                  <span className="product-tree-meta">
                    {group.versions.length} {t('common.agenticRag.version') || 'ver'}
                  </span>
                </div>
                {expandedFamilies.has(group.name) && (
                  <div className="product-tree-versions">
                    {group.versions.map(v => (
                      <label
                        key={v.product_id}
                        className={`product-tree-item product-tree-version product-tree-checkbox-row ${selectedProducts.includes(v.product_id) ? 'active' : ''}`}
                      >
                        <input
                          type="checkbox"
                          className="product-tree-checkbox"
                          checked={selectedProducts.includes(v.product_id)}
                          onChange={() => toggleProduct(v.product_id)}
                        />
                        <span className="product-tree-version-label">
                          {v.version}
                          {v.doc_version && <span className="product-tree-doc-ver">(v{v.doc_version})</span>}
                        </span>
                        <span className="product-tree-meta">
                          {v.language} · {v.pdf_count} PDFs
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}
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
              <span>{selectorLabel}</span>
              {!isAutoMode && selectedProducts.length > 1 && (
                <span className="product-selector-count">{selectedProducts.length}</span>
              )}
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
