/**
 * ClarificationBlock Component
 *
 * Displays query clarification options when the AI needs
 * more context to provide an accurate answer (Human-in-the-loop).
 */
import React, { useState } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import type { ClarificationRequest, ClarificationOption } from '../types';

interface ClarificationBlockProps {
  request: ClarificationRequest;
  selectedOptionId: string | null;
  customInput: string;
  onSelectOption: (optionId: string) => void;
  onCustomInputChange: (input: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
}

export const ClarificationBlock: React.FC<ClarificationBlockProps> = ({
  request,
  selectedOptionId,
  customInput,
  onSelectOption,
  onCustomInputChange,
  onSubmit,
  onSkip,
}) => {
  const { t } = useTranslation();
  const [showCustomInput, setShowCustomInput] = useState(false);

  const handleOptionClick = (option: ClarificationOption) => {
    setShowCustomInput(false);
    onSelectOption(option.option_id);
  };

  const handleCustomClick = () => {
    setShowCustomInput(true);
    onSelectOption(''); // Clear option selection
  };

  const canSubmit = selectedOptionId || customInput.trim();

  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        borderRadius: '12px',
        padding: '16px',
        marginBottom: '16px',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '12px',
        }}
      >
        <span style={{ fontSize: '20px' }}>?</span>
        <span
          style={{
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {t('agent.clarification.title') || 'Question Clarification'}
        </span>
      </div>

      {/* Question */}
      <p
        style={{
          color: 'var(--text-primary)',
          marginBottom: '16px',
          fontSize: '14px',
          lineHeight: 1.5,
        }}
      >
        {request.clarification_question}
      </p>

      {/* Options */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          marginBottom: '16px',
        }}
      >
        {request.options.map((option) => (
          <button
            key={option.option_id}
            onClick={() => handleOptionClick(option)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              padding: '12px 16px',
              borderRadius: '8px',
              border: selectedOptionId === option.option_id
                ? '2px solid var(--primary-color)'
                : '1px solid var(--border-color)',
              background: selectedOptionId === option.option_id
                ? 'var(--primary-color-light, rgba(139, 92, 246, 0.1))'
                : 'var(--bg-tertiary)',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease',
            }}
          >
            <span
              style={{
                fontWeight: 500,
                color: 'var(--text-primary)',
                marginBottom: '4px',
              }}
            >
              {option.label}
            </span>
            <span
              style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
              }}
            >
              {option.description}
            </span>
          </button>
        ))}

        {/* Custom input option */}
        {request.allow_custom_input && (
          <button
            onClick={handleCustomClick}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 16px',
              borderRadius: '8px',
              border: showCustomInput
                ? '2px solid var(--primary-color)'
                : '1px solid var(--border-color)',
              background: showCustomInput
                ? 'var(--primary-color-light, rgba(139, 92, 246, 0.1))'
                : 'var(--bg-tertiary)',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease',
            }}
          >
            <span style={{ color: 'var(--text-secondary)' }}>+</span>
            <span style={{ color: 'var(--text-secondary)' }}>
              {t('agent.clarification.customInput') || 'Enter custom query...'}
            </span>
          </button>
        )}

        {/* Custom input field */}
        {showCustomInput && (
          <div style={{ marginTop: '8px' }}>
            <input
              type="text"
              value={customInput}
              onChange={(e) => onCustomInputChange(e.target.value)}
              placeholder={t('agent.clarification.customPlaceholder') || 'Type your specific question...'}
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: '14px',
                outline: 'none',
              }}
              autoFocus
            />
          </div>
        )}
      </div>

      {/* Actions */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '8px',
        }}
      >
        <button
          onClick={onSkip}
          style={{
            padding: '8px 16px',
            borderRadius: '6px',
            border: '1px solid var(--border-color)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '14px',
          }}
        >
          {t('agent.clarification.skip') || 'Search anyway'}
        </button>
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          style={{
            padding: '8px 16px',
            borderRadius: '6px',
            border: 'none',
            background: canSubmit ? 'var(--primary-color)' : 'var(--bg-disabled)',
            color: canSubmit ? 'white' : 'var(--text-disabled)',
            cursor: canSubmit ? 'pointer' : 'not-allowed',
            fontSize: '14px',
            fontWeight: 500,
          }}
        >
          {t('agent.clarification.search') || 'Search'}
        </button>
      </div>
    </div>
  );
};

export default ClarificationBlock;
