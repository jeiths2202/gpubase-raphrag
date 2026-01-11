/**
 * AgentChat Module Exports
 */

// Components
export { MessageBubble } from './MessageBubble';
export { MessageContent } from './MessageContent';
export { IMSCredentialsModal, type IMSCredentialsModalProps } from './IMSCredentialsModal';

// Hooks
export { useFileAttachment, type UseFileAttachmentReturn } from './hooks';
export { useUrlAttachment, type UseUrlAttachmentReturn } from './hooks';
export {
  useStreamingChat,
  type UseStreamingChatReturn,
  type StreamingChatDependencies,
} from './hooks';

// Types
export type {
  ChatMessage,
  ToolCallInfo,
  AttachedFile,
  AttachedUrl,
  AgentLocalState,
  AgentSource,
} from './types';

// Constants
export {
  AGENT_CONFIGS,
  SUGGESTED_QUESTIONS,
  URL_REGEX,
  TEXT_EXTENSIONS,
  BINARY_EXTENSIONS,
  SUPPORTED_EXTENSIONS,
  MAX_TEXT_FILE_SIZE,
  MAX_BINARY_FILE_SIZE,
} from './constants';
