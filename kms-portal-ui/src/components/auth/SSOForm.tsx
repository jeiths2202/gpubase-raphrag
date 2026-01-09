/**
 * Corporate SSO Form Component
 *
 * Handles corporate SSO login via email domain.
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import FormInput from './FormInput';
import SubmitButton from './SubmitButton';
import type { SSOFormProps } from './types';

export const SSOForm: React.FC<SSOFormProps> = ({
  t,
  isLoading,
  onSubmit,
  onBack,
  validateEmail,
}) => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!validateEmail(email)) {
      setError(t('auth.errors.invalidCorporateEmail'));
      return;
    }

    await onSubmit(email);
  };

  return (
    <motion.form
      key="sso"
      onSubmit={handleSubmit}
      className="auth-form"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.3 }}
    >
      {error && (
        <div className="message error">{error}</div>
      )}

      <div className="verify-icon">&#127970;</div>
      <p className="verify-text">
        {t('auth.enterCorporateEmail')}
      </p>

      <FormInput
        id="corpEmail"
        label={t('auth.corporateEmail')}
        type="email"
        value={email}
        onChange={setEmail}
        placeholder={t('auth.corporateEmailPlaceholder')}
        autoComplete="email"
      />

      <SubmitButton
        label={t('auth.continueWithSSO')}
        isLoading={isLoading}
      />

      <button
        type="button"
        className="btn-link"
        onClick={onBack}
      >
        &#8592; {t('auth.backToLogin')}
      </button>
    </motion.form>
  );
};

export default SSOForm;
