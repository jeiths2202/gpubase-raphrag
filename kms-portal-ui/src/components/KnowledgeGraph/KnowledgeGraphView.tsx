/**
 * KnowledgeGraphView - ReactFlow 기반 인터랙티브 그래프 뷰어
 * 재사용 가능: mini=true (RAG 인라인) / mini=false (풀 페이지)
 */
import React, { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
} from 'reactflow';
import 'reactflow/dist/style.css';
import EntityNode from './EntityNode';
import './KnowledgeGraph.css';

interface KnowledgeGraphViewProps {
  nodes: Node[];
  edges: Edge[];
  onNodeClick?: (nodeId: string, data: Record<string, unknown>) => void;
  mini?: boolean;
  height?: number | string;
}

const nodeTypes: NodeTypes = { entity: EntityNode };

const KnowledgeGraphView: React.FC<KnowledgeGraphViewProps> = ({
  nodes,
  edges,
  onNodeClick,
  mini = false,
  height = 400,
}) => {
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.id, node.data as Record<string, unknown>);
    },
    [onNodeClick],
  );

  const defaultEdgeOptions = useMemo(
    () => ({
      type: 'smoothstep' as const,
      style: { stroke: 'var(--color-border, #94a3b8)', strokeWidth: 1.5 },
    }),
    [],
  );

  if (!nodes.length) return null;

  return (
    <div className={`kg-view${mini ? ' kg-view--mini' : ''}`} style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={!mini}
        nodesConnectable={false}
        elementsSelectable={!mini}
      >
        <Background gap={mini ? 20 : 16} size={1} />
        {!mini && <Controls showInteractive={false} />}
        {!mini && (
          <MiniMap
            nodeStrokeWidth={3}
            pannable
            zoomable
            style={{ height: 100, width: 140 }}
          />
        )}
      </ReactFlow>
    </div>
  );
};

export default KnowledgeGraphView;
