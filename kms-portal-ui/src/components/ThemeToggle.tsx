/**
 * ThemeToggle Component
 *
 * A button that cycles through theme options:
 * Light -> Dark -> System -> Light
 */
import React, { memo } from 'react';
import { useTheme } from '../hooks/useTheme';
import { Theme } from '../store/preferencesStore';

interface ThemeToggleProps {
  showLabel?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

// Text-only icons for debugging
const themeSymbols: Record<Theme, string> = {
  light: '☀',
  dark: '☽',
  system: '⚙',
};

export const ThemeToggle: React.FC<ThemeToggleProps> = memo(({
  showLabel = false,
  className = '',
  size = 'md',
}) => {
  const { theme, cycleTheme } = useTheme();
  const symbol = themeSymbols[theme];

  const buttonStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding: size === 'sm' ? '6px 10px' : size === 'lg' ? '10px 18px' : '8px 14px',
    background: 'var(--color-bg-secondary)',
    border: '1px solid var(--color-border)',
    borderRadius: '8px',
    color: 'var(--color-text-primary)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    fontSize: size === 'sm' ? '12px' : size === 'lg' ? '14px' : '13px',
  };

  const labelMap: Record<Theme, string> = {
    light: 'Light',
    dark: 'Dark',
    system: 'Auto',
  };

  return (
    <button
      type="button"
      style={buttonStyle}
      className={className}
      onClick={cycleTheme}
      aria-label={`${labelMap[theme]} mode`}
      title={`Current: ${labelMap[theme]} mode`}
    >
      <span style={{ fontSize: size === 'sm' ? '14px' : '16px' }}>{symbol}</span>
      {showLabel && <span>{labelMap[theme]}</span>}
    </button>
  );
});

ThemeToggle.displayName = 'ThemeToggle';
export default ThemeToggle;
