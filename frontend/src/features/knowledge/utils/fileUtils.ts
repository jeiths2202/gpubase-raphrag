// File Utility Functions
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import { SUPPORTED_FORMATS } from '../constants';

export const getFileTypeInfo = (filename: string): { icon: string; color: string; type: string } => {
  const ext = filename.toLowerCase().substring(filename.lastIndexOf('.'));
  for (const [type, info] of Object.entries(SUPPORTED_FORMATS)) {
    if (info.extensions.includes(ext)) {
      return { icon: info.icon, color: info.color, type };
    }
  }
  return { icon: '📄', color: '#6C757D', type: 'unknown' };
};

export const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};
