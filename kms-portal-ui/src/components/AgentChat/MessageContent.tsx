/**
 * MessageContent Component
 * Renders markdown content with custom styling for tables, code blocks, links, etc.
 *
 * SECURITY: Links are sanitized to prevent XSS via javascript: URIs
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy } from 'lucide-react';


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
}

export const MessageContent: React.FC<MessageContentProps> = ({ content }) => {
  if (!content) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Custom table wrapper with horizontal scroll
        table: ({ children }) => (
          <div className="agent-table-wrapper">
            <table className="agent-markdown-table">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="agent-table-header">{children}</thead>
        ),
        tbody: ({ children }) => (
          <tbody className="agent-table-body">{children}</tbody>
        ),
        tr: ({ children }) => (
          <tr className="agent-table-row">{children}</tr>
        ),
        th: ({ children }) => (
          <th className="agent-table-th">{children}</th>
        ),
        td: ({ children }) => (
          <td className="agent-table-td">{children}</td>
        ),
        // Code blocks
        code: ({ className, children }) => {
          const match = /language-(\w+)/.exec(className || '');
          const isInline = !match && !String(children).includes('\n');

          if (isInline) {
            return <code className="agent-inline-code">{children}</code>;
          }

          const language = match ? match[1] : 'text';
          const codeString = String(children).replace(/\n$/, '');

          return (
            <pre className="agent-code-block">
              <div className="agent-code-header">
                <span className="agent-code-lang">{language}</span>
                <button
                  className="agent-code-copy"
                  onClick={() => navigator.clipboard.writeText(codeString)}
                  title="Copy code"
                >
                  <Copy size={12} />
                </button>
              </div>
              <code>{codeString}</code>
            </pre>
          );
        },
        // Links - open in new tab with XSS protection
        a: ({ href, children }) => (
          <a
            href={sanitizeUrl(href)}
            target="_blank"
            rel="noopener noreferrer"
            className="agent-markdown-link"
          >
            {children}
          </a>
        ),
        // Paragraphs
        p: ({ children }) => <p className="agent-markdown-p">{children}</p>,
        // Headers with hierarchy styling
        h1: ({ children }) => <h1 className="agent-markdown-h1">{children}</h1>,
        h2: ({ children }) => <h2 className="agent-markdown-h2">{children}</h2>,
        h3: ({ children }) => <h3 className="agent-markdown-h3">{children}</h3>,
        h4: ({ children }) => <h4 className="agent-markdown-h4">{children}</h4>,
        // Lists
        ul: ({ children }) => <ul className="agent-markdown-ul">{children}</ul>,
        ol: ({ children }) => <ol className="agent-markdown-ol">{children}</ol>,
        li: ({ children }) => <li className="agent-markdown-li">{children}</li>,
        // Blockquote for important notes
        blockquote: ({ children }) => (
          <blockquote className="agent-markdown-blockquote">{children}</blockquote>
        ),
        // Horizontal rule for section dividers
        hr: () => <hr className="agent-markdown-hr" />,
        // Strong and emphasis
        strong: ({ children }) => <strong className="agent-markdown-strong">{children}</strong>,
        em: ({ children }) => <em className="agent-markdown-em">{children}</em>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

export default MessageContent;
