// DocumentsTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ThemeColors, Document } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import { SUPPORTED_FORMATS } from '../constants';
import { getFileTypeInfo, formatFileSize } from '../utils';

// Upload settings type
interface UploadSettings {
  processingMode: 'text_only' | 'vlm_enhanced' | 'multimodal' | 'ocr';
  enableVLM: boolean;
  extractTables: boolean;
  extractImages: boolean;
  language: string;
}

interface DocumentsTabProps {
  // State
  documents: Document[];
  selectedDocuments: string[];
  showUploadModal: boolean;
  uploadFile: File | null;
  uploadSettings: UploadSettings;
  uploading: boolean;
  uploadProgress: string | null;

  // State setters
  setSelectedDocuments: React.Dispatch<React.SetStateAction<string[]>>;
  setShowUploadModal: (show: boolean) => void;
  setUploadFile: (file: File | null) => void;
  setUploadSettings: React.Dispatch<React.SetStateAction<UploadSettings>>;

  // Functions
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  uploadDocument: () => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  tabStyle: (isActive: boolean) => React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const DocumentsTab: React.FC<DocumentsTabProps> = ({
  documents,
  selectedDocuments,
  showUploadModal,
  uploadFile,
  uploadSettings,
  uploading,
  uploadProgress,
  setSelectedDocuments,
  setShowUploadModal,
  setUploadFile,
  setUploadSettings,
  handleFileSelect,
  uploadDocument,
  themeColors,
  cardStyle,
  tabStyle,
  t
}) => {
  return (
    <motion.div
      key="documents"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1 }}
    >
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ margin: 0 }}>Documents</h2>
            <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
              {t('knowledge.documents.subtitle' as keyof import('../../../i18n/types').TranslationKeys, { count: selectedDocuments.length })}
            </p>
          </div>
          <button
            onClick={() => setShowUploadModal(true)}
            style={{ ...tabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            📤 Upload Document
          </button>
        </div>

        {/* Supported Formats Info */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px', padding: '12px', background: 'rgba(74,144,217,0.1)', borderRadius: '8px' }}>
          <span style={{ color: themeColors.textSecondary, fontSize: '12px' }}>Supported:</span>
          {Object.entries(SUPPORTED_FORMATS).map(([type, info]) => (
            <span key={type} style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span>{info.icon}</span>
              <span style={{ color: themeColors.textSecondary }}>{info.extensions.join(', ')}</span>
            </span>
          ))}
        </div>

        {/* Documents Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {documents.map(doc => {
            const fileInfo = getFileTypeInfo(doc.original_name);
            return (
              <div
                key={doc.id}
                onClick={() => {
                  setSelectedDocuments(prev =>
                    prev.includes(doc.id)
                      ? prev.filter(id => id !== doc.id)
                      : [...prev, doc.id]
                  );
                }}
                style={{
                  ...cardStyle,
                  cursor: 'pointer',
                  border: selectedDocuments.includes(doc.id)
                    ? `2px solid ${themeColors.accent}`
                    : `1px solid ${themeColors.cardBorder}`,
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'flex-start'
                }}
              >
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '8px',
                  background: `${fileInfo.color}20`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                  flexShrink: 0
                }}>
                  {fileInfo.icon}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {doc.original_name}
                  </div>
                  <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                    {doc.chunks_count} chunks | {doc.status}
                    {doc.file_size && ` | ${formatFileSize(doc.file_size)}`}
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                    <span style={{
                      fontSize: '10px',
                      padding: '2px 6px',
                      background: `${fileInfo.color}30`,
                      color: fileInfo.color,
                      borderRadius: '4px'
                    }}>
                      {fileInfo.type.toUpperCase()}
                    </span>
                    {doc.vlm_processed && (
                      <span style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        background: 'rgba(155, 89, 182, 0.3)',
                        color: '#9B59B6',
                        borderRadius: '4px'
                      }}>
                        VLM
                      </span>
                    )}
                    {doc.processing_mode && doc.processing_mode !== 'text_only' && (
                      <span style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        background: 'rgba(46, 204, 113, 0.3)',
                        color: '#2ECC71',
                        borderRadius: '4px'
                      }}>
                        {doc.processing_mode}
                      </span>
                    )}
                  </div>
                </div>
                {selectedDocuments.includes(doc.id) && (
                  <div style={{ color: themeColors.accent, fontSize: '20px' }}>✓</div>
                )}
              </div>
            );
          })}
        </div>

        {documents.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
            <p>No documents uploaded yet.</p>
            <button
              onClick={() => setShowUploadModal(true)}
              style={{ ...tabStyle(true), marginTop: '16px' }}
            >
              Upload your first document
            </button>
          </div>
        )}
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {showUploadModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => !uploading && setShowUploadModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                ...cardStyle,
                width: '500px',
                maxWidth: '90vw',
                maxHeight: '90vh',
                overflow: 'auto'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0 }}>Upload Document</h2>
                <button
                  onClick={() => !uploading && setShowUploadModal(false)}
                  disabled={uploading}
                  style={{ background: 'transparent', border: 'none', color: themeColors.text, fontSize: '24px', cursor: 'pointer' }}
                >
                  ×
                </button>
              </div>

              {/* File Drop Zone */}
              <div
                style={{
                  border: `2px dashed ${uploadFile ? themeColors.accent : themeColors.cardBorder}`,
                  borderRadius: '12px',
                  padding: '40px 20px',
                  textAlign: 'center',
                  marginBottom: '20px',
                  background: uploadFile ? 'rgba(74,144,217,0.1)' : 'transparent',
                  transition: 'all 0.2s',
                  position: 'relative'
                }}
              >
                {uploadFile ? (
                  <div>
                    <div style={{ fontSize: '48px', marginBottom: '12px' }}>
                      {getFileTypeInfo(uploadFile.name).icon}
                    </div>
                    <div style={{ fontWeight: 600 }}>{uploadFile.name}</div>
                    <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                      {formatFileSize(uploadFile.size)}
                    </div>
                    <button
                      onClick={() => setUploadFile(null)}
                      style={{ ...tabStyle(false), marginTop: '12px', fontSize: '12px' }}
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: '48px', marginBottom: '12px' }}>📤</div>
                    <p style={{ margin: 0 }}>Drop file here or click to browse</p>
                    <p style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '8px' }}>
                      PDF, Word, Excel, PowerPoint, Text, CSV, JSON, Images
                    </p>
                  </div>
                )}
                <input
                  type="file"
                  onChange={handleFileSelect}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.webp,.html,.htm"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    opacity: 0,
                    cursor: 'pointer'
                  }}
                />
              </div>

              {/* Processing Options */}
              <div style={{ marginBottom: '20px' }}>
                <h4 style={{ marginBottom: '12px' }}>Processing Options</h4>

                {/* Processing Mode */}
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ fontSize: '14px', color: themeColors.textSecondary, display: 'block', marginBottom: '8px' }}>
                    Processing Mode
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                    {[
                      { value: 'text_only', label: 'Text Only', desc: 'Basic text extraction' },
                      { value: 'vlm_enhanced', label: 'VLM Enhanced', desc: 'AI-assisted extraction' },
                      { value: 'multimodal', label: 'Multimodal', desc: 'Full image analysis' },
                      { value: 'ocr', label: 'OCR', desc: 'For scanned documents' }
                    ].map(mode => (
                      <div
                        key={mode.value}
                        onClick={() => setUploadSettings(prev => ({ ...prev, processingMode: mode.value as any }))}
                        style={{
                          padding: '12px',
                          borderRadius: '8px',
                          border: uploadSettings.processingMode === mode.value
                            ? `2px solid ${themeColors.accent}`
                            : `1px solid ${themeColors.cardBorder}`,
                          cursor: 'pointer',
                          background: uploadSettings.processingMode === mode.value ? 'rgba(74,144,217,0.1)' : 'transparent'
                        }}
                      >
                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{mode.label}</div>
                        <div style={{ fontSize: '11px', color: themeColors.textSecondary }}>{mode.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Toggle Options */}
                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={uploadSettings.enableVLM}
                      onChange={(e) => setUploadSettings(prev => ({ ...prev, enableVLM: e.target.checked }))}
                    />
                    <span>Enable VLM Analysis</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={uploadSettings.extractTables}
                      onChange={(e) => setUploadSettings(prev => ({ ...prev, extractTables: e.target.checked }))}
                    />
                    <span>Extract Tables</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={uploadSettings.extractImages}
                      onChange={(e) => setUploadSettings(prev => ({ ...prev, extractImages: e.target.checked }))}
                    />
                    <span>Extract Images</span>
                  </label>
                </div>
              </div>

              {/* Upload Progress */}
              {uploadProgress && (
                <div style={{
                  padding: '12px',
                  background: 'rgba(74,144,217,0.2)',
                  borderRadius: '8px',
                  marginBottom: '20px',
                  textAlign: 'center'
                }}>
                  {uploadProgress}
                </div>
              )}

              {/* Upload Button */}
              <button
                onClick={uploadDocument}
                disabled={!uploadFile || uploading}
                style={{
                  ...tabStyle(true),
                  width: '100%',
                  padding: '14px',
                  opacity: !uploadFile || uploading ? 0.5 : 1,
                  cursor: !uploadFile || uploading ? 'not-allowed' : 'pointer'
                }}
              >
                {uploading ? 'Processing...' : 'Upload & Process'}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default DocumentsTab;
