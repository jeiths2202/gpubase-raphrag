/**
 * DocumentCompareModal Component
 * Modal for comparing multiple documents on a specific topic
 */

import React, { useState, useCallback } from 'react';
import {
  X,
  GitCompare,
  FileText,
  ChevronDown,
  ChevronRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { MessageContent } from './MessageContent';
import {
  compareDocuments,
  type ComparisonSummary,
  type DocumentCompareResult,
} from '../../api/documentCompare.api';

interface DocumentCompareModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedDocuments: Array<{
    docId: string;
    docName: string;
  }>;
  defaultTopic?: string;
}

export const DocumentCompareModal: React.FC<DocumentCompareModalProps> = ({
  isOpen,
  onClose,
  selectedDocuments,
  defaultTopic = '',
}) => {
  const [topic, setTopic] = useState(defaultTopic);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComparisonSummary | null>(null);
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());

  const handleCompare = useCallback(async () => {
    if (!topic.trim() || selectedDocuments.length < 2) {
      setError('비교할 주제와 최소 2개의 문서를 선택해주세요.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const comparison = await compareDocuments(
        selectedDocuments.map(d => d.docId),
        topic.trim()
      );
      setResult(comparison);
      // Expand all documents by default
      setExpandedDocs(new Set(comparison.documents.map(d => d.doc_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : '비교 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [topic, selectedDocuments]);

  const toggleDocExpand = (docId: string) => {
    setExpandedDocs(prev => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  if (!isOpen) return null;

  return (
    <div className="document-compare-modal-overlay" onClick={onClose}>
      <div className="document-compare-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="document-compare-modal-header">
          <div className="document-compare-modal-title">
            <GitCompare size={20} />
            <span>문서 비교</span>
          </div>
          <button className="document-compare-modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="document-compare-modal-content">
          {/* Selected Documents */}
          <div className="document-compare-selected">
            <div className="document-compare-selected-label">
              선택된 문서 ({selectedDocuments.length})
            </div>
            <div className="document-compare-selected-list">
              {selectedDocuments.map((doc) => (
                <div key={doc.docId} className="document-compare-selected-item">
                  <FileText size={14} />
                  <span>{doc.docName}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Topic Input */}
          <div className="document-compare-topic">
            <label className="document-compare-topic-label">
              비교 주제
            </label>
            <input
              type="text"
              className="document-compare-topic-input"
              placeholder="비교할 주제나 질문을 입력하세요..."
              value={topic}
              onChange={e => setTopic(e.target.value)}
              disabled={isLoading}
            />
            <button
              className="document-compare-submit"
              onClick={handleCompare}
              disabled={isLoading || !topic.trim() || selectedDocuments.length < 2}
            >
              {isLoading ? (
                <>
                  <Loader2 size={16} className="spin" />
                  비교 중...
                </>
              ) : (
                <>
                  <GitCompare size={16} />
                  비교하기
                </>
              )}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="document-compare-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="document-compare-results">
              {/* Summary */}
              {result.summary && (
                <div className="document-compare-summary">
                  <div className="document-compare-summary-header">
                    <CheckCircle2 size={16} />
                    <span>비교 요약</span>
                  </div>
                  <p className="document-compare-summary-text">{result.summary}</p>
                </div>
              )}

              {/* Commonalities */}
              {result.commonalities.length > 0 && (
                <div className="document-compare-commonalities">
                  <div className="document-compare-section-header">공통점</div>
                  <ul className="document-compare-list">
                    {result.commonalities.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Differences */}
              {result.differences.length > 0 && (
                <div className="document-compare-differences">
                  <div className="document-compare-section-header">차이점</div>
                  <div className="document-compare-diff-list">
                    {result.differences.map((diff, idx) => (
                      <div key={idx} className="document-compare-diff-item">
                        <div className="document-compare-diff-aspect">{diff.aspect}</div>
                        {Object.entries(diff.documents).map(([key, value]) => (
                          <div key={key} className="document-compare-diff-detail">
                            {value}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Document Details */}
              <div className="document-compare-docs">
                <div className="document-compare-section-header">문서별 내용</div>
                {result.documents.map((doc: DocumentCompareResult) => (
                  <div key={doc.doc_id} className="document-compare-doc">
                    <button
                      className="document-compare-doc-header"
                      onClick={() => toggleDocExpand(doc.doc_id)}
                    >
                      {expandedDocs.has(doc.doc_id) ? (
                        <ChevronDown size={16} />
                      ) : (
                        <ChevronRight size={16} />
                      )}
                      <FileText size={16} />
                      <span className="document-compare-doc-name">{doc.doc_name}</span>
                      <span className="document-compare-doc-sections">
                        ({doc.relevant_sections.length}개 섹션)
                      </span>
                    </button>
                    {expandedDocs.has(doc.doc_id) && (
                      <div className="document-compare-doc-content">
                        {doc.relevant_sections.map((section, idx) => (
                          <div key={idx} className="document-compare-section">
                            {section.section_title && (
                              <div className="document-compare-section-title">
                                {section.section_title}
                                {section.page_number && (
                                  <span className="document-compare-section-page">
                                    p.{section.page_number}
                                  </span>
                                )}
                              </div>
                            )}
                            <div className="document-compare-section-content">
                              <MessageContent content={section.content} />
                            </div>
                          </div>
                        ))}
                        {doc.relevant_sections.length === 0 && (
                          <div className="document-compare-no-content">
                            이 주제에 대한 관련 내용이 없습니다.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DocumentCompareModal;
