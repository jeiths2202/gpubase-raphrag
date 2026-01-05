/**
 * Playwright Configuration for Visual Regression Testing
 *
 * Usage:
 *   npm run test:visual          # Run visual tests
 *   npm run test:visual:update   # Update baseline screenshots
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  // Test directory
  testDir: './src/__tests__',
  testMatch: '**/*.spec.ts',

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: process.env.CI ? 'github' : 'html',

  // Shared settings for all projects
  use: {
    // Base URL for navigation
    baseURL: 'http://localhost:3000',

    // MANDATORY: Enable trace for all tests
    trace: 'on',

    // MANDATORY: Enable screenshots for all tests
    screenshot: 'on',

    // MANDATORY: Enable video recording for all tests
    video: 'on',
  },

  // Configure projects for major browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Optionally add more browsers for cross-browser testing
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  // Snapshot settings
  snapshotDir: './src/__tests__/__snapshots__',

  // Expect settings for visual comparisons
  expect: {
    // Tolerate minor pixel differences (anti-aliasing, font rendering)
    toHaveScreenshot: {
      maxDiffPixels: 100,
      threshold: 0.2,
    },
  },

  // Run your local dev server before starting the tests
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
