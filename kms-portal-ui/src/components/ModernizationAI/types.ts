/**
 * Type definitions for Modernization AI Assistant.
 */

export type SystemType = 'host' | 'openframe' | 'all';

export type ChatTab = 'chat' | 'history' | 'sources' | 'notes';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  systemType: SystemType;
  sourceSystem?: 'host' | 'openframe';
  sources?: ChatSource[];
  sections?: ChatSection[];
}

export interface ChatSection {
  sourceSystem: 'host' | 'openframe';
  label: string;
  content: string;
}

export interface ChatSource {
  title: string;
  url?: string;
  domain?: string;
  snippet?: string;
}

export interface ChatNote {
  id: string;
  content: string;
  createdAt: number;
}

export interface ConversationItem {
  id: string;
  title: string;
  systemType: SystemType;
  updatedAt: number;
  messageCount: number;
}

export interface AnalysisContextInfo {
  analysisId?: string;
  fileName?: string;
  assetType?: string;
  sourceCodeSnippet?: string;
  sourceCodeFull?: string;
  targetProduct?: string;
}

export interface SSEEvent {
  type: string;
  token?: string;
  message?: string;
  source_system?: string;
  system_type?: string;
  label?: string;
  sources?: ChatSource[];
  [key: string]: unknown;
}
