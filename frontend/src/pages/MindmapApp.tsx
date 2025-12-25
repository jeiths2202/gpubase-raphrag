import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MindmapViewer from '../components/MindmapViewer';
import Sidebar from '../components/Sidebar';
import NodePanel from '../components/NodePanel';
import { mindmapApi } from '../services/api';
import type { MindmapFull, MindmapNode, MindmapInfo } from '../types/mindmap';
import { useAuthStore } from '../store/authStore';

const MindmapApp: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [currentMindmap, setCurrentMindmap] = useState<MindmapFull | null>(null);
  const [selectedNode, setSelectedNode] = useState<MindmapNode | null>(null);
  const [mindmapList, setMindmapList] = useState<MindmapInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);

  // Load mindmap list on mount
  useEffect(() => {
    loadMindmapList();
  }, []);

  const loadMindmapList = async () => {
    try {
      const { mindmaps } = await mindmapApi.list();
      setMindmapList(mindmaps);
    } catch (err) {
      console.error('Failed to load mindmap list:', err);
    }
  };

  const handleGenerateMindmap = useCallback(async (options: {
    title?: string;
    maxNodes?: number;
    focusTopic?: string;
    documentIds?: string[];
  }) => {
    setIsLoading(true);
    setError(null);

    try {
      let mindmap: MindmapFull;

      if (options.documentIds && options.documentIds.length > 0) {
        mindmap = await mindmapApi.generate({
          document_ids: options.documentIds,
          title: options.title,
          max_nodes: options.maxNodes || 50,
          focus_topic: options.focusTopic,
          language: 'auto',
        });
      } else {
        mindmap = await mindmapApi.generateFromAll({
          title: options.title,
          max_nodes: options.maxNodes || 50,
          focus_topic: options.focusTopic,
          language: 'auto',
        });
      }

      setCurrentMindmap(mindmap);
      setSelectedNode(null);
      await loadMindmapList();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate mindmap');
      console.error('Generate mindmap error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSelectMindmap = useCallback(async (mindmapId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const mindmap = await mindmapApi.get(mindmapId);
      setCurrentMindmap(mindmap);
      setSelectedNode(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load mindmap');
      console.error('Load mindmap error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleDeleteMindmap = useCallback(async (mindmapId: string) => {
    try {
      await mindmapApi.delete(mindmapId);
      if (currentMindmap?.id === mindmapId) {
        setCurrentMindmap(null);
        setSelectedNode(null);
      }
      await loadMindmapList();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete mindmap');
    }
  }, [currentMindmap]);

  const handleNodeSelect = useCallback((node: MindmapNode | null) => {
    setSelectedNode(node);
  }, []);

  const handleExpandNode = useCallback(async (nodeId: string) => {
    if (!currentMindmap) return;

    setIsLoading(true);
    try {
      const result = await mindmapApi.expand(currentMindmap.id, {
        node_id: nodeId,
        depth: 1,
        max_children: 10,
      });

      // Update mindmap with new nodes and edges
      setCurrentMindmap(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          node_count: prev.node_count + result.new_nodes.length,
          edge_count: prev.edge_count + result.new_edges.length,
          data: {
            ...prev.data,
            nodes: [...prev.data.nodes, ...result.new_nodes],
            edges: [...prev.data.edges, ...result.new_edges],
          },
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to expand node');
    } finally {
      setIsLoading(false);
    }
  }, [currentMindmap]);

  return (
    <div className="app-container" style={{
      display: 'flex',
      width: '100vw',
      height: '100vh',
      overflow: 'hidden',
    }}>
      {/* Sidebar */}
      {showSidebar && (
        <Sidebar
          mindmapList={mindmapList}
          currentMindmapId={currentMindmap?.id}
          onSelectMindmap={handleSelectMindmap}
          onDeleteMindmap={handleDeleteMindmap}
          onGenerateMindmap={handleGenerateMindmap}
          isLoading={isLoading}
        />
      )}

      {/* Main Content */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}>
        {/* Header */}
        <header style={{
          padding: '12px 20px',
          background: 'var(--color-bg-card)',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-text-secondary)',
                cursor: 'pointer',
                fontSize: '20px',
                padding: '4px',
              }}
            >
              {showSidebar ? '◀' : '▶'}
            </button>
            <h1 style={{
              fontSize: '18px',
              fontWeight: '600',
              color: 'var(--color-text-primary)',
            }}>
              {currentMindmap ? currentMindmap.title : 'KMS Mindmap'}
            </h1>
            {currentMindmap && (
              <span style={{
                fontSize: '13px',
                color: 'var(--color-text-muted)',
              }}>
                {currentMindmap.node_count} nodes / {currentMindmap.edge_count} edges
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {isLoading && (
              <span style={{
                fontSize: '13px',
                color: 'var(--color-primary)',
              }} className="loading">
                Processing...
              </span>
            )}
            {user?.role === 'admin' && (
              <button
                onClick={() => navigate('/admin')}
                style={{
                  padding: '8px 16px',
                  background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2))',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  borderRadius: '6px',
                  color: '#a5b4fc',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: '500',
                  transition: 'all 0.2s',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.3))';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2))';
                }}
              >
                관리자
              </button>
            )}
            <span style={{
              fontSize: '13px',
              color: 'var(--color-text-muted)',
            }}>
              {user?.name || user?.email}
            </span>
            <button
              onClick={() => logout()}
              style={{
                padding: '8px 16px',
                background: 'transparent',
                border: '1px solid var(--color-border)',
                borderRadius: '6px',
                color: 'var(--color-text-secondary)',
                cursor: 'pointer',
                fontSize: '13px',
                transition: 'all 0.2s',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-error)';
                e.currentTarget.style.color = 'var(--color-error)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-border)';
                e.currentTarget.style.color = 'var(--color-text-secondary)';
              }}
            >
              로그아웃
            </button>
          </div>
        </header>

        {/* Error Display */}
        {error && (
          <div style={{
            padding: '12px 20px',
            background: 'rgba(239, 68, 68, 0.1)',
            borderBottom: '1px solid var(--color-error)',
            color: 'var(--color-error)',
            fontSize: '14px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-error)',
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Mindmap Viewer */}
        <div style={{ flex: 1, position: 'relative' }}>
          {currentMindmap ? (
            <MindmapViewer
              mindmap={currentMindmap}
              selectedNodeId={selectedNode?.id}
              onNodeSelect={handleNodeSelect}
              onExpandNode={handleExpandNode}
            />
          ) : (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'var(--color-text-secondary)',
              gap: '20px',
            }}>
              <div style={{ fontSize: '64px' }}>🧠</div>
              <h2 style={{ fontSize: '24px', fontWeight: '500' }}>
                마인드맵 생성을 시작하세요
              </h2>
              <p style={{ fontSize: '14px', color: 'var(--color-text-muted)' }}>
                왼쪽 사이드바에서 새 마인드맵을 생성하거나 기존 마인드맵을 선택하세요
              </p>
              <button
                className="btn btn-primary"
                onClick={() => handleGenerateMindmap({ title: 'New Mindmap' })}
                disabled={isLoading}
              >
                {isLoading ? '생성 중...' : '전체 문서로 마인드맵 생성'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Node Detail Panel */}
      {selectedNode && currentMindmap && (
        <NodePanel
          mindmapId={currentMindmap.id}
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onExpand={() => handleExpandNode(selectedNode.id)}
        />
      )}
    </div>
  );
};

export default MindmapApp;
