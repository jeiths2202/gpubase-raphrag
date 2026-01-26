/**
 * Login Form Component
 *
 * Handles user/password login with social login options.
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import FormInput from './FormInput';
import SubmitButton from './SubmitButton';
import SocialLoginButtons from './SocialLoginButtons';
import type { LoginFormProps } from './types';

export const LoginForm: React.FC<LoginFormProps> = ({
  t,
  isLoading,
  onSubmit,
  onSSOClick,
  onGoogleSuccess,
  onGoogleError,
  isGoogleConfigured,
}) => {
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!userId || !password) {
      setError(t('auth.errors.enterIdAndPassword'));
      return;
    }

    const success = await onSubmit(userId, password);
    if (!success) {
      // Error handling is done in parent component via store
    }
  };

  return (
    <motion.form
      key="login"
      onSubmit={handleSubmit}
      className="auth-form"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3 }}
    >
      {error && (
        <div className="message error">{error}</div>
      )}

      <FormInput
        id="userId"
        label={t('auth.userId')}
        type="text"
        value={userId}
        onChange={setUserId}
        placeholder={t('auth.userIdPlaceholder')}
        autoComplete="username"
      />

      <FormInput
        id="password"
        label={t('auth.password')}
        type="password"
        value={password}
        onChange={setPassword}
        placeholder={t('auth.passwordPlaceholder')}
        autoComplete="current-password"
      />

      <SubmitButton
        label={t('auth.signIn')}
        isLoading={isLoading}
      />

      <div className="divider">
        <span>{t('auth.orContinueWith')}</span>
      </div>

      <SocialLoginButtons
        t={t}
        isLoading={isLoading}
        isGoogleConfigured={isGoogleConfigured}
        onGoogleSuccess={onGoogleSuccess}
        onGoogleError={onGoogleError}
        onSSOClick={onSSOClick}
      />
    </motion.form>
  );
};

export default LoginForm;
