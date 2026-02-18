/**
 * Main Layout Component
 *
 * ChatGPT-style 3-column layout with responsive sidebar.
 *
 * Layout Behavior:
 * - Desktop (> 1024px): Sidebar pushes content, open by default
 * - Mobile/Tablet (<= 1024px): Sidebar overlays content, closed by default
 *
 * Features:
 * - Smooth slide animations for sidebar
 * - Floating open button when sidebar is closed
 * - Backdrop overlay on mobile
 * - No layout jump during transitions
 */

import React, { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { SidebarToggleButton } from '../components/SidebarToggleButton';
import { AISidebar } from '../components/AISidebar';
import { useUIStore } from '../store/uiStore';

// Routes where AISidebar should be hidden (they have their own chat interface)
const HIDE_AI_SIDEBAR_ROUTES = ['/openframe-rag', '/open-agent', '/agentic-rag', '/legacy-modernization'];

// Breakpoint for mobile/tablet detection
const MOBILE_BREAKPOINT = 1024;

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const {
    leftSidebarOpen,
    rightSidebarOpen,
    setIsMobile,
    isMobile,
    setLeftSidebarOpen,
  } = useUIStore();

  // Check if current route should hide AISidebar
  const hideAISidebar = HIDE_AI_SIDEBAR_ROUTES.some(route => location.pathname.startsWith(route));

  // Handle window resize and set initial state based on screen size
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT;
      const wasMobile = isMobile;

      setIsMobile(mobile);

      // When transitioning from desktop to mobile, close sidebar
      // When transitioning from mobile to desktop, open sidebar
      if (mobile !== wasMobile) {
        setLeftSidebarOpen(!mobile);
      }
    };

    // Initial check
    const isInitialMobile = window.innerWidth < MOBILE_BREAKPOINT;
    setIsMobile(isInitialMobile);
    // Set initial sidebar state: open on desktop, closed on mobile
    setLeftSidebarOpen(!isInitialMobile);

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []); // Only run on mount

  // Close sidebar when clicking overlay on mobile
  const handleOverlayClick = () => {
    if (isMobile && leftSidebarOpen) {
      setLeftSidebarOpen(false);
    }
  };

  // Calculate layout classes for CSS transitions
  const layoutClass = [
    'portal-layout',
    leftSidebarOpen ? 'sidebar-open' : 'sidebar-closed',
    rightSidebarOpen ? 'right-open' : 'right-closed',
    isMobile ? 'is-mobile' : 'is-desktop',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={layoutClass}>
      {/* Header */}
      <Header showAISidebarToggle={!hideAISidebar} />

      {/* Sidebar Open Button - Shows when sidebar is closed */}
      <SidebarToggleButton />

      {/* Main container */}
      <div className="portal-container">
        {/* Left Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <main className="portal-content">
          <Outlet />
        </main>

        {/* AI Sidebar (Right) - Hidden on pages with their own chat interface */}
        {!hideAISidebar && <AISidebar />}
      </div>

      {/* Mobile overlay backdrop - click to close sidebar */}
      {isMobile && leftSidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={handleOverlayClick}
          aria-hidden="true"
        />
      )}
    </div>
  );
};

export default MainLayout;
