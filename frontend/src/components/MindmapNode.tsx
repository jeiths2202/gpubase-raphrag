import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import type { NodeType } from '../types/mindmap';

interface MindmapNodeData {
  label: string;
  nodeType: NodeType;
  description?: string;
  importance: number;
  color?: string;
  size?: number;
  isSelected?: boolean;
  isRoot?: boolean;
}

const MindmapNodeComponent: React.FC<NodeProps<MindmapNodeData>> = ({ data }) => {
  const {
    label,
    nodeType,
    description,
    importance,
    color = '#818cf8',
    size = 30,
    isSelected = false,
    isRoot = false,
  } = data;

  // Calculate actual size based on importance
  const nodeSize = isRoot ? 80 : Math.max(40, size + importance * 30);
  const fontSize = isRoot ? 14 : Math.max(10, 10 + importance * 4);

  // Get border style based on node type
  const getBorderStyle = () => {
    switch (nodeType) {
      case 'root':
        return '3px solid white';
      case 'entity':
        return '2px dashed rgba(255, 255, 255, 0.5)';
      case 'topic':
        return '2px solid rgba(255, 255, 255, 0.3)';
      default:
        return 'none';
    }
  };

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}
    >
      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        style={{
          background: color,
          border: 'none',
          width: 8,
          height: 8,
          top: -4,
        }}
      />

      {/* Node Circle */}
      <div
        style={{
          width: nodeSize,
          height: nodeSize,
          borderRadius: '50%',
          background: `linear-gradient(135deg, ${color} 0%, ${adjustColor(color, -30)} 100%)`,
          border: getBorderStyle(),
          boxShadow: isSelected
            ? `0 0 0 3px rgba(255, 255, 255, 0.5), 0 4px 20px ${color}80`
            : `0 4px 12px rgba(0, 0, 0, 0.3)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'transform 0.2s, box-shadow 0.2s',
        }}
        title={description || label}
      >
        {isRoot && (
          <span style={{ fontSize: '24px' }}>🧠</span>
        )}
      </div>

      {/* Label */}
      <div
        style={{
          marginTop: 8,
          padding: '4px 8px',
          background: 'rgba(30, 41, 59, 0.95)',
          borderRadius: 4,
          maxWidth: 150,
          textAlign: 'center',
        }}
      >
        <span
          style={{
            fontSize: fontSize,
            fontWeight: isRoot ? 600 : 500,
            color: '#f1f5f9',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            wordBreak: 'break-word',
          }}
        >
          {label}
        </span>

        {/* Type badge */}
        {nodeType !== 'root' && nodeType !== 'concept' && (
          <div
            style={{
              marginTop: 4,
              fontSize: 9,
              color: color,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            {nodeType}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          background: color,
          border: 'none',
          width: 8,
          height: 8,
          bottom: -4,
        }}
      />
    </div>
  );
};

// Helper function to adjust color brightness
function adjustColor(color: string, amount: number): string {
  const clamp = (val: number) => Math.min(255, Math.max(0, val));

  // Remove # if present
  const hex = color.replace('#', '');

  // Parse RGB values
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);

  // Adjust and clamp
  const newR = clamp(r + amount);
  const newG = clamp(g + amount);
  const newB = clamp(b + amount);

  // Convert back to hex
  return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
}

export default memo(MindmapNodeComponent);
