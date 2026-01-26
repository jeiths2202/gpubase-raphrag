/**
 * OAuth Callback Page
 *
 * Handles OAuth callback from external services (Notion, GitHub, etc.)
 * Extracts authorization code from URL and completes the OAuth flow.
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { useExternalConnectorsStore } from '../store/externalConnectorsStore';

type CallbackStatus = 'processing' | 'success' | 'error';

export const OAuthCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<CallbackStatus>('processing');
  const [errorMessage, setErrorMessage] = useState<string>('');

  // Flag to prevent duplicate processing (React strict mode or dependency changes)
  const isProcessingRef = useRef(false);
  const hasProcessedRef = useRef(false);

  const {
    pendingOAuthConnectionId,
    completeOAuthFlow,
    cancelSSO
  } = useExternalConnectorsStore();

  const processCallback = useCallback(async () => {
    // Prevent duplicate processing
    if (isProcessingRef.current || hasProcessedRef.current) {
      console.log('[OAuthCallback] Skipping duplicate processing');
      return;
    }
    isProcessingRef.current = true;
    // Extract parameters from URL
    const code = searchParams.get('code');
    const error = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');
    const state = searchParams.get('state');

    console.log('[OAuthCallback] Processing callback:', { code: code?.substring(0, 20), state, error, pendingOAuthConnectionId });

    // Check for OAuth errors
    if (error) {
      hasProcessedRef.current = true;
      isProcessingRef.current = false;
      setStatus('error');
      setErrorMessage(errorDescription || error || 'OAuth authorization was denied');
      return;
    }

    // Validate authorization code
    if (!code) {
      hasProcessedRef.current = true;
      isProcessingRef.current = false;
      setStatus('error');
      setErrorMessage('No authorization code received');
      return;
    }

    // SECURITY: State parameter is required for CSRF protection
    // State format: "{connection_id}:{random_token}"
    if (!state) {
      hasProcessedRef.current = true;
      isProcessingRef.current = false;
      setStatus('error');
      setErrorMessage('Missing OAuth state parameter. This may be a security issue.');
      console.error('[OAuthCallback] Missing state parameter - potential CSRF attack');
      return;
    }

    // Extract connection ID from state for fallback (primary source is pendingOAuthConnectionId)
    let connectionId = pendingOAuthConnectionId;
    if (!connectionId) {
      const stateParts = state.split(':');
      if (stateParts.length >= 1) {
        connectionId = stateParts[0];
        console.log('[OAuthCallback] Extracted connectionId from state:', connectionId);
      }
    }

    // Check for pending connection
    if (!connectionId) {
      hasProcessedRef.current = true;
      isProcessingRef.current = false;
      setStatus('error');
      setErrorMessage('No pending OAuth connection found. Please try connecting again.');
      console.error('[OAuthCallback] No connectionId found. state:', state, 'pendingOAuthConnectionId:', pendingOAuthConnectionId);
      return;
    }

    console.log('[OAuthCallback] Using connectionId:', connectionId);

    try {
      // Complete the OAuth flow with state for CSRF validation
      await completeOAuthFlow(connectionId, code, state);
      hasProcessedRef.current = true;
      setStatus('success');

      // Try to close the popup window if this was opened in a popup
      if (window.opener) {
        // Notify opener window
        console.log('[OAuthCallback] Sending oauth_success message to opener:', { connectionId, origin: window.location.origin });
        window.opener.postMessage({ type: 'oauth_success', connectionId: connectionId }, window.location.origin);
        console.log('[OAuthCallback] Message sent, closing popup in 1.5s');
        // Close popup after brief delay
        setTimeout(() => {
          window.close();
        }, 1500);
      } else {
        // Redirect to agent page if in main window
        setTimeout(() => {
          navigate('/agent', { replace: true });
        }, 2000);
      }
    } catch (err) {
      hasProcessedRef.current = true;
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Failed to complete authentication');
    } finally {
      isProcessingRef.current = false;
    }
  }, [searchParams, pendingOAuthConnectionId, completeOAuthFlow, navigate]);

  useEffect(() => {
    processCallback();
  }, [processCallback]);

  const handleClose = () => {
    cancelSSO();
    if (window.opener) {
      window.close();
    } else {
      navigate('/agent', { replace: true });
    }
  };

  const handleRetry = () => {
    cancelSSO();
    if (window.opener) {
      window.close();
    } else {
      navigate('/agent', { replace: true });
    }
  };

  return (
    <div className="oauth-callback-page">
      <div className="oauth-callback-container">
        {status === 'processing' && (
          <div className="oauth-callback-status processing">
            <Loader2 size={48} className="spin" />
            <h2>Completing Authentication</h2>
            <p>Please wait while we connect your account...</p>
          </div>
        )}

        {status === 'success' && (
          <div className="oauth-callback-status success">
            <CheckCircle2 size={48} />
            <h2>Connected Successfully!</h2>
            <p>Your account has been connected. You can now access your resources.</p>
            {window.opener ? (
              <p className="oauth-callback-hint">This window will close automatically...</p>
            ) : (
              <p className="oauth-callback-hint">Redirecting to AI Agent...</p>
            )}
          </div>
        )}

        {status === 'error' && (
          <div className="oauth-callback-status error">
            <XCircle size={48} />
            <h2>Connection Failed</h2>
            <p>{errorMessage}</p>
            <div className="oauth-callback-actions">
              <button className="oauth-callback-btn primary" onClick={handleRetry}>
                Try Again
              </button>
              <button className="oauth-callback-btn secondary" onClick={handleClose}>
                Close
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .oauth-callback-page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--bg-primary, #f5f5f5);
          padding: 20px;
        }

        .oauth-callback-container {
          background: var(--bg-secondary, #ffffff);
          border-radius: 12px;
          padding: 40px;
          max-width: 400px;
          width: 100%;
          text-align: center;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        }

        .oauth-callback-status {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }

        .oauth-callback-status h2 {
          margin: 0;
          font-size: 1.5rem;
          font-weight: 600;
          color: var(--text-primary, #333);
        }

        .oauth-callback-status p {
          margin: 0;
          color: var(--text-secondary, #666);
          line-height: 1.5;
        }

        .oauth-callback-status.processing svg {
          color: var(--accent-color, #3b82f6);
        }

        .oauth-callback-status.success svg {
          color: #22c55e;
        }

        .oauth-callback-status.error svg {
          color: #ef4444;
        }

        .oauth-callback-hint {
          font-size: 0.875rem;
          color: var(--text-tertiary, #999);
          font-style: italic;
        }

        .oauth-callback-actions {
          display: flex;
          gap: 12px;
          margin-top: 8px;
        }

        .oauth-callback-btn {
          padding: 10px 20px;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          border: none;
        }

        .oauth-callback-btn.primary {
          background: var(--accent-color, #3b82f6);
          color: white;
        }

        .oauth-callback-btn.primary:hover {
          background: var(--accent-hover, #2563eb);
        }

        .oauth-callback-btn.secondary {
          background: var(--bg-tertiary, #e5e7eb);
          color: var(--text-primary, #333);
        }

        .oauth-callback-btn.secondary:hover {
          background: var(--bg-hover, #d1d5db);
        }

        .spin {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default OAuthCallbackPage;
