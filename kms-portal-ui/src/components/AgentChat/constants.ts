/**
 * AgentChat Constants
 */

import {
  Sparkles,
  Code,
  Search,
  FileText,
  Globe,
  Brain,
  Shield,
} from 'lucide-react';
import type { AgentType } from '../../api/agent.api';

/**
 * Agent type configuration with icons and descriptions
 */
export const AGENT_CONFIGS: Record<AgentType, { icon: React.ElementType; label: string; description: string }> = {
  auto: {
    icon: Sparkles,
    label: 'Auto',
    description: 'Automatically detect the best agent',
  },
  rag: {
    icon: Search,
    label: 'RAG',
    description: 'Knowledge search and Q&A',
  },
  ims: {
    icon: FileText,
    label: 'IMS',
    description: 'Issue management search',
  },
  vision: {
    icon: Globe,
    label: 'Vision',
    description: 'Image and document analysis',
  },
  code: {
    icon: Code,
    label: 'Code',
    description: 'Code generation and analysis',
  },
  planner: {
    icon: Brain,
    label: 'Planner',
    description: 'Task planning and decomposition',
  },
  opencode: {
    icon: Shield,
    label: 'OpenCode',
    description: 'Document-grounded AI with 5-step verification',
  },
};

/**
 * Suggested questions per agent type
 */
export const SUGGESTED_QUESTIONS: Record<AgentType, string[]> = {
  auto: [
    'osctdlupdate 이슈 찾아줘',
    'What is HybridRAG?',
    'Find authentication issues',
  ],
  rag: [
    'What is HybridRAG?',
    'How does vector search work?',
    'Explain knowledge graphs',
  ],
  ims: [
    'Find authentication issues',
    'Search for recent bug reports',
    'Show high priority issues',
  ],
  vision: [
    'Analyze this document',
    'Describe the image content',
    'Extract text from the file',
  ],
  code: [
    'Write a factorial function',
    'Explain this code snippet',
    'Generate a REST API endpoint',
  ],
  planner: [
    'Plan a new feature implementation',
    'Break down this complex task',
    'Create a project roadmap',
  ],
  opencode: [
    'tjesmgr 명령어 설명해주세요',
    'What is error code -5212?',
    'TACF란 무엇인가요?',
  ],
};

/**
 * URL detection regex
 */
export const URL_REGEX = /https?:\/\/[^\s<>"{}|\\^`[\]]+/gi;

/**
 * Supported file extensions for attachment
 */
export const TEXT_EXTENSIONS = [
  '.txt', '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml',
  '.xml', '.csv', '.log', '.sql', '.sh', '.bat', '.html', '.css'
];
export const BINARY_EXTENSIONS = ['.pdf', '.docx'];
export const ARCHIVE_EXTENSIONS = ['.zip'];
export const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'];
export const SUPPORTED_EXTENSIONS = [...TEXT_EXTENSIONS, ...BINARY_EXTENSIONS, ...ARCHIVE_EXTENSIONS, ...IMAGE_EXTENSIONS];

/**
 * File size limits
 */
export const MAX_TEXT_FILE_SIZE = 500 * 1024; // 500KB for text files
export const MAX_BINARY_FILE_SIZE = 2 * 1024 * 1024; // 2MB for PDF/DOCX
export const MAX_ARCHIVE_FILE_SIZE = 10 * 1024 * 1024; // 10MB for ZIP files
export const MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024; // 5MB for images
