/**
 * KnowledgeGraphPage - 독립 Knowledge Graph Explorer
 *
 * Neo4j 엔티티 그래프를 ReactFlow로 인터랙티브하게 탐색합니다.
 * - 엔티티 검색 → 서브그래프 시각화
 * - 제품 선택 → 엔티티 개요 그래프
 * - 노드 클릭 → 상세 패널
 */
import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import { Search, GitBranch, Loader2, ChevronDown } from 'lucide-react';
import { KnowledgeGraphView } from '../components/KnowledgeGraph';
import type { Node, Edge } from 'reactflow';
import client from '../api/client';
import type { ProductGroup } from '../api/agentic-rag.api';
import './OpenAgentPage.css';
import '../components/KnowledgeGraph/KnowledgeGraph.css';

const BASE = '/graph-viz';

interface NodeDetail {
  id: string;
  label: string;
  entityType: string;
  color: string;
  properties: Record<string, unknown>;
}

export const KnowledgeGraphPage: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuthStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);

  // 제품 목록 로드
  useEffect(() => {
    if (!isAuthenticated) return;
    client
      .get('/agentic-rag/products')
      .then((res) => {
        const data = res.data?.data || res.data;
        if (data?.products) setProductGroups(data.products);
      })
      .catch(() => {});
  }, [isAuthenticated]);

  // 엔티티 검색
  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (!q) return;
    setLoading(true);
    setSelectedNode(null);
    try {
      const res = await client.get(`${BASE}/entity`, {
        params: { name: q, depth: 2, limit: 30 },
      });
      const data = res.data?.data || res.data;
      setNodes(data?.nodes || []);
      setEdges(data?.edges || []);
    } catch {
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  // 제품 개요 그래프
  const handleProductSelect = useCallback(
    async (pid: string) => {
      setSelectedProduct(pid);
      if (!pid) {
        setNodes([]);
        setEdges([]);
        return;
      }
      setLoading(true);
      setSelectedNode(null);
      try {
        const res = await client.get(`${BASE}/product/${pid}`, {
          params: { limit: 50 },
        });
        const data = res.data?.data || res.data;
        setNodes(data?.nodes || []);
        setEdges(data?.edges || []);
      } catch {
        setNodes([]);
        setEdges([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // 노드 클릭 → 상세 패널
  const handleNodeClick = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setSelectedNode({
        id: nodeId,
        label: (data.label as string) || nodeId,
        entityType: (data.entityType as string) || 'concept',
        color: (data.color as string) || '#6b7280',
        properties: (data.properties as Record<string, unknown>) || {},
      });
    },
    [],
  );

  // 엔터키 검색
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  if (!isAuthenticated) {
    return (
      <div className="openagent-page">
        <p>{t('common.loginRequired')}</p>
      </div>
    );
  }

  return (
    <div className="kg-page">
      {/* ── 툴바 ── */}
      <div className="kg-page-toolbar">
        <GitBranch size={20} />
        <input
          type="text"
          placeholder={t('knowledgeGraph.search')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          className="agent-mode-btn active"
          onClick={handleSearch}
          disabled={loading || !searchQuery.trim()}
        >
          {loading ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
        </button>

        {/* 제품 선택 */}
        <div style={{ position: 'relative' }}>
          <select
            value={selectedProduct}
            onChange={(e) => handleProductSelect(e.target.value)}
          >
            <option value="">{t('knowledgeGraph.productOverview')}</option>
            {productGroups.map((group) =>
              group.versions.map((v) => (
                <option key={v.product_id} value={v.product_id}>
                  {group.name} {v.version} ({v.pdf_count} PDFs)
                </option>
              )),
            )}
          </select>
          <ChevronDown size={14} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
        </div>
      </div>

      {/* ── メイン コンテンツ ── */}
      <div className="kg-page-content">
        {/* グラフ */}
        <div className="kg-page-graph">
          {nodes.length > 0 ? (
            <KnowledgeGraphView
              nodes={nodes}
              edges={edges}
              onNodeClick={handleNodeClick}
              height="100%"
            />
          ) : (
            <div
              className="kg-view"
              style={{
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--color-text-secondary)',
                fontSize: 14,
              }}
            >
              {loading
                ? t('common.loading')
                : t('knowledgeGraph.noData')}
            </div>
          )}
        </div>

        {/* 상세 패널 */}
        {selectedNode && (
          <div className="kg-page-detail">
            <h3>{selectedNode.label}</h3>
            <span
              className="kg-detail-type"
              style={{ background: selectedNode.color }}
            >
              {selectedNode.entityType}
            </span>
            <div className="kg-detail-props">
              {Object.entries(selectedNode.properties).map(([key, value]) => (
                <div key={key} className="kg-detail-prop">
                  <span className="kg-detail-prop-key">{key}</span>
                  <span className="kg-detail-prop-value">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
              {Object.keys(selectedNode.properties).length === 0 && (
                <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                  {t('knowledgeGraph.noProperties')}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Stats bar ── */}
      <div className="kg-page-stats">
        <span>{t('knowledgeGraph.nodeCount')}: {nodes.length}</span>
        <span>{t('knowledgeGraph.edgeCount')}: {edges.length}</span>
        {selectedProduct && <span>Product: {selectedProduct}</span>}
      </div>
    </div>
  );
};
