/**
 * UI Context Types
 *
 * Defines the schema for UI context that is shared between
 * the frontend and backend for context-aware AI responses.
 *
 * This context allows the AI assistant to understand:
 * - What page the user is currently viewing
 * - What item/content is selected or expanded
 * - User's language and theme preferences
 * - User's permission scope for role-based filtering
 */

/**
 * Page types in the application
 */
export type PageType =
  | 'home'
  | 'knowledge'
  | 'faq'
  | 'ims'
  | 'agent'
  | 'documents'
  | 'settings'
  | 'admin'
  | 'ai-studio'
  | 'external-portal'
  | 'unknown';

/**
 * Selected item types
 */
export type SelectedItemType =
  | 'faq_item'
  | 'document'
  | 'ims_issue'
  | 'knowledge_article'
  | 'agent_conversation'
  | 'search_result'
  | 'none';

/**
 * Selected item with content
 */
export interface SelectedItem {
  /** Type of the selected item */
  type: SelectedItemType;
  /** Unique identifier */
  id: string;
  /** Display title */
  title: string;
  /** Full content (may be filtered by role) */
  content?: string;
  /** Brief summary (always visible) */
  summary?: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Page-specific metadata
 */
export interface PageMetadata {
  /** FAQ category if on FAQ page */
  faq_category?: string;
  /** Search query if searching */
  search_query?: string;
  /** Active filters */
  active_filters?: Record<string, unknown>;
  /** IMS job ID if crawling */
  ims_job_id?: string;
  /** Document folder path */
  document_path?: string;
  /** Any additional page-specific data */
  [key: string]: unknown;
}

/**
 * Complete UI Context sent to AI
 */
export interface UIContext {
  /** Current page identifier */
  current_page: PageType;
  /** Human-readable page title */
  page_title: string;
  /** Page-specific metadata */
  page_metadata?: PageMetadata;
  /** Currently selected/expanded item */
  selected_item?: SelectedItem;
  /** List of visible UI components */
  visible_components: string[];
  /** User's preferred language */
  language: 'en' | 'ko' | 'ja';
  /** Current theme */
  theme: 'light' | 'dark';
  /** User's permission scope for content filtering */
  user_permission_scope: 'admin' | 'user';
  /** Timestamp when context was captured */
  captured_at: string;
}

/**
 * Filtered context for non-admin users
 * Content fields are redacted
 */
export interface FilteredUIContext {
  current_page: PageType;
  page_title: string;
  selected_item_summary?: {
    type: SelectedItemType;
    id: string;
    title: string;
    /** Content preview (truncated for non-admin) */
    content_preview?: string;
  };
  visible_components: string[];
  language: 'en' | 'ko' | 'ja';
  theme: 'light' | 'dark';
  user_permission_scope: 'admin' | 'user';
}

/**
 * Page title mapping
 */
export const PAGE_TITLES: Record<PageType, string> = {
  home: 'Home',
  knowledge: 'Knowledge Base',
  faq: 'FAQ',
  ims: 'IMS Search',
  agent: 'AI Agent',
  documents: 'Documents',
  settings: 'Settings',
  admin: 'Admin Dashboard',
  'ai-studio': 'AI Studio',
  'external-portal': 'External Portal',
  unknown: 'Unknown',
};

/**
 * Path to page type mapping
 */
export const PATH_TO_PAGE: Record<string, PageType> = {
  '/': 'home',
  '/home': 'home',
  '/knowledge': 'knowledge',
  '/faq': 'faq',
  '/ims': 'ims',
  '/agent': 'agent',
  '/documents': 'documents',
  '/settings': 'settings',
  '/admin': 'admin',
  '/mindmap': 'ai-studio',
  '/portal': 'external-portal',
};

/**
 * Get page type from pathname
 */
export function getPageTypeFromPath(pathname: string): PageType {
  // Check exact match first
  if (PATH_TO_PAGE[pathname]) {
    return PATH_TO_PAGE[pathname];
  }

  // Check prefix matches for nested routes
  for (const [path, pageType] of Object.entries(PATH_TO_PAGE)) {
    if (pathname.startsWith(path + '/')) {
      return pageType;
    }
  }

  return 'unknown';
}

/**
 * Maximum content length to include in context
 * Prevents excessive payload size
 */
export const MAX_CONTENT_LENGTH = 2000;

/**
 * Maximum number of selected items (for multi-select scenarios)
 */
export const MAX_SELECTED_ITEMS = 5;

/**
 * Truncate content to max length
 */
export function truncateContent(content: string, maxLength: number = MAX_CONTENT_LENGTH): string {
  if (content.length <= maxLength) {
    return content;
  }
  return content.slice(0, maxLength) + '...';
}
