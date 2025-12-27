import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useGoogleLogin } from '@react-oauth/google';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';
import { isCorpEmail, APP_CONFIG, GOOGLE_CLIENT_ID } from '../config/constants';
import ThemeToggle from '../components/ThemeToggle';
import LanguageSelector from '../components/LanguageSelector';

// Check if Google OAuth is configured
const isGoogleConfigured = !!GOOGLE_CLIENT_ID;

// Google Login Button Component - only uses hook when configured
interface GoogleLoginButtonProps {
  onSuccess: (token: string) => Promise<void>;
  onError: () => void;
  label: string;
}

const GoogleLoginButton: React.FC<GoogleLoginButtonProps> = ({ onSuccess, onError, label }) => {
  // Only call hook if Google is configured (component is only rendered when configured)
  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      if (tokenResponse.access_token) {
        await onSuccess(tokenResponse.access_token);
      }
    },
    onError,
  });

  return (
    <motion.button
      type="button"
      className="btn-google"
      onClick={() => googleLogin()}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      <svg className="google-icon" viewBox="0 0 24 24" width="20" height="20">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
      </svg>
      {label}
    </motion.button>
  );
};

type AuthMode = 'login' | 'register' | 'verify' | 'forgot';

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { login, loginWithGoogle, isLoading, error, clearError } = useAuthStore();

  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [localError, setLocalError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');
    clearError();

    if (!userId || !password) {
      setLocalError(t('auth.errors.enterIdAndPassword'));
      return;
    }

    const success = await login(userId, password);
    if (success) {
      navigate('/');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');
    setSuccessMessage('');

    if (!userId || !password || !email) {
      setLocalError(t('auth.errors.fillAllFields'));
      return;
    }

    if (password !== confirmPassword) {
      setLocalError(t('auth.errors.passwordsDoNotMatch'));
      return;
    }

    if (password.length < 8) {
      setLocalError(t('auth.errors.passwordTooShort'));
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, password, email }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage(t('auth.verificationSent'));
        setMode('verify');
      } else {
        setLocalError(data.detail?.message || t('auth.errors.registrationFailed'));
      }
    } catch {
      setLocalError(t('auth.errors.networkError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (!verificationCode) {
      setLocalError(t('auth.errors.enterVerificationCode'));
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch('/api/v1/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: verificationCode }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage(t('auth.accountVerified'));
        setTimeout(() => {
          setMode('login');
          setSuccessMessage('');
        }, 2000);
      } else {
        setLocalError(data.detail?.message || t('auth.errors.verificationFailed'));
      }
    } catch {
      setLocalError(t('auth.errors.networkError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGoogleSuccess = useCallback(async (token: string) => {
    const success = await loginWithGoogle(token);
    if (success) {
      navigate('/');
    }
  }, [loginWithGoogle, navigate]);

  const handleGoogleError = useCallback(() => {
    setLocalError(t('auth.errors.googleLoginFailed'));
  }, [t]);

  const handleSSOLogin = () => {
    if (isCorpEmail(email)) {
      window.location.href = `/api/v1/auth/sso/initiate?email=${encodeURIComponent(email)}`;
    } else {
      setLocalError(t('auth.errors.invalidCorporateEmail'));
    }
  };

  const displayError = localError || error;

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
            onClick={() => { setMode('login'); clearError(); setLocalError(''); }}
          >
            {t('auth.signIn')}
          </button>
          <button
            className={`tab ${mode === 'register' || mode === 'verify' ? 'active' : ''}`}
            onClick={() => { setMode('register'); clearError(); setLocalError(''); }}
          >
            {t('auth.register')}
          </button>
        </div>

        {/* Error/Success Messages */}
        <AnimatePresence>
          {displayError && (
            <motion.div
              className="message error"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
            >
              {displayError}
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
            <motion.form
              key="login"
              onSubmit={handleLogin}
              className="auth-form"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="input-group">
                <label>{t('auth.userId')}</label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder={t('auth.userIdPlaceholder')}
                  autoComplete="username"
                />
              </div>

              <div className="input-group">
                <label>{t('auth.password')}</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.passwordPlaceholder')}
                  autoComplete="current-password"
                />
              </div>

              <motion.button
                type="submit"
                className="btn-primary"
                disabled={isLoading}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {isLoading ? <span className="spinner" /> : t('auth.signIn')}
              </motion.button>

              <div className="divider">
                <span>{t('auth.orContinueWith')}</span>
              </div>

              <div className="social-buttons">
                {isGoogleConfigured && (
                  <GoogleLoginButton
                    onSuccess={handleGoogleSuccess}
                    onError={handleGoogleError}
                    label={t('auth.googleLogin')}
                  />
                )}

                <motion.button
                  type="button"
                  className="btn-sso"
                  onClick={() => setMode('forgot')}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <span className="sso-icon">🏢</span>
                  {t('auth.corporateSSO')}
                </motion.button>
              </div>
            </motion.form>
          )}

          {mode === 'register' && (
            <motion.form
              key="register"
              onSubmit={handleRegister}
              className="auth-form"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="input-group">
                <label>{t('auth.userId')}</label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder={t('auth.chooseUserId')}
                  autoComplete="username"
                />
              </div>

              <div className="input-group">
                <label>{t('auth.emailForVerification')}</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t('auth.emailPlaceholder')}
                  autoComplete="email"
                />
              </div>

              <div className="input-group">
                <label>{t('auth.password')}</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.passwordMinLength')}
                  autoComplete="new-password"
                />
              </div>

              <div className="input-group">
                <label>{t('auth.confirmPassword')}</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t('auth.confirmPasswordPlaceholder')}
                  autoComplete="new-password"
                />
              </div>

              <motion.button
                type="submit"
                className="btn-primary"
                disabled={isSubmitting}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {isSubmitting ? <span className="spinner" /> : t('auth.createAccount')}
              </motion.button>

              <p className="hint">
                {t('auth.verificationHint')}
              </p>
            </motion.form>
          )}

          {mode === 'verify' && (
            <motion.form
              key="verify"
              onSubmit={handleVerify}
              className="auth-form"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="verify-icon">📧</div>
              <p className="verify-text">
                {t('auth.verificationEmailSent')}<br />
                <strong>{email}</strong>
              </p>

              <div className="input-group">
                <label>{t('auth.verificationCode')}</label>
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value)}
                  placeholder={t('auth.verificationCodePlaceholder')}
                  maxLength={6}
                  className="code-input"
                  autoComplete="one-time-code"
                />
              </div>

              <motion.button
                type="submit"
                className="btn-primary"
                disabled={isSubmitting}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {isSubmitting ? <span className="spinner" /> : t('auth.verifyEmail')}
              </motion.button>

              <button
                type="button"
                className="btn-link"
                onClick={() => setMode('register')}
              >
                ← {t('auth.backToRegistration')}
              </button>
            </motion.form>
          )}

          {mode === 'forgot' && (
            <motion.form
              key="sso"
              onSubmit={(e) => { e.preventDefault(); handleSSOLogin(); }}
              className="auth-form"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="verify-icon">🏢</div>
              <p className="verify-text">
                {t('auth.enterCorporateEmail')}
              </p>

              <div className="input-group">
                <label>{t('auth.corporateEmail')}</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t('auth.corporateEmailPlaceholder')}
                  autoComplete="email"
                />
              </div>

              <motion.button
                type="submit"
                className="btn-primary"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {t('auth.continueWithSSO')}
              </motion.button>

              <button
                type="button"
                className="btn-link"
                onClick={() => setMode('login')}
              >
                ← {t('auth.backToLogin')}
              </button>
            </motion.form>
          )}
        </AnimatePresence>

        {/* Footer */}
        <div className="login-footer">
          <a href="#">{t('auth.termsOfService')}</a>
          <span>•</span>
          <a href="#">{t('auth.privacyPolicy')}</a>
        </div>
      </motion.div>

      <style>{`
        .login-container {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
          position: relative;
          overflow: hidden;
          background: var(--gradient-bg);
        }

        .login-controls {
          position: fixed;
          top: 20px;
          right: 20px;
          display: flex;
          gap: 8px;
          z-index: 100;
        }

        .login-bg {
          position: fixed;
          inset: 0;
          z-index: -1;
        }

        .gradient-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          opacity: 0.5;
          animation: float 20s infinite ease-in-out;
        }

        .orb-1 {
          width: 600px;
          height: 600px;
          background: radial-gradient(circle, rgba(99, 102, 241, 0.4) 0%, transparent 70%);
          top: -200px;
          right: -100px;
          animation-delay: 0s;
        }

        .orb-2 {
          width: 500px;
          height: 500px;
          background: radial-gradient(circle, rgba(139, 92, 246, 0.3) 0%, transparent 70%);
          bottom: -150px;
          left: -100px;
          animation-delay: -7s;
        }

        .orb-3 {
          width: 400px;
          height: 400px;
          background: radial-gradient(circle, rgba(59, 130, 246, 0.3) 0%, transparent 70%);
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          animation-delay: -14s;
        }

        @keyframes float {
          0%, 100% { transform: translate(0, 0) scale(1); }
          25% { transform: translate(30px, -30px) scale(1.05); }
          50% { transform: translate(-20px, 20px) scale(0.95); }
          75% { transform: translate(-30px, -20px) scale(1.02); }
        }

        .login-card {
          width: 100%;
          max-width: 420px;
          background: var(--color-bg-card);
          backdrop-filter: blur(20px);
          border: 1px solid var(--color-border);
          border-radius: 24px;
          padding: 40px;
          box-shadow: var(--shadow-xl);
        }

        .login-header {
          text-align: center;
          margin-bottom: 32px;
        }

        .logo {
          width: 64px;
          height: 64px;
          margin: 0 auto 16px;
          background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 8px 32px rgba(99, 102, 241, 0.3);
        }

        .logo-icon {
          font-size: 28px;
          font-weight: 700;
          color: white;
        }

        .login-header h1 {
          font-size: 28px;
          font-weight: 700;
          color: var(--color-text-primary);
          margin: 0 0 4px;
          letter-spacing: -0.5px;
        }

        .subtitle {
          font-size: 14px;
          color: var(--color-text-secondary);
          margin: 0;
        }

        .auth-tabs {
          display: flex;
          gap: 8px;
          margin-bottom: 24px;
          background: var(--color-bg-hover);
          padding: 4px;
          border-radius: 12px;
        }

        .tab {
          flex: 1;
          padding: 10px;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: var(--color-text-secondary);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }

        .tab.active {
          background: var(--color-primary);
          color: var(--color-text-inverse);
        }

        .tab:hover:not(.active) {
          color: var(--color-text-primary);
        }

        .message {
          padding: 12px 16px;
          border-radius: 10px;
          margin-bottom: 16px;
          font-size: 13px;
          overflow: hidden;
        }

        .message.error {
          background: var(--color-error-light);
          border: 1px solid var(--color-error);
          color: var(--color-error);
        }

        .message.success {
          background: var(--color-success-light);
          border: 1px solid var(--color-success);
          color: var(--color-success);
        }

        .auth-form {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .input-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .input-group label {
          font-size: 13px;
          font-weight: 500;
          color: var(--color-text-secondary);
        }

        .input-group input {
          padding: 14px 16px;
          background: var(--color-bg-input);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          color: var(--color-text-primary);
          font-size: 15px;
          transition: all 0.2s;
        }

        .input-group input::placeholder {
          color: var(--color-text-muted);
        }

        .input-group input:focus {
          outline: none;
          border-color: var(--color-border-focus);
          box-shadow: 0 0 0 3px var(--focus-ring-color);
        }

        .code-input {
          text-align: center;
          font-size: 24px !important;
          letter-spacing: 8px;
          font-weight: 600;
        }

        .btn-primary {
          padding: 14px 24px;
          background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
          border: none;
          border-radius: 12px;
          color: white;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          min-height: 48px;
        }

        .btn-primary:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
        }

        .btn-primary:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .spinner {
          width: 20px;
          height: 20px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .divider {
          display: flex;
          align-items: center;
          gap: 16px;
          color: var(--color-text-muted);
          font-size: 13px;
        }

        .divider::before,
        .divider::after {
          content: '';
          flex: 1;
          height: 1px;
          background: var(--color-border);
        }

        .social-buttons {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .btn-google {
          padding: 12px 24px;
          background: white;
          border: 1px solid #dadce0;
          border-radius: 12px;
          color: #3c4043;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          transition: all 0.2s;
          width: 100%;
        }

        .btn-google:hover {
          background: #f8f9fa;
          border-color: #dadce0;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .google-icon {
          flex-shrink: 0;
        }

        [data-theme="dark"] .btn-google {
          background: #131314;
          border-color: #5f6368;
          color: #e8eaed;
        }

        [data-theme="dark"] .btn-google:hover {
          background: #222326;
          border-color: #8e918f;
        }

        .btn-sso {
          padding: 12px 24px;
          background: var(--color-bg-hover);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          color: var(--color-text-primary);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          transition: all 0.2s;
        }

        .btn-sso:hover {
          background: var(--color-bg-active);
          border-color: var(--color-border-focus);
        }

        .sso-icon {
          font-size: 18px;
        }

        .verify-icon {
          font-size: 48px;
          text-align: center;
          margin-bottom: 8px;
        }

        .verify-text {
          text-align: center;
          color: var(--color-text-secondary);
          font-size: 14px;
          line-height: 1.6;
          margin-bottom: 8px;
        }

        .verify-text strong {
          color: var(--color-primary);
        }

        .hint {
          text-align: center;
          font-size: 12px;
          color: var(--color-text-muted);
          margin: 0;
        }

        .btn-link {
          background: none;
          border: none;
          color: var(--color-text-muted);
          font-size: 13px;
          cursor: pointer;
          padding: 8px;
          transition: color 0.2s;
        }

        .btn-link:hover {
          color: var(--color-text-primary);
        }

        .login-footer {
          margin-top: 32px;
          padding-top: 20px;
          border-top: 1px solid var(--color-border);
          display: flex;
          justify-content: center;
          gap: 16px;
          font-size: 12px;
        }

        .login-footer a {
          color: var(--color-text-muted);
          text-decoration: none;
          transition: color 0.2s;
        }

        .login-footer a:hover {
          color: var(--color-text-primary);
        }

        .login-footer span {
          color: var(--color-text-muted);
        }

        @media (prefers-reduced-motion: reduce) {
          .gradient-orb {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
};

export default LoginPage;
