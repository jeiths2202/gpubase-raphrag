/**
 * Agent Page
 *
 * Full-page AI Agent chat interface.
 */

import React from 'react';
import { AgentChat } from '../components/AgentChat';
import { useSimplePageContext } from '../hooks/usePageContext';
import './AgentPage.css';

export const AgentPage: React.FC = () => {
  // Register page context for AI awareness
  useSimplePageContext(['agent-chat', 'artifacts', 'conversations']);

  return (
    <div className="agent-page">
      <AgentChat />
    </div>
  );
};

export default AgentPage;
