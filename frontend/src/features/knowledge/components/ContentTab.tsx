// IMS Knowledge Service Tab
// AI Agent를 사용한 IMS지식 서비스

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  sourceUrl: string;
  createdAt: Date;
}

interface ContentTabProps {
  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const ContentTab: React.FC<ContentTabProps> = ({
  themeColors,
  cardStyle,
  t
}) => {
  // IMS URL connection state
  const [imsUrl, setImsUrl] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  // Knowledge items state
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);

  // Connect to IMS system via SSO
  const connectToIMS = async () => {
    if (!imsUrl.trim()) {
      setConnectionError(t('knowledge.imsKnowledge.connection.errors.emptyUrl' as keyof import('../../../i18n/types').TranslationKeys));
      return;
    }

    setConnecting(true);
    setConnectionError(null);

    try {
      // TODO: Implement SSO connection to IMS system
      // For now, simulate connection
      await new Promise(resolve => setTimeout(resolve, 1500));

      setIsConnected(true);
      setMessages([{
        id: Date.now().toString(),
        role: 'assistant',
        content: t('knowledge.imsKnowledge.connection.welcomeMessage' as keyof import('../../../i18n/types').TranslationKeys, { url: imsUrl }),
        timestamp: new Date()
      }]);
    } catch (error) {
      setConnectionError(t('knowledge.imsKnowledge.connection.errors.connectionFailed' as keyof import('../../../i18n/types').TranslationKeys));
      setIsConnected(false);
    } finally {
      setConnecting(false);
    }
  };

  // Disconnect from IMS
  const disconnectFromIMS = () => {
    setIsConnected(false);
    setMessages([]);
    setKnowledgeItems([]);
    setImsUrl('');
  };

