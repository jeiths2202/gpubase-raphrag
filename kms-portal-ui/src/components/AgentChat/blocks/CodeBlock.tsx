/**
 * CodeBlock Component
 * Renders code with syntax highlighting and copy button
 */
import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface CodeBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ block, className }) => {
  const [copied, setCopied] = useState(false);

  if (!block.content) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(block.content || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  return (
    <div className={`answer-block answer-block-code ${className || ''}`}>
      <div className="code-header">
        {block.language && (
          <span className="code-language">{block.language}</span>
        )}
        <button
          className={`code-copy-btn ${copied ? 'copied' : ''}`}
          onClick={handleCopy}
          title={copied ? 'Copied!' : 'Copy code'}
          type="button"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <pre>
        <code className={block.language ? `language-${block.language}` : ''}>
          {block.content}
        </code>
      </pre>
    </div>
  );
};

export default CodeBlock;
