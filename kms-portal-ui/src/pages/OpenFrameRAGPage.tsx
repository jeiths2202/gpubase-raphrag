/**
 * OpenFrame RAG Page
 *
 * Learning LLM-based Multi-Product RAG chat interface with:
 * - 8 product support with auto-detection and manual selection
 * - DeepSeek: Integrated search across all products
 * - Vector + Graph search augmentation
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useInputHistory } from '../hooks/useInputHistory';
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
  Cpu,
  X,
  BookOpen,
  Search,
  ChevronDown,
  Info,
} from 'lucide-react';
import { MessageContent } from '../components/AgentChat/MessageContent';
import './OpenAgentPage.css';

// Product IDs
const PRODUCTS = [
  'openframe_mvs',
  'msp_openframe',
  'vos3_openframe',
  'tibero7',
  'ofasm',
  'ofcobol',
  'xsp_openframe',
  'tmax',
] as const;

type ProductId = typeof PRODUCTS[number] | 'auto' | 'other';

// Product classification result
interface ClassificationResult {
  product: string;
  confidence: number;
  needs_selection: boolean;
  suggestions?: string[];
}

// Message source types
interface LearningLLMSource {
  model?: string;
  adapter?: string;
  product?: string;
  confidence: number;
}

interface VectorSource {
  file: string;
  page?: number;
  similarity: number;
}

interface GraphSource {
  entity: string;
  relation: string;
  target: string;
}

interface ProductSources {
  learning_llm?: LearningLLMSource;
  vector_search?: VectorSource[];
  graph_search?: GraphSource[];
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
  sources?: ProductSources;
  product_detected?: string;
  confidence?: number;
}

interface HealthStatus {
  available: boolean;
  message: string;
  model?: string;
}

// Helper function to extract filename from path
const getFilename = (path: string): string => {
  if (!path) return '';
  const parts = path.split(/[/\\]/);
  return parts[parts.length - 1] || path;
};

export const OpenFrameRAGPage: React.FC = () => {
  const { t, language } = useTranslation();

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  // Product selection state
  const [selectedProduct, setSelectedProduct] = useState<ProductId>('auto');
  const [showProductModal, setShowProductModal] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<string>('');
  const [classification, setClassification] = useState<ClassificationResult | null>(null);
  const [isClassifying, setIsClassifying] = useState(false);

  // DeepSeek state
  const [isDeepSeek, setIsDeepSeek] = useState(false);
  const [deepSeekProgress, setDeepSeekProgress] = useState<Record<string, 'pending' | 'searching' | 'done'>>({});

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { handleHistoryNav, resetHistory } = useInputHistory(messages);

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
      const response = await client.get<HealthStatus>('/openframe-rag/health');
      setHealthStatus({
        available: response.data.available,
        message: response.data.message,
        model: 'Learning LLM (QLoRA)',
      });
    } catch (err) {
      setHealthStatus({
        available: false,
        message: 'Failed to connect to OpenFrame RAG service',
      });
    }
  };

  const generateId = () => `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  // Get product display name
  const getProductName = (productId: string): string => {
    const key = `common.openframeRag.products.${productId}`;
    const translated = t(key);
    return translated !== key ? translated : productId;
  };

  // Classify query to detect product using backend API
  const classifyQuery = async (query: string): Promise<ClassificationResult> => {
    setIsClassifying(true);
    try {
      const response = await client.post('/openframe-rag/classify', {
        query,
        language,
      });

      if (response.data.success && response.data.classification) {
        return {
          product: response.data.classification.product,
          confidence: response.data.classification.confidence,
          needs_selection: response.data.classification.needs_selection,
          suggestions: response.data.classification.suggestions,
        };
      }

      return { product: 'unknown', confidence: 0.0, needs_selection: true };
    } catch (err) {
      console.error('Classification API error, using fallback:', err);
      // Fallback: simple keyword matching (client-side, case-insensitive via regex)

      // Command-based detection (high confidence)
      if (/tjesmgr|tacfmgr|hidbmgr|oscmgr|osimgr|ndbmgr/i.test(query)) {
        return { product: 'openframe_mvs', confidence: 1.0, needs_selection: false };
      }
      if (/tbboot|tbdown|tbsql|tibero|티베로/i.test(query)) {
        return { product: 'tibero7', confidence: 1.0, needs_selection: false };
      }
      if (/tmax|tuxedo|tmboot|tmdown/i.test(query)) {
        return { product: 'tmax', confidence: 0.9, needs_selection: false };
      }
      if (/ofasm|assembler/i.test(query)) {
        return { product: 'ofasm', confidence: 0.8, needs_selection: false };
      }
      if (/ofcobol|cobol/i.test(query)) {
        return { product: 'ofcobol', confidence: 0.8, needs_selection: false };
      }

      // OpenFrame Base detection (before generic openframe)
      if (/openframe.*base|base.*system|of_base|dataset|dsalc|catalog|catmgr|gdg|vsam/i.test(query)) {
        return { product: 'openframe_base', confidence: 0.8, needs_selection: false };
      }

      // Keyword-based detection (medium confidence)
      if (/openframe|jcl|mainframe|cobol|jeus/i.test(query)) {
        return { product: 'openframe_mvs', confidence: 0.6, needs_selection: true };
      }

      return { product: 'unknown', confidence: 0.0, needs_selection: true };
    } finally {
      setIsClassifying(false);
    }
  };

  // Handle sending message
  const handleSend = useCallback(async () => {
    if ((!input.trim() && !selectedFile) || isLoading) return;

    const query = input.trim();

    // If DeepSeek mode, handle separately
    if (isDeepSeek) {
      await handleDeepSeekSearch(query);
      return;
    }

    // Auto-detect product if set to auto
    if (selectedProduct === 'auto' && !selectedFile) {
      const result = await classifyQuery(query);
      setClassification(result);

      if (result.needs_selection) {
        // Show product selection modal
        setPendingQuery(query);
        setShowProductModal(true);
        return;
      }

      // Auto-detected with high confidence, proceed
      await sendMessage(query, result.product as ProductId);
    } else {
      // Use selected product
      await sendMessage(query, selectedProduct);
    }
  }, [input, selectedFile, isLoading, selectedProduct, isDeepSeek]);

  // Send message with specified product using SSE streaming
  const sendMessage = async (query: string, product: ProductId) => {
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: query,
      timestamp: new Date(),
      fileInfo: selectedFile ? { name: selectedFile.name, size: selectedFile.size } : undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    resetHistory();
    setIsLoading(true);
    setError(null);
    setShowProductModal(false);
    setPendingQuery('');

    // Prepare assistant message placeholder
    const assistantId = generateId();
    let assistantContent = '';
    let productDetected = product !== 'auto' ? product : undefined;
    let confidenceValue = 0;
    const sources: ProductSources = {};

    try {
      // Prepare request body - filter out messages with empty content
      const history = messages
        .slice(-10)
        .filter((m) => m.content && m.content.trim().length > 0)
        .map((m) => ({
          role: m.role,
          content: m.content,
        }));

      let fileContent: string | undefined;
      if (selectedFile) {
        fileContent = await selectedFile.text();
      }

      const requestBody = {
        message: query,
        product: product,
        history: history.length > 0 ? history : undefined,
        file_content: fileContent,
        language,
        use_learning_llm: true,
        use_vector_search: true,
        use_graph_search: true,
      };

      // Use SSE streaming
      console.log('[OpenFrameRAG] Sending request:', JSON.stringify(requestBody, null, 2));
      const authHeader = client.defaults.headers.common?.['Authorization'];
      const response = await fetch(`${client.defaults.baseURL}/openframe-rag/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authHeader ? { 'Authorization': String(authHeader) } : {}),
        },
        body: JSON.stringify(requestBody),
        credentials: 'include',
      });

      if (!response.ok) {
        // Try to get detailed error message from response body
        let errorDetail = response.statusText;
        try {
          const errorBody = await response.json();
          console.error('[OpenFrameRAG] Error response:', errorBody);
          errorDetail = errorBody.detail || errorBody.message || JSON.stringify(errorBody);
        } catch {
          // If response body is not JSON, use status text
        }
        throw new Error(`HTTP ${response.status}: ${errorDetail}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      // Add placeholder message
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          timestamp: new Date(),
        },
      ]);

      // Process SSE stream
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);

              switch (event.type) {
                case 'classification':
                  productDetected = event.data.product;
                  confidenceValue = event.data.confidence;
                  if (event.data.needs_selection) {
                    // Show modal for product selection
                    setPendingQuery(query);
                    setClassification({
                      product: event.data.product,
                      confidence: event.data.confidence,
                      needs_selection: true,
                      suggestions: event.data.suggestions,
                    });
                    setShowProductModal(true);
                    setIsLoading(false);
                    return;
                  }
                  break;

                case 'token':
                  assistantContent += event.data.content;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId ? { ...m, content: assistantContent } : m
                    )
                  );
                  break;

                case 'sources':
                  if (event.data.source_type === 'vector') {
                    sources.vector_search = [];
                  } else if (event.data.source_type === 'graph') {
                    sources.graph_search = [];
                  }
                  break;

                case 'done':
                  productDetected = event.data.product || productDetected;
                  confidenceValue = event.data.confidence === 'high' ? 0.9 :
                    event.data.confidence === 'medium' ? 0.7 : 0.5;
                  if (event.data.sources?.learning_llm) {
                    // Use API response data directly (includes model, adapter, product, confidence)
                    sources.learning_llm = {
                      model: event.data.sources.learning_llm.model,
                      adapter: event.data.sources.learning_llm.adapter,
                      product: event.data.sources.learning_llm.product || productDetected || 'unknown',
                      confidence: event.data.sources.learning_llm.confidence ?? confidenceValue,
                    };
                  }
                  break;

                case 'error':
                  setError(event.data.message || 'Stream error');
                  break;
              }
            } catch (parseErr) {
              // Ignore parse errors for non-JSON lines
            }
          }
        }
      }

      // Update final message with sources
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                sources,
                product_detected: productDetected,
                confidence: confidenceValue,
              }
            : m
        )
      );

      setSelectedFile(null);
    } catch (err: any) {
      console.error('OpenFrame RAG error:', err);
      setError(err.message || 'Failed to get response');
      // Remove placeholder message on error
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
    } finally {
      setIsLoading(false);
    }
  };

  // Handle DeepSeek search using SSE streaming
  const handleDeepSeekSearch = async (query: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: `[DeepSeek] ${query}`,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    resetHistory();
    setIsLoading(true);
    setError(null);

    // Initialize progress for all products
    const initialProgress: Record<string, 'pending' | 'searching' | 'done'> = {};
    PRODUCTS.forEach((p) => {
      initialProgress[p] = 'pending';
    });
    setDeepSeekProgress(initialProgress);

    const assistantId = generateId();
    let finalSummary = '';
    const productResults: Record<string, { response: string; confidence: number }> = {};

    try {
      // Prepare request
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const requestBody = {
        message: query,
        history: history.length > 0 ? history : undefined,
        language,
        max_products: 8,
        include_all_databases: true,
      };

      // Use SSE streaming for DeepSeek
      const deepSeekAuthHeader = client.defaults.headers.common?.['Authorization'];
      const response = await fetch(`${client.defaults.baseURL}/openframe-rag/deep-seek/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(deepSeekAuthHeader ? { 'Authorization': String(deepSeekAuthHeader) } : {}),
        },
        body: JSON.stringify(requestBody),
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      // Add placeholder message
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: t('common.openframeRag.searching'),
          timestamp: new Date(),
        },
      ]);

      // Process SSE stream
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);

              switch (event.type) {
                case 'progress':
                  // Update progress for current product
                  if (event.current_product) {
                    setDeepSeekProgress((prev) => ({
                      ...prev,
                      [event.current_product]: 'searching',
                    }));
                  }
                  break;

                case 'product_result':
                  // Mark product as done
                  if (event.current_product) {
                    setDeepSeekProgress((prev) => ({
                      ...prev,
                      [event.current_product]: 'done',
                    }));

                    // Store product result
                    if (event.product_result) {
                      productResults[event.current_product] = {
                        response: event.product_result.response || '',
                        confidence: event.product_result.confidence || 0,
                      };
                    }
                  }
                  break;

                case 'final':
                  // Final summary
                  if (event.product_result?.response) {
                    finalSummary = event.product_result.response;
                  }
                  break;

                case 'error':
                  setError(event.message || 'DeepSeek error');
                  break;
              }
            } catch (parseErr) {
              // Ignore parse errors
            }
          }
        }
      }

      // Build final message content
      let content = finalSummary;
      if (!content) {
        // Build from product results
        const validResults = Object.entries(productResults)
          .filter(([_, r]) => r.response && r.confidence > 0.3)
          .sort((a, b) => b[1].confidence - a[1].confidence);

        if (validResults.length > 0) {
          content = validResults
            .slice(0, 3)
            .map(([product, result]) => `**${getProductName(product)}** (${(result.confidence * 100).toFixed(0)}%)\n${result.response}`)
            .join('\n\n---\n\n');
        } else {
          content = t('common.openframeRag.noResults');
        }
      }

      // Update final message
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content,
                sources: {
                  learning_llm: { product: 'all', confidence: 0.8 },
                },
              }
            : m
        )
      );
    } catch (err: any) {
      console.error('DeepSeek error:', err);
      setError(err.message || 'DeepSeek search failed');
      // Remove placeholder on error
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
    } finally {
      setIsLoading(false);
      setDeepSeekProgress({});
    }
  };

  // Handle product selection from modal
  const handleProductSelect = async (product: ProductId) => {
    console.log('[OpenFrameRAG] Product selected:', product, 'pendingQuery:', pendingQuery);
    if (pendingQuery) {
      await sendMessage(pendingQuery, product);
    } else {
      console.warn('[OpenFrameRAG] No pending query when product selected');
    }
    setShowProductModal(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }
    handleHistoryNav(e, input, setInput);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
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
    <div className="openagent-page openframe-rag-page">
      {/* Header */}
      <header className="openagent-header">
        <div className="openagent-header-left">
          <Cpu size={24} className="openagent-icon" />
          <div>
            <h1>{t('common.openframeRag.title')}</h1>
            <span className="openagent-subtitle">{t('common.openframeRag.subtitle')}</span>
          </div>
        </div>
        <div className="openagent-header-right">
          {/* Product Selector */}
          <div className="openframe-product-selector">
            <select
              value={selectedProduct}
              onChange={(e) => setSelectedProduct(e.target.value as ProductId)}
              disabled={isLoading}
            >
              <option value="auto">{t('common.openframeRag.products.auto')}</option>
              {PRODUCTS.map((p) => (
                <option key={p} value={p}>
                  {getProductName(p)}
                </option>
              ))}
              <option value="other">{t('common.openframeRag.products.other')}</option>
            </select>
            <ChevronDown size={16} className="openframe-selector-icon" />
          </div>

          {/* DeepSeek Button */}
          <button
            className={`openframe-deepseek-btn ${isDeepSeek ? 'active' : ''}`}
            onClick={() => setIsDeepSeek(!isDeepSeek)}
            title={t('common.openframeRag.deepSeekDescription')}
          >
            <Search size={16} />
            <span>{t('common.openframeRag.deepSeek')}</span>
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

      {/* DeepSeek Warning */}
      {isDeepSeek && (
        <div className="openframe-deepseek-warning">
          <Info size={16} />
          <span>{t('common.openframeRag.deepSeekWarning')}</span>
        </div>
      )}

      {/* Settings Panel */}
      {showSettings && healthStatus && (
        <div className="openagent-settings">
          <h3>{t('common.openAgent.configuration')}</h3>
          <div className="openagent-settings-grid">
            <div className="openagent-setting">
              <label>Model</label>
              <span>{healthStatus.model || 'Learning LLM (QLoRA)'}</span>
            </div>
            <div className="openagent-setting">
              <label>Products</label>
              <span>8 OpenFrame Products</span>
            </div>
            <div className="openagent-setting">
              <label>Status</label>
              <span>{healthStatus.available ? 'Online' : 'Offline'}</span>
            </div>
          </div>
        </div>
      )}

      {/* DeepSeek Progress */}
      {Object.keys(deepSeekProgress).length > 0 && (
        <div className="openframe-deepseek-progress">
          <div className="openframe-deepseek-progress-header">
            <Search size={16} />
            <span>DeepSeek: {t('common.openframeRag.searching')}</span>
          </div>
          <div className="openframe-deepseek-progress-grid">
            {PRODUCTS.map((p) => (
              <div key={p} className={`openframe-deepseek-item ${deepSeekProgress[p]}`}>
                {deepSeekProgress[p] === 'done' ? (
                  <CheckCircle2 size={14} />
                ) : deepSeekProgress[p] === 'searching' ? (
                  <Loader2 size={14} className="spin" />
                ) : (
                  <span className="openframe-deepseek-pending" />
                )}
                <span>{getProductName(p)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="openagent-messages">
        {messages.length === 0 ? (
          <div className="openagent-empty">
            <Cpu size={48} className="openagent-empty-icon" />
            <h2>{t('common.openframeRag.welcomeTitle')}</h2>
            <p>{t('common.openframeRag.welcomeMessage')}</p>
            <div className="openagent-suggestions">
              <button onClick={() => setInput('tjesmgr BOOT 사용법')}>
                tjesmgr BOOT 사용법
              </button>
              <button onClick={() => setInput('에러코드 -5212 원인')}>
                에러코드 -5212 원인
              </button>
              <button onClick={() => setInput('Tibero tablespace 생성')}>
                Tibero tablespace 생성
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
                  <>
                    {/* Product Badge */}
                    {message.product_detected && (
                      <div className="openframe-product-badge">
                        <Cpu size={14} />
                        <span>{getProductName(message.product_detected)}</span>
                        {message.confidence && (
                          <span className="openframe-confidence">
                            ({(message.confidence * 100).toFixed(0)}%)
                          </span>
                        )}
                      </div>
                    )}
                    <MessageContent content={message.content} />
                  </>
                ) : (
                  <p>{message.content}</p>
                )}

                {/* Sources */}
                {message.sources && (
                  <div className="openagent-sources openframe-sources">
                    <div className="openagent-sources-header">
                      <BookOpen size={14} />
                      <span>{t('common.openframeRag.sources.learningLlm')}</span>
                    </div>
                    <div className="openframe-sources-list">
                      {message.sources.learning_llm && (
                        <div className="openframe-source-item learning-llm">
                          <span className="openframe-source-type">🧠</span>
                          <span>{message.sources.learning_llm.model || 'Learning LLM'}{message.sources.learning_llm.product ? ` (${getProductName(message.sources.learning_llm.product)})` : ''}</span>
                          <span className="openframe-source-score">
                            {(message.sources.learning_llm.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}
                      {message.sources.vector_search?.map((v, idx) => (
                        <div key={idx} className="openframe-source-item vector">
                          <span className="openframe-source-type">📄</span>
                          <span>{getFilename(v.file)}{v.page ? ` p.${v.page}` : ''}</span>
                          <span className="openframe-source-score">
                            {(v.similarity * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                      {message.sources.graph_search?.map((g, idx) => (
                        <div key={idx} className="openframe-source-item graph">
                          <span className="openframe-source-type">🔗</span>
                          <span>{g.entity} → {g.target}</span>
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
              <span>{isClassifying ? t('common.openframeRag.searching') : t('common.openAgent.thinking')}</span>
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

      {/* Product Selection Modal */}
      {showProductModal && (
        <div className="openframe-modal-overlay" onClick={() => setShowProductModal(false)}>
          <div className="openframe-modal" onClick={(e) => e.stopPropagation()}>
            <div className="openframe-modal-header">
              <h3>{t('common.openframeRag.selectProduct')}</h3>
              <button onClick={() => setShowProductModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="openframe-modal-body">
              <p className="openframe-modal-query">"{pendingQuery}"</p>
              <p className="openframe-modal-hint">{t('common.openframeRag.productRequired')}</p>

              <div className="openframe-product-grid">
                {PRODUCTS.map((p) => (
                  <button
                    key={p}
                    className={`openframe-product-option ${classification?.product === p ? 'suggested' : ''}`}
                    onClick={() => handleProductSelect(p)}
                  >
                    {getProductName(p)}
                    {classification?.product === p && (
                      <span className="openframe-suggested-badge">{t('common.openframeRag.autoDetected')}</span>
                    )}
                  </button>
                ))}
              </div>

              <div className="openframe-other-option">
                <button
                  className="openframe-product-option other"
                  onClick={() => handleProductSelect('other')}
                >
                  {getProductName('other')}
                </button>
                <p className="openframe-other-warning">
                  <AlertCircle size={14} />
                  {t('common.openframeRag.otherWarning')}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

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
            accept=".txt,.md,.py,.js,.ts,.json,.yaml,.yml,.xml,.html,.css,.java,.go,.rs,.c,.cpp,.h,.pdf"
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

export default OpenFrameRAGPage;
