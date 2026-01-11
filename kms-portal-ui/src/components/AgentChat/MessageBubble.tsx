/**
 * MessageBubble Component
 * Renders individual chat messages with support for user, assistant, and status messages.
 */

import React from 'react';
import {
  Bot,
  User,
  Wrench,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  Search,
  FileText,
  AlertCircle,
  Database,
  Loader2,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import { MessageContent } from './MessageContent';
import { AGENT_CONFIGS } from './constants';
import type { ChatMessage } from './types';

interface MessageBubbleProps {
  message: ChatMessage;
  onCopy: (content: string, messageId: string) => void;
  copiedMessageId: string | null;
  onCancel?: () => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onCopy,
  copiedMessageId,
  onCancel,
}) => {
  const { t } = useTranslation();
  const isUser = message.role === 'user';
  const isStatus = message.role === 'status';
  const agentConfig = message.agentType ? AGENT_CONFIGS[message.agentType] : null;
  const AgentIcon = agentConfig?.icon || Bot;

  // Render status message differently
  if (isStatus) {
    // Translate status key using i18n
    const statusKey = message.content as 'crawling' | 'ready' | 'searching' | 'processing';
    const translatedMessage = t(`common.agent.status.${statusKey}`) || message.content;

    // Get appropriate icon based on status
    const getStatusIcon = () => {
      switch (statusKey) {
        case 'crawling':
        case 'processing':
          return <Loader2 size={18} className="spin" />;
        case 'searching':
          return <Search size={18} className="pulse" />;
        case 'ready':
          return <CheckCircle2 size={18} />;
        default:
          return <Database size={18} />;
      }
    };

    return (
      <div className={`agent-status-message ${message.statusType || ''} ${statusKey}`}>
        <div className="agent-status-icon">
          {getStatusIcon()}
        </div>
        <div className="agent-status-content">
          <span>{translatedMessage}</span>
          {(statusKey === 'crawling' || statusKey === 'processing' || statusKey === 'searching') && (
            <span className="agent-status-dots">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`agent-message ${message.role} ${message.isStreaming ? 'streaming' : ''}`}>
      {/* Avatar */}
      <div className="agent-message-avatar">
        {isUser ? <User size={18} /> : <AgentIcon size={18} />}
      </div>

      {/* Content */}
      <div className="agent-message-content">
        {/* Agent type badge */}
        {!isUser && agentConfig && (
          <div className="agent-message-badge">
            <AgentIcon size={12} />
            <span>{agentConfig.label}</span>
          </div>
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="agent-tool-calls">
            {message.toolCalls.map((tool, idx) => (
              <div key={idx} className={`agent-tool-call ${tool.status}`}>
                <div className="agent-tool-call-header">
                  <Wrench size={14} />
                  <span className="agent-tool-call-name">{tool.name}</span>
                  {tool.status === 'pending' && <Loader2 size={14} className="spin" />}
                  {tool.status === 'success' && <CheckCircle2 size={14} />}
                  {tool.status === 'error' && <XCircle size={14} />}
                </div>
                {tool.input && Object.keys(tool.input).length > 0 && (
                  <div className="agent-tool-call-input">
                    <code>{JSON.stringify(tool.input, null, 2)}</code>
                  </div>
                )}
                {tool.output && (
                  <div className="agent-tool-call-output">
                    <span>{tool.output.substring(0, 200)}{tool.output.length > 200 ? '...' : ''}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message text */}
        <div className="agent-message-text">
          {message.error ? (
            <div className="agent-message-error">
              <AlertCircle size={16} />
              <span>{message.content}</span>
            </div>
          ) : (
            <MessageContent content={message.content} />
          )}
          {message.isStreaming && <span className="agent-typing-cursor" />}
        </div>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="agent-message-sources">
            <span className="agent-sources-label">Sources:</span>
            {message.sources.map((source, idx) => (
              <div key={idx} className="agent-source-item">
                <FileText size={12} />
                <span>{source.source}</span>
                <span className="agent-source-score">{Math.round(source.score * 100)}%</span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        {!isUser && !message.isStreaming && (
          <div className="agent-message-actions">
            <button
              className={`agent-message-action ${copiedMessageId === message.id ? 'copied' : ''}`}
              onClick={() => onCopy(message.content, message.id)}
              title="Copy"
            >
              {copiedMessageId === message.id ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        )}

        {/* Cancel button for streaming */}
        {message.isStreaming && onCancel && (
          <button className="agent-message-cancel" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
