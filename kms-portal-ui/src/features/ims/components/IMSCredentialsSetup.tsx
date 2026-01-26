/**
 * IMS Credentials Setup Component
 *
 * Modal form for entering and validating IMS credentials
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Key, Globe, User, Lock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { createCredentials, validateCredentials } from '../services/ims-api';
import { useIMSStore } from '../store/imsStore';

interface IMSCredentialsSetupProps {
  isOpen: boolean;
  onClose: () => void;
  t: (key: string) => string;
}

export const IMSCredentialsSetup: React.FC<IMSCredentialsSetupProps> = ({
  isOpen,
  onClose,
  t,
}) => {
  const { setCredentialsStatus } = useIMSStore();

  const [formData, setFormData] = useState({
    ims_url: 'https://ims.tmaxsoft.com',
    username: '',
    password: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setError(null);
    setSuccess(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setSuccess(false);

    try {
      // Save credentials
      await createCredentials(formData);

      // Validate credentials
      const validation = await validateCredentials();

      if (validation.is_valid) {
        setSuccess(true);
        setCredentialsStatus(true, true);
        setTimeout(() => {
          onClose();
        }, 1500);
      } else {
        setError(validation.message || t('ims.credentials.error'));
        setCredentialsStatus(true, false, validation.message);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('ims.credentials.error');
      setError(message);
      setCredentialsStatus(false, false, message);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="ims-modal-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className="ims-modal"
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="ims-modal__header">
            <div className="ims-modal__header-icon">
              <Key size={24} />
            </div>
            <div>
              <h2 className="ims-modal__title">{t('ims.credentials.title')}</h2>
              <p className="ims-modal__subtitle">{t('ims.credentials.subtitle')}</p>
            </div>
            <button className="ims-modal__close" onClick={onClose} aria-label="Close">
              <X size={20} />
            </button>
          </div>

          {/* Form */}
          <form className="ims-modal__form" onSubmit={handleSubmit}>
            {/* IMS URL */}
            <div className="ims-form-group">
              <label className="ims-form-label">
                <Globe size={16} />
                {t('ims.credentials.imsUrl')}
              </label>
              <input
                type="url"
                name="ims_url"
                className="ims-form-input"
                value={formData.ims_url}
                onChange={handleChange}
                placeholder="https://ims.example.com"
                required
              />
            </div>

            {/* Username */}
            <div className="ims-form-group">
              <label className="ims-form-label">
                <User size={16} />
                {t('ims.credentials.username')}
              </label>
              <input
                type="text"
                name="username"
                className="ims-form-input"
                value={formData.username}
                onChange={handleChange}
                placeholder={t('ims.credentials.usernamePlaceholder')}
                required
              />
            </div>

            {/* Password */}
            <div className="ims-form-group">
              <label className="ims-form-label">
                <Lock size={16} />
                {t('ims.credentials.password')}
              </label>
              <input
                type="password"
                name="password"
                className="ims-form-input"
                value={formData.password}
                onChange={handleChange}
                placeholder={t('ims.credentials.passwordPlaceholder')}
                required
              />
            </div>

            {/* Error message */}
            {error && (
              <div className="ims-form-message ims-form-message--error">
                <AlertCircle size={16} />
                {error}
              </div>
            )}

            {/* Success message */}
            {success && (
              <div className="ims-form-message ims-form-message--success">
                <CheckCircle size={16} />
                {t('ims.credentials.success')}
              </div>
            )}

            {/* Actions */}
            <div className="ims-modal__actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={isLoading}
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isLoading || !formData.username || !formData.password}
              >
                {isLoading ? (
                  <>
                    <Loader2 size={16} className="spin" />
                    {t('ims.credentials.validating')}
                  </>
                ) : (
                  t('ims.credentials.save')
                )}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default IMSCredentialsSetup;
