import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MindmapViewer from '../components/MindmapViewer';
import Sidebar from '../components/Sidebar';
import NodePanel from '../components/NodePanel';
import { mindmapApi } from '../services/api';
import type { MindmapFull, MindmapNode, MindmapInfo } from '../types/mindmap';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';
import './MindmapApp.css';

const MindmapApp: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { t } = useTranslation();
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
    <div className="mindmap-app-container">
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
      <div className="mindmap-main-content">
        {/* Header */}
        <header className="mindmap-header">
          <div className="mindmap-header-left">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="mindmap-sidebar-toggle"
            >
              {showSidebar ? '◀' : '▶'}
            </button>
            <h1 className="mindmap-header-title">
              {currentMindmap ? currentMindmap.title : 'KMS Mindmap'}
            </h1>
            {currentMindmap && (
              <span className="mindmap-header-meta">
                {currentMindmap.node_count} {t('mindmap.header.nodes')} / {currentMindmap.edge_count} {t('mindmap.header.edges')}
              </span>
            )}
          </div>
          <div className="mindmap-header-right">
            {isLoading && (
              <span className="mindmap-loading-text">
                {t('mindmap.header.processing')}
              </span>
            )}
            {user?.role === 'admin' && (
              <button
                onClick={() => navigate('/admin')}
                className="mindmap-admin-button"
              >
                {t('mindmap.header.admin')}
              </button>
            )}
            <span className="mindmap-user-name">
              {user?.name || user?.email}
            </span>
            <button
              onClick={() => logout()}
              className="mindmap-logout-button"
            >
              {t('mindmap.header.logout')}
            </button>
          </div>
        </header>

        {/* Error Display */}
        {error && (
          <div className="mindmap-error-banner">
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="mindmap-error-close"
            >
              ✕
            </button>
          </div>
        )}

        {/* Mindmap Viewer */}
        <div className="mindmap-viewer-container">
          {currentMindmap ? (
            <MindmapViewer
              mindmap={currentMindmap}
              selectedNodeId={selectedNode?.id}
              onNodeSelect={handleNodeSelect}
              onExpandNode={handleExpandNode}
            />
          ) : (
            <div className="mindmap-empty-state">
              <div className="mindmap-empty-state-icon">🧠</div>
              <h2 className="mindmap-empty-state-title">
                {t('mindmap.empty.title')}
              </h2>
              <p className="mindmap-empty-state-description">
                {t('mindmap.empty.description')}
              </p>
              <button
                className="btn btn-primary"
                onClick={() => handleGenerateMindmap({ title: 'New Mindmap' })}
                disabled={isLoading}
              >
                {isLoading ? t('mindmap.empty.generating') : t('mindmap.empty.generateAll')}
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
