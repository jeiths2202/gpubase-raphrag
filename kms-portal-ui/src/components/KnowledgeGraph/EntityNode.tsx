/**
 * EntityNode - ReactFlow 커스텀 노드
 * EntityType별 색상/아이콘으로 시각화
 */
import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import {
  Terminal,
  AlertTriangle,
  Settings,
  Workflow,
  Cpu,
  Circle,
  BookOpen,
  Tag,
  Zap,
  User,
  Building2,
  FileText,
} from 'lucide-react';

interface EntityNodeData {
  label: string;
  entityType: string;
  color: string;
  primary?: boolean;
  properties?: Record<string, unknown>;
}

const ICON_MAP: Record<string, React.FC<{ size?: string | number }>> = {
  command: Terminal,
  error_code: AlertTriangle,
  config: Settings,
  product: Workflow,
  technology: Cpu,
  concept: Circle,
  term: BookOpen,
  topic: Tag,
  process: Zap,
  person: User,
  organization: Building2,
  document: FileText,
};

const EntityNode: React.FC<NodeProps<EntityNodeData>> = ({ data, selected }) => {
  const Icon = ICON_MAP[data.entityType] || Circle;

  return (
    <div
      className={`kg-entity-node${data.primary ? ' kg-entity-node--primary' : ''}${selected ? ' kg-entity-node--selected' : ''}`}
      style={{ borderColor: data.color }}
    >
      <Handle type="target" position={Position.Top} className="kg-handle" />
      <div className="kg-entity-icon" style={{ color: data.color }}>
        <Icon size={14} />
      </div>
      <div className="kg-entity-label" title={data.label}>
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} className="kg-handle" />
    </div>
  );
};

export default memo(EntityNode);
