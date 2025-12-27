import React, { useState } from 'react';
import type { MindmapInfo } from '../types/mindmap';
import { useTranslation } from '../hooks/useTranslation';

interface SidebarProps {
  mindmapList: MindmapInfo[];
  currentMindmapId?: string;
  onSelectMindmap: (id: string) => void;
  onDeleteMindmap: (id: string) => void;
  onGenerateMindmap: (options: {
    title?: string;
    maxNodes?: number;
    focusTopic?: string;
    documentIds?: string[];
  }) => void;
  isLoading: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({
  mindmapList,
  currentMindmapId,
  onSelectMindmap,
  onDeleteMindmap,
  onGenerateMindmap,
  isLoading,
}) => {
  const { t } = useTranslation();
  const [showGenerateForm, setShowGenerateForm] = useState(false);
  const [title, setTitle] = useState('');
  const [maxNodes, setMaxNodes] = useState(50);
  const [focusTopic, setFocusTopic] = useState('');

  const handleGenerate = () => {
    onGenerateMindmap({
      title: title || undefined,
      maxNodes,
      focusTopic: focusTopic || undefined,
    });
    setShowGenerateForm(false);
    setTitle('');
    setFocusTopic('');
  };

  return (
    <div
      style={{
        width: '280px',
        height: '100%',
        background: 'var(--color-bg-card)',
        borderRight: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '24px' }}>🧠</span>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: '600', color: 'var(--color-text-primary)' }}>
              {t('mindmap.sidebar.title')}
            </h2>
            <span style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
              {t('mindmap.sidebar.subtitle')}
            </span>
          </div>
        </div>
      </div>

      {/* Generate Section */}
      <div style={{ padding: '16px', borderBottom: '1px solid var(--color-border)' }}>
        {!showGenerateForm ? (
          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            onClick={() => setShowGenerateForm(true)}
            disabled={isLoading}
          >
            {t('mindmap.sidebar.newMindmap')}
          </button>
        ) : (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <input
              type="text"
              className="input"
              placeholder={t('mindmap.sidebar.titlePlaceholder')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />

            <input
              type="text"
              className="input"
              placeholder={t('mindmap.sidebar.focusPlaceholder')}
              value={focusTopic}
              onChange={(e) => setFocusTopic(e.target.value)}
            />

            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '12px',
                  color: 'var(--color-text-secondary)',
                  marginBottom: '4px',
                }}
              >
                {t('mindmap.sidebar.maxNodes')} {maxNodes}
              </label>
              <input
                type="range"
                min="10"
                max="100"
                value={maxNodes}
                onChange={(e) => setMaxNodes(parseInt(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-success"
                style={{ flex: 1 }}
                onClick={handleGenerate}
                disabled={isLoading}
              >
                {isLoading ? t('mindmap.sidebar.generating') : t('mindmap.sidebar.generate')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setShowGenerateForm(false)}
              >
                {t('mindmap.sidebar.cancel')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Mindmap List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px' }}>
        <div
          style={{
            fontSize: '12px',
            fontWeight: '600',
            color: 'var(--color-text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '12px',
          }}
        >
          {t('mindmap.sidebar.savedMindmaps')} ({mindmapList.length})
        </div>

        {mindmapList.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              padding: '24px',
              color: 'var(--color-text-muted)',
              fontSize: '13px',
            }}
          >
            {t('mindmap.sidebar.noMindmaps')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {mindmapList.map((mm) => (
              <div
                key={mm.id}
                className={`card ${mm.id === currentMindmapId ? 'selected' : ''}`}
                style={{
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  background:
                    mm.id === currentMindmapId
                      ? 'var(--color-primary)'
                      : 'var(--color-bg-dark)',
                  borderColor:
                    mm.id === currentMindmapId
                      ? 'var(--color-primary)'
                      : 'var(--color-border)',
                }}
                onClick={() => onSelectMindmap(mm.id)}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: '14px',
                        fontWeight: '500',
                        color: 'var(--color-text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {mm.title}
                    </div>
                    <div
                      style={{
                        fontSize: '12px',
                        color:
                          mm.id === currentMindmapId
                            ? 'rgba(255,255,255,0.8)'
                            : 'var(--color-text-muted)',
                        marginTop: '4px',
                      }}
                    >
                      {mm.node_count} nodes / {mm.edge_count} edges
                    </div>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(t('mindmap.sidebar.deleteConfirm'))) {
                        onDeleteMindmap(mm.id);
                      }
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--color-text-muted)',
                      cursor: 'pointer',
                      padding: '4px',
                      fontSize: '14px',
                      opacity: 0.6,
                      transition: 'opacity 0.2s',
                    }}
                    onMouseOver={(e) => (e.currentTarget.style.opacity = '1')}
                    onMouseOut={(e) => (e.currentTarget.style.opacity = '0.6')}
                  >
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--color-border)',
          fontSize: '11px',
          color: 'var(--color-text-muted)',
          textAlign: 'center',
        }}
      >
        KMS v1.0 - Powered by Neo4j & Nemotron
      </div>
    </div>
  );
};

export default Sidebar;
