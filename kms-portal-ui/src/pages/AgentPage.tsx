/**
 * Agent Page
 *
 * Full-page AI Agent chat interface.
 */

import React from 'react';
import { AgentChat } from '../components/AgentChat';
import './AgentPage.css';

export const AgentPage: React.FC = () => {
  return (
    <div className="agent-page">
      <AgentChat />
    </div>
  );
};

export default AgentPage;
