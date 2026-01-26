/**
 * Agent Page
 *
 * Full-page AI Agent chat interface with floating window support.
 */

import React, { useEffect } from 'react';
import { AgentChat } from '../components/AgentChat';
import { FloatingChatWindow, MinimizedWindowButton } from '../components/FloatingChatWindow';
import { useSimplePageContext } from '../hooks/usePageContext';
import { usePreferencesStore } from '../store/preferencesStore';
import { useFloatingChatStore } from '../store/floatingChatStore';
import { Plus, X, Monitor } from 'lucide-react';
import './AgentPage.css';

export const AgentPage: React.FC = () => {
  // Register page context for AI awareness
  useSimplePageContext(['agent-chat', 'artifacts', 'conversations']);

  // Preferences store for display mode
  const { directModeDisplay, setDirectModeDisplay } = usePreferencesStore();

  // Floating chat windows store
  const {
    windows,
    createWindow,
    closeWindow,
    closeAllWindows,
    minimizeWindow,
    restoreWindow,
    bringToFront,
    updatePosition,
    updateSize,
    updateTitle,
  } = useFloatingChatStore();

  // Create initial window when entering floating mode
  useEffect(() => {
    if (directModeDisplay === 'floating' && windows.length === 0) {
      createWindow('auto', 'AI Chat');
    }
  }, [directModeDisplay, windows.length, createWindow]);

  // Handle new chat window
  const handleNewWindow = () => {
    console.log('[AgentPage] Creating new window, current count:', windows.length);
    const newId = createWindow('auto', 'New Chat');
    console.log('[AgentPage] New window created with id:', newId);
  };

  // Handle exit floating mode
  const handleExitFloating = () => {
    console.log('[AgentPage] Exiting floating mode');
    closeAllWindows();
    setDirectModeDisplay('inline');
  };

  // Inline mode - standard layout
  if (directModeDisplay === 'inline') {
    return (
      <div className="agent-page">
        <AgentChat />
      </div>
    );
  }

  // Floating mode - windows layout
  const minimizedWindows = windows.filter(w => w.isMinimized);
  const visibleWindows = windows.filter(w => !w.isMinimized);

  // Debug logging
  console.log('[AgentPage] Floating mode render:', {
    totalWindows: windows.length,
    minimized: minimizedWindows.length,
    visible: visibleWindows.length,
    showTaskbar: minimizedWindows.length > 0 || visibleWindows.length > 0,
  });

  return (
    <div className="agent-page floating-mode">
      {/* Top toolbar - always visible */}
      <div className="floating-mode-toolbar">
        <div className="floating-mode-toolbar-title">Floating Mode</div>
        <div className="floating-mode-toolbar-actions">
          <button className="floating-mode-new-btn" onClick={handleNewWindow}>
            <Plus size={16} />
            New Window
          </button>
          <button
            className="floating-mode-exit-btn"
            onClick={handleExitFloating}
          >
            <Monitor size={16} />
            Exit
          </button>
        </div>
      </div>

      {/* Background for empty state */}
      <div className="floating-mode-background">
        {windows.length === 0 && (
          <div className="floating-mode-hint">
            <p>No chat windows open</p>
            <button className="floating-mode-new-btn" onClick={handleNewWindow}>
              <Plus size={16} />
              New Chat Window
            </button>
          </div>
        )}
      </div>

      {/* Floating windows */}
      <div className="floating-windows-container">
        {visibleWindows.map((windowData) => (
          <FloatingChatWindow
            key={windowData.id}
            windowData={windowData}
            onClose={closeWindow}
            onMinimize={minimizeWindow}
            onBringToFront={bringToFront}
            onUpdatePosition={updatePosition}
            onUpdateSize={updateSize}
            onUpdateTitle={updateTitle}
            onNewWindow={handleNewWindow}
            onExitFloating={handleExitFloating}
          >
            <AgentChat
              windowId={windowData.id}
              isFloatingWindow={true}
            />
          </FloatingChatWindow>
        ))}
      </div>

      {/* Taskbar for minimized windows */}
      {(minimizedWindows.length > 0 || visibleWindows.length > 0) && (
        <div className="floating-taskbar">
          <button
            className="floating-taskbar-new"
            onClick={(e) => {
              e.stopPropagation();
              handleNewWindow();
            }}
            title="New Window"
          >
            <Plus size={16} />
          </button>

          {minimizedWindows.map((windowData) => (
            <MinimizedWindowButton
              key={windowData.id}
              windowData={windowData}
              onRestore={restoreWindow}
            />
          ))}

          {windows.length > 1 && (
            <button
              className="floating-taskbar-close-all"
              onClick={closeAllWindows}
              title="Close All"
            >
              <X size={14} />
            </button>
          )}

          <div className="floating-taskbar-divider" />

          <button
            className="floating-taskbar-exit"
            onClick={handleExitFloating}
            title="Exit Floating Mode"
          >
            <Monitor size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

export default AgentPage;
