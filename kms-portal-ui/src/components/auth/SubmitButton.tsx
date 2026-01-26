/**
 * Animated Submit Button Component
 */

import React from 'react';
import { motion } from 'framer-motion';

interface SubmitButtonProps {
  label: string;
  isLoading: boolean;
  disabled?: boolean;
  type?: 'submit' | 'button';
  onClick?: () => void;
  className?: string;
}

export const SubmitButton: React.FC<SubmitButtonProps> = ({
  label,
  isLoading,
  disabled = false,
  type = 'submit',
  onClick,
  className = 'btn-primary',
}) => {
  return (
    <motion.button
      type={type}
      className={className}
      disabled={disabled || isLoading}
      onClick={onClick}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      {isLoading ? <span className="spinner" /> : label}
    </motion.button>
  );
};

export default SubmitButton;
