/**
 * MessageContent Component
 * Renders markdown content with ChatGPT-style formatting.
 * Uses react-markdown with syntax highlighting via rehype-highlight.
 *
 * SECURITY: Links are sanitized to prevent XSS via javascript: URIs
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Copy, Check } from 'lucide-react';
import 'highlight.js/styles/github-dark.css';


/**
 * Sanitize URL to prevent XSS attacks via javascript: and other dangerous schemes.
 * Only allows http:, https:, mailto:, and relative URLs.
 */
const sanitizeUrl = (url: string | undefined): string => {
  if (!url) return '#';

  const trimmedUrl = url.trim().toLowerCase();

  // Block dangerous schemes
  if (
    trimmedUrl.startsWith('javascript:') ||
    trimmedUrl.startsWith('vbscript:') ||
    trimmedUrl.startsWith('data:text/html') ||
    trimmedUrl.startsWith('data:application')
  ) {
    return '#';
  }

  // Allow safe schemes and relative URLs
  if (
    trimmedUrl.startsWith('http://') ||
    trimmedUrl.startsWith('https://') ||
    trimmedUrl.startsWith('mailto:') ||
    trimmedUrl.startsWith('/') ||
    trimmedUrl.startsWith('#') ||
    !trimmedUrl.includes(':')  // Relative URLs without scheme
  ) {
    return url;
  }

  return '#';
};

interface MessageContentProps {
  content: string;
  /** Use ChatGPT-style class names (default: true) */
  useChatGPTStyle?: boolean;
}

/**
 * CopyButton - Code block copy button with feedback
 */
const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  return (
    <button
      className={`chatgpt-code-copy ${copied ? 'copied' : ''}`}
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Copy code'}
      type="button"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      <span>{copied ? 'Copied!' : 'Copy'}</span>
    </button>
  );
};

export const MessageContent: React.FC<MessageContentProps> = ({
  content,
  useChatGPTStyle = true,
}) => {
  const [enlargedImg, setEnlargedImg] = useState<string | null>(null);

  if (!content) return null;

  // CSS class prefix based on style mode
  const prefix = useChatGPTStyle ? 'chatgpt' : 'agent';

  return (
    <div className={useChatGPTStyle ? 'chatgpt-markdown' : ''}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Custom table wrapper with horizontal scroll
          table: ({ children }) => (
            <div className={`${prefix}-table-wrapper`}>
              <table className={`${prefix}-markdown-table`}>
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className={`${prefix}-table-header`}>{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className={`${prefix}-table-body`}>{children}</tbody>
          ),
          tr: ({ children }) => (
            <tr className={`${prefix}-table-row`}>{children}</tr>
          ),
          th: ({ children }) => (
            <th className={`${prefix}-table-th`}>{children}</th>
          ),
          td: ({ children }) => (
            <td className={`${prefix}-table-td`}>{children}</td>
          ),
          // Code blocks with syntax highlighting
          code: ({ className, children }) => {
            const match = /language-(\w+)/.exec(className || '');
            const isInline = !match && !String(children).includes('\n');

            if (isInline) {
              return <code className={`${prefix}-inline-code`}>{children}</code>;
            }

            const language = match ? match[1] : 'text';
            const codeString = String(children).replace(/\n$/, '');

            return (
              <pre className={`${prefix}-code-block`}>
                <div className={`${prefix}-code-header`}>
                  <span className={`${prefix}-code-lang`}>{language}</span>
                  <CopyButton text={codeString} />
                </div>
                <code className={className}>{children}</code>
              </pre>
            );
          },
          // Links - open in new tab with XSS protection
          a: ({ href, children }) => (
            <a
              href={sanitizeUrl(href)}
              target="_blank"
              rel="noopener noreferrer"
              className={`${prefix}-markdown-link`}
            >
              {children}
            </a>
          ),
          // Paragraphs
          p: ({ children }) => <p className={`${prefix}-markdown-p`}>{children}</p>,
          // Headers with hierarchy styling
          h1: ({ children }) => <h1 className={`${prefix}-markdown-h1`}>{children}</h1>,
          h2: ({ children }) => <h2 className={`${prefix}-markdown-h2`}>{children}</h2>,
          h3: ({ children }) => <h3 className={`${prefix}-markdown-h3`}>{children}</h3>,
          h4: ({ children }) => <h4 className={`${prefix}-markdown-h4`}>{children}</h4>,
          // Lists
          ul: ({ children }) => <ul className={`${prefix}-markdown-ul`}>{children}</ul>,
          ol: ({ children }) => <ol className={`${prefix}-markdown-ol`}>{children}</ol>,
          li: ({ children }) => <li className={`${prefix}-markdown-li`}>{children}</li>,
          // Blockquote for important notes
          blockquote: ({ children }) => (
            <blockquote className={`${prefix}-markdown-blockquote`}>{children}</blockquote>
          ),
          // Horizontal rule for section dividers
          hr: () => <hr className={`${prefix}-markdown-hr`} />,
          // Strong and emphasis
          strong: ({ children }) => <strong className={`${prefix}-markdown-strong`}>{children}</strong>,
          em: ({ children }) => <em className={`${prefix}-markdown-em`}>{children}</em>,
          // Images - constrain size, click to enlarge
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt || 'Image'}
              className={`${prefix}-markdown-img`}
              loading="lazy"
              style={{ cursor: 'pointer' }}
              onClick={() => src && setEnlargedImg(src)}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
      {enlargedImg && (
        <div
          className={`${prefix}-image-overlay`}
          onClick={() => setEnlargedImg(null)}
        >
          <img
            src={enlargedImg}
            alt="Enlarged"
            className={`${prefix}-image-enlarged`}
          />
        </div>
      )}
    </div>
  );
};

export default MessageContent;
