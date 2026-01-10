/**
 * LanguageSelector Component
 *
 * A dropdown for selecting languages (en, ko, ja)
 */
import React, { memo, useState, useRef, useEffect } from 'react';
import { Globe, Check } from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { LANGUAGES, LanguageCode } from '../i18n/types';

interface LanguageSelectorProps {
  showLabel?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const iconSizes = { sm: 14, md: 16, lg: 18 };
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
  const iconSize = iconSizes[size];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

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

  const dropdownStyle: React.CSSProperties = {
    position: 'absolute',
    top: 'calc(100% + 4px)',
    right: 0,
    background: 'var(--color-bg-secondary)',
    border: '1px solid var(--color-border)',
    borderRadius: '8px',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
    zIndex: 1000,
    minWidth: '160px',
    opacity: isOpen ? 1 : 0,
    visibility: isOpen ? 'visible' : 'hidden',
    transform: isOpen ? 'translateY(0)' : 'translateY(-8px)',
    transition: 'all 0.2s ease',
  };

  const optionStyle = (isSelected: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
    background: isSelected ? 'var(--color-primary-light, rgba(99, 102, 241, 0.1))' : 'transparent',
  });

  return (
    <div ref={containerRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        style={buttonStyle}
        className={className}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={`Select language. Current: ${currentLang.name}`}
        title={currentLang.nativeName}
      >
        <Globe size={iconSize} />
        <span style={{ fontWeight: 600, fontSize: '11px', letterSpacing: '0.5px' }}>
          {language.toUpperCase()}
        </span>
        {showLabel && <span>{currentLang.nativeName}</span>}
      </button>

      <div style={dropdownStyle} role="listbox" aria-label="Select language">
        <ul style={{ listStyle: 'none', margin: 0, padding: '4px' }}>
          {languageOptions.map((lang) => {
            const langInfo = LANGUAGES[lang];
            const isSelected = lang === language;
            return (
              <li
                key={lang}
                style={optionStyle(isSelected)}
                role="option"
                aria-selected={isSelected}
                tabIndex={0}
                onClick={() => { setLanguage(lang); setIsOpen(false); }}
                onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = 'var(--color-bg-hover)'; }}
                onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{
                  fontWeight: 700,
                  fontSize: '12px',
                  color: isSelected ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                  background: isSelected ? 'var(--color-primary-light)' : 'var(--color-bg-hover)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  minWidth: '28px',
                  textAlign: 'center',
                }}>
                  {lang.toUpperCase()}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <span style={{ fontWeight: 500, color: 'var(--color-text-primary)', fontSize: '14px' }}>
                    {langInfo.name}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                    {langInfo.nativeName}
                  </span>
                </span>
                {isSelected && (
                  <span style={{ marginLeft: 'auto', color: 'var(--color-primary)' }}>
                    <Check size={14} />
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
});

LanguageSelector.displayName = 'LanguageSelector';
export default LanguageSelector;
