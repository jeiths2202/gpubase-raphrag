import React, { useMemo, useCallback, useEffect } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  NodeTypes,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

import type { MindmapFull, MindmapNode as MindmapNodeType } from '../types/mindmap';
import MindmapNodeComponent from './MindmapNode';

interface MindmapViewerProps {
  mindmap: MindmapFull;
  selectedNodeId?: string;
  onNodeSelect: (node: MindmapNodeType | null) => void;
  onExpandNode: (nodeId: string) => void;
}

// Custom node types
const nodeTypes: NodeTypes = {
  mindmapNode: MindmapNodeComponent,
};

// Layout using dagre
const getLayoutedElements = (
  nodes: Node[],
  edges: Edge[],
  direction = 'TB'
): { nodes: Node[]; edges: Edge[] } => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 150;
  const nodeHeight = 50;

  const isHorizontal = direction === 'LR';
  dagreGraph.setGraph({ rankdir: direction, ranksep: 100, nodesep: 80 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
      targetPosition: isHorizontal ? 'left' : 'top',
      sourcePosition: isHorizontal ? 'right' : 'bottom',
    };
  });

  return { nodes: layoutedNodes as Node[], edges };
};

// Convert mindmap data to React Flow format
const convertToReactFlow = (
  mindmap: MindmapFull,
  selectedNodeId?: string
): { nodes: Node[]; edges: Edge[] } => {
  const nodes: Node[] = mindmap.data.nodes.map((node) => ({
    id: node.id,
    type: 'mindmapNode',
    position: { x: 0, y: 0 }, // Will be calculated by dagre
    data: {
      label: node.label,
      nodeType: node.type,
      description: node.description,
      importance: node.importance,
      color: node.color,
      size: node.size,
      isSelected: node.id === selectedNodeId,
      isRoot: node.type === 'root',
    },
    selected: node.id === selectedNodeId,
  }));

  const edges: Edge[] = mindmap.data.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label,
    animated: edge.relation === 'causes' || edge.relation === 'depends_on',
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: '#64748b',
    },
    style: {
      stroke: '#64748b',
      strokeWidth: Math.max(1, edge.strength * 3),
    },
    labelStyle: {
      fill: '#94a3b8',
      fontSize: 11,
    },
    labelBgStyle: {
      fill: '#1e293b',
      fillOpacity: 0.8,
    },
  }));

  return getLayoutedElements(nodes, edges, 'TB');
};

const MindmapViewer: React.FC<MindmapViewerProps> = ({
  mindmap,
  selectedNodeId,
  onNodeSelect,
  onExpandNode,
}) => {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => convertToReactFlow(mindmap, selectedNodeId),
    [mindmap, selectedNodeId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when mindmap changes
  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = convertToReactFlow(mindmap, selectedNodeId);
    setNodes(newNodes);
    setEdges(newEdges);
  }, [mindmap, selectedNodeId, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const mindmapNode = mindmap.data.nodes.find((n) => n.id === node.id);
      if (mindmapNode) {
        onNodeSelect(mindmapNode);
      }
    },
    [mindmap.data.nodes, onNodeSelect]
  );

  const handleNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onExpandNode(node.id);
    },
    [onExpandNode]
  );

  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: 'smoothstep',
        }}
      >
        <Controls
          position="bottom-left"
          style={{ marginBottom: '20px', marginLeft: '20px' }}
        />
        <MiniMap
          position="bottom-right"
          nodeColor={(node) => node.data?.color || '#3b82f6'}
          maskColor="rgba(15, 23, 42, 0.8)"
          style={{ marginBottom: '20px', marginRight: '20px' }}
        />
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#334155"
        />
      </ReactFlow>

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          top: '20px',
          left: '20px',
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
          borderRadius: '8px',
          padding: '12px',
          fontSize: '12px',
          zIndex: 5,
        }}
      >
        <div style={{ fontWeight: '600', marginBottom: '8px', color: 'var(--color-text-primary)' }}>
          Node Types
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {[
            { color: '#2563eb', label: 'Root' },
            { color: '#3b82f6', label: 'Concept' },
            { color: '#10b981', label: 'Entity' },
            { color: '#8b5cf6', label: 'Topic' },
            { color: '#f59e0b', label: 'Keyword' },
          ].map((item) => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: item.color,
                }}
              />
              <span style={{ color: 'var(--color-text-secondary)' }}>{item.label}</span>
            </div>
          ))}
        </div>
        <div style={{
          marginTop: '10px',
          paddingTop: '10px',
          borderTop: '1px solid var(--color-border)',
          color: 'var(--color-text-muted)',
          fontSize: '11px',
        }}>
          Double-click to expand
        </div>
      </div>
    </div>
  );
};

export default MindmapViewer;
