/**
 * LanguageSelector Component
 *
 * A dropdown listbox for selecting languages
 * Supports English (en), Korean (ko), and Japanese (ja)
 *
 * Features:
 * - Dropdown listbox with all language options
 * - Animated transitions
 * - Accessible (keyboard navigation, ARIA labels)
 * - Shows current language with flag
 * - Click outside to close
 */
import React, { memo, useState, useRef, useEffect } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { LANGUAGES, LanguageCode } from '../i18n/types';

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
    dropdown: 'min-width: 140px;',
  },
  md: {
    button: 'padding: 8px 14px; font-size: 15px;',
    flag: 'font-size: 18px;',
    label: 'font-size: 13px;',
    dropdown: 'min-width: 160px;',
  },
  lg: {
    button: 'padding: 10px 18px; font-size: 16px;',
    flag: 'font-size: 22px;',
    label: 'font-size: 14px;',
    dropdown: 'min-width: 180px;',
  },
};

const languageOptions: LanguageCode[] = ['en', 'ko', 'ja'];

export const LanguageSelector: React.FC<LanguageSelectorProps> = memo(({
  showLabel = false,
  className = '',
  size = 'md',
}) => {
  const { language, setLanguage } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const currentLang = LANGUAGES[language];
  const sizes = sizeConfig[size];

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Handle keyboard navigation
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setIsOpen(false);
    } else if (event.key === 'ArrowDown' && !isOpen) {
      event.preventDefault();
      setIsOpen(true);
    }
  };

  const handleOptionKeyDown = (event: React.KeyboardEvent, lang: LanguageCode) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleSelectLanguage(lang);
    } else if (event.key === 'Escape') {
      setIsOpen(false);
    }
  };

  const handleSelectLanguage = (lang: LanguageCode) => {
    setLanguage(lang);
    setIsOpen(false);
  };

  const toggleDropdown = () => {
    setIsOpen(!isOpen);
  };

  return (
    <>
      <style>{`
        .language-selector-container {
          position: relative;
          display: inline-block;
        }

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

        .language-selector[aria-expanded="true"] {
          border-color: var(--color-border-focus);
          background: var(--color-bg-hover);
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

        .language-dropdown-arrow {
          margin-left: 4px;
          font-size: 10px;
          transition: transform 0.2s ease;
          color: var(--color-text-secondary);
        }

        .language-selector[aria-expanded="true"] .language-dropdown-arrow {
          transform: rotate(180deg);
        }

        .language-dropdown {
          position: absolute;
          top: calc(100% + 4px);
          right: 0;
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          z-index: 1000;
          opacity: 0;
          visibility: hidden;
          transform: translateY(-8px);
          transition: all 0.2s ease;
          ${sizes.dropdown}
        }

        .language-dropdown.open {
          opacity: 1;
          visibility: visible;
          transform: translateY(0);
        }

        .language-dropdown-list {
          list-style: none;
          margin: 0;
          padding: 4px;
        }

        .language-option {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 6px;
          cursor: pointer;
          transition: background 0.15s ease;
        }

        .language-option:hover {
          background: var(--color-bg-hover);
        }

        .language-option:focus {
          outline: none;
          background: var(--color-bg-hover);
        }

        .language-option.selected {
          background: var(--color-primary-transparent, rgba(59, 130, 246, 0.1));
        }

        .language-option-flag {
          font-size: 20px;
        }

        .language-option-text {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .language-option-name {
          font-weight: 500;
          color: var(--color-text-primary);
          font-size: 14px;
        }

        .language-option-native {
          font-size: 12px;
          color: var(--color-text-secondary);
        }

        .language-option-check {
          margin-left: auto;
          color: var(--color-primary, #6366f1);
          font-size: 14px;
        }

        @media (prefers-reduced-motion: reduce) {
          .language-selector,
          .language-flag,
          .language-dropdown,
          .language-dropdown-arrow {
            transition: none;
          }
        }
      `}</style>

      <div className="language-selector-container" ref={containerRef}>
        <button
          type="button"
          className={`language-selector ${className}`}
          onClick={toggleDropdown}
          onKeyDown={handleKeyDown}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-label={`Select language. Current: ${currentLang.name}`}
          title={currentLang.nativeName}
        >
          <span className="language-flag" role="img" aria-hidden="true">
            {currentLang.flag}
          </span>
          {showLabel ? (
            <span className="language-label">{currentLang.nativeName}</span>
          ) : (
            <span className="language-code">{language.toUpperCase()}</span>
          )}
          <span className="language-dropdown-arrow" aria-hidden="true">▼</span>
        </button>

        <div
          className={`language-dropdown ${isOpen ? 'open' : ''}`}
          role="listbox"
          aria-label="Select language"
        >
          <ul className="language-dropdown-list">
            {languageOptions.map((lang) => {
              const langInfo = LANGUAGES[lang];
              const isSelected = lang === language;
              return (
                <li
                  key={lang}
                  className={`language-option ${isSelected ? 'selected' : ''}`}
                  role="option"
                  aria-selected={isSelected}
                  tabIndex={0}
                  onClick={() => handleSelectLanguage(lang)}
                  onKeyDown={(e) => handleOptionKeyDown(e, lang)}
                >
                  <span className="language-option-flag" role="img" aria-hidden="true">
                    {langInfo.flag}
                  </span>
                  <span className="language-option-text">
                    <span className="language-option-name">{langInfo.name}</span>
                    <span className="language-option-native">{langInfo.nativeName}</span>
                  </span>
                  {isSelected && (
                    <span className="language-option-check" aria-hidden="true">✓</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </>
  );
});

LanguageSelector.displayName = 'LanguageSelector';

export default LanguageSelector;
