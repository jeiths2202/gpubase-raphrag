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
import { useInputHistory } from '../hooks/useInputHistory';
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
  Paperclip,
  X,
  History,
  Plus,
  Link2,
  Sparkles,
  HelpCircle,
  GitBranch,
  Code2,
  ThumbsUp,
  ThumbsDown,
  Upload,
} from 'lucide-react';
import { MessageContent } from '../components/AgentChat/MessageContent';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { ExternalConnectorsModal } from '../components/AgentChat/ExternalConnectorsModal';
import { FAQRegistrationModal } from '../components/AgentChat/FAQRegistrationModal';
import { submitQuickFeedback, cancelFeedback } from '../api/feedback.api';
import { useFileAttachment } from '../components/AgentChat/hooks/useFileAttachment';
import { useExternalConnectorsStore } from '../store/externalConnectorsStore';
import { conversationApi } from '../api/conversation.api';
import type { ConversationMessage } from '../api/conversation.api';
import { getFAQItems, type FAQItemAPI } from '../api/faq.api';
import client from '../api/client';
import type { AgentType } from '../api/agent.api';
import type {
  AgenticRAGRequest,
  AgentMode,
  ClarificationCandidate,
  VerifiedSentence,
  SSEEvent,
  ProductGroup,
} from '../api/agentic-rag.api';
import { TracePanel } from '../components/TracePanel/TracePanel';
import { useTraceStore } from '../store/traceStore';
import { KnowledgeGraphView } from '../components/KnowledgeGraph';
import type { Node, Edge } from 'reactflow';
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
  graphData?: { nodes: Node[]; edges: Edge[] };
  timestamp: Date;
}