  // Send message to AI Agent
  const sendMessage = async () => {
    if (!inputMessage.trim() || isGenerating) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsGenerating(true);

    try {
      // TODO: Implement AI Agent API call
      // For now, simulate AI response
      await new Promise(resolve => setTimeout(resolve, 2000));

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: t('knowledge.imsKnowledge.chat.assistantResponse' as keyof import('../../../i18n/types').TranslationKeys, { query: inputMessage }),
        timestamp: new Date()
      };

      setMessages(prev => [...prev, aiMessage]);

      // Create knowledge item
      const newKnowledge: KnowledgeItem = {
        id: Date.now().toString(),
        title: inputMessage.slice(0, 50),
        content: aiMessage.content,
        sourceUrl: imsUrl,
        createdAt: new Date()
      };

      setKnowledgeItems(prev => [newKnowledge, ...prev]);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: t('knowledge.imsKnowledge.chat.error' as keyof import('../../../i18n/types').TranslationKeys),
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsGenerating(false);
    }
  };

  // Save knowledge item
  const saveKnowledge = async (item: KnowledgeItem) => {
    // TODO: Implement save to backend
    alert(t('knowledge.imsKnowledge.knowledge.saveSuccess' as keyof import('../../../i18n/types').TranslationKeys, { title: item.title }));
  };

  return (
    <motion.div
      key="content"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '20px', overflow: 'auto' }}
    >
      {/* Header */}
      <div style={cardStyle}>
        <h2>{t('knowledge.imsKnowledge.header.title' as keyof import('../../../i18n/types').TranslationKeys)}</h2>
        <p style={{ color: themeColors.textSecondary, marginTop: '8px' }}>
          {t('knowledge.imsKnowledge.header.subtitle' as keyof import('../../../i18n/types').TranslationKeys)}
        </p>
      </div>

      {/* IMS Connection Section */}
      <div style={cardStyle}>
        <h3 style={{ marginBottom: '16px' }}>{t('knowledge.imsKnowledge.connection.title' as keyof import('../../../i18n/types').TranslationKeys)}</h3>

        {!isConnected ? (
          <div>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 600 }}>
                {t('knowledge.imsKnowledge.connection.urlLabel' as keyof import('../../../i18n/types').TranslationKeys)}
              </label>
              <input
                type="url"
                value={imsUrl}
                onChange={(e) => setImsUrl(e.target.value)}
                placeholder={t('knowledge.imsKnowledge.connection.urlPlaceholder' as keyof import('../../../i18n/types').TranslationKeys)}
                disabled={connecting}
                style={{
                  width: '100%',
                  padding: '12px',
                  background: themeColors.inputBg,
                  border: `1px solid ${themeColors.cardBorder}`,
                  borderRadius: '8px',
                  color: themeColors.text,
                  fontSize: '14px'
                }}
                onKeyPress={(e) => e.key === 'Enter' && connectToIMS()}
              />
            </div>

            {connectionError && (
              <div style={{
                padding: '12px',
                background: 'rgba(231, 76, 60, 0.1)',
                border: '1px solid #E74C3C',
                borderRadius: '8px',
                color: '#E74C3C',
                marginBottom: '12px'
              }}>
                {connectionError}
              </div>
            )}

            <button
              onClick={connectToIMS}
              disabled={connecting}
              style={{
                padding: '12px 24px',
                background: connecting ? themeColors.cardBg : themeColors.accent,
                border: 'none',
                borderRadius: '8px',
                color: 'white',
                fontWeight: 600,
                cursor: connecting ? 'not-allowed' : 'pointer',
                opacity: connecting ? 0.6 : 1
              }}
            >
              {connecting
                ? t('knowledge.imsKnowledge.connection.connecting' as keyof import('../../../i18n/types').TranslationKeys)
                : t('knowledge.imsKnowledge.connection.connectButton' as keyof import('../../../i18n/types').TranslationKeys)}
            </button>

            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'rgba(52, 152, 219, 0.1)',
              borderRadius: '8px',
              fontSize: '13px',
              color: themeColors.textSecondary
            }}>
              {t('knowledge.imsKnowledge.connection.helpText' as keyof import('../../../i18n/types').TranslationKeys)}
            </div>
          </div>
        ) : (
          <div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px',
              background: 'rgba(46, 204, 113, 0.1)',
              border: '1px solid #2ECC71',
              borderRadius: '8px',
              marginBottom: '12px'
            }}>
              <div>
                <div style={{ fontWeight: 600, color: '#2ECC71' }}>{t('knowledge.imsKnowledge.connection.connected' as keyof import('../../../i18n/types').TranslationKeys)}</div>
                <div style={{ fontSize: '13px', color: themeColors.textSecondary, marginTop: '4px' }}>
                  {imsUrl}
                </div>
              </div>
              <button
                onClick={disconnectFromIMS}
                style={{
                  padding: '8px 16px',
                  background: 'transparent',
                  border: `1px solid ${themeColors.cardBorder}`,
                  borderRadius: '6px',
                  color: themeColors.text,
                  cursor: 'pointer'
                }}
              >
                {t('knowledge.imsKnowledge.connection.disconnect' as keyof import('../../../i18n/types').TranslationKeys)}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* AI Chat Interface - Only visible when connected */}
      {isConnected && (
        <div style={{ ...cardStyle, flex: 1, display: 'flex', flexDirection: 'column', minHeight: '400px' }}>
          <h3 style={{ marginBottom: '16px' }}>{t('knowledge.imsKnowledge.chat.title' as keyof import('../../../i18n/types').TranslationKeys)}</h3>

          {/* Messages */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            background: 'rgba(255,255,255,0.02)',
            borderRadius: '8px',
            marginBottom: '16px'
          }}>
            {messages.map(msg => (
              <div
                key={msg.id}
                style={{
                  marginBottom: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start'
                }}
              >
                <div style={{
                  maxWidth: '80%',
                  padding: '12px 16px',
                  borderRadius: '12px',
                  background: msg.role === 'user'
                    ? themeColors.accent
                    : 'rgba(255,255,255,0.05)',
                  color: themeColors.text
                }}>
                  <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                    {msg.content}
                  </div>
                  <div style={{
                    fontSize: '11px',
                    marginTop: '8px',
                    opacity: 0.7
                  }}>
                    {msg.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}

            {isGenerating && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: themeColors.textSecondary
              }}>
                <span>{t('knowledge.imsKnowledge.chat.generating' as keyof import('../../../i18n/types').TranslationKeys)}</span>
                <span className="loading-dots">...</span>
              </div>
            )}
          </div>

          {/* Input */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              placeholder={t('knowledge.imsKnowledge.chat.inputPlaceholder' as keyof import('../../../i18n/types').TranslationKeys)}
              disabled={isGenerating}
              style={{
                flex: 1,
                padding: '12px',
                background: themeColors.inputBg,
                border: `1px solid ${themeColors.cardBorder}`,
                borderRadius: '8px',
                color: themeColors.text,
                fontSize: '14px'
              }}
            />
            <button
              onClick={sendMessage}
              disabled={isGenerating || !inputMessage.trim()}
              style={{
                padding: '12px 24px',
                background: isGenerating || !inputMessage.trim() ? themeColors.cardBg : themeColors.accent,
                border: 'none',
                borderRadius: '8px',
                color: 'white',
                fontWeight: 600,
                cursor: isGenerating || !inputMessage.trim() ? 'not-allowed' : 'pointer',
                opacity: isGenerating || !inputMessage.trim() ? 0.6 : 1
              }}
            >
              {t('knowledge.imsKnowledge.chat.sendButton' as keyof import('../../../i18n/types').TranslationKeys)}
            </button>
          </div>
        </div>
      )}

      {/* Knowledge Items List */}
      {isConnected && knowledgeItems.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginBottom: '16px' }}>
            {t('knowledge.imsKnowledge.knowledge.title' as keyof import('../../../i18n/types').TranslationKeys, { count: knowledgeItems.length })}
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
            {knowledgeItems.map(item => (
              <div
                key={item.id}
                style={{
                  padding: '16px',
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${themeColors.cardBorder}`,
                  borderRadius: '8px'
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: '8px' }}>
                  {item.title}
                </div>
                <div style={{
                  fontSize: '13px',
                  color: themeColors.textSecondary,
                  marginBottom: '12px',
                  lineHeight: 1.5,
                  maxHeight: '60px',
                  overflow: 'hidden'
                }}>
                  {item.content}
                </div>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: '12px',
                  color: themeColors.textSecondary
                }}>
                  <span>{item.createdAt.toLocaleString()}</span>
                  <button
                    onClick={() => saveKnowledge(item)}
                    style={{
                      padding: '6px 12px',
                      background: themeColors.accent,
                      border: 'none',
                      borderRadius: '6px',
                      color: 'white',
                      fontSize: '12px',
                      cursor: 'pointer'
                    }}
                  >
                    {t('knowledge.imsKnowledge.knowledge.saveButton' as keyof import('../../../i18n/types').TranslationKeys)}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default ContentTab;
