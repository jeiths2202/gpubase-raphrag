/**
 * Main Layout Component
 *
 * 3-column layout with left sidebar, main content, and AI sidebar
 * Based on Zendesk + NotebookLM hybrid design
 */

import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { AISidebar } from '../components/AISidebar';
import { useUIStore } from '../store/uiStore';

// Breakpoint for mobile detection
const MOBILE_BREAKPOINT = 1024;

export const MainLayout: React.FC = () => {
  const { leftSidebarOpen, rightSidebarOpen, setIsMobile, isMobile, toggleLeftSidebar } =
    useUIStore();

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT;
      setIsMobile(mobile);
    };

    // Initial check
    handleResize();

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [setIsMobile]);

  // Calculate layout class
  const layoutClass = [
    'portal-layout',
    leftSidebarOpen ? 'left-open' : 'left-collapsed',
    rightSidebarOpen ? 'right-open' : 'right-closed',
    isMobile ? 'mobile' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={layoutClass}>
      {/* Header */}
      <Header onMenuClick={isMobile ? toggleLeftSidebar : undefined} showAISidebarToggle={true} />

      {/* Main container */}
      <div className="portal-container">
        {/* Left Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <main className="portal-content">
          <Outlet />
        </main>

        {/* AI Sidebar (Right) */}
        <AISidebar />
      </div>

      {/* Mobile overlay */}
      {isMobile && leftSidebarOpen && (
        <div className="portal-overlay" onClick={toggleLeftSidebar} aria-hidden="true" />
      )}
    </div>
  );
};

export default MainLayout;
