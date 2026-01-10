/**
 * Social Login Buttons Component
 *
 * Google OAuth and Corporate SSO buttons.
 */

import React from 'react';
import { motion } from 'framer-motion';
import { GoogleLoginButton } from './GoogleLoginButton';
import type { SocialLoginButtonsProps } from './types';

export const SocialLoginButtons: React.FC<SocialLoginButtonsProps> = ({
  t,
  isLoading,
  isGoogleConfigured,
  onGoogleSuccess,
  onGoogleError,
  onSSOClick,
}) => {
  return (
    <div className="social-buttons">
      {isGoogleConfigured && (
        <GoogleLoginButton
          label={t('auth.googleLogin')}
          isLoading={isLoading}
          onSuccess={onGoogleSuccess}
          onError={onGoogleError}
        />
      )}

      <motion.button
        type="button"
        className="btn-sso"
        onClick={onSSOClick}
        disabled={isLoading}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <span className="sso-icon">&#127970;</span>
        {t('auth.corporateSSO')}
      </motion.button>
    </div>
  );
};

export default SocialLoginButtons;
