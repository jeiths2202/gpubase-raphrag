// ChatTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ThemeColors, ChatMessage } from '../types';
import { TranslateFunction } from '../../../i18n/types';

// Session document type (inline as it's specific to chat)
interface SessionDocument {
  id: string;
  filename: string;
  status: string;
  chunk_count: number;
  word_count: number;
}

// External connection type
interface ExternalConnection {
  id: string;
  resource_type: string;
  status: string;
  document_count: number;
  chunk_count: number;
  last_sync_at: string | null;
  error_message: string | null;
}

// Available resource type
interface AvailableResource {
  type: string;
  name: string;
  icon: string;
  descriptionKey: string;
  authType: string;
}

// Clipboard content type
interface ClipboardContent {
  type: 'image' | 'text' | null;
  data: string | null;
  mimeType: string | null;
  preview: string | null;
}

interface ChatTabProps {
  // State
  messages: ChatMessage[];
  inputMessage: string;
  isLoading: boolean;
  selectedDocuments: string[];
  sessionDocuments: SessionDocument[];
  suggestedQuestions: string[];
  showPasteModal: boolean;
  pasteContent: string;
  pasteTitle: string;
  uploadingSessionDoc: boolean;
  dragOver: boolean;
  externalConnections: ExternalConnection[];
  availableResources: AvailableResource[];
  showExternalModal: boolean;
  connectingResource: string | null;
  syncingConnection: string | null;
  clipboardContent: ClipboardContent;

  // State setters
  setInputMessage: (value: string) => void;
  setSelectedSource: (source: any) => void;
  setShowSourcePanel: (show: boolean) => void;
  setShowPasteModal: (show: boolean) => void;
  setPasteContent: (content: string) => void;
  setPasteTitle: (title: string) => void;
  setShowExternalModal: (show: boolean) => void;

