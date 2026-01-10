/**
 * Shared types for auth components
 */

export type AuthMode = 'login' | 'register' | 'verify' | 'forgot';

export interface AuthFormProps {
  t: (key: string) => string;
  isLoading: boolean;
  onSuccess?: () => void;
}

export interface LoginFormProps extends AuthFormProps {
  onSubmit: (userId: string, password: string) => Promise<boolean>;
  onSSOClick: () => void;
  onGoogleSuccess: (token: string) => Promise<void>;
  onGoogleError: () => void;
  isGoogleConfigured: boolean;
}

export interface RegisterFormProps extends AuthFormProps {
  onSubmit: (userId: string, email: string, password: string) => Promise<boolean>;
  onModeChange: (mode: AuthMode) => void;
}

export interface VerifyFormProps extends AuthFormProps {
  email: string;
  onSubmit: (code: string) => Promise<boolean>;
  onBack: () => void;
}

export interface SSOFormProps extends AuthFormProps {
  onSubmit: (email: string) => Promise<void>;
  onBack: () => void;
  validateEmail: (email: string) => boolean;
}

export interface SocialLoginButtonsProps {
  t: (key: string) => string;
  isLoading: boolean;
  isGoogleConfigured: boolean;
  onGoogleSuccess: (token: string) => Promise<void>;
  onGoogleError: () => void;
  onSSOClick: () => void;
}
