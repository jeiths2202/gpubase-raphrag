// Knowledge Feature Types
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

export interface Project {
  id: string;
  name: string;
  description?: string;
  color?: string;
  document_count: number;
  note_count: number;
  created_at: string;
}

export interface Note {
  id: string;
  title: string;
  preview: string;
  note_type: string;
  folder_name?: string;
  tags: string[];
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface Folder {
  id: string;
  name: string;
  note_count: number;
  children: Folder[];
  color?: string;
}

export interface Document {
  id: string;
  filename: string;
  original_name: string;
  status: string;
  chunks_count: number;
  document_type?: string;
  processing_mode?: string;
  vlm_processed?: boolean;
  file_size?: number;
  mime_type?: string;
}

export interface ContentItem {
  id: string;
  content_type: string;
  status: string;
  title: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: { doc_name: string; chunk_index: number; content: string; score: number }[];
  timestamp: Date;
}

export interface Conversation {
  id: string;
  title: string;
  queries_count: number;
  last_query_at?: string;
}

// Knowledge Graph types
export interface KGEntity {
  id: string;
  label: string;
  entity_type: string;
  properties: Record<string, any>;
  confidence: number;
  x?: number;
  y?: number;
  color?: string;
}

export interface KGRelationship {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight: number;
  confidence: number;
}

export interface KnowledgeGraphData {
  id: string;
  name: string;
  description?: string;
  entities: KGEntity[];
  relationships: KGRelationship[];
  entity_count: number;
  relationship_count: number;
  source_query?: string;
  created_at: string;
}

// Knowledge Article types
export type KnowledgeStatus = 'draft' | 'pending' | 'in_review' | 'approved' | 'rejected' | 'published';
export type KnowledgeCategory = 'technical' | 'process' | 'guideline' | 'troubleshooting' | 'best_practice' | 'tutorial' | 'faq' | 'announcement' | 'research' | 'other';
export type SupportedLanguage = 'ko' | 'ja' | 'en';

export interface KnowledgeTranslation {
  language: SupportedLanguage;
  title: string;
  content: string;
  summary?: string;
}

export interface ReviewComment {
  id: string;
  reviewer_id: string;
  reviewer_name: string;
  comment: string;
  action: string;
  created_at: string;
}

export interface KnowledgeArticle {
  id: string;
  title: string;
  content: string;
  summary?: string;
  primary_language: SupportedLanguage;
  category: KnowledgeCategory;
  tags: string[];
  author_id: string;
  author_name: string;
  author_department?: string;
  status: KnowledgeStatus;
  reviewer_id?: string;
  reviewer_name?: string;
  review_comments: ReviewComment[];
  translations: Record<string, KnowledgeTranslation>;
  view_count: number;
  recommendation_count: number;
  created_at: string;
  published_at?: string;
}

export interface TopContributor {
  user_id: string;
  username: string;
  department?: string;
  total_recommendations: number;
  article_count: number;
  rank: number;
}

export interface CategoryOption {
  value: KnowledgeCategory;
  label: string;
}

// Notification types
export interface Notification {
  id: string;
  user_id: string;
  type: string;
  title: string;
  message: string;
  reference_type?: string;
  reference_id?: string;
  is_read: boolean;
  created_at: string;
}

export type TabType = 'chat' | 'documents' | 'web-sources' | 'notes' | 'content' | 'projects' | 'mindmap' | 'knowledge-graph' | 'knowledge-articles';

// Web Source types
export interface WebSource {
  id: string;
  url: string;
  display_name: string;
  domain: string;
  status: 'pending' | 'fetching' | 'extracting' | 'chunking' | 'embedding' | 'ready' | 'error' | 'stale';
  metadata: {
    title?: string;
    description?: string;
    author?: string;
    content_type: string;
    language?: string;
  };
  stats: {
    word_count: number;
    chunk_count: number;
    fetch_time_ms: number;
  };
  tags: string[];
  error_message?: string;
  created_at: string;
  fetched_at?: string;
}

export type ThemeType = 'dark' | 'light';

// Session Document type (for chat context)
export interface SessionDocument {
  id: string;
  filename: string;
  status: string;
  chunk_count: number;
  word_count: number;
}

// Theme Colors type
export interface ThemeColors {
  bg: string;
  cardBg: string;
  cardBorder: string;
  text: string;
  textSecondary: string;
  accent: string;
  accentHover: string;
}

// External Connection type
export interface ExternalConnection {
  id: string;
  resource_type: string;
  status: string;
  document_count: number;
  chunk_count: number;
  last_sync_at: string | null;
  error_message: string | null;
}

// Available Resource type
export interface AvailableResource {
  type: string;
  name: string;
  icon: string;
  descriptionKey: string;
  authType: string;
}
