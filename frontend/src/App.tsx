import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import LoginPage from './pages/LoginPage';
import MainDashboard from './pages/MainDashboard';
import MindmapApp from './pages/MindmapApp';
import AdminDashboard from './pages/AdminDashboard';
import KnowledgeApp from './pages/KnowledgeApp';
import { useAuthStore } from './store/authStore';
import { usePreferencesStore, initializeThemeListener } from './store/preferencesStore';
import { I18nProvider } from './i18n/I18nContext';
import { useTranslation } from './hooks/useTranslation';
import { GOOGLE_CLIENT_ID } from './config/constants';

// Check if Google OAuth is configured
const isGoogleConfigured = !!GOOGLE_CLIENT_ID;

// Conditional wrapper for Google OAuth
const GoogleOAuthWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (isGoogleConfigured) {
    return <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{children}</GoogleOAuthProvider>;
  }
  return <>{children}</>;
};

// Protected Route component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, checkAuth } = useAuthStore();
  const { loadPreferences } = usePreferencesStore();
  const { t } = useTranslation();
  const [isChecking, setIsChecking] = React.useState(true);

  useEffect(() => {
    const verifyAuth = async () => {
      const authenticated = await checkAuth();
      // Load user preferences from server if authenticated
      if (authenticated) {
        await loadPreferences();
      }
      setIsChecking(false);
    };
    verifyAuth();
  }, [checkAuth, loadPreferences]);

  if (isChecking) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'var(--color-bg-primary)',
        color: 'var(--color-text-primary)',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div className="loading" style={{ fontSize: '24px', marginBottom: '16px' }}>
            {t('common.loading')}
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Public Route - redirect to app if already authenticated
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

const App: React.FC = () => {
  // Initialize theme listener for system preference changes
  useEffect(() => {
    const cleanup = initializeThemeListener();
    return cleanup;
  }, []);

  return (
    <GoogleOAuthWrapper>
      <I18nProvider>
        <BrowserRouter>
          <Routes>
          {/* Public routes */}
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />

          {/* Protected routes */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainDashboard />
              </ProtectedRoute>
            }
          />

          {/* Knowledge search route */}
          <Route
            path="/knowledge"
            element={
              <ProtectedRoute>
                <KnowledgeApp />
              </ProtectedRoute>
            }
          />

          {/* Mindmap route */}
          <Route
            path="/mindmap"
            element={
              <ProtectedRoute>
                <MindmapApp />
              </ProtectedRoute>
            }
          />

          {/* Admin routes */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute>
                <AdminDashboard />
              </ProtectedRoute>
            }
          />

          {/* Catch all - redirect to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </BrowserRouter>
      </I18nProvider>
    </GoogleOAuthWrapper>
  );
};

export default App;
