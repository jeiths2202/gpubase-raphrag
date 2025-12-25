import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { GoogleLogin } from '@react-oauth/google';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { isCorpEmail, APP_CONFIG } from '../config/constants';

type AuthMode = 'login' | 'register' | 'verify' | 'forgot';

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
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
      setLocalError('Please enter your ID and password');
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
      setLocalError('Please fill in all fields');
      return;
    }

    if (password !== confirmPassword) {
      setLocalError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters');
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
        setSuccessMessage('Verification code sent to your email');
        setMode('verify');
      } else {
        setLocalError(data.detail?.message || 'Registration failed');
      }
    } catch {
      setLocalError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (!verificationCode) {
      setLocalError('Please enter verification code');
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
        setSuccessMessage('Account verified! You can now login.');
        setTimeout(() => {
          setMode('login');
          setSuccessMessage('');
        }, 2000);
      } else {
        setLocalError(data.detail?.message || 'Verification failed');
      }
    } catch {
      setLocalError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGoogleSuccess = async (credentialResponse: { credential?: string }) => {
    if (credentialResponse.credential) {
      const success = await loginWithGoogle(credentialResponse.credential);
      if (success) {
        navigate('/');
      }
    }
  };

  const handleSSOLogin = () => {
    if (isCorpEmail(email)) {
      // Redirect to SSO
      window.location.href = `/api/v1/auth/sso/initiate?email=${encodeURIComponent(email)}`;
    } else {
      setLocalError('Please enter a valid corporate email');
    }
  };

  const displayError = localError || error;

  return (
    <div className="login-container">
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
            Sign In
          </button>
          <button
            className={`tab ${mode === 'register' || mode === 'verify' ? 'active' : ''}`}
            onClick={() => { setMode('register'); clearError(); setLocalError(''); }}
          >
            Register
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
                <label>User ID</label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder="Enter your user ID"
                  autoComplete="username"
                />
              </div>

              <div className="input-group">
                <label>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
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
                {isLoading ? <span className="spinner" /> : 'Sign In'}
              </motion.button>

              <div className="divider">
                <span>or continue with</span>
              </div>

              <div className="social-buttons">
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={() => setLocalError('Google login failed')}
                  theme="filled_black"
                  shape="pill"
                  size="large"
                  text="continue_with"
                  width="100%"
                />

                <motion.button
                  type="button"
                  className="btn-sso"
                  onClick={() => setMode('forgot')}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <span className="sso-icon">🏢</span>
                  Corporate SSO
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
                <label>User ID</label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder="Choose a user ID"
                  autoComplete="username"
                />
              </div>

              <div className="input-group">
                <label>Email (for verification)</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  autoComplete="email"
                />
              </div>

              <div className="input-group">
                <label>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                />
              </div>

              <div className="input-group">
                <label>Confirm Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
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
                {isSubmitting ? <span className="spinner" /> : 'Create Account'}
              </motion.button>

              <p className="hint">
                A verification code will be sent to your email
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
                We sent a verification code to<br />
                <strong>{email}</strong>
              </p>

              <div className="input-group">
                <label>Verification Code</label>
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value)}
                  placeholder="Enter 6-digit code"
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
                {isSubmitting ? <span className="spinner" /> : 'Verify Email'}
              </motion.button>

              <button
                type="button"
                className="btn-link"
                onClick={() => setMode('register')}
              >
                ← Back to registration
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
                Enter your corporate email to sign in with SSO
              </p>

              <div className="input-group">
                <label>Corporate Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  autoComplete="email"
                />
              </div>

              <motion.button
                type="submit"
                className="btn-primary"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Continue with SSO
              </motion.button>

              <button
                type="button"
                className="btn-link"
                onClick={() => setMode('login')}
              >
                ← Back to login
              </button>
            </motion.form>
          )}
        </AnimatePresence>

        {/* Footer */}
        <div className="login-footer">
          <a href="#">Terms of Service</a>
          <span>•</span>
          <a href="#">Privacy Policy</a>
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
        }

        .login-bg {
          position: fixed;
          inset: 0;
          background: linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #0f0f23 100%);
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
          background: rgba(255, 255, 255, 0.03);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 24px;
          padding: 40px;
          box-shadow:
            0 4px 24px rgba(0, 0, 0, 0.2),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset;
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
          color: #fff;
          margin: 0 0 4px;
          letter-spacing: -0.5px;
        }

        .subtitle {
          font-size: 14px;
          color: rgba(255, 255, 255, 0.5);
          margin: 0;
        }

        .auth-tabs {
          display: flex;
          gap: 8px;
          margin-bottom: 24px;
          background: rgba(255, 255, 255, 0.05);
          padding: 4px;
          border-radius: 12px;
        }

        .tab {
          flex: 1;
          padding: 10px;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }

        .tab.active {
          background: rgba(99, 102, 241, 0.2);
          color: #a5b4fc;
        }

        .tab:hover:not(.active) {
          color: rgba(255, 255, 255, 0.8);
        }

        .message {
          padding: 12px 16px;
          border-radius: 10px;
          margin-bottom: 16px;
          font-size: 13px;
          overflow: hidden;
        }

        .message.error {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5;
        }

        .message.success {
          background: rgba(34, 197, 94, 0.15);
          border: 1px solid rgba(34, 197, 94, 0.3);
          color: #86efac;
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
          color: rgba(255, 255, 255, 0.7);
        }

        .input-group input {
          padding: 14px 16px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          color: #fff;
          font-size: 15px;
          transition: all 0.2s;
        }

        .input-group input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .input-group input:focus {
          outline: none;
          border-color: rgba(99, 102, 241, 0.5);
          background: rgba(99, 102, 241, 0.05);
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
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
          color: rgba(255, 255, 255, 0.3);
          font-size: 13px;
        }

        .divider::before,
        .divider::after {
          content: '';
          flex: 1;
          height: 1px;
          background: rgba(255, 255, 255, 0.1);
        }

        .social-buttons {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .btn-sso {
          padding: 12px 24px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          color: rgba(255, 255, 255, 0.8);
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
          background: rgba(255, 255, 255, 0.08);
          border-color: rgba(255, 255, 255, 0.15);
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
          color: rgba(255, 255, 255, 0.7);
          font-size: 14px;
          line-height: 1.6;
          margin-bottom: 8px;
        }

        .verify-text strong {
          color: #a5b4fc;
        }

        .hint {
          text-align: center;
          font-size: 12px;
          color: rgba(255, 255, 255, 0.4);
          margin: 0;
        }

        .btn-link {
          background: none;
          border: none;
          color: rgba(255, 255, 255, 0.5);
          font-size: 13px;
          cursor: pointer;
          padding: 8px;
          transition: color 0.2s;
        }

        .btn-link:hover {
          color: rgba(255, 255, 255, 0.8);
        }

        .login-footer {
          margin-top: 32px;
          padding-top: 20px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          justify-content: center;
          gap: 16px;
          font-size: 12px;
        }

        .login-footer a {
          color: rgba(255, 255, 255, 0.4);
          text-decoration: none;
          transition: color 0.2s;
        }

        .login-footer a:hover {
          color: rgba(255, 255, 255, 0.7);
        }

        .login-footer span {
          color: rgba(255, 255, 255, 0.2);
        }

        /* Google button override */
        .social-buttons > div {
          width: 100% !important;
        }

        .social-buttons iframe {
          width: 100% !important;
        }
      `}</style>
    </div>
  );
};

export default LoginPage;
