/**
 * MessageContent Component
 * Renders markdown content with custom styling for tables, code blocks, links, etc.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy } from 'lucide-react';

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
        // Links - open in new tab
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="agent-markdown-link">
            {children}
          </a>
        ),
        p: ({ children }) => <p className="agent-markdown-p">{children}</p>,
        h2: ({ children }) => <h2 className="agent-markdown-h2">{children}</h2>,
        h3: ({ children }) => <h3 className="agent-markdown-h3">{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

export default MessageContent;
