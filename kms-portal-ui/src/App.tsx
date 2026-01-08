/**
 * App Component
 *
 * Main application component with routing and providers
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { I18nProvider } from './i18n/I18nContext';
import { useAuthStore } from './store/authStore';

// Layouts
import { MainLayout } from './layouts/MainLayout';
import { AuthLayout } from './layouts/AuthLayout';

// Pages
import { LoginPage } from './pages/LoginPage';
import { HomePage } from './pages/HomePage';
import { KnowledgeBasePage } from './pages/KnowledgeBasePage';
import { ArticleDetailPage } from './pages/ArticleDetailPage';
import { IMSPage } from './pages/IMSPage';
import { AIStudioPage } from './pages/AIStudioPage';
import { ExternalPortalPage } from './pages/ExternalPortalPage';
import { FAQPage } from './pages/FAQPage';
import { SettingsPage } from './pages/SettingsPage';

// Import global styles
import './styles/index.css';

/**
 * Protected Route Guard
 * Redirects to login if not authenticated
 */
const ProtectedRoute: React.FC = () => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
};

/**
 * Public Route Guard
 * Redirects to home if already authenticated
 */
const PublicRoute: React.FC = () => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
};

/**
 * Placeholder page for unimplemented routes
 */
const PlaceholderPage: React.FC<{ title: string }> = ({ title }) => (
  <div className="placeholder-page">
    <div className="placeholder-content">
      <h1>{title}</h1>
      <p>This page is under construction.</p>
      <p>Check back soon for updates!</p>
    </div>
  </div>
);

/**
 * Main App Component
 */
export const App: React.FC = () => {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes (login, etc.) */}
          <Route element={<PublicRoute />}>
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<LoginPage />} />
            </Route>
          </Route>

          {/* Protected routes */}
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              {/* Home/Dashboard */}
              <Route path="/" element={<HomePage />} />

              {/* Knowledge Base (Phase 2) */}
              <Route path="/knowledge" element={<KnowledgeBasePage />} />
              <Route path="/knowledge/:articleId" element={<ArticleDetailPage />} />

              {/* IMS (Phase 3) */}
              <Route path="/ims" element={<IMSPage />} />

              {/* AI Studio / Mindmap (Phase 5) */}
              <Route path="/mindmap" element={<AIStudioPage />} />

              {/* FAQ */}
              <Route path="/faq" element={<FAQPage />} />

              {/* Documents */}
              <Route path="/documents" element={<PlaceholderPage title="Documents" />} />

              {/* Analytics */}
              <Route path="/analytics" element={<PlaceholderPage title="Analytics" />} />

              {/* Admin */}
              <Route path="/admin" element={<PlaceholderPage title="Admin Dashboard" />} />

              {/* Settings */}
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>

          {/* External Portal (Phase 6) - Separate layout without AI sidebar */}
          <Route path="/portal" element={<ExternalPortalPage />} />
          <Route path="/portal/*" element={<ExternalPortalPage />} />

          {/* 404 - Redirect to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </I18nProvider>
  );
};

export default App;
