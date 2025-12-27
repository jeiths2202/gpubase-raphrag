// Knowledge Feature Constants
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

export const API_BASE = '/api/v1';

// Supported file formats
export const SUPPORTED_FORMATS = {
  pdf: { extensions: ['.pdf'], icon: '📄', color: '#E74C3C' },
  word: { extensions: ['.doc', '.docx'], icon: '📝', color: '#2B579A' },
  excel: { extensions: ['.xls', '.xlsx'], icon: '📊', color: '#217346' },
  powerpoint: { extensions: ['.ppt', '.pptx'], icon: '📽️', color: '#D24726' },
  text: { extensions: ['.txt', '.md', '.markdown'], icon: '📃', color: '#6C757D' },
  data: { extensions: ['.csv', '.json'], icon: '📋', color: '#17A2B8' },
  image: { extensions: ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'], icon: '🖼️', color: '#9B59B6' },
  html: { extensions: ['.html', '.htm'], icon: '🌐', color: '#E44D26' }
};
