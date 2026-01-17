/**
 * Enhancement Detail Modal for Admin Dashboard
 * Displays detailed enhancement info with admin workflow controls
 */
import React, { useState, useEffect } from 'react';
import {
  X,
  Bot,
  Clock,
  User,
  FileText,
  GitBranch,
  Code,
  ListChecks,
  Play,
  CheckCircle,
  XCircle,
  Loader2,
  AlertCircle,
  Shield,
  Database,
  TestTube,
  Undo2,
  FileCode,
} from 'lucide-react';
import { formatDate, getStatusColor, getPriorityColor, getTypeIcon } from './utils';

// API Response types (matching improvements.api.ts)
interface EnhancementDetail {
  id: string;
  title: string;
  description: string;
  type: string | null;
  priority: string | null;
  status: string;
  author_id: string;
  author_name: string;
  created_at: string;
  updated_at: string;
  ai_analyzed: boolean;
  ai_analysis: AIAnalysis | null;
  architecture_proposal: ArchitectureProposal | null;
  implementation_plan: ImplementationPlan | null;
  timeline: TimelineEvent[];
  attachments: Attachment[];
  comments: Comment[];
}

interface AIAnalysis {
  summary: string;
  feasibility_score: number;
  estimated_complexity: string;
  affected_components: string[];
  potential_risks: string[];
  recommended_approach: string;
}

interface ArchitectureProposal {
  approach: string;
  design_decisions: DesignDecision[];
  file_changes: FileChange[];
  new_files: NewFile[];
  api_changes: APIChange[];
  database_changes: string[];
  security_considerations: string[];
  backward_compatible: boolean;
  migration_required: boolean;
}

interface DesignDecision {
  title: string;
  description: string;
  rationale: string;
  alternatives_considered: string[];
  trade_offs?: string;
}

interface FileChange {
  file_path: string;
  change_type: string;
  description: string;
  estimated_lines: number;
}

interface NewFile {
  file_path: string;
  purpose: string;
}

interface APIChange {
  method: string;
  endpoint: string;
  change_type: string;
  description: string;
}

interface ImplementationPlan {
  phases: Phase[];
  test_strategy: TestStrategy;
  rollback_plan: string;
}

interface Phase {
  phase_number: number;
  title: string;
  description: string;
  tasks: string[];
  dependencies: number[];
  estimated_effort?: string;
}

interface TestStrategy {
  unit_tests: string[];
  integration_tests: string[];
  e2e_tests: string[];
  manual_tests: string[];
}

interface TimelineEvent {
  id: string;
  timestamp: string;
  actor_type: 'user' | 'agent';
  actor_name: string;
  description: string;
}

interface Attachment {
  id: string;
  original_name: string;
  file_size: number;
}

interface Comment {
  id: string;
  author_name: string;
  author_type: 'user' | 'agent';
  content: string;
  created_at: string;
}

interface EnhanceDetailModalProps {
  requestId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onActionComplete: () => void;
}

type TabType = 'description' | 'analysis' | 'architecture' | 'implementation' | 'timeline';

