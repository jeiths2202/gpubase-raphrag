// Style Defaults for Knowledge Components
// Provides fallback values when style props are not provided
// These match the CSS design tokens from KnowledgeApp.css

import React from 'react';
import type { ThemeColors } from '../types';

// Default theme colors matching CSS variables
export const defaultThemeColors: ThemeColors = {
  bg: 'var(--color-bg-primary, #0a0a1a)',
  cardBg: 'var(--color-bg-card, rgba(255,255,255,0.03))',
  cardBorder: 'var(--color-border, rgba(255,255,255,0.08))',
  text: 'var(--color-text-primary, #f8fafc)',
  textSecondary: 'var(--color-text-secondary, #94a3b8)',
  accent: 'var(--color-primary, #6366f1)',
  accentHover: 'var(--color-primary-hover, #818cf8)',
  inputBg: 'var(--color-bg-input, rgba(255,255,255,0.05))',
  inputText: 'var(--color-text-primary, #f8fafc)'
};

// Default card style matching .knowledge-card class
export const defaultCardStyle: React.CSSProperties = {
  background: 'var(--color-bg-card, rgba(255,255,255,0.03))',
  backdropFilter: 'blur(var(--glass-blur, 12px))',
  border: '1px solid var(--color-border, rgba(255,255,255,0.08))',
  borderRadius: 'var(--radius-card, 16px)',
  padding: 'var(--spacing-card-padding, 24px)'
};

// Default tab style matching .knowledge-tab class
export const defaultTabStyle = (isActive: boolean): React.CSSProperties => ({
  padding: 'var(--space-3, 12px) var(--space-6, 24px)',
  border: 'none',
  background: isActive
    ? 'var(--gradient-primary, linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%))'
    : 'transparent',
  color: isActive
    ? 'var(--color-text-inverse, #ffffff)'
    : 'var(--color-text-secondary, #94a3b8)',
  borderRadius: 'var(--radius-base, 8px)',
  cursor: 'pointer',
  fontWeight: isActive ? 600 : 400,
  transition: 'all var(--duration-fast, 0.15s) var(--ease-default, ease)',
  boxShadow: isActive ? 'var(--shadow-sm, 0 1px 2px 0 rgba(0, 0, 0, 0.05))' : 'none'
});

// Default input style matching .knowledge-input class
export const defaultInputStyle: React.CSSProperties = {
  padding: 'var(--spacing-input-padding-y, 10px) var(--spacing-input-padding-x, 14px)',
  background: 'var(--color-bg-input, rgba(255,255,255,0.05))',
  border: '1px solid var(--color-border, rgba(255,255,255,0.08))',
  borderRadius: 'var(--radius-input, 8px)',
  color: 'var(--color-text-primary, #f8fafc)',
  fontSize: '14px'
};
