// ProjectsTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors, Project } from '../types';
import { TranslateFunction } from '../../../i18n/types';

interface ProjectsTabProps {
  // State
  projects: Project[];
  selectedProject: Project | null;

  // State setters
  setSelectedProject: (project: Project | null) => void;

  // Functions
  createProject: (name: string, description: string) => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  tabStyle: (isActive: boolean) => React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const ProjectsTab: React.FC<ProjectsTabProps> = ({
  projects,
  selectedProject,
  setSelectedProject,
  createProject,
  themeColors,
  cardStyle,
  tabStyle,
  t
}) => {
  return (
    <motion.div
      key="projects"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1 }}
    >
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>Projects</h2>
          <button
            onClick={() => {
              const name = prompt(t('knowledge.projects.projectName' as keyof import('../../../i18n/types').TranslationKeys));
              if (name) createProject(name, '');
            }}
            style={tabStyle(true)}
          >
            + New Project
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px', marginTop: '20px' }}>
          {projects.map(project => (
            <div
              key={project.id}
              onClick={() => setSelectedProject(project)}
              style={{
                ...cardStyle,
                cursor: 'pointer',
                border: selectedProject?.id === project.id
                  ? `2px solid ${themeColors.accent}`
                  : `1px solid ${themeColors.cardBorder}`
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '8px',
                  background: project.color || themeColors.accent,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '20px'
                }}>
                  📁
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>{project.name}</div>
                  <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                    {project.document_count} docs | {project.note_count} notes
                  </div>
                </div>
              </div>
              {project.description && (
                <div style={{ marginTop: '12px', fontSize: '14px', color: themeColors.textSecondary }}>
                  {project.description}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

export default ProjectsTab;
