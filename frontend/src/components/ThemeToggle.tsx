/**
 * ThemeToggle Component
 *
 * A button that cycles through theme options:
 * Light -> Dark -> System -> Light
 *
 * Features:
 * - Animated icon transitions
 * - Accessible (keyboard navigation, ARIA labels)
 * - Shows current theme state
 */
import React, { memo } from 'react';
import { useTheme } from '../hooks/useTheme';
import { Theme } from '../store/preferencesStore';

interface ThemeToggleProps {
  /** Show label text next to icon */
  showLabel?: boolean;
  /** Additional CSS class */
  className?: string;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
}

// Theme icons and labels
const themeConfig: Record<Theme, { icon: string; label: string; ariaLabel: string }> = {
  light: {
    icon: '☀️',
    label: '라이트',
    ariaLabel: '라이트 모드 (클릭하여 다크 모드로 전환)',
  },
  dark: {
    icon: '🌙',
    label: '다크',
    ariaLabel: '다크 모드 (클릭하여 시스템 설정으로 전환)',
  },
  system: {
    icon: '💻',
    label: '시스템',
    ariaLabel: '시스템 설정 따르기 (클릭하여 라이트 모드로 전환)',
  },
};

// Size configurations
const sizeConfig = {
  sm: {
    button: 'padding: 6px 10px; font-size: 14px;',
    icon: 'font-size: 16px;',
    label: 'font-size: 12px;',
  },
  md: {
    button: 'padding: 8px 14px; font-size: 15px;',
    icon: 'font-size: 18px;',
    label: 'font-size: 13px;',
  },
  lg: {
    button: 'padding: 10px 18px; font-size: 16px;',
    icon: 'font-size: 22px;',
    label: 'font-size: 14px;',
  },
};

export const ThemeToggle: React.FC<ThemeToggleProps> = memo(({
  showLabel = false,
  className = '',
  size = 'md',
}) => {
  const { theme, cycleTheme, resolvedTheme } = useTheme();
  const config = themeConfig[theme];
  const sizes = sizeConfig[size];

  return (
    <>
      <style>{`
        .theme-toggle {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          color: var(--color-text-primary);
          cursor: pointer;
          transition: all 0.2s ease;
          ${sizes.button}
        }

        .theme-toggle:hover {
          background: var(--color-bg-hover);
          border-color: var(--color-border-focus);
        }

        .theme-toggle:focus-visible {
          outline: 2px solid var(--color-border-focus);
          outline-offset: 2px;
        }

        .theme-toggle:active {
          transform: scale(0.97);
        }

        .theme-toggle-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          transition: transform 0.3s ease;
          ${sizes.icon}
        }

        .theme-toggle:hover .theme-toggle-icon {
          transform: rotate(15deg);
        }

        .theme-toggle-label {
          color: var(--color-text-secondary);
          ${sizes.label}
        }

        .theme-toggle-indicator {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: ${resolvedTheme === 'dark' ? 'var(--color-primary)' : 'var(--color-warning)'};
          transition: background 0.2s ease;
        }

        @media (prefers-reduced-motion: reduce) {
          .theme-toggle,
          .theme-toggle-icon {
            transition: none;
          }
        }
      `}</style>

      <button
        type="button"
        className={`theme-toggle ${className}`}
        onClick={cycleTheme}
        aria-label={config.ariaLabel}
        title={`현재: ${config.label} 모드`}
      >
        <span className="theme-toggle-icon" role="img" aria-hidden="true">
          {config.icon}
        </span>
        {showLabel && (
          <span className="theme-toggle-label">{config.label}</span>
        )}
        <span className="theme-toggle-indicator" aria-hidden="true" />
      </button>
    </>
  );
});

ThemeToggle.displayName = 'ThemeToggle';

export default ThemeToggle;
