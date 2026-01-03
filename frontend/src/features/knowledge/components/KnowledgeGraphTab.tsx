// KnowledgeGraphTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors, KnowledgeGraphData } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import { defaultThemeColors, defaultCardStyle, defaultTabStyle } from '../utils/styleDefaults';

interface KnowledgeGraphTabProps {
  // State
  selectedDocuments: string[];
  kgQuery: string;
  selectedKG: KnowledgeGraphData | null;
  buildingKG: boolean;
  queryingKG: boolean;
  knowledgeGraphs: KnowledgeGraphData[];
  kgAnswer: string | null;

  // State setters
  setKgQuery: (query: string) => void;
  setSelectedKG: (kg: KnowledgeGraphData | null) => void;

  // Functions
  buildKnowledgeGraph: () => void;
  queryKnowledgeGraph: () => void;
  deleteKnowledgeGraph: (id: string) => void;
  getEntityColor: (entityType: string) => string;

  // Styles (optional - CSS classes used by default)
  themeColors?: ThemeColors;
  cardStyle?: React.CSSProperties;
  tabStyle?: (isActive: boolean) => React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const KnowledgeGraphTab: React.FC<KnowledgeGraphTabProps> = ({
  selectedDocuments,
  kgQuery,
  selectedKG,
  buildingKG,
  queryingKG,
  knowledgeGraphs,
  kgAnswer,
  setKgQuery,
  setSelectedKG,
  buildKnowledgeGraph,
  queryKnowledgeGraph,
  deleteKnowledgeGraph,
  getEntityColor,
  themeColors,
  cardStyle,
  tabStyle,
  t
}) => {
  // Use defaults when style props are not provided
  const actualThemeColors = themeColors || defaultThemeColors;
  const actualCardStyle = cardStyle || defaultCardStyle;
  const actualTabStyle = tabStyle || defaultTabStyle;

  return (
    <motion.div
      key="knowledge-graph"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      {/* Header */}
      <div style={actualCardStyle}>
        <h2 style={{ margin: 0 }}>Knowledge Graph</h2>
        <p style={{ color: actualThemeColors.textSecondary, margin: '8px 0 0' }}>
          {t('knowledge.knowledgeGraph.subtitle' as keyof import('../../../i18n/types').TranslationKeys, { count: selectedDocuments.length })}
        </p>
      </div>

      {/* Query Input & Actions */}
      <div style={{ ...cardStyle, display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <input
          type="text"
          value={kgQuery}
          onChange={(e) => setKgQuery(e.target.value)}
          placeholder={t('knowledge.knowledgeGraph.placeholder' as keyof import('../../../i18n/types').TranslationKeys)}
          style={{
            flex: 1,
            minWidth: '300px',
            padding: '12px 16px',
            background: 'rgba(255,255,255,0.1)',
            border: `1px solid ${actualThemeColors.cardBorder}`,
            borderRadius: '8px',
            color: actualThemeColors.text,
            fontSize: '16px'
          }}
          onKeyPress={(e) => e.key === 'Enter' && (selectedKG ? queryKnowledgeGraph() : buildKnowledgeGraph())}
        />
        <button
          onClick={buildKnowledgeGraph}
          disabled={buildingKG || !kgQuery.trim()}
          style={{
            padding: '12px 24px',
            background: '#2ECC71',
            color: '#fff',
            border: 'none',
            borderRadius: '8px',
            cursor: buildingKG || !kgQuery.trim() ? 'not-allowed' : 'pointer',
            opacity: buildingKG || !kgQuery.trim() ? 0.5 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          {buildingKG ? t('knowledge.knowledgeGraph.building' as keyof import('../../../i18n/types').TranslationKeys) : `🔗 ${t('knowledge.knowledgeGraph.createKG' as keyof import('../../../i18n/types').TranslationKeys)}`}
        </button>
        {selectedKG && (
          <button
            onClick={queryKnowledgeGraph}
            disabled={queryingKG || !kgQuery.trim()}
            style={{
              padding: '12px 24px',
              background: actualThemeColors.accent,
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              cursor: queryingKG || !kgQuery.trim() ? 'not-allowed' : 'pointer',
              opacity: queryingKG || !kgQuery.trim() ? 0.5 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            {queryingKG ? t('knowledge.knowledgeGraph.querying' as keyof import('../../../i18n/types').TranslationKeys) : `🔍 ${t('knowledge.knowledgeGraph.queryKG' as keyof import('../../../i18n/types').TranslationKeys)}`}
          </button>
        )}
      </div>

      {/* Main Content Area */}
      <div style={{ display: 'flex', gap: '16px', flex: 1 }}>
        {/* KG List Sidebar */}
        <div style={{ ...cardStyle, width: '250px', flexShrink: 0 }}>
          <h3 style={{ margin: '0 0 16px' }}>Knowledge Graphs</h3>
          {knowledgeGraphs.length === 0 ? (
            <div style={{ color: actualThemeColors.textSecondary, fontSize: '14px', textAlign: 'center', padding: '20px 0' }}>
              {t('knowledge.knowledgeGraph.noGraphs' as keyof import('../../../i18n/types').TranslationKeys)}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {knowledgeGraphs.map(kg => (
                <div
                  key={kg.id}
                  onClick={() => setSelectedKG(kg)}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    background: selectedKG?.id === kg.id ? 'rgba(74,144,217,0.2)' : 'rgba(255,255,255,0.05)',
                    border: selectedKG?.id === kg.id ? `2px solid ${actualThemeColors.accent}` : '1px solid transparent',
                    position: 'relative'
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>{kg.name}</div>
                  <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary }}>
                    {kg.entity_count} entities | {kg.relationship_count} relationships
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteKnowledgeGraph(kg.id);
                    }}
                    style={{
                      position: 'absolute',
                      top: '8px',
                      right: '8px',
                      background: 'transparent',
                      border: 'none',
                      color: '#E74C3C',
                      cursor: 'pointer',
                      fontSize: '14px',
                      padding: '4px'
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Graph Visualization */}
        <div style={{ ...cardStyle, flex: 1, display: 'flex', flexDirection: 'column' }}>
          {selectedKG ? (
            <>
              {/* KG Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                  <h3 style={{ margin: 0 }}>{selectedKG.name}</h3>
                  <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary, marginTop: '4px' }}>
                    {selectedKG.source_query && `Query: "${selectedKG.source_query}"`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <span style={{ padding: '4px 8px', background: 'rgba(46,204,113,0.2)', borderRadius: '4px', fontSize: '12px' }}>
                    {selectedKG.entity_count} Entities
                  </span>
                  <span style={{ padding: '4px 8px', background: 'rgba(74,144,217,0.2)', borderRadius: '4px', fontSize: '12px' }}>
                    {selectedKG.relationship_count} Relations
                  </span>
                </div>
              </div>

              {/* KG Answer */}
              {kgAnswer && (
                <div style={{
                  padding: '16px',
                  background: 'rgba(74,144,217,0.1)',
                  borderRadius: '8px',
                  marginBottom: '16px',
                  borderLeft: `4px solid ${actualThemeColors.accent}`
                }}>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>{t('knowledge.knowledgeGraph.aiAnswer' as keyof import('../../../i18n/types').TranslationKeys)}</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{kgAnswer}</div>
                </div>
              )}

              {/* Graph SVG Visualization */}
              <div style={{
                flex: 1,
                minHeight: '400px',
                background: 'rgba(0,0,0,0.2)',
                borderRadius: '8px',
                position: 'relative',
                overflow: 'hidden'
              }}>
                <svg width="100%" height="100%" style={{ display: 'block' }}>
                  <defs>
                    <marker
                      id="arrowhead"
                      markerWidth="10"
                      markerHeight="7"
                      refX="10"
                      refY="3.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 10 3.5, 0 7" fill={actualThemeColors.textSecondary} />
                    </marker>
                  </defs>

                  {/* Relationships (Edges) */}
                  {selectedKG.relationships.map((rel, idx) => {
                    const sourceEntity = selectedKG.entities.find(e => e.id === rel.source_id);
                    const targetEntity = selectedKG.entities.find(e => e.id === rel.target_id);
                    if (!sourceEntity || !targetEntity) return null;

                    // Calculate positions in a circular layout if not set
                    const entityCount = selectedKG.entities.length;
                    const sourceIndex = selectedKG.entities.findIndex(e => e.id === rel.source_id);
                    const targetIndex = selectedKG.entities.findIndex(e => e.id === rel.target_id);
                    const centerX = 400;
                    const centerY = 250;
                    const radius = Math.min(300, Math.max(150, entityCount * 20));

                    const sourceX = sourceEntity.x ?? (centerX + radius * Math.cos(2 * Math.PI * sourceIndex / entityCount));
                    const sourceY = sourceEntity.y ?? (centerY + radius * Math.sin(2 * Math.PI * sourceIndex / entityCount));
                    const targetX = targetEntity.x ?? (centerX + radius * Math.cos(2 * Math.PI * targetIndex / entityCount));
                    const targetY = targetEntity.y ?? (centerY + radius * Math.sin(2 * Math.PI * targetIndex / entityCount));

                    // Calculate midpoint for label
                    const midX = (sourceX + targetX) / 2;
                    const midY = (sourceY + targetY) / 2;

                    return (
                      <g key={rel.id || idx}>
                        <line
                          x1={sourceX}
                          y1={sourceY}
                          x2={targetX}
                          y2={targetY}
                          stroke={actualThemeColors.textSecondary}
                          strokeWidth={Math.max(1, rel.weight * 2)}
                          strokeOpacity={0.5}
                          markerEnd="url(#arrowhead)"
                        />
                        <text
                          x={midX}
                          y={midY - 5}
                          fill={actualThemeColors.textSecondary}
                          fontSize="10"
                          textAnchor="middle"
                          style={{ pointerEvents: 'none' }}
                        >
                          {rel.relation_type.replace(/_/g, ' ')}
                        </text>
                      </g>
                    );
                  })}

                  {/* Entities (Nodes) */}
                  {selectedKG.entities.map((entity, idx) => {
                    const entityCount = selectedKG.entities.length;
                    const centerX = 400;
                    const centerY = 250;
                    const radius = Math.min(300, Math.max(150, entityCount * 20));
                    const x = entity.x ?? (centerX + radius * Math.cos(2 * Math.PI * idx / entityCount));
                    const y = entity.y ?? (centerY + radius * Math.sin(2 * Math.PI * idx / entityCount));
                    const nodeRadius = 25 + (entity.confidence * 10);
                    const color = entity.color || getEntityColor(entity.entity_type);

                    return (
                      <g key={entity.id} style={{ cursor: 'pointer' }}>
                        {/* Node circle */}
                        <circle
                          cx={x}
                          cy={y}
                          r={nodeRadius}
                          fill={color}
                          fillOpacity={0.8}
                          stroke={color}
                          strokeWidth={2}
                        />
                        {/* Entity label */}
                        <text
                          x={x}
                          y={y + 4}
                          fill="#fff"
                          fontSize="11"
                          textAnchor="middle"
                          style={{ pointerEvents: 'none', fontWeight: 600 }}
                        >
                          {entity.label.length > 10 ? entity.label.substring(0, 10) + '...' : entity.label}
                        </text>
                        {/* Entity type badge */}
                        <text
                          x={x}
                          y={y + nodeRadius + 14}
                          fill={actualThemeColors.textSecondary}
                          fontSize="9"
                          textAnchor="middle"
                          style={{ pointerEvents: 'none' }}
                        >
                          {entity.entity_type}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {/* Legend */}
                <div style={{
                  position: 'absolute',
                  bottom: '12px',
                  left: '12px',
                  background: 'rgba(0,0,0,0.7)',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '8px',
                  maxWidth: '400px'
                }}>
                  {Array.from(new Set(selectedKG.entities.map(e => e.entity_type))).map(type => (
                    <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <div style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '50%',
                        background: getEntityColor(type)
                      }} />
                      <span style={{ fontSize: '10px', color: actualThemeColors.text }}>{type}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Entity/Relationship Details */}
              <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
                {/* Entities List */}
                <div style={{ flex: 1 }}>
                  <h4 style={{ margin: '0 0 8px' }}>Entities ({selectedKG.entity_count})</h4>
                  <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                    {selectedKG.entities.slice(0, 20).map(entity => (
                      <div
                        key={entity.id}
                        style={{
                          padding: '8px',
                          background: 'rgba(255,255,255,0.05)',
                          borderRadius: '6px',
                          marginBottom: '4px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px'
                        }}
                      >
                        <div style={{
                          width: '10px',
                          height: '10px',
                          borderRadius: '50%',
                          background: getEntityColor(entity.entity_type)
                        }} />
                        <span style={{ fontWeight: 500 }}>{entity.label}</span>
                        <span style={{ fontSize: '11px', color: actualThemeColors.textSecondary }}>
                          ({entity.entity_type})
                        </span>
                      </div>
                    ))}
                    {selectedKG.entities.length > 20 && (
                      <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary, padding: '8px' }}>
                        + {selectedKG.entities.length - 20} more entities
                      </div>
                    )}
                  </div>
                </div>

                {/* Relationships List */}
                <div style={{ flex: 1 }}>
                  <h4 style={{ margin: '0 0 8px' }}>Relationships ({selectedKG.relationship_count})</h4>
                  <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                    {selectedKG.relationships.slice(0, 20).map(rel => {
                      const source = selectedKG.entities.find(e => e.id === rel.source_id);
                      const target = selectedKG.entities.find(e => e.id === rel.target_id);
                      return (
                        <div
                          key={rel.id}
                          style={{
                            padding: '8px',
                            background: 'rgba(255,255,255,0.05)',
                            borderRadius: '6px',
                            marginBottom: '4px',
                            fontSize: '12px'
                          }}
                        >
                          <span style={{ fontWeight: 500 }}>{source?.label || '?'}</span>
                          <span style={{ color: actualThemeColors.accent, margin: '0 6px' }}>
                            → {rel.relation_type.replace(/_/g, ' ')} →
                          </span>
                          <span style={{ fontWeight: 500 }}>{target?.label || '?'}</span>
                        </div>
                      );
                    })}
                    {selectedKG.relationships.length > 20 && (
                      <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary, padding: '8px' }}>
                        + {selectedKG.relationships.length - 20} more relationships
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: actualThemeColors.textSecondary }}>
              <div style={{ fontSize: '64px', marginBottom: '16px' }}>🔗</div>
              <h3>{t('knowledge.knowledgeGraph.createPrompt.title' as keyof import('../../../i18n/types').TranslationKeys)}</h3>
              <p style={{ textAlign: 'center', maxWidth: '400px', marginTop: '8px' }}>
                {t('knowledge.knowledgeGraph.createPrompt.description' as keyof import('../../../i18n/types').TranslationKeys)}
              </p>
              <div style={{ display: 'flex', gap: '8px', marginTop: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
                {[
                  t('knowledge.knowledgeGraph.createPrompt.examples.example1' as keyof import('../../../i18n/types').TranslationKeys),
                  'Neo4j Knowledge Graph',
                  t('knowledge.knowledgeGraph.createPrompt.examples.example2' as keyof import('../../../i18n/types').TranslationKeys)
                ].map((example, i) => (
                  <button
                    key={i}
                    onClick={() => setKgQuery(example)}
                    style={{
                      ...actualTabStyle(false),
                      fontSize: '12px',
                      padding: '8px 12px'
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default KnowledgeGraphTab;
