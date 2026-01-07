/**
 * Main Entry Point
 *
 * Application bootstrap with MSW initialization
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

/**
 * Initialize MSW and render app
 */
async function enableMocking() {
  // Only enable MSW in development
  if (import.meta.env.DEV) {
    const { worker } = await import('./mocks/browser');

    // Start the worker
    return worker.start({
      onUnhandledRequest: 'bypass', // Don't warn about unhandled requests
      serviceWorker: {
        url: '/mockServiceWorker.js',
      },
    });
  }

  return Promise.resolve();
}

// Initialize app
enableMocking().then(() => {
  const root = document.getElementById('root');

  if (!root) {
    throw new Error('Root element not found');
  }

  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
