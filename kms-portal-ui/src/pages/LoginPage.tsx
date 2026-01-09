/**
 * Login Page
 *
 * Full-featured authentication page with:
 * - User/password login
 * - Registration with email verification
 * - Google OAuth
 * - Corporate SSO
 *
 * Uses the centralized auth store with HttpOnly cookie authentication.
 */
import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';
import { isCorpEmail, APP_CONFIG, GOOGLE_CLIENT_ID } from '../config/constants';
import ThemeToggle from '../components/ThemeToggle';
import LanguageSelector from '../components/LanguageSelector';
import {
  LoginForm,
  RegisterForm,
  VerifyForm,
  SSOForm,
  type AuthMode,
} from '../components/auth';
import './LoginPage.css';

// Check if Google OAuth is configured
const isGoogleConfigured = !!GOOGLE_CLIENT_ID;

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  // Auth store - using new API layer with HttpOnly cookies
  const {
    login,
    register,
    verifyEmail,
    loginWithGoogle,
    loginWithSSO,
    isLoading,
    error,
    clearError,
  } = useAuthStore();

  // Local state
  const [mode, setMode] = useState<AuthMode>('login');
  const [registrationEmail, setRegistrationEmail] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Navigation helper after successful auth
  const navigateAfterAuth = useCallback(() => {
    const currentUser = useAuthStore.getState().user;
    if (currentUser?.role === 'user') {
      navigate('/knowledge');
    } else {
      navigate('/');
    }
  }, [navigate]);

  // Mode change handler
  const handleModeChange = useCallback((newMode: AuthMode) => {
    setMode(newMode);
    clearError();
    setSuccessMessage('');
  }, [clearError]);

  // =========================================================================
  // Login Handler
  // =========================================================================
  const handleLogin = useCallback(async (userId: string, password: string): Promise<boolean> => {
    clearError();
    const success = await login(userId, password);
    if (success) {
      navigateAfterAuth();
    }
    return success;
  }, [login, clearError, navigateAfterAuth]);

  // =========================================================================
  // Registration Handler
  // =========================================================================
  const handleRegister = useCallback(async (
    userId: string,
    email: string,
    password: string
  ): Promise<boolean> => {
    clearError();
    setSuccessMessage('');

    const success = await register(userId, email, password);
    if (success) {
      setRegistrationEmail(email);
      setSuccessMessage(t('auth.verificationSent'));
      return true;
    }
    return false;
  }, [register, clearError, t]);

  // =========================================================================
  // Email Verification Handler
  // =========================================================================
  const handleVerify = useCallback(async (code: string): Promise<boolean> => {
    clearError();

    const success = await verifyEmail(registrationEmail, code);
    if (success) {
      setSuccessMessage(t('auth.accountVerified'));
      setTimeout(navigateAfterAuth, 1500);
      return true;
    }
    return false;
  }, [verifyEmail, registrationEmail, clearError, navigateAfterAuth, t]);

  // =========================================================================
  // Google OAuth Handler
  // =========================================================================
  const handleGoogleLogin = useCallback(async () => {
    clearError();
    // In a real implementation, this would receive the Google credential
    // from the Google Sign-In button callback
    const success = await loginWithGoogle('');
    if (success) {
      navigateAfterAuth();
    }
  }, [loginWithGoogle, clearError, navigateAfterAuth]);

  // =========================================================================
  // SSO Login Handler
  // =========================================================================
  const handleSSOLogin = useCallback(async (email: string) => {
    clearError();
    const ssoUrl = await loginWithSSO(email);
    if (ssoUrl) {
      window.location.href = ssoUrl;
    }
  }, [loginWithSSO, clearError]);

  return (
    <div className="login-container">
      {/* Theme/Language Controls */}
      <div className="login-controls">
        <ThemeToggle size="sm" />
        <LanguageSelector size="sm" />
      </div>

      {/* Animated Background */}
      <div className="login-bg">
        <div className="gradient-orb orb-1" />
        <div className="gradient-orb orb-2" />
        <div className="gradient-orb orb-3" />
      </div>

      {/* Login Card */}
      <motion.div
        className="login-card"
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Logo & Title */}
        <motion.div
          className="login-header"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="logo">
            <span className="logo-icon">K</span>
          </div>
          <h1>{APP_CONFIG.name}</h1>
          <p className="subtitle">{APP_CONFIG.fullName}</p>
        </motion.div>

        {/* Mode Tabs */}
        <div className="auth-tabs">
          <button
            className={`tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => handleModeChange('login')}
          >
            {t('auth.signIn')}
          </button>
          <button
            className={`tab ${mode === 'register' || mode === 'verify' ? 'active' : ''}`}
            onClick={() => handleModeChange('register')}
          >
            {t('auth.register')}
          </button>
        </div>

        {/* Error/Success Messages */}
        <AnimatePresence>
          {error && (
            <motion.div
              className="message error"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
            >
              {error}
            </motion.div>
          )}
          {successMessage && (
            <motion.div
              className="message success"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
            >
              {successMessage}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Forms */}
        <AnimatePresence mode="wait">
          {mode === 'login' && (
            <LoginForm
              t={t}
              isLoading={isLoading}
              onSubmit={handleLogin}
              onSSOClick={() => handleModeChange('forgot')}
              onGoogleClick={handleGoogleLogin}
              isGoogleConfigured={isGoogleConfigured}
            />
          )}

          {mode === 'register' && (
            <RegisterForm
              t={t}
              isLoading={isLoading}
              onSubmit={handleRegister}
              onModeChange={handleModeChange}
            />
          )}

          {mode === 'verify' && (
            <VerifyForm
              t={t}
              isLoading={isLoading}
              email={registrationEmail}
              onSubmit={handleVerify}
              onBack={() => handleModeChange('register')}
            />
          )}

          {mode === 'forgot' && (
            <SSOForm
              t={t}
              isLoading={isLoading}
              onSubmit={handleSSOLogin}
              onBack={() => handleModeChange('login')}
              validateEmail={isCorpEmail}
            />
          )}
        </AnimatePresence>

        {/* Footer */}
        <div className="login-footer">
          <a href="#">{t('auth.termsOfService')}</a>
          <span>&#8226;</span>
          <a href="#">{t('auth.privacyPolicy')}</a>
        </div>
      </motion.div>
    </div>
  );
};

export { LoginPage };
export default LoginPage;
