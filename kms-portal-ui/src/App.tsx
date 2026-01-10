/**
 * App Component
 *
 * Main application component with routing and providers.
 * Uses enhanced route guards with session validation.
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { I18nProvider } from './i18n/I18nContext';
import { AuthProvider } from './providers';
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

// Route Guards
import { AuthGuard, PublicGuard } from './components/guards';

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
import { AgentPage } from './pages/AgentPage';

// Import global styles
import './styles/index.css';

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
    <GoogleOAuthWrapper>
      <I18nProvider>
        <AuthProvider>
          <BrowserRouter>
          <Routes>
          {/* Public routes (login, etc.) - redirects to home if authenticated */}
          <Route element={<PublicGuard />}>
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<LoginPage />} />
            </Route>
          </Route>

          {/* Protected routes - redirects to login if not authenticated */}
          <Route element={<AuthGuard />}>
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

              {/* AI Agent Chat */}
              <Route path="/agent" element={<AgentPage />} />

              {/* FAQ */}
              <Route path="/faq" element={<FAQPage />} />

              {/* Documents */}
              <Route path="/documents" element={<PlaceholderPage title="Documents" />} />

              {/* Analytics */}
              <Route path="/analytics" element={<PlaceholderPage title="Analytics" />} />

              {/* Settings */}
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>

          {/* Admin routes - requires admin role */}
          <Route element={<AuthGuard requiredRole="admin" />}>
            <Route element={<MainLayout />}>
              <Route path="/admin" element={<PlaceholderPage title="Admin Dashboard" />} />
            </Route>
          </Route>

          {/* External Portal (Phase 6) - Separate layout without AI sidebar */}
          <Route path="/portal" element={<ExternalPortalPage />} />
          <Route path="/portal/*" element={<ExternalPortalPage />} />

          {/* 404 - Redirect to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </BrowserRouter>
        </AuthProvider>
      </I18nProvider>
    </GoogleOAuthWrapper>
  );
};

export default App;
