import React, { useState, useEffect } from 'react';
import { mindmapApi } from '../services/api';
import { useTranslation } from '../hooks/useTranslation';
import type { MindmapNode, QueryNodeResponse, NodeDetailResponse } from '../types/mindmap';

interface NodePanelProps {
  mindmapId: string;
  node: MindmapNode;
  onClose: () => void;
  onExpand: () => void;
}

const NodePanel: React.FC<NodePanelProps> = ({
  mindmapId,
  node,
  onClose,
  onExpand,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'info' | 'query' | 'related'>('info');
  const [question, setQuestion] = useState('');
  const [queryResult, setQueryResult] = useState<QueryNodeResponse | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load node detail when node changes
  useEffect(() => {
    loadNodeDetail();
  }, [node.id]);

  const loadNodeDetail = async () => {
    setIsLoading(true);
    try {
      const detail = await mindmapApi.getNodeDetail(mindmapId, node.id);
      setNodeDetail(detail);
    } catch (err) {
      console.error('Failed to load node detail:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuery = async () => {
    if (!question.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await mindmapApi.query(mindmapId, {
        node_id: node.id,
        question: question,
      });
      setQueryResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSummarize = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await mindmapApi.query(mindmapId, {
        node_id: node.id,
      });
      setQueryResult(result);
      setActiveTab('query');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Summarize failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Get node type color and label
  const getTypeInfo = (type: string) => {
    const types: Record<string, { color: string; label: string }> = {
      root: { color: '#6366f1', label: 'Root' },
      concept: { color: '#818cf8', label: 'Concept' },
      entity: { color: '#10b981', label: 'Entity' },
      topic: { color: '#a78bfa', label: 'Topic' },
      keyword: { color: '#f59e0b', label: 'Keyword' },
    };
    return types[type] || types.concept;
  };

  const typeInfo = getTypeInfo(node.type);

  return (
    <div
      className="fade-in"
      style={{
        width: '380px',
        height: '100%',
        background: 'var(--color-bg-card)',
        borderLeft: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: '4px',
              background: typeInfo.color,
              color: 'white',
              fontSize: '11px',
              fontWeight: '600',
              textTransform: 'uppercase',
              marginBottom: '8px',
            }}
          >
            {typeInfo.label}
          </div>
          <h3
            style={{
              fontSize: '18px',
              fontWeight: '600',
              color: 'var(--color-text-primary)',
              wordBreak: 'break-word',
            }}
          >
            {node.label}
          </h3>
          {node.description && (
            <p
              style={{
                fontSize: '13px',
                color: 'var(--color-text-secondary)',
                marginTop: '6px',
                lineHeight: 1.5,
              }}
            >
              {node.description}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
            fontSize: '20px',
            padding: '4px',
            marginLeft: '8px',
          }}
        >
          ✕
        </button>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        {[
          { key: 'info', labelKey: 'mindmap.panel.tabs.info' },
          { key: 'query', labelKey: 'mindmap.panel.tabs.query' },
          { key: 'related', labelKey: 'mindmap.panel.tabs.related' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as typeof activeTab)}
            style={{
              flex: 1,
              padding: '12px',
              background: 'none',
              border: 'none',
              borderBottom:
                activeTab === tab.key
                  ? '2px solid var(--color-primary)'
                  : '2px solid transparent',
              color:
                activeTab === tab.key
                  ? 'var(--color-primary)'
                  : 'var(--color-text-secondary)',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              transition: 'all 0.2s',
            }}
          >
            {t(tab.labelKey as keyof import('../i18n/types').TranslationKeys)}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
        {/* Info Tab */}
        {activeTab === 'info' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Importance */}
            <div>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: '600',
                  color: 'var(--color-text-muted)',
                  marginBottom: '6px',
                }}
              >
                {t('mindmap.panel.importance')}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div
                  style={{
                    flex: 1,
                    height: '8px',
                    background: 'var(--color-bg-dark)',
                    borderRadius: '4px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${node.importance * 100}%`,
                      height: '100%',
                      background: typeInfo.color,
                      borderRadius: '4px',
                    }}
                  />
                </div>
                <span style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  {Math.round(node.importance * 100)}%
                </span>
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={onExpand}
                disabled={isLoading}
              >
                🔍 {t('mindmap.panel.expand')}
              </button>
              <button
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={handleSummarize}
                disabled={isLoading}
              >
                📝 {t('mindmap.panel.summarize')}
              </button>
            </div>

            {/* Source Content */}
            {nodeDetail?.source_content && nodeDetail.source_content.length > 0 && (
              <div>
                <div
                  style={{
                    fontSize: '12px',
                    fontWeight: '600',
                    color: 'var(--color-text-muted)',
                    marginBottom: '8px',
                  }}
                >
                  {t('mindmap.panel.sourceDocuments')}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {nodeDetail.source_content.map((source, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '10px',
                        background: 'var(--color-bg-dark)',
                        borderRadius: '6px',
                        fontSize: '12px',
                        color: 'var(--color-text-secondary)',
                        lineHeight: 1.5,
                      }}
                    >
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--color-text-muted)',
                          marginBottom: '4px',
                        }}
                      >
                        📄 {source.doc_id}
                      </div>
                      {source.content}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Query Tab */}
        {activeTab === 'query' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                className="input"
                placeholder={t('mindmap.panel.askPlaceholder', { label: node.label })}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
              />
              <button
                className="btn btn-primary"
                onClick={handleQuery}
                disabled={isLoading || !question.trim()}
              >
                {t('mindmap.panel.ask')}
              </button>
            </div>

            {error && (
              <div
                style={{
                  padding: '10px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid var(--color-error)',
                  borderRadius: '6px',
                  color: 'var(--color-error)',
                  fontSize: '13px',
                }}
              >
                {error}
              </div>
            )}

            {isLoading && (
              <div
                style={{
                  textAlign: 'center',
                  padding: '20px',
                  color: 'var(--color-text-muted)',
                }}
                className="loading"
              >
                {t('mindmap.panel.generatingAnswer')}
              </div>
            )}

            {queryResult && !isLoading && (
              <div className="fade-in">
                <div
                  style={{
                    fontSize: '12px',
                    fontWeight: '600',
                    color: 'var(--color-text-muted)',
                    marginBottom: '8px',
                  }}
                >
                  {t('mindmap.panel.answer')}
                </div>
                <div
                  style={{
                    padding: '12px',
                    background: 'var(--color-bg-dark)',
                    borderRadius: '8px',
                    fontSize: '14px',
                    color: 'var(--color-text-primary)',
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {queryResult.answer}
                </div>

                {queryResult.related_concepts.length > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    <div
                      style={{
                        fontSize: '12px',
                        fontWeight: '600',
                        color: 'var(--color-text-muted)',
                        marginBottom: '6px',
                      }}
                    >
                      {t('mindmap.panel.relatedConcepts')}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {queryResult.related_concepts.map((concept, idx) => (
                        <span
                          key={idx}
                          style={{
                            padding: '4px 10px',
                            background: 'var(--color-bg-hover)',
                            borderRadius: '12px',
                            fontSize: '12px',
                            color: 'var(--color-text-secondary)',
                          }}
                        >
                          {concept}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Related Tab */}
        {activeTab === 'related' && (
          <div>
            {isLoading ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '20px',
                  color: 'var(--color-text-muted)',
                }}
                className="loading"
              >
                {t('common.loading')}
              </div>
            ) : nodeDetail?.connected_nodes && nodeDetail.connected_nodes.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {nodeDetail.connected_nodes.map((connectedNode) => {
                  const connectedTypeInfo = getTypeInfo(connectedNode.type);
                  const edge = nodeDetail.edges.find(
                    (e) => e.source === connectedNode.id || e.target === connectedNode.id
                  );

                  return (
                    <div
                      key={connectedNode.id}
                      style={{
                        padding: '12px',
                        background: 'var(--color-bg-dark)',
                        borderRadius: '8px',
                        borderLeft: `3px solid ${connectedTypeInfo.color}`,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          marginBottom: '4px',
                        }}
                      >
                        <span
                          style={{
                            width: '12px',
                            height: '12px',
                            borderRadius: '50%',
                            background: connectedTypeInfo.color,
                          }}
                        />
                        <span
                          style={{
                            fontSize: '14px',
                            fontWeight: '500',
                            color: 'var(--color-text-primary)',
                          }}
                        >
                          {connectedNode.label}
                        </span>
                      </div>
                      {edge && (
                        <div
                          style={{
                            fontSize: '12px',
                            color: 'var(--color-text-muted)',
                            marginLeft: '20px',
                          }}
                        >
                          {edge.label || edge.relation.replace(/_/g, ' ')}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div
                style={{
                  textAlign: 'center',
                  padding: '20px',
                  color: 'var(--color-text-muted)',
                  fontSize: '13px',
                }}
              >
                {t('mindmap.panel.noRelatedNodes')}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default NodePanel;
