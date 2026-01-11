/**
 * Vitest Test Setup
 *
 * Global test configuration and mocks
 */

import { vi, afterEach, afterAll } from 'vitest';

// Mock window.matchMedia BEFORE any imports that might use it
// This must be at module level, not in beforeAll, because zustand stores
// are initialized at module load time
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver at module level
(window as Window & typeof globalThis).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Now import testing library (after mocks are set up)
import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Reset mocks after all tests
afterAll(() => {
  vi.restoreAllMocks();
});
