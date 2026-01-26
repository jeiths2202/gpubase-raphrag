/**
 * Settings Popup Component
 *
 * Modal dialog for language selection and user preferences
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { LANGUAGES, LanguageCode } from '../i18n/types';
import { useTranslation } from '../hooks/useTranslation';
import './SettingsPopup.css';

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsPopup: React.FC<SettingsPopupProps> = ({
  isOpen,
  onClose,
}) => {
  const { t, language, setLanguage } = useTranslation();

  if (!isOpen) return null;

  const handleLanguageChange = (lang: LanguageCode) => {
    setLanguage(lang);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="settings-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="settings-popup"
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="settings-popup__header">
              <h2 className="settings-popup__title">{t('common.nav.settings')}</h2>
              <button
                className="settings-popup__close"
                onClick={onClose}
                aria-label={t('common.close')}
              >
                <X size={20} />
              </button>
            </div>

            {/* Content */}
            <div className="settings-popup__content">
              {/* Language Settings */}
              <div className="settings-section">
                <label className="settings-section__label">
                  {t('common.settings.language')}
                </label>
                <div className="settings-language-list">
                  {(['en', 'ko', 'ja'] as LanguageCode[]).map((lang) => {
                    const langInfo = LANGUAGES[lang];
                    const isSelected = language === lang;
                    return (
                      <button
                        key={lang}
                        className={`settings-language-btn ${isSelected ? 'active' : ''}`}
                        onClick={() => handleLanguageChange(lang)}
                      >
                        <span className="settings-language-flag">{langInfo.flag}</span>
                        <div className="settings-language-info">
                          <span className="settings-language-native">{langInfo.nativeName}</span>
                          <span className="settings-language-name">{langInfo.name}</span>
                        </div>
                        {isSelected && (
                          <span className="settings-language-check">✓</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default SettingsPopup;
