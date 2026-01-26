/**
 * Mock API Handlers Index
 *
 * Exports all MSW handlers for the KMS Portal
 */

import { authHandlers } from './auth';
import { knowledgeHandlers } from './knowledge';
import { chatHandlers } from './chat';
import { imsHandlers } from './ims';

export const handlers = [...authHandlers, ...knowledgeHandlers, ...chatHandlers, ...imsHandlers];
