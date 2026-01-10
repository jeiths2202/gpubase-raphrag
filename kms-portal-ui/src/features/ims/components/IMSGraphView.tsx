/**
 * IMS Graph View Component
 *
 * Force-directed graph visualization for issue relationships
 */

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import type { IMSIssue, IssuePriority, GraphNode, GraphLink } from '../types';

interface IMSGraphViewProps {
  issues: IMSIssue[];
  onIssueClick?: (issue: IMSIssue) => void;
  t: (key: string) => string;
}

const PRIORITY_COLORS: Record<IssuePriority, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  trivial: '#94a3b8',
};

const LINK_COLORS: Record<string, string> = {
  similarity: '#3b82f6',
  project: '#22c55e',
  label: '#f97316',
};

export const IMSGraphView: React.FC<IMSGraphViewProps> = ({ issues, onIssueClick, t }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const animationRef = useRef<number>();

  // Deduplicate issues by ID to prevent React key warnings
  const uniqueIssues = React.useMemo(() => {
    const uniqueMap = new Map<string, IMSIssue>();
    issues.forEach(issue => {
      if (!uniqueMap.has(issue.id)) {
        uniqueMap.set(issue.id, issue);
      }
    });
    return Array.from(uniqueMap.values());
  }, [issues]);

  // Initialize graph data
  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight || 500;

    // Create nodes
    const newNodes: GraphNode[] = uniqueIssues.map((issue) => ({
      id: issue.id,
      x: width / 2 + (Math.random() - 0.5) * width * 0.8,
      y: height / 2 + (Math.random() - 0.5) * height * 0.8,
      vx: 0,
      vy: 0,
      issue,
      color: PRIORITY_COLORS[issue.priority] || '#94a3b8',
    }));

    // Create links based on relationships
    const newLinks: GraphLink[] = [];

    // Build a map of ims_id -> issue for quick lookup
    const imsIdToIssue = new Map<string, IMSIssue>();
    uniqueIssues.forEach((issue) => {
      imsIdToIssue.set(issue.ims_id, issue);
    });

    // Create links from related_issue_ids (actual IMS relationships)
    for (const issue of uniqueIssues) {
      if (issue.related_issue_ids && issue.related_issue_ids.length > 0) {
        for (const relatedImsId of issue.related_issue_ids) {
          const relatedIssue = imsIdToIssue.get(relatedImsId);
          if (relatedIssue && relatedIssue.id !== issue.id) {
            // Check if link already exists (avoid duplicates)
            const linkExists = newLinks.some(
              (link) =>
                (link.source === issue.id && link.target === relatedIssue.id) ||
                (link.source === relatedIssue.id && link.target === issue.id)
            );
            if (!linkExists) {
              newLinks.push({
                source: issue.id,
                target: relatedIssue.id,
                type: 'project', // Use 'project' type for related issues (green color)
                strength: 0.5, // Strong connection for actual relations
              });
            }
          }
        }
      }
    }

    // Additional links for similarity scores (if no direct relationship exists)
    for (let i = 0; i < uniqueIssues.length; i++) {
      for (let j = i + 1; j < uniqueIssues.length; j++) {
        const issueA = uniqueIssues[i];
        const issueB = uniqueIssues[j];

        // Skip if already linked via related_issue_ids
        const alreadyLinked = newLinks.some(
          (link) =>
            (link.source === issueA.id && link.target === issueB.id) ||
            (link.source === issueB.id && link.target === issueA.id)
        );

        if (!alreadyLinked) {
          // Similarity link (if both have similar scores)
          if (
            issueA.similarity_score &&
            issueB.similarity_score &&
            Math.abs(issueA.similarity_score - issueB.similarity_score) < 0.15
          ) {
            newLinks.push({
              source: issueA.id,
              target: issueB.id,
              type: 'similarity',
              strength: 0.3,
            });
          }

          // Shared labels link
          const sharedLabels = issueA.labels?.filter((l) => issueB.labels?.includes(l));
          if (sharedLabels && sharedLabels.length > 0) {
            newLinks.push({
              source: issueA.id,
              target: issueB.id,
              type: 'label',
              strength: 0.2 * sharedLabels.length,
            });
          }
        }
      }
    }

    setNodes(newNodes);
    setLinks(newLinks);
  }, [uniqueIssues]);

  // Force simulation
  const simulate = useCallback(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight || 500;
    const centerX = width / 2;
    const centerY = height / 2;

    setNodes((prevNodes) => {
      const newNodes = prevNodes.map((node) => ({ ...node }));

      // Apply forces
      for (const node of newNodes) {
        // Center attraction
        node.vx += (centerX - node.x) * 0.001;
        node.vy += (centerY - node.y) * 0.001;

        // Node repulsion
        for (const other of newNodes) {
          if (node.id === other.id) continue;
          const dx = node.x - other.x;
          const dy = node.y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 1000 / (dist * dist);
          node.vx += (dx / dist) * force;
          node.vy += (dy / dist) * force;
        }
      }

      // Apply link forces
      for (const link of links) {
        const source = newNodes.find((n) => n.id === link.source);
        const target = newNodes.find((n) => n.id === link.target);
        if (!source || !target) continue;

        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const targetDist = 150;
        const force = (dist - targetDist) * link.strength * 0.01;

        source.vx += (dx / dist) * force;
        source.vy += (dy / dist) * force;
        target.vx -= (dx / dist) * force;
        target.vy -= (dy / dist) * force;
      }

      // Update positions with velocity decay
      for (const node of newNodes) {
        node.vx *= 0.9;
        node.vy *= 0.9;
        node.x += node.vx;
        node.y += node.vy;

        // Boundary constraints
        node.x = Math.max(30, Math.min(width - 30, node.x));
        node.y = Math.max(30, Math.min(height - 30, node.y));
      }

      return newNodes;
    });
  }, [links]);

  // Animation loop
  useEffect(() => {
    const animate = () => {
      simulate();
      animationRef.current = requestAnimationFrame(animate);
    };
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [simulate]);

  // Draw graph
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight || 500;
    canvas.width = width * window.devicePixelRatio;
    canvas.height = height * window.devicePixelRatio;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Apply zoom
    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-width / 2, -height / 2);

    // Draw links
    for (const link of links) {
      const source = nodes.find((n) => n.id === link.source);
      const target = nodes.find((n) => n.id === link.target);
      if (!source || !target) continue;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.strokeStyle = LINK_COLORS[link.type] || '#666';
      ctx.globalAlpha = 0.3;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // Draw nodes
    for (const node of nodes) {
      const isSelected = selectedNode === node.id;
      const isHovered = hoveredNode === node.id;
      const radius = isSelected || isHovered ? 12 : 8;

      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = node.color;
      ctx.fill();

      if (isSelected || isHovered) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw label
        ctx.fillStyle = '#fff';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(node.issue.ims_id, node.x, node.y - 18);
      }
    }

    ctx.restore();
  }, [nodes, links, zoom, selectedNode, hoveredNode]);

  // Handle canvas click
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - container.clientWidth / 2) / zoom + container.clientWidth / 2;
    const y = (e.clientY - rect.top - (container.clientHeight || 500) / 2) / zoom + (container.clientHeight || 500) / 2;

    for (const node of nodes) {
      const dx = node.x - x;
      const dy = node.y - y;
      if (dx * dx + dy * dy < 144) {
        setSelectedNode(node.id);
        onIssueClick?.(node.issue);
        return;
      }
    }
    setSelectedNode(null);
  };

  // Handle mouse move for hover
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - container.clientWidth / 2) / zoom + container.clientWidth / 2;
    const y = (e.clientY - rect.top - (container.clientHeight || 500) / 2) / zoom + (container.clientHeight || 500) / 2;

    for (const node of nodes) {
      const dx = node.x - x;
      const dy = node.y - y;
      if (dx * dx + dy * dy < 144) {
        setHoveredNode(node.id);
        canvas.style.cursor = 'pointer';
        return;
      }
    }
    setHoveredNode(null);
    canvas.style.cursor = 'default';
  };

  return (
    <div className="ims-graph" ref={containerRef}>
      {/* Controls */}
      <div className="ims-graph__controls">
        <button onClick={() => setZoom((z) => Math.min(z + 0.2, 3))} title="Zoom In">
          <ZoomIn size={18} />
        </button>
        <button onClick={() => setZoom((z) => Math.max(z - 0.2, 0.5))} title="Zoom Out">
          <ZoomOut size={18} />
        </button>
        <button onClick={() => setZoom(1)} title="Reset">
          <Maximize2 size={18} />
        </button>
      </div>

      {/* Legend */}
      <div className="ims-graph__legend">
        <div className="ims-graph__legend-title">{t('ims.graph.legend')}</div>
        <div className="ims-graph__legend-item">
          <span className="ims-graph__legend-line" style={{ background: LINK_COLORS.similarity }} />
          {t('ims.graph.similarity')}
        </div>
        <div className="ims-graph__legend-item">
          <span className="ims-graph__legend-line" style={{ background: LINK_COLORS.project }} />
          {t('ims.graph.relatedIssue')}
        </div>
        <div className="ims-graph__legend-item">
          <span className="ims-graph__legend-line" style={{ background: LINK_COLORS.label }} />
          {t('ims.graph.sharedLabels')}
        </div>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        className="ims-graph__canvas"
        onClick={handleCanvasClick}
        onMouseMove={handleMouseMove}
      />
    </div>
  );
};

export default IMSGraphView;
