import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export default function SSOCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    const handleCallback = async () => {
      const token = searchParams.get('token');

      if (!token) {
        setError('SSO token is missing');
        setIsProcessing(false);
        setTimeout(() => navigate('/login'), 3000);
        return;
      }

      try {
        // Call backend SSO callback endpoint
        const response = await fetch(`/api/v1/auth/sso/callback?token=${token}`, {
          method: 'GET',
          credentials: 'include', // Include cookies
        });

        const data = await response.json();

        if (response.ok && data.success) {
          // Extract tokens from response
          const { access_token, refresh_token } = data.data;

          // Update auth store
          login(access_token, refresh_token);

          // Redirect to dashboard
          setTimeout(() => navigate('/dashboard'), 1000);
        } else {
          const errorMessage = data.error?.message || 'SSO authentication failed';
          setError(errorMessage);
          setIsProcessing(false);
          setTimeout(() => navigate('/login'), 3000);
        }
      } catch (err) {
        console.error('SSO callback error:', err);
        setError('Network error during SSO authentication');
        setIsProcessing(false);
        setTimeout(() => navigate('/login'), 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate, login]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: '#f5f5f5',
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '8px',
        padding: '40px',
        boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
        maxWidth: '400px',
        width: '100%',
        textAlign: 'center'
      }}>
        {isProcessing ? (
          <>
            <div style={{
              width: '50px',
              height: '50px',
              border: '4px solid #f3f3f3',
              borderTop: '4px solid #3498db',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              margin: '0 auto 20px'
            }} />
            <h2 style={{ marginBottom: '10px', color: '#333' }}>
              SSO Authentication
            </h2>
            <p style={{ color: '#666', fontSize: '14px' }}>
              Processing your SSO login...
            </p>
          </>
        ) : error ? (
          <>
            <div style={{
              width: '50px',
              height: '50px',
              backgroundColor: '#e74c3c',
              borderRadius: '50%',
              margin: '0 auto 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontSize: '24px',
              fontWeight: 'bold'
            }}>
              ✕
            </div>
            <h2 style={{ marginBottom: '10px', color: '#e74c3c' }}>
              Authentication Failed
            </h2>
            <p style={{ color: '#666', fontSize: '14px', marginBottom: '20px' }}>
              {error}
            </p>
            <p style={{ color: '#999', fontSize: '12px' }}>
              Redirecting to login page...
            </p>
          </>
        ) : (
          <>
            <div style={{
              width: '50px',
              height: '50px',
              backgroundColor: '#27ae60',
              borderRadius: '50%',
              margin: '0 auto 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontSize: '24px',
              fontWeight: 'bold'
            }}>
              ✓
            </div>
            <h2 style={{ marginBottom: '10px', color: '#27ae60' }}>
              Login Successful
            </h2>
            <p style={{ color: '#666', fontSize: '14px' }}>
              Redirecting to dashboard...
            </p>
          </>
        )}
      </div>

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
