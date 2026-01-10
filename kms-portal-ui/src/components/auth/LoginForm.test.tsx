/**
 * LoginForm Component Unit Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../../test/utils';
import { LoginForm } from './LoginForm';

// Mock GoogleLoginButton to avoid requiring GoogleOAuthProvider
vi.mock('./GoogleLoginButton', () => ({
  GoogleLoginButton: ({ label, onSuccess }: { label: string; onSuccess: (token: string) => void }) => (
    <button type="button" onClick={() => onSuccess('mock-token')}>
      {label}
    </button>
  ),
}));

// Mock translation function
const mockT = (key: string) => {
  const translations: Record<string, string> = {
    'auth.userId': 'User ID',
    'auth.userIdPlaceholder': 'Enter your user ID',
    'auth.password': 'Password',
    'auth.passwordPlaceholder': 'Enter your password',
    'auth.signIn': 'Sign In',
    'auth.orContinueWith': 'Or continue with',
    'auth.googleLogin': 'Google',
    'auth.corporateSSO': 'Corporate SSO',
    'auth.errors.enterIdAndPassword': 'Please enter user ID and password',
  };
  return translations[key] || key;
};

describe('LoginForm', () => {
  const mockOnSubmit = vi.fn();
  const mockOnSSOClick = vi.fn();
  const mockOnGoogleSuccess = vi.fn();
  const mockOnGoogleError = vi.fn();

  const defaultProps = {
    t: mockT,
    isLoading: false,
    onSubmit: mockOnSubmit,
    onSSOClick: mockOnSSOClick,
    onGoogleSuccess: mockOnGoogleSuccess,
    onGoogleError: mockOnGoogleError,
    isGoogleConfigured: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render login form with all fields', () => {
    render(<LoginForm {...defaultProps} />);

    expect(screen.getByLabelText('User ID')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument();
  });

  it('should render Google login button when configured', () => {
    render(<LoginForm {...defaultProps} />);

    expect(screen.getByRole('button', { name: /Google/i })).toBeInTheDocument();
  });

  it('should not render Google login button when not configured', () => {
    render(<LoginForm {...defaultProps} isGoogleConfigured={false} />);

    expect(screen.queryByRole('button', { name: /Google/i })).not.toBeInTheDocument();
  });

  it('should render SSO button', () => {
    render(<LoginForm {...defaultProps} />);

    expect(screen.getByRole('button', { name: /Corporate SSO/i })).toBeInTheDocument();
  });

  it('should call onSubmit with credentials when form is submitted', async () => {
    mockOnSubmit.mockResolvedValueOnce(true);

    render(<LoginForm {...defaultProps} />);

    const userIdInput = screen.getByLabelText('User ID');
    const passwordInput = screen.getByLabelText('Password');
    const submitButton = screen.getByRole('button', { name: 'Sign In' });

    await userEvent.type(userIdInput, 'testuser');
    await userEvent.type(passwordInput, 'password123');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith('testuser', 'password123');
    });
  });

  it('should show error when submitting empty form', async () => {
    render(<LoginForm {...defaultProps} />);

    const submitButton = screen.getByRole('button', { name: 'Sign In' });
    await userEvent.click(submitButton);

    expect(screen.getByText('Please enter user ID and password')).toBeInTheDocument();
    expect(mockOnSubmit).not.toHaveBeenCalled();
  });

  it('should disable form fields when loading', () => {
    render(<LoginForm {...defaultProps} isLoading={true} />);

    // When loading, the button shows a spinner instead of text
    const submitButton = screen.getByRole('button', { name: '' });
    expect(submitButton).toBeDisabled();
    expect(submitButton.querySelector('.spinner')).toBeInTheDocument();
  });

  it('should call onGoogleSuccess when Google button is clicked', async () => {
    render(<LoginForm {...defaultProps} />);

    const googleButton = screen.getByRole('button', { name: /Google/i });
    await userEvent.click(googleButton);

    expect(mockOnGoogleSuccess).toHaveBeenCalledWith('mock-token');
  });

  it('should call onSSOClick when SSO button is clicked', async () => {
    render(<LoginForm {...defaultProps} />);

    const ssoButton = screen.getByRole('button', { name: /Corporate SSO/i });
    await userEvent.click(ssoButton);

    expect(mockOnSSOClick).toHaveBeenCalled();
  });
});
