/**
 * IMS Graph View Component
 * D3.js-based force-directed graph for visualizing issue relationships
 */

import React, { useEffect, useRef, useState } from 'react';
import type { IMSIssue } from './IMSTableView';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  issues: IMSIssue[];
  t: TranslateFunction;
  onIssueClick?: (issue: IMSIssue) => void;
}

interface GraphNode {
  id: string;
  issue: IMSIssue;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: 'similarity' | 'related' | 'project';
  value: number;
}

export const IMSGraphView: React.FC<Props> = ({ issues, t, onIssueClick }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);

  useEffect(() => {
    if (!svgRef.current || issues.length === 0) return;

    // Clear previous graph
    const svg = svgRef.current;
    while (svg.firstChild) {
      svg.removeChild(svg.firstChild);
    }

    const width = svg.clientWidth;
    const height = svg.clientHeight;

    // Create nodes
    const nodes: GraphNode[] = issues.map(issue => ({
      id: issue.id,
      issue
    }));

    // Create links based on similarity and relationships
    const links: GraphLink[] = [];

    // Add similarity-based links
    for (let i = 0; i < issues.length; i++) {
      for (let j = i + 1; j < issues.length; j++) {
        const issue1 = issues[i];
        const issue2 = issues[j];

        // Link by similarity score if available
        if (issue1.similarity_score && issue2.similarity_score) {
          const avgScore = (issue1.similarity_score + issue2.similarity_score) / 2;
          if (avgScore > 0.7) {
            links.push({
              source: issue1.id,
              target: issue2.id,
              type: 'similarity',
              value: avgScore
            });
          }
        }

        // Link by same project
        if (issue1.project_key === issue2.project_key) {
          links.push({
            source: issue1.id,
            target: issue2.id,
            type: 'project',
            value: 0.5
          });
        }

        // Link by shared labels
        const sharedLabels = issue1.labels.filter(l => issue2.labels.includes(l));
        if (sharedLabels.length > 0) {
          links.push({
            source: issue1.id,
            target: issue2.id,
            type: 'related',
            value: sharedLabels.length * 0.3
          });
        }
      }
    }

    // Create SVG elements
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    svg.appendChild(g);

    // Create links
    const linkElements = links.map(link => {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('stroke', getLinkColor(link.type));
      line.setAttribute('stroke-opacity', '0.4');
      line.setAttribute('stroke-width', String(link.value * 3));
      g.appendChild(line);
      return { element: line, data: link };
    });

    // Create node groups
    const nodeElements = nodes.map(node => {
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.setAttribute('cursor', 'pointer');

      // Circle
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('r', '12');
      circle.setAttribute('fill', getNodeColor(node.issue));
      circle.setAttribute('stroke', '#fff');
      circle.setAttribute('stroke-width', '2');
      group.appendChild(circle);

      // Label
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('font-size', '10');
      text.setAttribute('dy', '-15');
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', 'var(--text)');
      text.textContent = node.issue.ims_id;
      group.appendChild(text);

      g.appendChild(group);

      // Event listeners
      group.addEventListener('click', () => {
        setSelectedNode(node.id);
        if (onIssueClick) {
          onIssueClick(node.issue);
        }
      });

      group.addEventListener('mouseenter', () => {
        circle.setAttribute('r', '16');
        circle.setAttribute('stroke-width', '3');
      });

      group.addEventListener('mouseleave', () => {
        circle.setAttribute('r', '12');
        circle.setAttribute('stroke-width', '2');
      });

      return { element: group, data: node };
    });

    // Simple force simulation (lightweight alternative to D3)
    const simulation = {
      nodes,
      links: links.map(l => ({
        ...l,
        source: nodes.find(n => n.id === l.source)!,
        target: nodes.find(n => n.id === l.target)!
      })),
      alpha: 1,
      alphaDecay: 0.02,
      velocityDecay: 0.4
    };

    // Initialize positions
    nodes.forEach((node, i) => {
      const angle = (i / nodes.length) * 2 * Math.PI;
      const radius = Math.min(width, height) / 3;
      node.x = width / 2 + radius * Math.cos(angle);
      node.y = height / 2 + radius * Math.sin(angle);
      node.vx = 0;
      node.vy = 0;
    });

    // Animation loop
    let frameId: number;
    const tick = () => {
      if (simulation.alpha < 0.01) return;

      simulation.alpha *= (1 - simulation.alphaDecay);

      // Apply forces
      nodes.forEach(node => {
        // Center force
        const centerX = width / 2;
        const centerY = height / 2;
        node.vx = (node.vx || 0) + (centerX - (node.x || 0)) * 0.01;
        node.vy = (node.vy || 0) + (centerY - (node.y || 0)) * 0.01;

        // Collision force
        nodes.forEach(other => {
          if (node === other) return;
          const dx = (other.x || 0) - (node.x || 0);
          const dy = (other.y || 0) - (node.y || 0);
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 50) {
            const force = (50 - dist) / dist;
            node.vx = (node.vx || 0) - dx * force * 0.1;
            node.vy = (node.vy || 0) - dy * force * 0.1;
          }
        });
      });

      // Link force
      simulation.links.forEach(link => {
        const source = link.source as GraphNode;
        const target = link.target as GraphNode;
        const dx = (target.x || 0) - (source.x || 0);
        const dy = (target.y || 0) - (source.y || 0);
        const dist = Math.sqrt(dx * dx + dy * dy);
        const targetDist = 100;
        const force = (dist - targetDist) / dist * 0.1 * link.value;

        source.vx = (source.vx || 0) + dx * force;
        source.vy = (source.vy || 0) + dy * force;
        target.vx = (target.vx || 0) - dx * force;
        target.vy = (target.vy || 0) - dy * force;
      });

      // Update positions
      nodes.forEach(node => {
        node.vx = (node.vx || 0) * simulation.velocityDecay;
        node.vy = (node.vy || 0) * simulation.velocityDecay;
        node.x = (node.x || 0) + (node.vx || 0);
        node.y = (node.y || 0) + (node.vy || 0);

        // Boundaries
        const margin = 20;
        node.x = Math.max(margin, Math.min(width - margin, node.x));
        node.y = Math.max(margin, Math.min(height - margin, node.y));
      });

      // Update DOM
      linkElements.forEach(({ element, data }) => {
        const source = simulation.links.find(l => l === data)?.source as GraphNode;
        const target = simulation.links.find(l => l === data)?.target as GraphNode;
        if (source && target) {
          element.setAttribute('x1', String(source.x));
          element.setAttribute('y1', String(source.y));
          element.setAttribute('x2', String(target.x));
          element.setAttribute('y2', String(target.y));
        }
      });

      nodeElements.forEach(({ element, data }) => {
        element.setAttribute('transform', `translate(${data.x}, ${data.y})`);
      });

      frameId = requestAnimationFrame(tick);
    };

    tick();

    return () => {
      if (frameId) cancelAnimationFrame(frameId);
    };
  }, [issues, onIssueClick]);

  const getNodeColor = (issue: IMSIssue): string => {
    switch (issue.priority.toUpperCase()) {
      case 'CRITICAL': return '#dc2626';
      case 'HIGH': return '#f59e0b';
      case 'MEDIUM': return '#3b82f6';
      case 'LOW': return '#10b981';
      default: return '#6b7280';
    }
  };

  const getLinkColor = (type: string): string => {
    switch (type) {
      case 'similarity': return '#6366f1';
      case 'project': return '#10b981';
      case 'related': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{ width: '100%', height: '600px', position: 'relative' }}>
      {/* Controls */}
      <div style={{
        position: 'absolute',
        top: '16px',
        right: '16px',
        zIndex: 10,
        display: 'flex',
        gap: '8px'
      }}>
        <button
          onClick={() => setZoomLevel(prev => Math.min(prev + 0.2, 3))}
          style={{
            padding: '8px 12px',
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          +
        </button>
        <button
          onClick={() => setZoomLevel(prev => Math.max(prev - 0.2, 0.5))}
          style={{
            padding: '8px 12px',
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          −
        </button>
      </div>

      {/* Legend */}
      <div style={{
        position: 'absolute',
        bottom: '16px',
        left: '16px',
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '12px',
        fontSize: '12px',
        zIndex: 10
      }}>
        <div style={{ fontWeight: 600, marginBottom: '8px' }}>Legend</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '20px', height: '3px', background: '#6366f1' }} />
            <span>Similarity</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '20px', height: '3px', background: '#10b981' }} />
            <span>Same Project</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '20px', height: '3px', background: '#f59e0b' }} />
            <span>Related</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        style={{
          width: '100%',
          height: '100%',
          background: 'var(--input-bg)',
          borderRadius: '12px',
          border: '1px solid var(--border)',
          transform: `scale(${zoomLevel})`,
          transformOrigin: 'center',
          transition: 'transform 0.2s'
        }}
      />

      {issues.length === 0 && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
          color: 'var(--text-secondary)'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>🕸️</div>
          <div style={{ fontSize: '16px', fontWeight: 500 }}>No issues to visualize</div>
        </div>
      )}
    </div>
  );
};
