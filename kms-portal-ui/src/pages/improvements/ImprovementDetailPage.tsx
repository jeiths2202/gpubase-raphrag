/**
 * Improvement Detail Page
 *
 * Displays full details of an enhancement request with AI analysis
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  Clock,
  User,
  FileText,
  MessageSquare,
  Send,
  Loader2,
  AlertCircle,
  GitBranch,
  Code,
  FileCode,
  Shield,
  Database,
  ListChecks,
  TestTube,
  Undo2,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuthStore } from '../../store/authStore';
import {
  getEnhancement,
  addComment,
  EnhancementDetail,
  EnhancementStatus,
  EnhancementType,
  EnhancementPriority,
} from '../../api/improvements.api';
import './ImprovementDetailPage.css';

// Status colors
const STATUS_COLORS: Record<EnhancementStatus, string> = {
  submitted: 'status-submitted',
  analyzing: 'status-analyzing',
  analyzed: 'status-analyzed',
  architecture_review: 'status-review',
  approved: 'status-approved',
  rejected: 'status-rejected',
  implementing: 'status-implementing',
  code_review: 'status-review',
  testing: 'status-testing',
  verified: 'status-verified',
  released: 'status-released',
  closed: 'status-closed',
};

// Priority colors
const PRIORITY_COLORS: Record<EnhancementPriority, string> = {
  critical: 'priority-critical',
  high: 'priority-high',
  medium: 'priority-medium',
  low: 'priority-low',
};

// Type icons
const TYPE_ICONS: Record<EnhancementType, string> = {
  feature: '✨',
  bug_fix: '🐛',
  improvement: '📈',
  refactor: '🔧',
  documentation: '📝',
  security: '🔒',
  performance: '⚡',
};

type TabType = 'description' | 'analysis' | 'architecture' | 'implementation' | 'timeline' | 'comments';

export const ImprovementDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();

  // State
  const [enhancement, setEnhancement] = useState<EnhancementDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('description');
  const [commentText, setCommentText] = useState('');
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);

  // Load enhancement
  const loadEnhancement = async () => {
    if (!id) return;
    setIsLoading(true);
    setError(null);

    try {
      const data = await getEnhancement(id);
      setEnhancement(data);
    } catch (err) {
      setError(t('improvements.errors.notFound'));
      console.error('Failed to load enhancement:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadEnhancement();
  }, [id]);

  // Format date
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  // Handle comment
  const handleAddComment = async () => {
    if (!id || !commentText.trim()) return;
    setIsSubmittingComment(true);

    try {
      await addComment(id, commentText);
      setCommentText('');
      await loadEnhancement();
    } catch (err) {
      console.error('Failed to add comment:', err);
    } finally {
      setIsSubmittingComment(false);
    }
  };

  if (isLoading) {
    return (
      <div className="improvement-detail-page loading">
        <div className="spinner" />
        <p>{t('common.loading')}</p>
      </div>
    );
  }

  if (error || !enhancement) {
    return (
      <div className="improvement-detail-page error">
        <AlertCircle size={48} />
        <p>{error || t('improvements.errors.notFound')}</p>
        <button className="btn-secondary" onClick={() => navigate('/improvements')}>
          {t('common.back')}
        </button>
      </div>
    );
  }

  return (
    <div className="improvement-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/improvements')}>
          <ArrowLeft size={20} />
          {t('common.back')}
        </button>

        {/* Admin actions are only available in Admin Dashboard */}
      </div>

      {/* Title Section */}
      <div className="detail-title-section">
        <div className="title-row">
          {enhancement.type && (
            <span className="type-icon">{TYPE_ICONS[enhancement.type]}</span>
          )}
          <h1>{enhancement.title}</h1>
        </div>

        <div className="badges-row">
          <span className={`status-badge ${STATUS_COLORS[enhancement.status]}`}>
            {t(`improvements.status.${enhancement.status}`)}
          </span>
          {enhancement.priority && (
            <span className={`priority-badge ${PRIORITY_COLORS[enhancement.priority]}`}>
              {t(`improvements.priority.${enhancement.priority}`)}
            </span>
          )}
          {enhancement.ai_analyzed && (
            <span className="ai-badge">
              <Bot size={14} />
              AI Analyzed
            </span>
          )}
        </div>

        <div className="meta-row">
          <span>
            <User size={14} />
            {enhancement.author_name}
          </span>
          <span>
            <Clock size={14} />
            {formatDate(enhancement.created_at)}
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <button
          className={activeTab === 'description' ? 'active' : ''}
          onClick={() => setActiveTab('description')}
        >
          {t('improvements.form.description')}
        </button>
        <button
          className={activeTab === 'analysis' ? 'active' : ''}
          onClick={() => setActiveTab('analysis')}
          disabled={!enhancement.ai_analysis}
        >
          {t('improvements.analysis.title')}
          {enhancement.ai_analysis && <Bot size={14} />}
        </button>
        <button
          className={activeTab === 'architecture' ? 'active' : ''}
          onClick={() => setActiveTab('architecture')}
          disabled={!enhancement.architecture_proposal}
        >
          {t('improvements.architecture.title')}
        </button>
        <button
          className={activeTab === 'implementation' ? 'active' : ''}
          onClick={() => setActiveTab('implementation')}
          disabled={!enhancement.implementation_plan}
        >
          {t('improvements.implementation.title')}
          {enhancement.implementation_plan && <ListChecks size={14} />}
        </button>
        <button
          className={activeTab === 'timeline' ? 'active' : ''}
          onClick={() => setActiveTab('timeline')}
        >
          {t('improvements.timeline.title')}
        </button>
        <button
          className={activeTab === 'comments' ? 'active' : ''}
          onClick={() => setActiveTab('comments')}
        >
          {t('improvements.comments.title')} ({enhancement.comments.length})
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Description Tab */}
        {activeTab === 'description' && (
          <div className="description-tab">
            <div className="description-content">
              <pre>{enhancement.description}</pre>
            </div>

            {enhancement.attachments.length > 0 && (
              <div className="attachments-section">
                <h3>{t('improvements.form.attachments')}</h3>
                <div className="attachment-list">
                  {enhancement.attachments.map((att) => (
                    <div key={att.id} className="attachment-item">
                      <FileText size={18} />
                      <span className="att-name">{att.original_name}</span>
                      <span className="att-size">
                        {(att.file_size / 1024).toFixed(1)} KB
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Analysis Tab */}
        {activeTab === 'analysis' && enhancement.ai_analysis && (
          <div className="analysis-tab">
            <div className="analysis-section">
              <h3>{t('improvements.analysis.summary')}</h3>
              <p>{enhancement.ai_analysis.summary}</p>
            </div>

            <div className="analysis-grid">
              <div className="analysis-card">
                <label>{t('improvements.analysis.feasibility')}</label>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${enhancement.ai_analysis.feasibility_score * 100}%` }}
                  />
                </div>
                <span>{Math.round(enhancement.ai_analysis.feasibility_score * 100)}%</span>
              </div>

              <div className="analysis-card">
                <label>{t('improvements.analysis.complexity')}</label>
                <span className="complexity-badge">
                  {enhancement.ai_analysis.estimated_complexity}
                </span>
              </div>
            </div>

            {enhancement.ai_analysis.affected_components.length > 0 && (
              <div className="analysis-section">
                <h3>{t('improvements.analysis.components')}</h3>
                <ul className="component-list">
                  {enhancement.ai_analysis.affected_components.map((comp, i) => (
                    <li key={i}>{comp}</li>
                  ))}
                </ul>
              </div>
            )}

            {enhancement.ai_analysis.potential_risks.length > 0 && (
              <div className="analysis-section">
                <h3>{t('improvements.analysis.risks')}</h3>
                <ul className="risk-list">
                  {enhancement.ai_analysis.potential_risks.map((risk, i) => (
                    <li key={i}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="analysis-section">
              <h3>{t('improvements.analysis.approach')}</h3>
              <p>{enhancement.ai_analysis.recommended_approach}</p>
            </div>
          </div>
        )}

        {/* Architecture Tab */}
        {activeTab === 'architecture' && enhancement.architecture_proposal && (
          <div className="architecture-tab">
            <div className="architecture-section">
              <h3>{t('improvements.architecture.approach')}</h3>
              <p>{enhancement.architecture_proposal.approach}</p>
            </div>

            {/* Design Decisions */}
            {enhancement.architecture_proposal.design_decisions.length > 0 && (
              <div className="architecture-section">
                <h3>{t('improvements.architecture.designDecisions')}</h3>
                <div className="decision-list">
                  {enhancement.architecture_proposal.design_decisions.map((decision, i) => (
                    <div key={i} className="decision-card">
                      <div className="decision-header">
                        <GitBranch size={16} />
                        <h4>{decision.title}</h4>
                      </div>
                      <p className="decision-description">{decision.description}</p>
                      <div className="decision-rationale">
                        <strong>{t('improvements.architecture.rationale')}:</strong> {decision.rationale}
                      </div>
                      {decision.alternatives_considered.length > 0 && (
                        <div className="decision-alternatives">
                          <strong>{t('improvements.architecture.alternatives')}:</strong>
                          <ul>
                            {decision.alternatives_considered.map((alt, j) => (
                              <li key={j}>{alt}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {decision.trade_offs && (
                        <div className="decision-tradeoffs">
                          <strong>{t('improvements.architecture.tradeoffs')}:</strong> {decision.trade_offs}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* File Changes */}
            {enhancement.architecture_proposal.file_changes.length > 0 && (
              <div className="architecture-section">
                <h3>
                  <FileCode size={18} />
                  {t('improvements.architecture.fileChanges')}
                </h3>
                <div className="file-change-list">
                  {enhancement.architecture_proposal.file_changes.map((file, i) => (
                    <div key={i} className="file-change-item">
                      <div className="file-path">
                        <Code size={14} />
                        <code>{file.file_path}</code>
                        <span className={`change-type ${file.change_type}`}>{file.change_type}</span>
                      </div>
                      <p>{file.description}</p>
                      {file.estimated_lines > 0 && (
                        <span className="estimated-lines">~{file.estimated_lines} lines</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* New Files */}
            {enhancement.architecture_proposal.new_files.length > 0 && (
              <div className="architecture-section">
                <h3>
                  <FileText size={18} />
                  {t('improvements.architecture.newFiles')}
                </h3>
                <div className="new-file-list">
                  {enhancement.architecture_proposal.new_files.map((file, i) => (
                    <div key={i} className="new-file-item">
                      <div className="file-path">
                        <FileText size={14} />
                        <code>{file.file_path}</code>
                        <span className="change-type add">new</span>
                      </div>
                      <p>{file.purpose}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* API Changes */}
            {enhancement.architecture_proposal.api_changes.length > 0 && (
              <div className="architecture-section">
                <h3>{t('improvements.architecture.apiChanges')}</h3>
                <div className="api-change-list">
                  {enhancement.architecture_proposal.api_changes.map((api, i) => (
                    <div key={i} className="api-change-item">
                      <div className="api-header">
                        <span className={`method ${api.method.toLowerCase()}`}>{api.method}</span>
                        <code>{api.endpoint}</code>
                        <span className={`change-type ${api.change_type}`}>{api.change_type}</span>
                      </div>
                      <p>{api.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Database Changes */}
            {enhancement.architecture_proposal.database_changes.length > 0 && (
              <div className="architecture-section">
                <h3>
                  <Database size={18} />
                  {t('improvements.architecture.databaseChanges')}
                </h3>
                <ul className="database-change-list">
                  {enhancement.architecture_proposal.database_changes.map((change, i) => (
                    <li key={i}>{change}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Security Considerations */}
            {enhancement.architecture_proposal.security_considerations.length > 0 && (
              <div className="architecture-section">
                <h3>
                  <Shield size={18} />
                  {t('improvements.architecture.security')}
                </h3>
                <ul className="security-list">
                  {enhancement.architecture_proposal.security_considerations.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Compatibility Info */}
            <div className="architecture-section compatibility-section">
              <div className="compatibility-badge-group">
                <span className={`compatibility-badge ${enhancement.architecture_proposal.backward_compatible ? 'compatible' : 'breaking'}`}>
                  {enhancement.architecture_proposal.backward_compatible
                    ? t('improvements.architecture.backwardCompatible')
                    : t('improvements.architecture.breakingChanges')}
                </span>
                {enhancement.architecture_proposal.migration_required && (
                  <span className="migration-badge">
                    {t('improvements.architecture.migrationRequired')}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Architecture Tab - No Proposal */}
        {activeTab === 'architecture' && !enhancement.architecture_proposal && (
          <div className="architecture-tab empty">
            <GitBranch size={48} />
            <p>{t('improvements.architecture.noProposal')}</p>
            <p className="admin-note">{t('improvements.architecture.adminOnly')}</p>
          </div>
        )}

        {/* Implementation Tab */}
        {activeTab === 'implementation' && enhancement.implementation_plan && (
          <div className="implementation-tab">
            {/* Phases */}
            <div className="implementation-section">
              <h3>
                <ListChecks size={18} />
                {t('improvements.implementation.phases')}
              </h3>
              <div className="phase-list">
                {enhancement.implementation_plan.phases.map((phase) => (
                  <div key={phase.phase_number} className="phase-card">
                    <div className="phase-header">
                      <span className="phase-number">{phase.phase_number}</span>
                      <h4>{phase.title}</h4>
                      {phase.estimated_effort && (
                        <span className="phase-effort">{phase.estimated_effort}</span>
                      )}
                    </div>
                    <p className="phase-description">{phase.description}</p>
                    {phase.tasks.length > 0 && (
                      <div className="phase-tasks">
                        <strong>{t('improvements.implementation.tasks')}:</strong>
                        <ul>
                          {phase.tasks.map((task, i) => (
                            <li key={i}>{task}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {phase.dependencies.length > 0 && (
                      <div className="phase-dependencies">
                        <span>{t('improvements.implementation.dependsOn')}: Phase {phase.dependencies.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Test Strategy */}
            <div className="implementation-section">
              <h3>
                <TestTube size={18} />
                {t('improvements.implementation.testStrategy')}
              </h3>
              <div className="test-strategy">
                {enhancement.implementation_plan.test_strategy.unit_tests.length > 0 && (
                  <div className="test-category">
                    <h4>{t('improvements.implementation.unitTests')}</h4>
                    <ul>
                      {enhancement.implementation_plan.test_strategy.unit_tests.map((test, i) => (
                        <li key={i}>{test}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {enhancement.implementation_plan.test_strategy.integration_tests.length > 0 && (
                  <div className="test-category">
                    <h4>{t('improvements.implementation.integrationTests')}</h4>
                    <ul>
                      {enhancement.implementation_plan.test_strategy.integration_tests.map((test, i) => (
                        <li key={i}>{test}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {enhancement.implementation_plan.test_strategy.e2e_tests.length > 0 && (
                  <div className="test-category">
                    <h4>{t('improvements.implementation.e2eTests')}</h4>
                    <ul>
                      {enhancement.implementation_plan.test_strategy.e2e_tests.map((test, i) => (
                        <li key={i}>{test}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {enhancement.implementation_plan.test_strategy.manual_tests.length > 0 && (
                  <div className="test-category">
                    <h4>{t('improvements.implementation.manualTests')}</h4>
                    <ul>
                      {enhancement.implementation_plan.test_strategy.manual_tests.map((test, i) => (
                        <li key={i}>{test}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            {/* Rollback Plan */}
            {enhancement.implementation_plan.rollback_plan && (
              <div className="implementation-section">
                <h3>
                  <Undo2 size={18} />
                  {t('improvements.implementation.rollback')}
                </h3>
                <p className="rollback-plan">{enhancement.implementation_plan.rollback_plan}</p>
              </div>
            )}
          </div>
        )}

        {/* Implementation Tab - No Plan */}
        {activeTab === 'implementation' && !enhancement.implementation_plan && (
          <div className="implementation-tab empty">
            <ListChecks size={48} />
            <p>{t('improvements.implementation.noPlan')}</p>
            <p className="admin-note">{t('improvements.implementation.adminOnly')}</p>
          </div>
        )}

        {/* Timeline Tab */}
        {activeTab === 'timeline' && (
          <div className="timeline-tab">
            {enhancement.timeline.map((event) => (
              <div key={event.id} className="timeline-item">
                <div className="timeline-dot" />
                <div className="timeline-content">
                  <div className="timeline-header">
                    <span className="timeline-actor">
                      {event.actor_type === 'agent' ? <Bot size={14} /> : <User size={14} />}
                      {event.actor_name}
                    </span>
                    <span className="timeline-date">{formatDate(event.timestamp)}</span>
                  </div>
                  <p>{event.description}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Comments Tab */}
        {activeTab === 'comments' && (
          <div className="comments-tab">
            <div className="comment-input">
              <textarea
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                placeholder={t('improvements.comments.placeholder')}
                rows={3}
              />
              <button
                className="btn-primary"
                onClick={handleAddComment}
                disabled={isSubmittingComment || !commentText.trim()}
              >
                {isSubmittingComment ? (
                  <Loader2 size={18} className="spinning" />
                ) : (
                  <Send size={18} />
                )}
                {t('improvements.comments.submit')}
              </button>
            </div>

            {enhancement.comments.length === 0 ? (
              <div className="no-comments">
                <MessageSquare size={32} />
                <p>{t('improvements.comments.noComments')}</p>
              </div>
            ) : (
              <div className="comment-list">
                {enhancement.comments.map((comment) => (
                  <div key={comment.id} className="comment-item">
                    <div className="comment-header">
                      <span className="comment-author">
                        {comment.author_type === 'agent' ? <Bot size={14} /> : <User size={14} />}
                        {comment.author_name}
                      </span>
                      <span className="comment-date">{formatDate(comment.created_at)}</span>
                    </div>
                    <p>{comment.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

    </div>
  );
};

export default ImprovementDetailPage;
