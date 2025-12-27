// Theme Utility Functions
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import type { ThemeType, ThemeColors } from '../types';

export const getThemeColors = (theme: ThemeType): ThemeColors => {
  return theme === 'dark' ? {
    bg: 'linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%)',
    cardBg: 'rgba(255,255,255,0.05)',
    cardBorder: 'rgba(255,255,255,0.1)',
    text: '#fff',
    textSecondary: 'rgba(255,255,255,0.7)',
    accent: '#4A90D9',
    accentHover: '#357ABD'
  } : {
    bg: 'linear-gradient(135deg, #f5f7fa 0%, #e4e9f2 50%, #d3dce6 100%)',
    cardBg: 'rgba(255,255,255,0.8)',
    cardBorder: 'rgba(0,0,0,0.1)',
    text: '#1a1a2e',
    textSecondary: 'rgba(0,0,0,0.6)',
    accent: '#4A90D9',
    accentHover: '#357ABD'
  };
};

export const getCardStyle = (themeColors: ThemeColors): React.CSSProperties => ({
  background: themeColors.cardBg,
  backdropFilter: 'blur(20px)',
  border: `1px solid ${themeColors.cardBorder}`,
  borderRadius: '16px',
  padding: '20px'
});

export const getTabStyle = (isActive: boolean, themeColors: ThemeColors): React.CSSProperties => ({
  padding: '12px 24px',
  border: 'none',
  background: isActive ? themeColors.accent : 'transparent',
  color: isActive ? '#fff' : themeColors.textSecondary,
  borderRadius: '8px',
  cursor: 'pointer',
  fontWeight: isActive ? 600 : 400,
  transition: 'all 0.2s'
});

export const getInputStyle = (themeColors: ThemeColors): React.CSSProperties => ({
  padding: '10px 14px',
  background: 'rgba(255,255,255,0.1)',
  border: `1px solid ${themeColors.cardBorder}`,
  borderRadius: '8px',
  color: themeColors.text,
  fontSize: '14px'
});