export const EnhanceDetailModal: React.FC<EnhanceDetailModalProps> = ({
  requestId,
  isOpen,
  onClose,
  onActionComplete,
}) => {
  const [detail, setDetail] = useState<EnhancementDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('description');

  // Action states
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isDesigning, setIsDesigning] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [isImplementing, setIsImplementing] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  // Fetch detail when modal opens
  useEffect(() => {
    if (isOpen && requestId) {
      fetchDetail();
    }
  }, [isOpen, requestId]);

  const fetchDetail = async () => {
    if (!requestId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to fetch enhancement detail');
      const data = await response.json();
      setDetail(data.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load detail');
    } finally {
      setLoading(false);
    }
  };

  // Action handlers
  const handleAnalyze = async () => {
    if (!requestId) return;
    setIsAnalyzing(true);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}/analyze`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to analyze');
      await fetchDetail();
      onActionComplete();
    } catch (err) {
      console.error('Analyze failed:', err);
      alert('Failed to analyze enhancement');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDesignArchitecture = async () => {
    if (!requestId) return;
    setIsDesigning(true);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}/architecture`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to design architecture');
      await fetchDetail();
      onActionComplete();
    } catch (err) {
      console.error('Design failed:', err);
      alert('Failed to design architecture');
    } finally {
      setIsDesigning(false);
    }
  };

  const handleApprove = async () => {
    if (!requestId) return;
    setIsApproving(true);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}/approve`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to approve');
      await fetchDetail();
      onActionComplete();
    } catch (err) {
      console.error('Approve failed:', err);
      alert('Failed to approve enhancement');
    } finally {
      setIsApproving(false);
    }
  };

  const handleReject = async () => {
    if (!requestId || !rejectReason.trim()) return;
    setIsRejecting(true);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}/reject`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (!response.ok) throw new Error('Failed to reject');
      setShowRejectModal(false);
      setRejectReason('');
      await fetchDetail();
      onActionComplete();
    } catch (err) {
      console.error('Reject failed:', err);
      alert('Failed to reject enhancement');
    } finally {
      setIsRejecting(false);
    }
  };

  const handleImplement = async () => {
    if (!requestId) return;
    setIsImplementing(true);
    try {
      const response = await fetch(`/api/v1/enhancements/${requestId}/implement`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to start implementation');
      await fetchDetail();
      onActionComplete();
    } catch (err) {
      console.error('Implement failed:', err);
      alert('Failed to start implementation');
    } finally {
      setIsImplementing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="enhance-modal-overlay" onClick={onClose}>
      <div className="enhance-modal enhance-detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="enhance-modal-header">
          <h2>Enhancement Details</h2>
          <button className="enhance-modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="enhance-modal-content">
          {loading && (
            <div className="enhance-detail-loading">
              <Loader2 size={32} className="spinning" />
              <p>Loading enhancement details...</p>
            </div>
          )}

          {error && (
            <div className="enhance-detail-error">
              <AlertCircle size={32} />
              <p>{error}</p>
              <button onClick={fetchDetail}>Retry</button>
            </div>
          )}

          {!loading && !error && detail && (
            <>
              {/* Title Section */}
              <div className="enhance-detail-title-section">
                <div className="enhance-detail-title-row">
                  {detail.type && (
                    <span className="enhance-type-icon">{getTypeIcon(detail.type as any)}</span>
                  )}
                  <h3>{detail.title}</h3>
                </div>

                <div className="enhance-detail-badges">
                  <span
                    className="enhance-status-badge"
                    style={{
                      backgroundColor: `${getStatusColor(detail.status as any)}20`,
                      color: getStatusColor(detail.status as any),
                    }}
                  >
                    {detail.status.replace('_', ' ')}
                  </span>
                  {detail.priority && (
                    <span
                      className="enhance-priority-badge"
                      style={{
                        backgroundColor: `${getPriorityColor(detail.priority as any)}20`,
                        color: getPriorityColor(detail.priority as any),
                      }}
                    >
                      {detail.priority}
                    </span>
                  )}
                  {detail.ai_analyzed && (
                    <span className="enhance-ai-analyzed-badge">
                      <Bot size={14} />
                      AI Analyzed
                    </span>
                  )}
                </div>

                <div className="enhance-detail-meta">
                  <span>
                    <User size={14} />
                    {detail.author_name}
                  </span>
                  <span>
                    <Clock size={14} />
                    {formatDate(detail.created_at)}
                  </span>
                </div>
              </div>

              {/* Admin Actions */}
              <div className="enhance-detail-actions">
                {detail.status === 'submitted' && (
                  <button
                    className="enhance-action-btn enhance-action-btn--analyze"
                    onClick={handleAnalyze}
                    disabled={isAnalyzing}
                  >
                    {isAnalyzing ? <Loader2 size={16} className="spinning" /> : <Bot size={16} />}
                    Analyze with AI
                  </button>
                )}

                {detail.status === 'analyzed' && (
                  <>
                    {!detail.architecture_proposal && (
                      <button
                        className="enhance-action-btn enhance-action-btn--design"
                        onClick={handleDesignArchitecture}
                        disabled={isDesigning}
                      >
                        {isDesigning ? <Loader2 size={16} className="spinning" /> : <GitBranch size={16} />}
                        Design Architecture
                      </button>
                    )}
                    <button
                      className="enhance-action-btn enhance-action-btn--approve"
                      onClick={handleApprove}
                      disabled={isApproving}
                    >
                      {isApproving ? <Loader2 size={16} className="spinning" /> : <CheckCircle size={16} />}
                      Approve
                    </button>
                    <button
                      className="enhance-action-btn enhance-action-btn--reject"
                      onClick={() => setShowRejectModal(true)}
                    >
                      <XCircle size={16} />
                      Reject
                    </button>
                  </>
                )}

                {detail.status === 'approved' && (
                  <button
                    className="enhance-action-btn enhance-action-btn--implement"
                    onClick={handleImplement}
                    disabled={isImplementing}
                  >
                    {isImplementing ? <Loader2 size={16} className="spinning" /> : <Play size={16} />}
                    Start Implementation
                  </button>
                )}
              </div>

              {/* Tabs */}
              <div className="enhance-detail-tabs">
                <button
                  className={activeTab === 'description' ? 'active' : ''}
                  onClick={() => setActiveTab('description')}
                >
                  Description
                </button>
                <button
                  className={activeTab === 'analysis' ? 'active' : ''}
                  onClick={() => setActiveTab('analysis')}
                  disabled={!detail.ai_analysis}
                >
                  Analysis
                  {detail.ai_analysis && <Bot size={12} />}
                </button>
                <button
                  className={activeTab === 'architecture' ? 'active' : ''}
                  onClick={() => setActiveTab('architecture')}
                  disabled={!detail.architecture_proposal}
                >
                  Architecture
                </button>
                <button
                  className={activeTab === 'implementation' ? 'active' : ''}
                  onClick={() => setActiveTab('implementation')}
                  disabled={!detail.implementation_plan}
                >
                  Implementation
                </button>
                <button
                  className={activeTab === 'timeline' ? 'active' : ''}
                  onClick={() => setActiveTab('timeline')}
                >
                  Timeline
                </button>
              </div>

              {/* Tab Content */}
              <div className="enhance-detail-tab-content">
                {/* Description Tab */}
                {activeTab === 'description' && (
                  <div className="enhance-tab-description">
                    <pre>{detail.description}</pre>
                    {detail.attachments.length > 0 && (
                      <div className="enhance-attachments">
                        <h4>Attachments</h4>
                        {detail.attachments.map((att) => (
                          <div key={att.id} className="enhance-attachment-item">
                            <FileText size={16} />
                            <span>{att.original_name}</span>
                            <span className="enhance-attachment-size">
                              {(att.file_size / 1024).toFixed(1)} KB
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Analysis Tab */}
                {activeTab === 'analysis' && detail.ai_analysis && (
                  <div className="enhance-tab-analysis">
                    <div className="enhance-analysis-section">
                      <h4>Summary</h4>
                      <p>{detail.ai_analysis.summary}</p>
                    </div>

                    <div className="enhance-analysis-grid">
                      <div className="enhance-analysis-card">
                        <label>Feasibility</label>
                        <div className="enhance-progress-bar">
                          <div
                            className="enhance-progress-fill"
                            style={{ width: `${detail.ai_analysis.feasibility_score * 100}%` }}
                          />
                        </div>
                        <span>{Math.round(detail.ai_analysis.feasibility_score * 100)}%</span>
                      </div>
                      <div className="enhance-analysis-card">
                        <label>Complexity</label>
                        <span className="enhance-complexity-badge">
                          {detail.ai_analysis.estimated_complexity}
                        </span>
                      </div>
                    </div>

                    {detail.ai_analysis.affected_components.length > 0 && (
                      <div className="enhance-analysis-section">
                        <h4>Affected Components</h4>
                        <ul>
                          {detail.ai_analysis.affected_components.map((comp, i) => (
                            <li key={i}>{comp}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {detail.ai_analysis.potential_risks.length > 0 && (
                      <div className="enhance-analysis-section">
                        <h4>Potential Risks</h4>
                        <ul className="enhance-risk-list">
                          {detail.ai_analysis.potential_risks.map((risk, i) => (
                            <li key={i}>{risk}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="enhance-analysis-section">
                      <h4>Recommended Approach</h4>
                      <p>{detail.ai_analysis.recommended_approach}</p>
                    </div>
                  </div>
                )}

                {/* Architecture Tab */}
                {activeTab === 'architecture' && detail.architecture_proposal && (
                  <div className="enhance-tab-architecture">
                    <div className="enhance-arch-section">
                      <h4>Implementation Approach</h4>
                      <p>{detail.architecture_proposal.approach}</p>
                    </div>

                    {detail.architecture_proposal.design_decisions.length > 0 && (
                      <div className="enhance-arch-section">
                        <h4>Design Decisions</h4>
                        {detail.architecture_proposal.design_decisions.map((decision, i) => (
                          <div key={i} className="enhance-decision-card">
                            <div className="enhance-decision-header">
                              <GitBranch size={14} />
                              <h5>{decision.title}</h5>
                            </div>
                            <p>{decision.description}</p>
                            <div className="enhance-decision-rationale">
                              <strong>Rationale:</strong> {decision.rationale}
                            </div>
                            {decision.trade_offs && (
                              <div className="enhance-decision-tradeoffs">
                                <strong>Trade-offs:</strong> {decision.trade_offs}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {detail.architecture_proposal.file_changes.length > 0 && (
                      <div className="enhance-arch-section">
                        <h4>
                          <FileCode size={16} />
                          File Changes
                        </h4>
                        <div className="enhance-file-list">
                          {detail.architecture_proposal.file_changes.map((file, i) => (
                            <div key={i} className="enhance-file-item">
                              <Code size={14} />
                              <code>{file.file_path}</code>
                              <span className={`enhance-change-type ${file.change_type}`}>
                                {file.change_type}
                              </span>
                              {file.estimated_lines > 0 && (
                                <span className="enhance-lines">~{file.estimated_lines} lines</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {detail.architecture_proposal.database_changes.length > 0 && (
                      <div className="enhance-arch-section">
                        <h4>
                          <Database size={16} />
                          Database Changes
                        </h4>
                        <ul>
                          {detail.architecture_proposal.database_changes.map((change, i) => (
                            <li key={i}>{change}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {detail.architecture_proposal.security_considerations.length > 0 && (
                      <div className="enhance-arch-section">
                        <h4>
                          <Shield size={16} />
                          Security Considerations
                        </h4>
                        <ul>
                          {detail.architecture_proposal.security_considerations.map((item, i) => (
                            <li key={i}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="enhance-arch-compatibility">
                      <span className={detail.architecture_proposal.backward_compatible ? 'compatible' : 'breaking'}>
                        {detail.architecture_proposal.backward_compatible ? 'Backward Compatible' : 'Breaking Changes'}
                      </span>
                      {detail.architecture_proposal.migration_required && (
                        <span className="migration">Migration Required</span>
                      )}
                    </div>
                  </div>
                )}

                {/* Implementation Tab */}
                {activeTab === 'implementation' && detail.implementation_plan && (
                  <div className="enhance-tab-implementation">
                    <div className="enhance-impl-section">
                      <h4>
                        <ListChecks size={16} />
                        Implementation Phases
                      </h4>
                      <div className="enhance-phase-list">
                        {detail.implementation_plan.phases.map((phase) => (
                          <div key={phase.phase_number} className="enhance-phase-card">
                            <div className="enhance-phase-header">
                              <span className="enhance-phase-number">{phase.phase_number}</span>
                              <h5>{phase.title}</h5>
                              {phase.estimated_effort && (
                                <span className="enhance-phase-effort">{phase.estimated_effort}</span>
                              )}
                            </div>
                            <p>{phase.description}</p>
                            {phase.tasks.length > 0 && (
                              <ul>
                                {phase.tasks.map((task, i) => (
                                  <li key={i}>{task}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="enhance-impl-section">
                      <h4>
                        <TestTube size={16} />
                        Test Strategy
                      </h4>
                      <div className="enhance-test-strategy">
                        {detail.implementation_plan.test_strategy.unit_tests.length > 0 && (
                          <div className="enhance-test-category">
                            <h5>Unit Tests</h5>
                            <ul>
                              {detail.implementation_plan.test_strategy.unit_tests.map((t, i) => (
                                <li key={i}>{t}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {detail.implementation_plan.test_strategy.integration_tests.length > 0 && (
                          <div className="enhance-test-category">
                            <h5>Integration Tests</h5>
                            <ul>
                              {detail.implementation_plan.test_strategy.integration_tests.map((t, i) => (
                                <li key={i}>{t}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>

                    {detail.implementation_plan.rollback_plan && (
                      <div className="enhance-impl-section">
                        <h4>
                          <Undo2 size={16} />
                          Rollback Plan
                        </h4>
                        <p>{detail.implementation_plan.rollback_plan}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Timeline Tab */}
                {activeTab === 'timeline' && (
                  <div className="enhance-tab-timeline">
                    {detail.timeline.length === 0 ? (
                      <p className="enhance-timeline-empty">No timeline events yet.</p>
                    ) : (
                      <div className="enhance-timeline-list">
                        {detail.timeline.map((event) => (
                          <div key={event.id} className="enhance-timeline-item">
                            <div className="enhance-timeline-dot" />
                            <div className="enhance-timeline-content">
                              <div className="enhance-timeline-header">
                                <span className="enhance-timeline-actor">
                                  {event.actor_type === 'agent' ? <Bot size={12} /> : <User size={12} />}
                                  {event.actor_name}
                                </span>
                                <span className="enhance-timeline-date">{formatDate(event.timestamp)}</span>
                              </div>
                              <p>{event.description}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Reject Modal */}
        {showRejectModal && (
          <div className="enhance-reject-modal-overlay" onClick={() => setShowRejectModal(false)}>
            <div className="enhance-reject-modal" onClick={(e) => e.stopPropagation()}>
              <h3>Reject Enhancement</h3>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Enter rejection reason..."
                rows={4}
              />
              <div className="enhance-reject-modal-actions">
                <button
                  className="enhance-btn-secondary"
                  onClick={() => setShowRejectModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="enhance-btn-reject"
                  onClick={handleReject}
                  disabled={!rejectReason.trim() || isRejecting}
                >
                  {isRejecting ? <Loader2 size={16} className="spinning" /> : null}
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
