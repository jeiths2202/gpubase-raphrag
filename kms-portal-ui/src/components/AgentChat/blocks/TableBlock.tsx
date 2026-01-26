/**
 * TableBlock Component
 * Renders tabular data with headers and rows
 */
import React from 'react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface TableBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const TableBlock: React.FC<TableBlockProps> = ({ block, className }) => {
  if (!block.rows || block.rows.length === 0) return null;

  return (
    <div className={`answer-block answer-block-table ${className || ''}`}>
      <div className="table-wrapper">
        <table>
          {block.headers && block.headers.length > 0 && (
            <thead>
              <tr>
                {block.headers.map((header, index) => (
                  <th key={index}>{header}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TableBlock;