  // Functions
  sendMessage: () => void;
  saveAIResponse: (messageId: string) => void;
  removeSessionDocument: (docId: string) => void;
  handleDragOver: (e: React.DragEvent) => void;
  handleDragLeave: (e: React.DragEvent) => void;
  handleDrop: (e: React.DragEvent) => void;
  handleClipboardPaste: (e: React.ClipboardEvent) => void;
  addClipboardToSession: () => void;
  clearClipboardContent: () => void;
  pasteSessionText: () => void;
  connectExternalResource: (resourceType: string) => void;
  disconnectExternalResource: (connectionId: string) => void;
  syncExternalResource: (connectionId: string) => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  tabStyle: (isActive: boolean) => React.CSSProperties;
  inputStyle: React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const ChatTab: React.FC<ChatTabProps> = ({
  messages,
  inputMessage,
  isLoading,
  selectedDocuments,
  sessionDocuments,
  suggestedQuestions,
  showPasteModal,
  pasteContent,
  pasteTitle,
  uploadingSessionDoc,
  dragOver,
  externalConnections,
  availableResources,
  showExternalModal,
  connectingResource,
  syncingConnection,
  clipboardContent,
  setInputMessage,
  setSelectedSource,
  setShowSourcePanel,
  setShowPasteModal,
  setPasteContent,
  setPasteTitle,
  setShowExternalModal,
  sendMessage,
  saveAIResponse,
  removeSessionDocument,
  handleDragOver,
  handleDragLeave,
  handleDrop,
  handleClipboardPaste,
  addClipboardToSession,
  clearClipboardContent,
  pasteSessionText,
  connectExternalResource,
  disconnectExternalResource,
  syncExternalResource,
  themeColors,
  cardStyle,
  tabStyle,
  inputStyle,
  t
}) => {
  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      {/* Chat Header */}
      <div style={cardStyle}>
        <h2 style={{ margin: 0 }}>{t('knowledge.chat.title')}</h2>
        <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
          {t('knowledge.chat.subtitle', { count: selectedDocuments.length })}
        </p>
      </div>

      {/* Messages */}
      <div style={{ ...cardStyle, flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
            <p>{t('knowledge.chat.startPrompt')}</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', marginTop: '16px' }}>
              {[
                { key: 'summarize', label: t('knowledge.chat.quickPrompts.summarize') },
                { key: 'keyConcepts', label: t('knowledge.chat.quickPrompts.keyConcepts') },
                { key: 'showExamples', label: t('knowledge.chat.quickPrompts.showExamples') }
              ].map((q) => (
                <button
                  key={q.key}
                  onClick={() => setInputMessage(q.label)}
                  style={{ ...tabStyle(false), fontSize: '14px' }}
                >
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map(msg => (
            <div
              key={msg.id}
              style={{
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                background: msg.role === 'user' ? themeColors.accent : 'rgba(255,255,255,0.1)',
                padding: '12px 16px',
                borderRadius: '12px'
              }}
            >
              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>

              {/* Sources (Citations) */}
              {msg.sources && msg.sources.length > 0 && (
                <div style={{ marginTop: '12px', fontSize: '12px' }}>
                  <div style={{ color: themeColors.textSecondary, marginBottom: '8px' }}>
                    {t('knowledge.sources')} ({msg.sources.length}):
                  </div>
                  {msg.sources.map((source, idx) => (
                    <div
                      key={idx}
                      onClick={() => {
                        setSelectedSource(source);
                        setShowSourcePanel(true);
                      }}
                      style={{
                        padding: '8px',
                        background: 'rgba(74,144,217,0.2)',
                        borderRadius: '6px',
                        marginBottom: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      <span style={{ fontWeight: 600 }}>[{idx + 1}]</span> {source.doc_name} (신뢰도: {(source.score * 100).toFixed(0)}%)
                    </div>
                  ))}
                </div>
              )}

              {/* Save to note button */}
              {msg.role === 'assistant' && (
                <button
                  onClick={() => saveAIResponse(msg.id)}
                  style={{ ...tabStyle(false), fontSize: '12px', marginTop: '8px' }}
                >
                  📝 노트로 저장
                </button>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div style={{ alignSelf: 'flex-start', padding: '12px 16px', background: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}>
            <span className="loading">응답 생성 중...</span>
          </div>
        )}
      </div>

      {/* Suggested Questions */}
      {suggestedQuestions.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {suggestedQuestions.map((q, i) => (
            <button
              key={i}
              onClick={() => setInputMessage(q)}
              style={{ ...tabStyle(false), fontSize: '12px' }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Session Documents */}
      {sessionDocuments.length > 0 && (
        <div style={{
          ...cardStyle,
          background: 'rgba(46, 204, 113, 0.1)',
          border: '1px solid rgba(46, 204, 113, 0.3)',
          padding: '12px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '14px' }}>📎 현재 대화에서 사용 중인 문서</span>
            <span style={{
              fontSize: '11px',
              padding: '2px 6px',
              background: 'rgba(46, 204, 113, 0.3)',
              borderRadius: '4px',
              color: '#2ECC71'
            }}>
              우선 참조
            </span>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {sessionDocuments.map(doc => (
              <div
                key={doc.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 10px',
                  background: 'rgba(255,255,255,0.1)',
                  borderRadius: '6px',
                  fontSize: '12px'
                }}
              >
                <span>{doc.filename}</span>
                {doc.status === 'processing' && (
                  <span style={{ color: '#F1C40F' }}>처리중...</span>
                )}
                {doc.status === 'ready' && (
                  <span style={{ color: '#2ECC71' }}>({doc.chunk_count} chunks)</span>
                )}
                {doc.status === 'error' && (
                  <span style={{ color: '#E74C3C' }}>오류</span>
                )}
                <button
                  onClick={() => removeSessionDocument(doc.id)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#E74C3C',
                    cursor: 'pointer',
                    padding: '2px 4px',
                    fontSize: '14px'
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input with File Upload */}
      <div
        style={{
          ...cardStyle,
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          border: dragOver ? `2px dashed ${themeColors.accent}` : undefined,
          background: dragOver ? 'rgba(74, 144, 217, 0.1)' : undefined
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* External Resources Indicator */}
        {externalConnections.filter(c => c.status === 'connected').length > 0 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 12px',
            background: 'rgba(46, 204, 113, 0.1)',
            borderRadius: '6px',
            fontSize: '12px',
            color: '#2ECC71',
            marginBottom: '4px'
          }}>
            🔗 {t('knowledge.external.connectedStatus' as keyof import('../../../i18n/types').TranslationKeys)}:
            {externalConnections.filter(c => c.status === 'connected').map(conn => {
              const resource = availableResources.find(r => r.type === conn.resource_type);
              return (
                <span key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {resource?.icon} {t(`knowledge.external.resources.${resource?.type === 'google_drive' ? 'googleDrive' : resource?.type}.name` as keyof import('../../../i18n/types').TranslationKeys)} ({conn.document_count})
                </span>
              );
            })}
          </div>
        )}

        {/* External Resources Button */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            onClick={() => setShowExternalModal(true)}
            style={{
              padding: '8px 12px',
              fontSize: '14px',
              fontWeight: 'bold',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              borderRadius: '8px',
              cursor: 'pointer',
              transition: 'all 0.2s',
              background: externalConnections.some(c => c.status === 'connected')
                ? 'rgba(46, 204, 113, 0.2)'
                : 'rgba(74, 144, 217, 0.15)',
              border: externalConnections.some(c => c.status === 'connected')
                ? '1px solid #2ECC71'
                : '1px solid rgba(74, 144, 217, 0.5)',
              color: externalConnections.some(c => c.status === 'connected')
                ? '#2ECC71'
                : themeColors.accent
            }}
            title={t('knowledge.external.buttonTitle' as keyof import('../../../i18n/types').TranslationKeys)}
          >
            ➕ {t('knowledge.external.button' as keyof import('../../../i18n/types').TranslationKeys)}
          </button>
          {uploadingSessionDoc && (
            <span style={{ color: themeColors.textSecondary, fontSize: '12px' }}>
              {t('knowledge.clipboard.processing' as keyof import('../../../i18n/types').TranslationKeys)}
            </span>
          )}
        </div>

        {/* Clipboard Content Preview */}
        {clipboardContent.type && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              padding: '12px 16px',
              background: clipboardContent.type === 'image'
                ? 'rgba(155, 89, 182, 0.15)'
                : 'rgba(52, 152, 219, 0.15)',
              border: clipboardContent.type === 'image'
                ? '1px solid rgba(155, 89, 182, 0.4)'
                : '1px solid rgba(52, 152, 219, 0.4)',
              borderRadius: '8px'
            }}
          >
            {/* Content Type Icon */}
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '8px',
              background: clipboardContent.type === 'image'
                ? 'rgba(155, 89, 182, 0.3)'
                : 'rgba(52, 152, 219, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              flexShrink: 0
            }}>
              {clipboardContent.type === 'image' ? '🖼️' : '📄'}
            </div>

            {/* Preview Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: clipboardContent.type === 'image' ? '#9B59B6' : '#3498DB',
                  textTransform: 'uppercase'
                }}>
                  {clipboardContent.type === 'image' ? t('knowledge.clipboard.image' as keyof import('../../../i18n/types').TranslationKeys) : t('knowledge.clipboard.text' as keyof import('../../../i18n/types').TranslationKeys)} • {clipboardContent.mimeType}
                </span>
              </div>

              {clipboardContent.type === 'image' ? (
                <img
                  src={clipboardContent.preview || ''}
                  alt={t('knowledge.clipboard.preview' as keyof import('../../../i18n/types').TranslationKeys)}
                  style={{
                    maxWidth: '200px',
                    maxHeight: '120px',
                    borderRadius: '4px',
                    objectFit: 'contain'
                  }}
                />
              ) : (
                <div style={{
                  fontSize: '13px',
                  color: themeColors.textSecondary,
                  lineHeight: 1.4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical'
                }}>
                  {clipboardContent.preview}
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
              <button
                onClick={addClipboardToSession}
                disabled={uploadingSessionDoc}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  fontWeight: 500,
                  fontSize: '13px',
                  cursor: uploadingSessionDoc ? 'not-allowed' : 'pointer',
                  background: 'rgba(46, 204, 113, 0.9)',
                  border: '1px solid #2ECC71',
                  color: '#fff',
                  transition: 'all 0.2s'
                }}
              >
                ✓ {t('knowledge.clipboard.add' as keyof import('../../../i18n/types').TranslationKeys)}
              </button>
              <button
                onClick={clearClipboardContent}
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  cursor: 'pointer',
                  background: 'rgba(231, 76, 60, 0.15)',
                  border: '1px solid rgba(231, 76, 60, 0.4)',
                  color: '#E74C3C',
                  transition: 'all 0.2s'
                }}
              >
                ✕
              </button>
            </div>
          </motion.div>
        )}

        {/* Message Input */}
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {/* File Attachment Button */}
          <label
            htmlFor="file-upload-input"
            style={{
              padding: '12px',
              background: 'rgba(255,255,255,0.1)',
              border: `1px solid ${themeColors.cardBorder}`,
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s',
              minWidth: '48px',
              height: '48px'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.15)';
              e.currentTarget.style.borderColor = themeColors.accent;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.1)';
              e.currentTarget.style.borderColor = themeColors.cardBorder;
            }}
            title={t('knowledge.chat.attachFile' as keyof import('../../../i18n/types').TranslationKeys) || 'Attach file'}
          >
            📎
            <input
              id="file-upload-input"
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => {
                const files = e.target.files;
                if (files && files.length > 0 && handleDrop) {
                  // Create a synthetic drag event to reuse existing upload logic
                  const dataTransfer = new DataTransfer();
                  Array.from(files).forEach(file => {
                    dataTransfer.items.add(file);
                  });
                  const syntheticEvent = {
                    preventDefault: () => {},
                    dataTransfer: dataTransfer
                  } as React.DragEvent;
                  handleDrop(syntheticEvent);
                }
                // Reset input to allow re-uploading same file
                e.target.value = '';
              }}
              accept=".pdf,.doc,.docx,.txt,.md,.json,.png,.jpg,.jpeg,.gif,.bmp"
            />
          </label>

          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            onPaste={handleClipboardPaste}
            placeholder={t('knowledge.chat.inputPlaceholder')}
            style={{
              flex: 1,
              padding: '12px 16px',
              background: 'rgba(255,255,255,0.1)',
              border: `1px solid ${themeColors.cardBorder}`,
              borderRadius: '8px',
              color: themeColors.text,
              fontSize: '16px'
            }}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !inputMessage.trim()}
            style={{
              padding: '12px 24px',
              background: themeColors.accent,
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading || !inputMessage.trim() ? 0.5 : 1
            }}
          >
            {t('knowledge.chat.send')}
          </button>
        </div>
      </div>

      {/* Text Paste Modal */}
      <AnimatePresence>
        {showPasteModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => setShowPasteModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              style={{ ...cardStyle, width: '600px', maxWidth: '90%' }}
              onClick={e => e.stopPropagation()}
            >
              <h3 style={{ margin: '0 0 16px' }}>📝 {t('knowledge.upload.pasteText')}</h3>
              <p style={{ color: themeColors.textSecondary, fontSize: '14px', marginBottom: '16px' }}>
                문서 내용이나 참고자료를 붙여넣으면 현재 대화에서 우선적으로 참조합니다.
              </p>

              <input
                type="text"
                placeholder="제목 (선택)"
                value={pasteTitle}
                onChange={e => setPasteTitle(e.target.value)}
                style={{
                  ...inputStyle,
                  width: '100%',
                  marginBottom: '12px'
                }}
              />

              <textarea
                placeholder="내용을 붙여넣으세요..."
                value={pasteContent}
                onChange={e => setPasteContent(e.target.value)}
                style={{
                  ...inputStyle,
                  width: '100%',
                  minHeight: '200px',
                  resize: 'vertical',
                  fontFamily: 'inherit'
                }}
              />

              <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                <button
                  onClick={() => setShowPasteModal(false)}
                  style={{ ...tabStyle(false), flex: 1 }}
                >
                  취소
                </button>
                <button
                  onClick={pasteSessionText}
                  disabled={!pasteContent.trim() || uploadingSessionDoc}
                  style={{
                    ...tabStyle(true),
                    flex: 1,
                    opacity: !pasteContent.trim() || uploadingSessionDoc ? 0.5 : 1,
                    cursor: !pasteContent.trim() || uploadingSessionDoc ? 'not-allowed' : 'pointer'
                  }}
                >
                  {uploadingSessionDoc ? '처리 중...' : '추가'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* External Connection Modal */}
      <AnimatePresence>
        {showExternalModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => setShowExternalModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              style={{ ...cardStyle, width: '600px', maxWidth: '90%', maxHeight: '80vh', overflow: 'auto' }}
              onClick={e => e.stopPropagation()}
            >
              <h3 style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🔗 {t('knowledge.external.title' as keyof import('../../../i18n/types').TranslationKeys)}
              </h3>
              <p style={{ color: themeColors.textSecondary, fontSize: '14px', marginBottom: '20px' }}>
                {t('knowledge.external.description' as keyof import('../../../i18n/types').TranslationKeys)}
              </p>

              {/* Connected Resources */}
              {externalConnections.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <h4 style={{ margin: '0 0 12px', fontSize: '14px', color: themeColors.textSecondary }}>
                    {t('knowledge.external.connectedResources' as keyof import('../../../i18n/types').TranslationKeys)}
                  </h4>
                  {externalConnections.map(conn => {
                    const resource = availableResources.find(r => r.type === conn.resource_type);
                    return (
                      <div key={conn.id} style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '12px',
                        background: 'rgba(255,255,255,0.05)',
                        borderRadius: '8px',
                        marginBottom: '8px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '24px' }}>{resource?.icon}</span>
                          <div>
                            <div style={{ fontWeight: 500 }}>{resource?.name}</div>
                            <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                              {conn.status === 'connected' ? (
                                <span style={{ color: '#2ECC71' }}>
                                  ✓ {t('knowledge.external.connected' as keyof import('../../../i18n/types').TranslationKeys)} • {conn.document_count} {t('knowledge.external.documents' as keyof import('../../../i18n/types').TranslationKeys)} • {conn.chunk_count} {t('knowledge.external.chunks' as keyof import('../../../i18n/types').TranslationKeys)}
                                </span>
                              ) : conn.status === 'syncing' ? (
                                <span style={{ color: '#F39C12' }}>{t('knowledge.external.syncing' as keyof import('../../../i18n/types').TranslationKeys)}</span>
                              ) : conn.status === 'error' ? (
                                <span style={{ color: '#E74C3C' }}>{t('knowledge.external.error' as keyof import('../../../i18n/types').TranslationKeys)}: {conn.error_message}</span>
                              ) : (
                                <span>{t('knowledge.external.waiting' as keyof import('../../../i18n/types').TranslationKeys)}</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          {conn.status === 'connected' && (
                            <button
                              onClick={() => syncExternalResource(conn.id)}
                              disabled={syncingConnection === conn.id}
                              style={{
                                fontSize: '12px',
                                padding: '6px 12px',
                                borderRadius: '6px',
                                cursor: syncingConnection === conn.id ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s',
                                background: 'rgba(74, 144, 217, 0.15)',
                                border: '1px solid rgba(74, 144, 217, 0.5)',
                                color: themeColors.accent
                              }}
                            >
                              {syncingConnection === conn.id ? t('knowledge.external.syncing' as keyof import('../../../i18n/types').TranslationKeys) : `🔄 ${t('knowledge.external.syncButton' as keyof import('../../../i18n/types').TranslationKeys)}`}
                            </button>
                          )}
                          <button
                            onClick={() => disconnectExternalResource(conn.id)}
                            style={{
                              fontSize: '12px',
                              padding: '6px 12px',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              transition: 'all 0.2s',
                              background: 'rgba(231, 76, 60, 0.15)',
                              border: '1px solid rgba(231, 76, 60, 0.5)',
                              color: '#E74C3C'
                            }}
                          >
                            {t('knowledge.external.disconnect' as keyof import('../../../i18n/types').TranslationKeys)}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Available Resources */}
              <h4 style={{ margin: '0 0 12px', fontSize: '14px', color: themeColors.textSecondary }}>
                {t('knowledge.external.availableResources' as keyof import('../../../i18n/types').TranslationKeys)}
              </h4>
              <div style={{ display: 'grid', gap: '12px' }}>
                {availableResources.map(resource => {
                  const isConnected = externalConnections.some(
                    c => c.resource_type === resource.type && c.status === 'connected'
                  );
                  const isConnecting = connectingResource === resource.type;

                  return (
                    <div key={resource.type} style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px',
                      background: isConnected ? 'rgba(46, 204, 113, 0.1)' : 'rgba(255,255,255,0.05)',
                      borderRadius: '8px',
                      border: isConnected ? '1px solid rgba(46, 204, 113, 0.3)' : '1px solid transparent'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <span style={{ fontSize: '32px' }}>{resource.icon}</span>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '16px' }}>
                            {t(`knowledge.external.resources.${resource.type === 'google_drive' ? 'googleDrive' : resource.type}.name` as keyof import('../../../i18n/types').TranslationKeys)}
                          </div>
                          <div style={{ fontSize: '13px', color: themeColors.textSecondary }}>
                            {t(`knowledge.external.resources.${resource.type === 'google_drive' ? 'googleDrive' : resource.type}.description` as keyof import('../../../i18n/types').TranslationKeys)}
                          </div>
                          <div style={{
                            fontSize: '11px',
                            color: themeColors.textSecondary,
                            marginTop: '4px'
                          }}>
                            {resource.authType === 'oauth2' ? `🔐 ${t('knowledge.external.oauthAuth' as keyof import('../../../i18n/types').TranslationKeys)}` : `🔑 ${t('knowledge.external.apiToken' as keyof import('../../../i18n/types').TranslationKeys)}`}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => !isConnected && connectExternalResource(resource.type)}
                        disabled={isConnected || isConnecting}
                        style={{
                          padding: '10px 20px',
                          borderRadius: '8px',
                          fontWeight: 500,
                          cursor: isConnected ? 'not-allowed' : 'pointer',
                          transition: 'all 0.2s',
                          opacity: isConnected ? 0.7 : 1,
                          background: isConnected
                            ? 'rgba(46, 204, 113, 0.2)'
                            : 'rgba(74, 144, 217, 0.9)',
                          border: isConnected
                            ? '1px solid #2ECC71'
                            : '1px solid rgba(74, 144, 217, 1)',
                          color: isConnected ? '#2ECC71' : '#ffffff'
                        }}
                      >
                        {isConnected ? `✓ ${t('knowledge.external.connected' as keyof import('../../../i18n/types').TranslationKeys)}` : isConnecting ? t('knowledge.external.connecting' as keyof import('../../../i18n/types').TranslationKeys) : t('knowledge.external.connect' as keyof import('../../../i18n/types').TranslationKeys)}
                      </button>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
                <button
                  onClick={() => setShowExternalModal(false)}
                  style={{
                    padding: '10px 24px',
                    borderRadius: '8px',
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    background: 'rgba(255, 255, 255, 0.1)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    color: themeColors.text
                  }}
                >
                  {t('knowledge.external.close' as keyof import('../../../i18n/types').TranslationKeys)}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ChatTab;
