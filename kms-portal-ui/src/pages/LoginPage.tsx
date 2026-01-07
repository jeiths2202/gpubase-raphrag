/**
 * Login Page
 *
 * Authentication page with user/password and Google OAuth options
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogIn, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';

export const LoginPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login, loginWithGoogle, isLoading, error, clearError } = useAuthStore();

  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    if (!userId || !password) {
      return;
    }

    try {
      await login(userId, password);
      navigate('/');
    } catch (err) {
      // Error is handled by store
    }
  };

  // Handle Google login
  const handleGoogleLogin = async () => {
    clearError();
    try {
      await loginWithGoogle();
      navigate('/');
    } catch (err) {
      // Error is handled by store
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-icon">K</div>
        </div>

        {/* Title */}
        <div className="login-header">
          <h1 className="login-title">{t('auth.loginTitle')}</h1>
          <p className="login-subtitle">{t('auth.loginSubtitle')}</p>
        </div>

        {/* Error message */}
        {error && (
          <div className="login-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Login form */}
        <form className="login-form" onSubmit={handleSubmit}>
          {/* User ID */}
          <div className="login-field">
            <label htmlFor="userId" className="login-label">
              {t('auth.userId')}
            </label>
            <input
              type="text"
              id="userId"
              className="input login-input"
              placeholder={t('auth.userIdPlaceholder')}
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              disabled={isLoading}
              autoComplete="username"
            />
          </div>

          {/* Password */}
          <div className="login-field">
            <label htmlFor="password" className="login-label">
              {t('auth.password')}
            </label>
            <div className="login-password-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                id="password"
                className="input login-input"
                placeholder={t('auth.passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="login-password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Remember me & Forgot password */}
          <div className="login-options">
            <label className="login-checkbox">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              <span>{t('auth.rememberMe')}</span>
            </label>
            <a href="#" className="login-forgot">
              {t('auth.forgotPassword')}
            </a>
          </div>

          {/* Submit button */}
          <button type="submit" className="btn btn-primary login-submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 size={18} className="spin" />
                <span>{t('auth.loggingIn')}</span>
              </>
            ) : (
              <>
                <LogIn size={18} />
                <span>{t('auth.signIn')}</span>
              </>
            )}
          </button>
        </form>

        {/* Divider */}
        <div className="login-divider">
          <span>{t('auth.orContinueWith')}</span>
        </div>

        {/* Social login */}
        <div className="login-social">
          <button
            type="button"
            className="btn btn-secondary login-social-btn"
            onClick={handleGoogleLogin}
            disabled={isLoading}
          >
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span>{t('auth.googleLogin')}</span>
          </button>

          <button
            type="button"
            className="btn btn-secondary login-social-btn"
            disabled={isLoading}
          >
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="currentColor"
                d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"
              />
            </svg>
            <span>{t('auth.corporateSSO')}</span>
          </button>
        </div>

        {/* Demo credentials hint */}
        <div className="login-demo-hint">
          <p>Demo credentials:</p>
          <code>admin / admin123</code> or <code>user / user123</code>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