export const AgenticRAGPage: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated, user } = useAuthStore();
  const userRole = user?.role;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);  // empty = auto
  const [isAutoMode, setIsAutoMode] = useState(true);
  const [showProductSelector, setShowProductSelector] = useState(false);
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set());
  const [agentMode, setAgentMode] = useState<AgentMode>('rag');
  const [specialAgent, setSpecialAgent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { handleHistoryNav, resetHistory } = useInputHistory(messages);

  // --- Feature 1: File attachment ---
  const selectedAgentRef = useRef<AgentType>('rag');
  const {
    attachedFiles, fileError, fileInputRef,
    handleFileAttach, handleFileChange, handleRemoveFile,
    getFileContext, clearFileError,
  } = useFileAttachment(selectedAgentRef);

  // --- Feature 2: Conversation history ---
  const [showHistorySidebar, setShowHistorySidebar] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  // --- Feature 3: External connectors ---
  const [showConnectorsModal, setShowConnectorsModal] = useState(false);
  const { getActiveResourcesContext } = useExternalConnectorsStore();

  // --- Feature 5: FAQ ---
  const [faqItems, setFaqItems] = useState<FAQItemAPI[]>([]);

  // --- Feature 6: Feedback & FAQ Registration ---
  const [feedbackState, setFeedbackState] = useState<Record<string, 'thumbs_up' | 'thumbs_down' | null>>({});
  const [faqModal, setFaqModal] = useState<{ open: boolean; question: string; answer: string }>({
    open: false, question: '', answer: '',
  });

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
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as globalThis.Node)) {
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

  // Load FAQ items on mount
  useEffect(() => {
    if (!isAuthenticated) return;
    getFAQItems({ limit: 5, category: 'openframe' })
      .then(res => {
        if (res.data?.items) setFaqItems(res.data.items);
      })
      .catch(() => { /* FAQ unavailable */ });
  }, [isAuthenticated]);

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

  // --- Feature 6: Feedback handler ---
  const handleFeedback = useCallback(async (messageId: string, type: 'thumbs_up' | 'thumbs_down') => {
    const current = feedbackState[messageId];
    if (current === type) {
      // Toggle off (cancel feedback)
      try {
        await cancelFeedback(messageId);
      } catch { /* cancel is best-effort */ }
      setFeedbackState(prev => ({ ...prev, [messageId]: null }));
    } else {
      // Find the user question preceding this assistant message
      const msgIdx = messages.findIndex(m => m.id === messageId);
      const userMsg = messages.slice(0, msgIdx).reverse().find(m => m.role === 'user');
      const assistantMsg = messages.find(m => m.id === messageId);

      try {
        await submitQuickFeedback({
          message_id: messageId,
          feedback_type: type,
          query: userMsg?.content,
          answer: assistantMsg?.content,
          conversation_id: activeConversationId || undefined,
        });
      } catch { /* feedback submission is best-effort */ }
      setFeedbackState(prev => ({ ...prev, [messageId]: type }));
    }
  }, [feedbackState, messages, activeConversationId]);

  // --- Feature 6: FAQ modal opener ---
  const openFAQModal = useCallback((msg: ChatMessage) => {
    const msgIdx = messages.findIndex(m => m.id === msg.id);
    const userMsg = messages.slice(0, msgIdx).reverse().find(m => m.role === 'user');
    setFaqModal({ open: true, question: userMsg?.content || '', answer: msg.content });
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
    resetHistory();
    setIsStreaming(true);

    // File context from attachment
    const fileCtx = getFileContext();
    // External connectors context
    const externalCtx = getActiveResourcesContext();

    const request: AgenticRAGRequest = {
      message: text,
      product: isAutoMode ? 'auto' : (selectedProducts[0] || 'auto'),
      products: (!isAutoMode && selectedProducts.length > 0) ? selectedProducts : undefined,
      selected_product: overrideProduct || undefined,
      language: 'ja',
      agent_mode: specialAgent ? 'special' : agentMode,
      history: messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-10)
        .map(m => ({ role: m.role, content: m.content, product: m.product })),
      ...(fileCtx ? { file_context: fileCtx } : {}),
      ...(externalCtx ? { external_context: externalCtx } : {}),
    };

    // Conversation persistence: create if needed, save user message
    let convId = activeConversationId;
    try {
      if (!convId) {
        const conv = await conversationApi.create({
          title: text.slice(0, 50),
          agent_type: 'rag',
          language: 'ja',
        });
        convId = conv.id;
        setActiveConversationId(convId);
      }
      await conversationApi.addMessage(convId, { role: 'user', content: text });
    } catch { /* conversation save optional */ }

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

            case 'vllm_direct_fallthrough':
              // vLLM 직접 응답 불충분 → 부분 출력 클리어, RAG로 전환
              currentContent = '';
              setMessages(prev => prev.filter(m => m.id !== assistantId));
              break;

            case 'web_doc_match':
              // Web doc 매칭 알림 (score >= 0.9)
              break;

            case 'agent_mode':
              // 감지된 모드 표시 (auto인 경우)
              break;

            case 'plan_start': {
              // TracePanel 초기화 + 열기
              const traceId = (event as Record<string, unknown>).trace_id as string;
              if (traceId) {
                useTraceStore.getState().initTrace(traceId);
                useTraceStore.getState().openPanel();
              }
              break;
            }

            case 'plan_step': {
              // 플랜 단계를 timeline에 추가
              const ps = event as Record<string, unknown>;
              useTraceStore.getState().updateFromTraceData({
                timeline_event: {
                  event: 'plan_step',
                  task_id: `step_${(ps.step_index as number) + 1}`,
                  agent_type: (ps.agent_type as string) || 'planner',
                  timestamp: new Date().toISOString(),
                  success: true,
                },
              });
              break;
            }

            case 'trace_data': {
              // TracePanel DAG 업데이트 — trace_data 내부 객체를 추출하여 전달
              const traceOuter = event as Record<string, unknown>;
              const traceInner = traceOuter.trace_data as Record<string, unknown> | undefined;
              if (traceInner) {
                useTraceStore.getState().updateFromTraceData(traceInner);
                // DAG 구조가 포함된 경우 TracePanel 자동 열기
                if (traceInner.dag) {
                  useTraceStore.getState().openPanel();
                }
              }
              break;
            }

            case 'graph_data': {
              const ev = event as Record<string, unknown>;
              const graphNodes = ev.nodes as Node[] | undefined;
              const graphEdges = ev.edges as Edge[] | undefined;
              if (graphNodes && graphNodes.length > 0) {
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantId
                      ? { ...m, graphData: { nodes: graphNodes, edges: graphEdges || [] } }
                      : m
                  )
                );
              }
              break;
            }

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
      // Save assistant response to conversation
      if (convId && currentContent) {
        try {
          await conversationApi.addMessage(convId, { role: 'assistant', content: currentContent });
        } catch { /* optional */ }
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
  }, [isStreaming, isAuthenticated, isAutoMode, selectedProducts, messages, activeConversationId, agentMode]);

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
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
      return;
    }
    handleHistoryNav(e, input, setInput);
  };

  // Clear messages
  const handleClear = () => {
    setMessages([]);
    setActiveConversationId(null);
  };

  // Conversation history handlers
  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setActiveConversationId(null);
  }, []);

  const handleSelectConversation = useCallback(async (conversationId: string) => {
    try {
      const conv = await conversationApi.get(conversationId, true);
      setActiveConversationId(conversationId);
      const restored: ChatMessage[] = conv.messages.map((m: ConversationMessage) => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: new Date(m.created_at),
      }));
      setMessages(restored);
    } catch { /* load failed */ }
  }, []);

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
              <MessageContent content={msg.content} />
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

              {/* 관련 엔티티 그래프 (Neo4j → ReactFlow) */}
              {msg.graphData && msg.graphData.nodes.length > 0 && (
                <details className="graph-mini-container">
                  <summary>
                    <GitBranch size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    {t('knowledgeGraph.relatedGraph')} ({msg.graphData.nodes.length})
                  </summary>
                  <div style={{ height: 280 }}>
                    <KnowledgeGraphView
                      nodes={msg.graphData.nodes}
                      edges={msg.graphData.edges}
                      mini
                    />
                  </div>
                </details>
              )}

              {/* Feedback actions (👍/👎 + FAQ registration) */}
              {!isStreaming && (
                <div className="agentic-rag-message-actions">
                  <button
                    className={`agentic-rag-feedback-btn ${feedbackState[msg.id] === 'thumbs_up' ? 'active thumbs-up' : ''}`}
                    onClick={() => handleFeedback(msg.id, 'thumbs_up')}
                    title={t('common.agent.feedback.thumbsUp') || 'Helpful'}
                  >
                    <ThumbsUp size={14} />
                  </button>
                  <button
                    className={`agentic-rag-feedback-btn ${feedbackState[msg.id] === 'thumbs_down' ? 'active thumbs-down' : ''}`}
                    onClick={() => handleFeedback(msg.id, 'thumbs_down')}
                    title={t('common.agent.feedback.thumbsDown') || 'Not helpful'}
                  >
                    <ThumbsDown size={14} />
                  </button>
                  {(userRole === 'admin' || userRole === 'leader') && (
                    <button
                      className="agentic-rag-feedback-btn faq-register"
                      onClick={() => openFAQModal(msg)}
                      title={t('common.agent.faq.registerTitle') || 'Register as FAQ'}
                    >
                      <Upload size={14} />
                    </button>
                  )}
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
    <div className="openagent-page agentic-rag-layout">
      {/* Feature 2: Conversation History Sidebar */}
      <ConversationSidebar
        agentType="rag"
        isOpen={showHistorySidebar}
        onToggle={() => setShowHistorySidebar(prev => !prev)}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
      />

      {/* Main content wrapper (flex column, fills space next to sidebar) */}
      <div className="openagent-main-content">

      {/* Toolbar header bar */}
      <div className="openagent-header" style={{ justifyContent: 'flex-end' }}>
        <div className="openagent-header-right">
          <button
            className={`openagent-btn-icon ${showHistorySidebar ? 'active' : ''}`}
            onClick={() => setShowHistorySidebar(prev => !prev)}
            title={t('common.agenticRag.history') || 'History'}
          >
            <History size={18} />
          </button>
          <button
            className="openagent-btn-icon"
            onClick={handleNewConversation}
            title={t('common.agenticRag.newConversation') || 'New Conversation'}
          >
            <Plus size={18} />
          </button>
          <button
            className="openagent-btn-icon"
            onClick={() => setShowConnectorsModal(true)}
            title={t('common.agenticRag.connectors') || 'External Connectors'}
          >
            <Link2 size={18} />
          </button>
          {/* Agent Mode Selector */}
          <div className="agent-mode-selector">
            <button
              className={`agent-mode-btn ${agentMode === 'rag' ? 'active' : ''}`}
              onClick={() => setAgentMode('rag')}
              title={t('common.agenticRag.modeRag') || 'RAG / Search'}
            >
              <Search size={14} />
              <span>RAG</span>
            </button>
            <button
              className={`agent-mode-btn ${agentMode === 'code' ? 'active' : ''}`}
              onClick={() => setAgentMode('code')}
              title={t('common.agenticRag.modeCode') || 'Code / Script'}
            >
              <Code2 size={14} />
              <span>Code</span>
            </button>
            <button
              className={`agent-mode-btn ${agentMode === 'planner' ? 'active' : ''}`}
              onClick={() => setAgentMode('planner')}
              title={t('common.agenticRag.modePlanner') || 'Planner'}
            >
              <GitBranch size={14} />
              <span>Plan</span>
            </button>
          </div>
          {/* Special Agent Checkbox */}
          <label className="special-agent-toggle" title={t('common.agenticRag.specialAgent') || 'Special Agent'}>
            <input
              type="checkbox"
              checked={specialAgent}
              onChange={(e) => setSpecialAgent(e.target.checked)}
            />
            <Sparkles size={14} />
            <span>Special</span>
          </label>
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
        {messages.length === 0 && !isStreaming ? (
          <div className="openagent-empty">
            <Sparkles size={48} style={{ opacity: 0.3 }} />
            <p>{t('common.agenticRag.emptyState') || '製品に関する技術的な質問を入力してください'}</p>
            <p style={{ fontSize: '0.85rem', opacity: 0.6 }}>
              {t('common.agenticRag.emptyHint') || 'コマンド使用法、エラーコード、設定方法など'}
            </p>
            {/* Feature 4: Suggestion buttons */}
            <div className="openagent-suggestions">
              <button onClick={() => setInput(t('common.agenticRag.suggestion1') || '')}>
                {t('common.agenticRag.suggestion1')}
              </button>
              <button onClick={() => setInput(t('common.agenticRag.suggestion2') || '')}>
                {t('common.agenticRag.suggestion2')}
              </button>
              <button onClick={() => setInput(t('common.agenticRag.suggestion3') || '')}>
                {t('common.agenticRag.suggestion3')}
              </button>
            </div>
            {/* Feature 5: FAQ section */}
            {faqItems.length > 0 && (
              <div className="openagent-suggestions" style={{ marginTop: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, opacity: 0.7, fontSize: '0.85rem' }}>
                  <HelpCircle size={14} />
                  <span>{t('common.agenticRag.faqTitle') || 'FAQ'}</span>
                </div>
                {faqItems.map(faq => (
                  <button key={faq.id} onClick={() => { setInput(faq.question); sendMessage(faq.question); }}>
                    {faq.question}
                  </button>
                ))}
              </div>
            )}
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

      {/* Feature 1: Attached files display */}
      {attachedFiles.length > 0 && (
        <div className="openagent-selected-file">
          {attachedFiles.map(f => (
            <div key={f.name} className="openagent-selected-file" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px' }}>
              <Paperclip size={14} />
              <span style={{ fontSize: '0.85rem' }}>{f.name}</span>
              <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>({(f.size / 1024).toFixed(1)}KB)</span>
              <button onClick={() => handleRemoveFile(f.name)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}>
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {fileError && (
        <div style={{ color: 'red', fontSize: '0.8rem', padding: '0 16px' }} onClick={clearFileError}>
          {fileError}
        </div>
      )}

      {/* Input */}
      <form className="openagent-input-area" onSubmit={handleSubmit}>
        <div className="openagent-input-row">
          {/* Feature 1: File attach button */}
          <input
            ref={fileInputRef}
            type="file"
            style={{ display: 'none' }}
            onChange={handleFileChange}
            accept=".txt,.md,.py,.js,.ts,.json,.yaml,.yml,.xml,.html,.css,.java,.go,.rs,.c,.cpp,.h,.pdf"
          />
          <button
            type="button"
            className="openagent-btn-attach"
            onClick={handleFileAttach}
            disabled={isStreaming}
            title={t('common.agenticRag.attachFile') || 'Attach File'}
          >
            <Paperclip size={20} />
          </button>
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
            disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
          >
            {isStreaming ? <Loader2 size={20} className="spinning" /> : <Send size={20} />}
          </button>
        </div>
      </form>

      {/* Feature 3: External Connectors Modal */}
      <ExternalConnectorsModal
        isOpen={showConnectorsModal}
        onClose={() => setShowConnectorsModal(false)}
        t={t}
      />

      {/* Feature 6: FAQ Registration Modal */}
      <FAQRegistrationModal
        isOpen={faqModal.open}
        onClose={() => setFaqModal(prev => ({ ...prev, open: false }))}
        onSuccess={() => setFaqModal(prev => ({ ...prev, open: false }))}
        t={t}
        question={faqModal.question}
        answer={faqModal.answer}
        agentType="rag"
      />

      {/* TracePanel for Planner mode */}
      <TracePanel t={t} />

      </div>{/* end openagent-main-content */}
    </div>
  );
};

export default AgenticRAGPage;
