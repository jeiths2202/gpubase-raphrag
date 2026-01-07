/**
 * AI Studio Page
 *
 * ReactFlow-based mindmap visualization with AI concept extraction
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Brain,
  Download,
  Upload,
  Trash2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RefreshCw,
  Save,
  Sparkles,
  Circle,
  X,
  Wand2
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './AIStudioPage.css';

// Node types
type NodeType = 'concept' | 'topic' | 'detail' | 'question' | 'insight';

interface MindmapNode {
  id: string;
  type: NodeType;
  label: string;
  x: number;
  y: number;
  children: string[];
  parent: string | null;
  expanded: boolean;
  color?: string;
}

interface Mindmap {
  id: string;
  title: string;
  nodes: Record<string, MindmapNode>;
  rootId: string;
  createdAt: string;
  updatedAt: string;
}

// Mock data for initial mindmap
const createInitialMindmap = (): Mindmap => ({
  id: 'mindmap-1',
  title: 'Knowledge Management',
  rootId: 'node-1',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  nodes: {
    'node-1': {
      id: 'node-1',
      type: 'concept',
      label: 'Knowledge Management',
      x: 400,
      y: 300,
      children: ['node-2', 'node-3', 'node-4', 'node-5'],
      parent: null,
      expanded: true,
      color: '#6366F1'
    },
    'node-2': {
      id: 'node-2',
      type: 'topic',
      label: 'Document Processing',
      x: 200,
      y: 150,
      children: ['node-6', 'node-7'],
      parent: 'node-1',
      expanded: true,
      color: '#8B5CF6'
    },
    'node-3': {
      id: 'node-3',
      type: 'topic',
      label: 'Search & Retrieval',
      x: 600,
      y: 150,
      children: ['node-8', 'node-9'],
      parent: 'node-1',
      expanded: true,
      color: '#EC4899'
    },
    'node-4': {
      id: 'node-4',
      type: 'topic',
      label: 'AI Integration',
      x: 200,
      y: 450,
      children: ['node-10'],
      parent: 'node-1',
      expanded: true,
      color: '#10B981'
    },
    'node-5': {
      id: 'node-5',
      type: 'topic',
      label: 'User Experience',
      x: 600,
      y: 450,
      children: ['node-11'],
      parent: 'node-1',
      expanded: true,
      color: '#F59E0B'
    },
    'node-6': {
      id: 'node-6',
      type: 'detail',
      label: 'PDF Extraction',
      x: 80,
      y: 80,
      children: [],
      parent: 'node-2',
      expanded: true
    },
    'node-7': {
      id: 'node-7',
      type: 'detail',
      label: 'Text Analysis',
      x: 320,
      y: 80,
      children: [],
      parent: 'node-2',
      expanded: true
    },
    'node-8': {
      id: 'node-8',
      type: 'detail',
      label: 'Vector Search',
      x: 480,
      y: 80,
      children: [],
      parent: 'node-3',
      expanded: true
    },
    'node-9': {
      id: 'node-9',
      type: 'detail',
      label: 'Graph Query',
      x: 720,
      y: 80,
      children: [],
      parent: 'node-3',
      expanded: true
    },
    'node-10': {
      id: 'node-10',
      type: 'insight',
      label: 'RAG Pipeline',
      x: 200,
      y: 530,
      children: [],
      parent: 'node-4',
      expanded: true
    },
    'node-11': {
      id: 'node-11',
      type: 'question',
      label: 'How to improve UX?',
      x: 600,
      y: 530,
      children: [],
      parent: 'node-5',
      expanded: true
    }
  }
});

// Node color mapping
const nodeColors: Record<NodeType, string> = {
  concept: '#6366F1',
  topic: '#8B5CF6',
  detail: '#64748B',
  question: '#F59E0B',
  insight: '#10B981'
};

export const AIStudioPage: React.FC = () => {
  const { t } = useTranslation();
  const [mindmap, setMindmap] = useState<Mindmap>(createInitialMindmap);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showNodeEditor, setShowNodeEditor] = useState(false);
  const [editingLabel, setEditingLabel] = useState('');

  // Handle canvas mouse events for panning
  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
      setSelectedNode(null);
    }
  }, [pan]);

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      });
    }
  }, [isDragging, dragStart]);

  const handleCanvasMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Handle node selection
  const handleNodeClick = useCallback((nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedNode(nodeId);
    setEditingLabel(mindmap.nodes[nodeId].label);
    setShowNodeEditor(true);
  }, [mindmap]);

  // Handle node drag
  const handleNodeDrag = useCallback((nodeId: string, deltaX: number, deltaY: number) => {
    setMindmap(prev => ({
      ...prev,
      nodes: {
        ...prev.nodes,
        [nodeId]: {
          ...prev.nodes[nodeId],
          x: prev.nodes[nodeId].x + deltaX / zoom,
          y: prev.nodes[nodeId].y + deltaY / zoom
        }
      }
    }));
  }, [zoom]);

  // Zoom controls
  const handleZoomIn = () => setZoom(z => Math.min(z + 0.1, 2));
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.1, 0.5));
  const handleZoomReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Add new node
  const handleAddNode = useCallback((type: NodeType) => {
    const parentId = selectedNode || mindmap.rootId;
    const parent = mindmap.nodes[parentId];
    const newId = `node-${Date.now()}`;

    const newNode: MindmapNode = {
      id: newId,
      type,
      label: t('studio.newNode'),
      x: parent.x + (Math.random() - 0.5) * 200,
      y: parent.y + 100,
      children: [],
      parent: parentId,
      expanded: true,
      color: nodeColors[type]
    };

    setMindmap(prev => ({
      ...prev,
      nodes: {
        ...prev.nodes,
        [newId]: newNode,
        [parentId]: {
          ...prev.nodes[parentId],
          children: [...prev.nodes[parentId].children, newId]
        }
      }
    }));

    setSelectedNode(newId);
    setEditingLabel(t('studio.newNode'));
    setShowNodeEditor(true);
  }, [selectedNode, mindmap, t]);

  // Delete node
  const handleDeleteNode = useCallback(() => {
    if (!selectedNode || selectedNode === mindmap.rootId) return;

    const node = mindmap.nodes[selectedNode];
    const parentId = node.parent;

    // Recursively collect all descendant IDs
    const collectDescendants = (nodeId: string): string[] => {
      const n = mindmap.nodes[nodeId];
      return [nodeId, ...n.children.flatMap(collectDescendants)];
    };

    const toDelete = collectDescendants(selectedNode);

    setMindmap(prev => {
      const newNodes = { ...prev.nodes };
      toDelete.forEach(id => delete newNodes[id]);

      if (parentId) {
        newNodes[parentId] = {
          ...newNodes[parentId],
          children: newNodes[parentId].children.filter(id => id !== selectedNode)
        };
      }

      return { ...prev, nodes: newNodes };
    });

    setSelectedNode(null);
    setShowNodeEditor(false);
  }, [selectedNode, mindmap]);

  // Update node label
  const handleUpdateLabel = useCallback(() => {
    if (!selectedNode) return;

    setMindmap(prev => ({
      ...prev,
      nodes: {
        ...prev.nodes,
        [selectedNode]: {
          ...prev.nodes[selectedNode],
          label: editingLabel
        }
      }
    }));
  }, [selectedNode, editingLabel]);

  // AI Generate concepts
  const handleAIGenerate = useCallback(async () => {
    if (!aiPrompt.trim()) return;

    setIsGenerating(true);

    // Simulate AI generation
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Generate mock concepts based on prompt
    const concepts = [
      `${aiPrompt} - Overview`,
      `${aiPrompt} - Implementation`,
      `${aiPrompt} - Best Practices`,
      `${aiPrompt} - Challenges`
    ];

    const parentId = selectedNode || mindmap.rootId;
    const parent = mindmap.nodes[parentId];
    const baseX = parent.x;
    const baseY = parent.y + 120;

    const newNodes: Record<string, MindmapNode> = {};
    const newChildIds: string[] = [];

    concepts.forEach((concept, index) => {
      const newId = `node-ai-${Date.now()}-${index}`;
      newChildIds.push(newId);
      newNodes[newId] = {
        id: newId,
        type: 'insight',
        label: concept,
        x: baseX + (index - 1.5) * 150,
        y: baseY + Math.abs(index - 1.5) * 50,
        children: [],
        parent: parentId,
        expanded: true,
        color: nodeColors.insight
      };
    });

    setMindmap(prev => ({
      ...prev,
      nodes: {
        ...prev.nodes,
        ...newNodes,
        [parentId]: {
          ...prev.nodes[parentId],
          children: [...prev.nodes[parentId].children, ...newChildIds]
        }
      }
    }));

    setIsGenerating(false);
    setAiPrompt('');
    setShowAIPanel(false);
  }, [aiPrompt, selectedNode, mindmap]);

  // Render connections
  const renderConnections = () => {
    const connections: JSX.Element[] = [];

    Object.values(mindmap.nodes).forEach(node => {
      if (node.parent && mindmap.nodes[node.parent]) {
        const parent = mindmap.nodes[node.parent];
        connections.push(
          <line
            key={`connection-${node.parent}-${node.id}`}
            className="mindmap-connection"
            x1={parent.x}
            y1={parent.y}
            x2={node.x}
            y2={node.y}
            stroke={node.color || '#64748B'}
            strokeWidth="2"
            strokeOpacity="0.4"
          />
        );
      }
    });

    return connections;
  };

  // Render nodes
  const renderNodes = () => {
    return Object.values(mindmap.nodes).map(node => (
      <MindmapNodeComponent
        key={node.id}
        node={node}
        isSelected={selectedNode === node.id}
        isRoot={node.id === mindmap.rootId}
        onClick={(e) => handleNodeClick(node.id, e)}
        onDrag={(dx, dy) => handleNodeDrag(node.id, dx, dy)}
      />
    ));
  };

  return (
    <div className="studio-page">
      {/* Header */}
      <div className="studio-header">
        <div className="studio-header-left">
          <Brain className="studio-icon" />
          <div className="studio-title-group">
            <h1 className="studio-title">{t('studio.title')}</h1>
            <span className="studio-subtitle">{mindmap.title}</span>
          </div>
        </div>

        <div className="studio-header-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setShowAIPanel(true)}
          >
            <Sparkles size={16} />
            {t('studio.aiGenerate')}
          </button>
          <button className="btn btn-ghost btn-sm">
            <Save size={16} />
            {t('common.save')}
          </button>
          <button className="btn btn-ghost btn-sm">
            <Download size={16} />
            {t('studio.export')}
          </button>
          <button className="btn btn-ghost btn-sm">
            <Upload size={16} />
            {t('studio.import')}
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="studio-toolbar">
        <div className="studio-toolbar-group">
          <span className="studio-toolbar-label">{t('studio.addNode')}:</span>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('topic')}
            title={t('studio.nodeTypes.topic')}
          >
            <Circle size={14} fill="#8B5CF6" stroke="#8B5CF6" />
            <span>{t('studio.nodeTypes.topic')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('detail')}
            title={t('studio.nodeTypes.detail')}
          >
            <Circle size={14} fill="#64748B" stroke="#64748B" />
            <span>{t('studio.nodeTypes.detail')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('question')}
            title={t('studio.nodeTypes.question')}
          >
            <Circle size={14} fill="#F59E0B" stroke="#F59E0B" />
            <span>{t('studio.nodeTypes.question')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('insight')}
            title={t('studio.nodeTypes.insight')}
          >
            <Circle size={14} fill="#10B981" stroke="#10B981" />
            <span>{t('studio.nodeTypes.insight')}</span>
          </button>
        </div>

        <div className="studio-toolbar-group">
          <button
            className="studio-tool-btn"
            onClick={handleDeleteNode}
            disabled={!selectedNode || selectedNode === mindmap.rootId}
            title={t('common.delete')}
          >
            <Trash2 size={16} />
          </button>
        </div>

        <div className="studio-toolbar-spacer" />

        <div className="studio-toolbar-group">
          <button className="studio-tool-btn" onClick={handleZoomOut}>
            <ZoomOut size={16} />
          </button>
          <span className="studio-zoom-level">{Math.round(zoom * 100)}%</span>
          <button className="studio-tool-btn" onClick={handleZoomIn}>
            <ZoomIn size={16} />
          </button>
          <button className="studio-tool-btn" onClick={handleZoomReset}>
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div
        className="studio-canvas"
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleCanvasMouseMove}
        onMouseUp={handleCanvasMouseUp}
        onMouseLeave={handleCanvasMouseUp}
      >
        <svg
          className="studio-svg"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
          }}
        >
          <g className="mindmap-connections">
            {renderConnections()}
          </g>
          <g className="mindmap-nodes">
            {renderNodes()}
          </g>
        </svg>

        {/* Node Editor Panel */}
        {showNodeEditor && selectedNode && (
          <div className="studio-node-editor">
            <div className="studio-node-editor-header">
              <h3>{t('studio.editNode')}</h3>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowNodeEditor(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="studio-node-editor-body">
              <label className="studio-editor-label">{t('studio.nodeLabel')}</label>
              <input
                type="text"
                className="input"
                value={editingLabel}
                onChange={(e) => setEditingLabel(e.target.value)}
                onBlur={handleUpdateLabel}
                onKeyDown={(e) => e.key === 'Enter' && handleUpdateLabel()}
              />
              <div className="studio-node-info">
                <span>{t('studio.nodeType')}: {mindmap.nodes[selectedNode].type}</span>
              </div>
            </div>
          </div>
        )}

        {/* AI Generation Panel */}
        {showAIPanel && (
          <div className="studio-ai-panel">
            <div className="studio-ai-panel-header">
              <Wand2 className="studio-ai-icon" />
              <h3>{t('studio.aiAssistant')}</h3>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowAIPanel(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="studio-ai-panel-body">
              <p className="studio-ai-description">
                {t('studio.aiDescription')}
              </p>
              <textarea
                className="studio-ai-input"
                placeholder={t('studio.aiPlaceholder')}
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                rows={4}
              />
              <button
                className="btn btn-primary"
                onClick={handleAIGenerate}
                disabled={!aiPrompt.trim() || isGenerating}
              >
                {isGenerating ? (
                  <>
                    <RefreshCw size={16} className="spin" />
                    {t('studio.generating')}
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    {t('studio.generateConcepts')}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="studio-status">
        <span>{t('studio.nodes')}: {Object.keys(mindmap.nodes).length}</span>
        <span>{t('studio.selected')}: {selectedNode ? mindmap.nodes[selectedNode].label : t('studio.none')}</span>
        <span>{t('studio.lastSaved')}: {new Date(mindmap.updatedAt).toLocaleTimeString()}</span>
      </div>
    </div>
  );
};

// Mindmap Node Component
interface MindmapNodeProps {
  node: MindmapNode;
  isSelected: boolean;
  isRoot: boolean;
  onClick: (e: React.MouseEvent) => void;
  onDrag: (deltaX: number, deltaY: number) => void;
}

const MindmapNodeComponent: React.FC<MindmapNodeProps> = ({
  node,
  isSelected,
  isRoot,
  onClick,
  onDrag
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const handleMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (isDragging) {
      const deltaX = e.clientX - dragStart.x;
      const deltaY = e.clientY - dragStart.y;
      onDrag(deltaX, deltaY);
      setDragStart({ x: e.clientX, y: e.clientY });
    }
  }, [isDragging, dragStart, onDrag]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const nodeWidth = isRoot ? 160 : 120;
  const nodeHeight = isRoot ? 48 : 36;

  return (
    <g
      className={`mindmap-node ${node.type} ${isSelected ? 'selected' : ''} ${isRoot ? 'root' : ''}`}
      transform={`translate(${node.x - nodeWidth / 2}, ${node.y - nodeHeight / 2})`}
      onClick={onClick}
      onMouseDown={handleMouseDown}
      style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
    >
      <rect
        className="mindmap-node-bg"
        width={nodeWidth}
        height={nodeHeight}
        rx={isRoot ? 12 : 8}
        fill={node.color || nodeColors[node.type]}
        stroke={isSelected ? '#FFF' : 'transparent'}
        strokeWidth={isSelected ? 3 : 0}
      />
      <text
        className="mindmap-node-label"
        x={nodeWidth / 2}
        y={nodeHeight / 2}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="white"
        fontSize={isRoot ? 14 : 12}
        fontWeight={isRoot ? 600 : 500}
      >
        {node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label}
      </text>
    </g>
  );
};

export default AIStudioPage;
