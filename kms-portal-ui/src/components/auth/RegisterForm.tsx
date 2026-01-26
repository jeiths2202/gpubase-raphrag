/**
 * Registration Form Component
 *
 * Handles user registration with validation.
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import FormInput from './FormInput';
import SubmitButton from './SubmitButton';
import type { RegisterFormProps } from './types';

export const RegisterForm: React.FC<RegisterFormProps> = ({
  t,
  isLoading,
  onSubmit,
  onModeChange,
}) => {
  const [userId, setUserId] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');

  const validatePassword = (pwd: string): string | null => {
    const hasUpper = /[A-Z]/.test(pwd);
    const hasLower = /[a-z]/.test(pwd);
    const hasDigit = /[0-9]/.test(pwd);
    const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:',.<>?/]/.test(pwd);

    if (pwd.length < 8) {
      return t('auth.errors.passwordTooShort');
    }

    if (!(hasUpper && hasLower && hasDigit && hasSpecial)) {
      return t('auth.errors.passwordComplexity');
    }

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validate user ID format
    if (!/^[a-zA-Z0-9_]+$/.test(userId)) {
      setError(t('auth.errors.invalidUserId'));
      return;
    }

    // Validate required fields
    if (!userId || !password || !email) {
      setError(t('auth.errors.fillAllFields'));
      return;
    }

    // Validate password match
    if (password !== confirmPassword) {
      setError(t('auth.errors.passwordsDoNotMatch'));
      return;
    }

    // Validate password complexity
    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    const success = await onSubmit(userId, email, password);
    if (success) {
      onModeChange('verify');
    }
  };

  return (
    <motion.form
      key="register"
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

      <FormInput
        id="regUserId"
        label={t('auth.userId')}
        type="text"
        value={userId}
        onChange={setUserId}
        placeholder={t('auth.chooseUserId')}
        autoComplete="username"
      />

      <FormInput
        id="regEmail"
        label={t('auth.emailForVerification')}
        type="email"
        value={email}
        onChange={setEmail}
        placeholder={t('auth.emailPlaceholder')}
        autoComplete="email"
      />

      <FormInput
        id="regPassword"
        label={t('auth.password')}
        type="password"
        value={password}
        onChange={setPassword}
        placeholder={t('auth.passwordMinLength')}
        autoComplete="new-password"
      />

      <FormInput
        id="regConfirmPassword"
        label={t('auth.confirmPassword')}
        type="password"
        value={confirmPassword}
        onChange={setConfirmPassword}
        placeholder={t('auth.confirmPasswordPlaceholder')}
        autoComplete="new-password"
      />

      <SubmitButton
        label={t('auth.createAccount')}
        isLoading={isLoading}
      />

      <p className="hint">
        {t('auth.verificationHint')}
      </p>
    </motion.form>
  );
};

export default RegisterForm;
