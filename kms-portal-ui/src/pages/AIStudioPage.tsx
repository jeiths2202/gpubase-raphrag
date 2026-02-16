/**
 * AI Studio Page
 *
 * ReactFlow-based mindmap visualization with AI concept extraction
 * Integrated with backend mindmap API for knowledge graph exploration
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
  Wand2,
  Minimize2,
  GripHorizontal,
  FileText,
  Expand,
  Search,
  Loader2,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import {
  mindmapApi,
  MindmapFull,
  MindmapInfo,
  NodeDetailResponse,
  QueryNodeResponse,
  MindmapNode as ApiMindmapNode,
  NodeType as ApiNodeType,
} from '../api';
import './AIStudioPage.css';

// Storage key for AI panel position
const AI_PANEL_POSITION_KEY = 'kms-studio-ai-panel-position';

// Default panel position (right side)
const DEFAULT_PANEL_POSITION = { x: -500, y: 100 }; // Relative to right edge

interface PanelPosition {
  x: number;
  y: number;
}

// Load saved panel position from localStorage
const loadPanelPosition = (): PanelPosition => {
  try {
    const saved = localStorage.getItem(AI_PANEL_POSITION_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.warn('Failed to load panel position:', e);
  }
  return DEFAULT_PANEL_POSITION;
};

// Save panel position to localStorage
const savePanelPosition = (position: PanelPosition) => {
  try {
    localStorage.setItem(AI_PANEL_POSITION_KEY, JSON.stringify(position));
  } catch (e) {
    console.warn('Failed to save panel position:', e);
  }
};

// Node types for visualization
type VisualNodeType = 'concept' | 'topic' | 'detail' | 'question' | 'insight' | 'root' | 'entity' | 'keyword';

interface VisualizationNode {
  id: string;
  type: VisualNodeType;
  label: string;
  x: number;
  y: number;
  children: string[];
  parent: string | null;
  expanded: boolean;
  color?: string;
  description?: string;
  importance?: number;
}

interface VisualizationMindmap {
  id: string;
  title: string;
  nodes: Record<string, VisualizationNode>;
  rootId: string;
  createdAt: string;
  updatedAt: string;
}

// Node color mapping
const nodeColors: Record<VisualNodeType, string> = {
  root: '#6366F1',
  concept: '#6366F1',
  topic: '#8B5CF6',
  detail: '#64748B',
  question: '#F59E0B',
  insight: '#10B981',
  entity: '#EC4899',
  keyword: '#06B6D4',
};

// Map API node type to visual type
const mapNodeType = (apiType: ApiNodeType): VisualNodeType => {
  const typeMap: Record<ApiNodeType, VisualNodeType> = {
    root: 'root',
    concept: 'concept',
    entity: 'entity',
    topic: 'topic',
    keyword: 'keyword',
  };
  return typeMap[apiType] || 'concept';
};

// Get color for node type
const getColorForType = (type: VisualNodeType): string => {
  return nodeColors[type] || nodeColors.concept;
};

// Calculate radial layout positions for nodes
// Adds padding to ensure nodes don't get clipped at canvas edges
const calculateNodePositions = (
  nodes: ApiMindmapNode[],
  edges: { source: string; target: string }[],
  rootId: string | undefined,
  canvasWidth: number = 800,
  canvasHeight: number = 600
): Map<string, { x: number; y: number }> => {
  const positions = new Map<string, { x: number; y: number }>();

  if (nodes.length === 0) return positions;

  // Padding to prevent nodes from being clipped at edges
  const padding = 150;

  // Build adjacency list
  const adjacency = new Map<string, string[]>();
  nodes.forEach(n => adjacency.set(n.id, []));
  edges.forEach(e => {
    adjacency.get(e.source)?.push(e.target);
  });

  // Find root node (use provided rootId or first node)
  const root = rootId || nodes[0]?.id;
  if (!root) return positions;

  // BFS to assign levels
  const levels = new Map<string, number>();
  const queue: string[] = [root];
  levels.set(root, 0);

  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentLevel = levels.get(current)!;
    const children = adjacency.get(current) || [];

    children.forEach(child => {
      if (!levels.has(child)) {
        levels.set(child, currentLevel + 1);
        queue.push(child);
      }
    });
  }

  // Group nodes by level
  const nodesByLevel = new Map<number, string[]>();
  levels.forEach((level, nodeId) => {
    if (!nodesByLevel.has(level)) {
      nodesByLevel.set(level, []);
    }
    nodesByLevel.get(level)!.push(nodeId);
  });

  // Calculate the maximum level to determine required space
  const maxLevel = Math.max(...Array.from(levels.values()), 0);
  const levelRadius = 150;
  const requiredRadius = maxLevel * levelRadius + padding;

  // Position nodes radially with center adjusted for padding
  const centerX = Math.max(canvasWidth / 2, requiredRadius + padding);
  const centerY = Math.max(canvasHeight / 2, requiredRadius + padding);

  nodesByLevel.forEach((nodeIds, level) => {
    if (level === 0) {
      // Root at center
      positions.set(nodeIds[0], { x: centerX, y: centerY });
    } else {
      const radius = level * levelRadius;
      const angleStep = (2 * Math.PI) / nodeIds.length;
      const startAngle = -Math.PI / 2; // Start from top

      nodeIds.forEach((nodeId, index) => {
        const angle = startAngle + index * angleStep;
        positions.set(nodeId, {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        });
      });
    }
  });

  // Handle any nodes not reached by BFS (disconnected nodes)
  nodes.forEach((node, index) => {
    if (!positions.has(node.id)) {
      positions.set(node.id, {
        x: padding + 100 + (index % 5) * 150,
        y: padding + 100 + Math.floor(index / 5) * 100,
      });
    }
  });

  return positions;
};

// Convert API mindmap data to visualization format
const convertToVisualization = (data: MindmapFull): VisualizationMindmap => {
  const { nodes: apiNodes, edges: apiEdges, root_id } = data.data;

  // Calculate positions
  const positions = calculateNodePositions(
    apiNodes,
    apiEdges.map(e => ({ source: e.source, target: e.target })),
    root_id
  );

  // Build parent-child relationships
  const childrenMap = new Map<string, string[]>();
  const parentMap = new Map<string, string>();

  apiNodes.forEach(n => childrenMap.set(n.id, []));
  apiEdges.forEach(e => {
    childrenMap.get(e.source)?.push(e.target);
    if (!parentMap.has(e.target)) {
      parentMap.set(e.target, e.source);
    }
  });

  // Convert nodes
  const nodes: Record<string, VisualizationNode> = {};
  apiNodes.forEach(apiNode => {
    const pos = positions.get(apiNode.id) || { x: 400, y: 300 };
    const visualType = mapNodeType(apiNode.type);

    nodes[apiNode.id] = {
      id: apiNode.id,
      type: visualType,
      label: apiNode.label,
      x: apiNode.x ?? pos.x,
      y: apiNode.y ?? pos.y,
      children: childrenMap.get(apiNode.id) || [],
      parent: parentMap.get(apiNode.id) || null,
      expanded: true,
      color: apiNode.color || getColorForType(visualType),
      description: apiNode.description,
      importance: apiNode.importance,
    };
  });

  return {
    id: data.id,
    title: data.title,
    nodes,
    rootId: root_id || apiNodes[0]?.id || '',
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
};

// Learning LLM product options (15 main QLoRA adapters)
const PRODUCT_OPTIONS = [
  { value: 'openframe_base', label: 'OpenFrame Base' },
  { value: 'openframe_batch', label: 'OpenFrame Batch' },
  { value: 'openframe_common', label: 'OpenFrame Common' },
  { value: 'openframe_hidb', label: 'OpenFrame HIDB' },
  { value: 'openframe_osc', label: 'OpenFrame OSC' },
  { value: 'openframe_osi', label: 'OpenFrame OSI' },
  { value: 'openframe_tacf', label: 'OpenFrame TACF' },
  { value: 'openframe_vos3', label: 'OpenFrame VOS3' },
  { value: 'ofcobol', label: 'OF COBOL' },
  { value: 'ofpli', label: 'OF PLI' },
  { value: 'ofmanager', label: 'OF Manager' },
  { value: 'tmax', label: 'Tmax' },
  { value: 'tibero7', label: 'Tibero 7' },
  { value: 'protrieve', label: 'ProTrieve' },
  { value: 'prosort', label: 'ProSort' },
];

export const AIStudioPage: React.FC = () => {
  const { t, language } = useTranslation();

  // API data state
  const [currentMindmapData, setCurrentMindmapData] = useState<MindmapFull | null>(null);
  const [savedMindmaps, setSavedMindmaps] = useState<MindmapInfo[]>([]);
  const [selectedNodeDetail, setSelectedNodeDetail] = useState<NodeDetailResponse | null>(null);
  const [queryAnswer, setQueryAnswer] = useState<QueryNodeResponse | null>(null);

  // Visualization state (derived from API data)
  const [mindmap, setMindmap] = useState<VisualizationMindmap | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [showNodeEditor, setShowNodeEditor] = useState(false);
  const [editingLabel, setEditingLabel] = useState('');

  // Loading states
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExpanding, setIsExpanding] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // Error state
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Query input
  const [nodeQuery, setNodeQuery] = useState('');

  // AI Panel floating state
  const [aiPanelPosition, setAiPanelPosition] = useState<PanelPosition>(loadPanelPosition);
  const [isAiPanelMinimized, setIsAiPanelMinimized] = useState(false);
  const [isAiPanelDragging, setIsAiPanelDragging] = useState(false);
  const [aiPanelDragStart, setAiPanelDragStart] = useState({ x: 0, y: 0 });

  // Update visualization when API data changes
  useEffect(() => {
    if (currentMindmapData) {
      const visualization = convertToVisualization(currentMindmapData);
      setMindmap(visualization);
    } else {
      setMindmap(null);
    }
  }, [currentMindmapData]);

  // Load saved mindmaps on mount
  useEffect(() => {
    const loadMindmaps = async () => {
      try {
        const result = await mindmapApi.list(1, 50);
        setSavedMindmaps(result.mindmaps);
      } catch (error) {
        console.error('Failed to load mindmaps:', error);
      }
    };
    loadMindmaps();
  }, []);

  // Handle canvas mouse events for panning
  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
      setSelectedNode(null);
      setShowNodeEditor(false);
      setSelectedNodeDetail(null);
      setQueryAnswer(null);
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

  // Handle node selection with detail fetch
  const handleNodeClick = useCallback(async (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedNode(nodeId);
    setShowNodeEditor(true);
    setQueryAnswer(null);

    if (mindmap) {
      setEditingLabel(mindmap.nodes[nodeId]?.label || '');
    }

    // Fetch node detail from API
    if (currentMindmapData) {
      setIsLoadingDetail(true);
      try {
        const detail = await mindmapApi.getNodeDetail(currentMindmapData.id, nodeId);
        setSelectedNodeDetail(detail);
      } catch (error) {
        console.error('Failed to fetch node detail:', error);
        setSelectedNodeDetail(null);
      } finally {
        setIsLoadingDetail(false);
      }
    }
  }, [mindmap, currentMindmapData]);

  // Handle node drag
  const handleNodeDrag = useCallback((nodeId: string, deltaX: number, deltaY: number) => {
    setMindmap(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [nodeId]: {
            ...prev.nodes[nodeId],
            x: prev.nodes[nodeId].x + deltaX / zoom,
            y: prev.nodes[nodeId].y + deltaY / zoom
          }
        }
      };
    });
  }, [zoom]);

  // Zoom controls
  const handleZoomIn = () => setZoom(z => Math.min(z + 0.1, 2));
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.1, 0.5));
  const handleZoomReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // AI Panel drag handlers
  const handleAiPanelDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAiPanelDragging(true);
    setAiPanelDragStart({
      x: e.clientX - aiPanelPosition.x,
      y: e.clientY - aiPanelPosition.y
    });
  }, [aiPanelPosition]);

  const handleAiPanelDragMove = useCallback((e: MouseEvent) => {
    if (isAiPanelDragging) {
      const newX = e.clientX - aiPanelDragStart.x;
      const newY = e.clientY - aiPanelDragStart.y;

      // Constrain to viewport with some padding
      const constrainedX = Math.max(-window.innerWidth + 100, Math.min(newX, window.innerWidth - 100));
      const constrainedY = Math.max(60, Math.min(newY, window.innerHeight - 100));

      setAiPanelPosition({ x: constrainedX, y: constrainedY });
    }
  }, [isAiPanelDragging, aiPanelDragStart]);

  const handleAiPanelDragEnd = useCallback(() => {
    if (isAiPanelDragging) {
      setIsAiPanelDragging(false);
      savePanelPosition(aiPanelPosition);
    }
  }, [isAiPanelDragging, aiPanelPosition]);

  // AI Panel drag effect
  useEffect(() => {
    if (isAiPanelDragging) {
      window.addEventListener('mousemove', handleAiPanelDragMove);
      window.addEventListener('mouseup', handleAiPanelDragEnd);
      return () => {
        window.removeEventListener('mousemove', handleAiPanelDragMove);
        window.removeEventListener('mouseup', handleAiPanelDragEnd);
      };
    }
  }, [isAiPanelDragging, handleAiPanelDragMove, handleAiPanelDragEnd]);

  // Toggle AI Panel minimize
  const toggleAiPanelMinimize = useCallback(() => {
    setIsAiPanelMinimized(prev => !prev);
  }, []);

  // Add new node (local only - not saved to API)
  const handleAddNode = useCallback((type: VisualNodeType) => {
    if (!mindmap) return;

    const parentId = selectedNode || mindmap.rootId;
    const parent = mindmap.nodes[parentId];
    if (!parent) return;

    const newId = `node-local-${Date.now()}`;

    const newNode: VisualizationNode = {
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

    setMindmap(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [newId]: newNode,
          [parentId]: {
            ...prev.nodes[parentId],
            children: [...prev.nodes[parentId].children, newId]
          }
        }
      };
    });

    setSelectedNode(newId);
    setEditingLabel(t('studio.newNode'));
    setShowNodeEditor(true);
  }, [selectedNode, mindmap, t]);

  // Delete node
  const handleDeleteNode = useCallback(() => {
    if (!mindmap || !selectedNode || selectedNode === mindmap.rootId) return;

    const node = mindmap.nodes[selectedNode];
    const parentId = node.parent;

    // Recursively collect all descendant IDs
    const collectDescendants = (nodeId: string): string[] => {
      const n = mindmap.nodes[nodeId];
      if (!n) return [nodeId];
      return [nodeId, ...n.children.flatMap(collectDescendants)];
    };

    const toDelete = collectDescendants(selectedNode);

    setMindmap(prev => {
      if (!prev) return prev;
      const newNodes = { ...prev.nodes };
      toDelete.forEach(id => delete newNodes[id]);

      if (parentId && newNodes[parentId]) {
        newNodes[parentId] = {
          ...newNodes[parentId],
          children: newNodes[parentId].children.filter(id => id !== selectedNode)
        };
      }

      return { ...prev, nodes: newNodes };
    });

    setSelectedNode(null);
    setShowNodeEditor(false);
    setSelectedNodeDetail(null);
  }, [selectedNode, mindmap]);

  // Update node label
  const handleUpdateLabel = useCallback(() => {
    if (!selectedNode || !mindmap) return;

    setMindmap(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [selectedNode]: {
            ...prev.nodes[selectedNode],
            label: editingLabel
          }
        }
      };
    });
  }, [selectedNode, editingLabel, mindmap]);

  // AI Generate mindmap (real API call)
  const handleAIGenerate = useCallback(async () => {
    if (!aiPrompt.trim()) return;

    setIsGenerating(true);
    setGenerateError(null);

    try {
      const response = await mindmapApi.generate({
        focus_topic: aiPrompt.trim(),
        max_nodes: 30,
        depth: 3,
        language: language,  // Use user's current language setting
        product_id: selectedProduct || undefined,
      });

      setCurrentMindmapData(response.mindmap);
      setAiPrompt('');
      setShowAIPanel(false);

      // Refresh saved mindmaps list
      const result = await mindmapApi.list(1, 50);
      setSavedMindmaps(result.mindmaps);
    } catch (error: unknown) {
      console.error('Failed to generate mindmap:', error);
      // Extract error message from axios error response
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { data?: { detail?: string }, status?: number } };
        if (axiosError.response?.status === 400) {
          // No documents error - show user-friendly message
          setGenerateError(t('studio.noDocumentsError') || 'No documents found. Please upload documents to the knowledge base first.');
        } else {
          setGenerateError(axiosError.response?.data?.detail || 'Failed to generate mindmap');
        }
      } else {
        setGenerateError('Failed to generate mindmap');
      }
    } finally {
      setIsGenerating(false);
    }
  }, [aiPrompt, language, selectedProduct, t]);

  // Expand node (real API call)
  const handleExpandNode = useCallback(async () => {
    if (!selectedNode || !currentMindmapData) return;

    setIsExpanding(true);

    try {
      await mindmapApi.expandNode(currentMindmapData.id, {
        node_id: selectedNode,
        depth: 1,
        max_children: 5,
      });

      // Refresh the mindmap data
      const updated = await mindmapApi.get(currentMindmapData.id);
      setCurrentMindmapData(updated);
    } catch (error) {
      console.error('Failed to expand node:', error);
    } finally {
      setIsExpanding(false);
    }
  }, [selectedNode, currentMindmapData]);

  // Query node (real API call)
  const handleQueryNode = useCallback(async () => {
    if (!selectedNode || !currentMindmapData) return;

    setIsQuerying(true);

    try {
      const response = await mindmapApi.queryNode(currentMindmapData.id, {
        node_id: selectedNode,
        question: nodeQuery.trim() || undefined,
      });

      setQueryAnswer(response);
      setNodeQuery('');
    } catch (error) {
      console.error('Failed to query node:', error);
    } finally {
      setIsQuerying(false);
    }
  }, [selectedNode, currentMindmapData, nodeQuery]);

  // Load a saved mindmap
  const handleLoadMindmap = useCallback(async (mindmapId: string) => {
    try {
      const data = await mindmapApi.get(mindmapId);
      setCurrentMindmapData(data);
    } catch (error) {
      console.error('Failed to load mindmap:', error);
    }
  }, []);

  // Generate from all documents
  const handleGenerateFromAll = useCallback(async () => {
    setIsGenerating(true);

    try {
      const response = await mindmapApi.generateFromAllDocuments({
        max_nodes: 50,
        language: language,  // Use user's current UI language
        product_id: selectedProduct || undefined,
      });

      setCurrentMindmapData(response.mindmap);
      setShowAIPanel(false);

      // Refresh saved mindmaps list
      const result = await mindmapApi.list(1, 50);
      setSavedMindmaps(result.mindmaps);
    } catch (error) {
      console.error('Failed to generate mindmap from all documents:', error);
    } finally {
      setIsGenerating(false);
    }
  }, [language, selectedProduct]);

  // Render connections
  const renderConnections = () => {
    if (!mindmap) return null;

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
    if (!mindmap) return null;

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

  // Render empty state
  const renderEmptyState = () => (
    <div className="studio-empty-state">
      <div className="studio-empty-icon">
        <Brain size={64} />
      </div>
      <h2>{t('studio.emptyTitle') || 'No Mindmap Yet'}</h2>
      <p>{t('studio.emptyDescription') || 'Create a new mindmap from your knowledge base or focus on a specific topic.'}</p>
      <div className="studio-empty-actions">
        <button
          className="btn btn-primary btn-lg"
          onClick={() => setShowAIPanel(true)}
        >
          <Sparkles size={20} />
          {t('studio.createNew') || 'Create New Mindmap'}
        </button>
        {savedMindmaps.length > 0 && (
          <div className="studio-saved-mindmaps">
            <span className="studio-saved-label">{t('studio.orLoad') || 'Or load saved mindmap'}:</span>
            <div className="studio-saved-list">
              {savedMindmaps.slice(0, 5).map(mm => (
                <button
                  key={mm.id}
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleLoadMindmap(mm.id)}
                >
                  {mm.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="studio-page">
      {/* Header */}
      <div className="studio-header">
        <div className="studio-header-left">
          <Brain className="studio-icon" />
          <div className="studio-title-group">
            <h1 className="studio-title">{t('studio.title')}</h1>
            <span className="studio-subtitle">
              {mindmap?.title || t('studio.noMindmap') || 'No mindmap loaded'}
            </span>
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
          <button className="btn btn-ghost btn-sm" disabled={!mindmap}>
            <Save size={16} />
            {t('common.save')}
          </button>
          <button className="btn btn-ghost btn-sm" disabled={!mindmap}>
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
            disabled={!mindmap}
          >
            <Circle size={14} fill="#8B5CF6" stroke="#8B5CF6" />
            <span>{t('studio.nodeTypes.topic')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('detail')}
            title={t('studio.nodeTypes.detail')}
            disabled={!mindmap}
          >
            <Circle size={14} fill="#64748B" stroke="#64748B" />
            <span>{t('studio.nodeTypes.detail')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('question')}
            title={t('studio.nodeTypes.question')}
            disabled={!mindmap}
          >
            <Circle size={14} fill="#F59E0B" stroke="#F59E0B" />
            <span>{t('studio.nodeTypes.question')}</span>
          </button>
          <button
            className="studio-tool-btn"
            onClick={() => handleAddNode('insight')}
            title={t('studio.nodeTypes.insight')}
            disabled={!mindmap}
          >
            <Circle size={14} fill="#10B981" stroke="#10B981" />
            <span>{t('studio.nodeTypes.insight')}</span>
          </button>
        </div>

        <div className="studio-toolbar-group">
          <button
            className="studio-tool-btn"
            onClick={handleDeleteNode}
            disabled={!mindmap || !selectedNode || selectedNode === mindmap?.rootId}
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
        {!mindmap ? (
          renderEmptyState()
        ) : (
          (() => {
            // Calculate bounds of all nodes to create appropriate viewBox
            const nodeList = Object.values(mindmap.nodes);
            const viewBoxPadding = 120; // Extra padding around content
            const nodeHalfWidth = 80; // Half of max node width
            const nodeHalfHeight = 30; // Half of max node height

            // Default viewBox for empty or single node mindmaps
            if (nodeList.length === 0) {
              return (
                <svg
                  className="studio-svg"
                  viewBox="0 0 800 600"
                  preserveAspectRatio="xMidYMid meet"
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
              );
            }

            let minX = Infinity, maxX = -Infinity;
            let minY = Infinity, maxY = -Infinity;

            nodeList.forEach(node => {
              minX = Math.min(minX, node.x - nodeHalfWidth);
              maxX = Math.max(maxX, node.x + nodeHalfWidth);
              minY = Math.min(minY, node.y - nodeHalfHeight);
              maxY = Math.max(maxY, node.y + nodeHalfHeight);
            });

            // Ensure minimum dimensions and add padding
            const viewBoxX = minX - viewBoxPadding;
            const viewBoxY = minY - viewBoxPadding;
            const viewBoxWidth = Math.max(400, (maxX - minX) + viewBoxPadding * 2);
            const viewBoxHeight = Math.max(300, (maxY - minY) + viewBoxPadding * 2);

            return (
              <svg
                className="studio-svg"
                viewBox={`${viewBoxX} ${viewBoxY} ${viewBoxWidth} ${viewBoxHeight}`}
                preserveAspectRatio="xMidYMid meet"
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
            );
          })()
        )}

        {/* Node Editor Panel */}
        {showNodeEditor && selectedNode && mindmap && (
          <div className="studio-node-editor">
            <div className="studio-node-editor-header">
              <h3>{t('studio.editNode')}</h3>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowNodeEditor(false);
                  setSelectedNodeDetail(null);
                  setQueryAnswer(null);
                }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="studio-node-editor-body">
              {/* Node Label */}
              <label className="studio-editor-label">{t('studio.nodeLabel')}</label>
              <input
                type="text"
                className="input"
                value={editingLabel}
                onChange={(e) => setEditingLabel(e.target.value)}
                onBlur={handleUpdateLabel}
                onKeyDown={(e) => e.key === 'Enter' && handleUpdateLabel()}
              />

              {/* Node Info */}
              <div className="studio-node-info">
                <span>{t('studio.nodeType')}: {mindmap.nodes[selectedNode]?.type}</span>
              </div>

              {/* Description (from API) */}
              {selectedNodeDetail?.node?.description && (
                <div className="studio-node-description">
                  <label className="studio-editor-label">{t('studio.description') || 'Description'}</label>
                  <p>{selectedNodeDetail.node.description}</p>
                </div>
              )}

              {/* Loading indicator for node detail */}
              {isLoadingDetail && (
                <div className="studio-loading">
                  <Loader2 size={16} className="spin" />
                  <span>{t('common.loading') || 'Loading...'}</span>
                </div>
              )}

              {/* Related Concepts */}
              {selectedNodeDetail && selectedNodeDetail.connected_nodes.length > 0 && (
                <div className="studio-related-concepts">
                  <label className="studio-editor-label">
                    {t('studio.relatedConcepts') || 'Related Concepts'}
                  </label>
                  <div className="concept-tags">
                    {selectedNodeDetail.connected_nodes.slice(0, 8).map(node => (
                      <span
                        key={node.id}
                        className="concept-tag"
                        onClick={() => handleNodeClick(node.id, { stopPropagation: () => {} } as React.MouseEvent)}
                      >
                        {node.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Node Actions */}
              <div className="studio-node-actions">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleExpandNode}
                  disabled={isExpanding || !currentMindmapData}
                  title={t('studio.expandNode') || 'Expand this node'}
                >
                  {isExpanding ? (
                    <Loader2 size={14} className="spin" />
                  ) : (
                    <Expand size={14} />
                  )}
                  {t('studio.expand') || 'Expand'}
                </button>
              </div>

              {/* Query Section */}
              <div className="studio-query-section">
                <label className="studio-editor-label">
                  {t('studio.askAboutNode') || 'Ask about this concept'}
                </label>
                <div className="studio-query-input">
                  <input
                    type="text"
                    className="input"
                    placeholder={t('studio.queryPlaceholder') || 'Enter your question...'}
                    value={nodeQuery}
                    onChange={(e) => setNodeQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleQueryNode()}
                  />
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleQueryNode}
                    disabled={isQuerying || !currentMindmapData}
                  >
                    {isQuerying ? (
                      <Loader2 size={14} className="spin" />
                    ) : (
                      <Search size={14} />
                    )}
                  </button>
                </div>
              </div>

              {/* Query Answer */}
              {queryAnswer && (
                <div className="studio-answer-section">
                  <label className="studio-editor-label">
                    {t('studio.answer') || 'Answer'}
                  </label>
                  <div className="studio-answer-content">
                    {queryAnswer.answer}
                  </div>

                  {/* Related Concepts from Query */}
                  {queryAnswer.related_concepts.length > 0 && (
                    <div className="studio-query-related">
                      <span className="studio-related-label">
                        {t('studio.relatedTopics') || 'Related topics'}:
                      </span>
                      <div className="concept-tags">
                        {queryAnswer.related_concepts.map((concept, idx) => (
                          <span key={idx} className="concept-tag small">
                            {concept}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Sources */}
                  {queryAnswer.sources.length > 0 && (
                    <div className="studio-sources">
                      <span className="studio-sources-label">
                        <FileText size={12} />
                        {t('studio.sources') || 'Sources'}
                      </span>
                      <ul className="studio-sources-list">
                        {queryAnswer.sources.slice(0, 3).map((source, idx) => (
                          <li key={idx}>
                            {source.title || `Source ${idx + 1}`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Floating AI Generation Panel */}
        {showAIPanel && (
          <div
            className={`studio-ai-panel floating ${isAiPanelMinimized ? 'minimized' : ''} ${isAiPanelDragging ? 'dragging' : ''}`}
            style={{
              left: aiPanelPosition.x < 0 ? 'auto' : aiPanelPosition.x,
              right: aiPanelPosition.x < 0 ? Math.abs(aiPanelPosition.x) : 'auto',
              top: aiPanelPosition.y,
              transform: 'none'
            }}
          >
            {/* Drag Handle Header */}
            <div
              className="studio-ai-panel-header"
              onMouseDown={handleAiPanelDragStart}
            >
              <div className="studio-ai-panel-drag-handle">
                <GripHorizontal size={16} />
              </div>
              <Wand2 className="studio-ai-icon" />
              <h3>{t('studio.aiAssistant')}</h3>
              <div className="studio-ai-panel-actions">
                <button
                  className="btn btn-ghost btn-xs"
                  onClick={toggleAiPanelMinimize}
                  title={isAiPanelMinimized ? 'Expand' : 'Minimize'}
                >
                  {isAiPanelMinimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
                </button>
                <button
                  className="btn btn-ghost btn-xs"
                  onClick={() => setShowAIPanel(false)}
                  title="Close"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Collapsible Body */}
            {!isAiPanelMinimized && (
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
                <select
                  className="studio-ai-select"
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    marginBottom: '8px',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color, #e2e8f0)',
                    background: 'var(--bg-secondary, #f8fafc)',
                    color: 'var(--text-primary, #334155)',
                    fontSize: '13px',
                  }}
                >
                  <option value="">{t('mindmap.sidebar.productPlaceholder')}</option>
                  {PRODUCT_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                {selectedProduct && (
                  <div style={{
                    fontSize: '12px',
                    color: '#10b981',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}>
                    <Sparkles size={12} />
                    {t('mindmap.sidebar.learningLlmActive')}
                  </div>
                )}
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

                {generateError && (
                  <div className="studio-error-message">
                    {generateError}
                  </div>
                )}

                <div className="studio-ai-divider">
                  <span>{t('common.or') || 'or'}</span>
                </div>

                <button
                  className="btn btn-secondary"
                  onClick={handleGenerateFromAll}
                  disabled={isGenerating}
                >
                  {isGenerating ? (
                    <>
                      <RefreshCw size={16} className="spin" />
                      {t('studio.generating')}
                    </>
                  ) : (
                    <>
                      <Brain size={16} />
                      {t('studio.generateFromAll') || 'Generate from All Documents'}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

      </div>

      {/* Status Bar */}
      <div className="studio-status">
        <span>
          {t('studio.nodes')}: {mindmap ? Object.keys(mindmap.nodes).length : 0}
        </span>
        <span>
          {t('studio.selected')}: {selectedNode && mindmap ? mindmap.nodes[selectedNode]?.label : t('studio.none')}
        </span>
        <span>
          {t('studio.lastSaved')}: {mindmap ? new Date(mindmap.updatedAt).toLocaleTimeString() : '-'}
        </span>
      </div>
    </div>
  );
};

// Mindmap Node Component
interface MindmapNodeProps {
  node: VisualizationNode;
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
