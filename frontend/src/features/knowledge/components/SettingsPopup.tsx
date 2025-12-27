// Settings Popup Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LANGUAGES, LanguageCode, TranslateFunction } from '../../../i18n/types';
import type { ThemeColors } from '../types';

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  t: TranslateFunction;
}

export const SettingsPopup: React.FC<SettingsPopupProps> = ({
  isOpen,
  onClose,
  language,
  setLanguage,
  themeColors,
  cardStyle,
  t
}) => {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2000
          }}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              ...cardStyle,
              width: '400px',
              maxWidth: '90vw',
              padding: '24px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>{t('knowledge.sidebar.settings')}</h2>
              <button
                onClick={onClose}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: themeColors.text,
                  fontSize: '24px',
                  cursor: 'pointer',
                  padding: '4px'
                }}
              >
                ×
              </button>
            </div>

            {/* Language Settings */}
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, color: themeColors.textSecondary }}>
                Language / 언어 / 言語
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {(['en', 'ko', 'ja'] as LanguageCode[]).map((lang) => {
                  const langInfo = LANGUAGES[lang];
                  const isSelected = language === lang;
                  return (
                    <button
                      key={lang}
                      onClick={() => setLanguage(lang)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        padding: '12px 16px',
                        background: isSelected ? themeColors.accent : 'rgba(255, 255, 255, 0.05)',
                        border: isSelected ? `2px solid ${themeColors.accent}` : '2px solid transparent',
                        borderRadius: '8px',
                        color: isSelected ? '#fff' : themeColors.text,
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        textAlign: 'left'
                      }}
                    >
                      <span style={{ fontSize: '24px' }}>{langInfo.flag}</span>
                      <div>
                        <div style={{ fontWeight: 500 }}>{langInfo.nativeName}</div>
                        <div style={{ fontSize: '12px', opacity: 0.7 }}>{langInfo.name}</div>
                      </div>
                      {isSelected && (
                        <span style={{ marginLeft: 'auto', fontSize: '18px' }}>✓</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default SettingsPopup;
