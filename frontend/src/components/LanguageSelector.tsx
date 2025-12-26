/**
 * LanguageSelector Component
 *
 * A button that toggles between available languages
 * Currently supports English (en) and Korean (ko)
 *
 * Features:
 * - Animated transitions
 * - Accessible (keyboard navigation, ARIA labels)
 * - Shows current language with flag
 */
import React, { memo } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { LanguageCode, LANGUAGES } from '../i18n/types';

interface LanguageSelectorProps {
  /** Show full language name */
  showLabel?: boolean;
  /** Additional CSS class */
  className?: string;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
}

// Size configurations
const sizeConfig = {
  sm: {
    button: 'padding: 6px 10px; font-size: 14px;',
    flag: 'font-size: 16px;',
    label: 'font-size: 12px;',
  },
  md: {
    button: 'padding: 8px 14px; font-size: 15px;',
    flag: 'font-size: 18px;',
    label: 'font-size: 13px;',
  },
  lg: {
    button: 'padding: 10px 18px; font-size: 16px;',
    flag: 'font-size: 22px;',
    label: 'font-size: 14px;',
  },
};

export const LanguageSelector: React.FC<LanguageSelectorProps> = memo(({
  showLabel = false,
  className = '',
  size = 'md',
}) => {
  const { language, toggleLanguage } = useTranslation();
  const currentLang = LANGUAGES[language];
  const nextLang = LANGUAGES[language === 'en' ? 'ko' : 'en'];
  const sizes = sizeConfig[size];

  const ariaLabel = `Current language: ${currentLang.name}. Click to switch to ${nextLang.name}`;

  return (
    <>
      <style>{`
        .language-selector {
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

        .language-selector:hover {
          background: var(--color-bg-hover);
          border-color: var(--color-border-focus);
        }

        .language-selector:focus-visible {
          outline: 2px solid var(--color-border-focus);
          outline-offset: 2px;
        }

        .language-selector:active {
          transform: scale(0.97);
        }

        .language-flag {
          display: flex;
          align-items: center;
          justify-content: center;
          transition: transform 0.3s ease;
          ${sizes.flag}
        }

        .language-selector:hover .language-flag {
          transform: scale(1.1);
        }

        .language-label {
          color: var(--color-text-secondary);
          ${sizes.label}
        }

        .language-code {
          font-weight: 600;
          color: var(--color-text-primary);
          text-transform: uppercase;
          font-size: 11px;
          letter-spacing: 0.5px;
        }

        @media (prefers-reduced-motion: reduce) {
          .language-selector,
          .language-flag {
            transition: none;
          }
        }
      `}</style>

      <button
        type="button"
        className={`language-selector ${className}`}
        onClick={toggleLanguage}
        aria-label={ariaLabel}
        title={`${currentLang.nativeName} → ${nextLang.nativeName}`}
      >
        <span className="language-flag" role="img" aria-hidden="true">
          {currentLang.flag}
        </span>
        {showLabel ? (
          <span className="language-label">{currentLang.nativeName}</span>
        ) : (
          <span className="language-code">{language.toUpperCase()}</span>
        )}
      </button>
    </>
  );
});

LanguageSelector.displayName = 'LanguageSelector';

export default LanguageSelector;
