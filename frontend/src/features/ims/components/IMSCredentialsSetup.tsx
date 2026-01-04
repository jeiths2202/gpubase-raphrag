/**
 * IMS Credentials Setup Component
 * Modal for entering and validating IMS credentials
 */

import React, { useState } from 'react';
import { imsApiService } from '../services/ims-api';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  t: TranslateFunction;
  onClose: () => void;
  onSuccess: () => void;
}

export const IMSCredentialsSetup: React.FC<Props> = ({ t, onClose, onSuccess }) => {
  const [imsUrl, setImsUrl] = useState('https://ims.tmaxsoft.com');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      await imsApiService.createCredentials({ ims_url: imsUrl, username, password });
      await imsApiService.validateCredentials();
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save credentials');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '32px',
        maxWidth: '500px',
        width: '100%'
      }}>
        <h2 style={{ margin: '0 0 16px', fontSize: '20px' }}>IMS Credentials Setup</h2>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
              IMS URL
            </label>
            <input
              type="url"
              value={imsUrl}
              onChange={(e) => setImsUrl(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
                fontSize: '14px'
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
                fontSize: '14px'
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
                fontSize: '14px'
              }}
            />
          </div>
          {error && (
            <div style={{
              padding: '12px',
              background: 'rgba(231, 76, 60, 0.1)',
              border: '1px solid #E74C3C',
              borderRadius: '6px',
              color: '#E74C3C',
              fontSize: '14px'
            }}>
              {error}
            </div>
          )}
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              style={{
                padding: '10px 20px',
                background: 'transparent',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                padding: '10px 20px',
                background: 'var(--accent)',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                fontWeight: 600,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.6 : 1,
                fontSize: '14px'
              }}
            >
              {isSubmitting ? 'Saving...' : 'Save & Validate'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
