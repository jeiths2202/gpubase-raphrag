/**
 * MSW Browser Worker Setup
 *
 * Configures Mock Service Worker for browser environment
 */

import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

// Create the worker instance
export const worker = setupWorker(...handlers);

// Export for use in main.tsx
export { handlers };
