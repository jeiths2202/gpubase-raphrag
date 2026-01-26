/**
 * SidebarToggleButton Component
 *
 * ChatGPT-style floating button to open the sidebar when it's closed.
 * Appears on the left side of the screen when sidebar is hidden.
 *
 * Features:
 * - Keyboard accessible (Tab, Enter, Space)
 * - ARIA attributes for screen readers
 * - Smooth hover/focus animations
 */

import React from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useUIStore } from '../store/uiStore';

export const SidebarToggleButton: React.FC = () => {
  const { t } = useTranslation();
  const { leftSidebarOpen, setLeftSidebarOpen } = useUIStore();

  // Only show when sidebar is closed
  if (leftSidebarOpen) {
    return null;
  }

  const handleOpen = () => {
    setLeftSidebarOpen(true);
  };

  // Handle keyboard events for accessibility
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleOpen();
    }
  };

  return (
    <button
      className="sidebar-open-button"
      onClick={handleOpen}
      onKeyDown={handleKeyDown}
      aria-label={t('common.expandSidebar')}
      aria-expanded={false}
      aria-controls="main-sidebar"
      title={t('common.expandSidebar')}
      tabIndex={0}
    >
      <img src="/tmax-logo.png" alt="Tmax Logo" className="sidebar-open-logo" />
    </button>
  );
};

export default SidebarToggleButton;
