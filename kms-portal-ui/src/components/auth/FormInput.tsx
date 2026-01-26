/**
 * Reusable Form Input Component
 */

import React from 'react';

interface FormInputProps {
  id: string;
  label: string;
  type?: 'text' | 'password' | 'email';
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  maxLength?: number;
  className?: string;
  disabled?: boolean;
}

export const FormInput: React.FC<FormInputProps> = ({
  id,
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  autoComplete,
  maxLength,
  className,
  disabled,
}) => {
  return (
    <div className="input-group">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        maxLength={maxLength}
        className={className}
        disabled={disabled}
      />
    </div>
  );
};

export default FormInput;
