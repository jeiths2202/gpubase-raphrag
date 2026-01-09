/**
 * Email Verification Form Component
 *
 * Handles email verification code entry.
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import FormInput from './FormInput';
import SubmitButton from './SubmitButton';
import type { VerifyFormProps } from './types';

export const VerifyForm: React.FC<VerifyFormProps> = ({
  t,
  isLoading,
  email,
  onSubmit,
  onBack,
}) => {
  const [verificationCode, setVerificationCode] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!verificationCode) {
      setError(t('auth.errors.enterVerificationCode'));
      return;
    }

    await onSubmit(verificationCode);
  };

  return (
    <motion.form
      key="verify"
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

      <div className="verify-icon">&#128231;</div>
      <p className="verify-text">
        {t('auth.verificationEmailSent')}<br />
        <strong>{email}</strong>
      </p>

      <FormInput
        id="verifyCode"
        label={t('auth.verificationCode')}
        type="text"
        value={verificationCode}
        onChange={setVerificationCode}
        placeholder={t('auth.verificationCodePlaceholder')}
        maxLength={6}
        className="code-input"
        autoComplete="one-time-code"
      />

      <SubmitButton
        label={t('auth.verifyEmail')}
        isLoading={isLoading}
      />

      <button
        type="button"
        className="btn-link"
        onClick={onBack}
      >
        &#8592; {t('auth.backToRegistration')}
      </button>
    </motion.form>
  );
};

export default VerifyForm;
