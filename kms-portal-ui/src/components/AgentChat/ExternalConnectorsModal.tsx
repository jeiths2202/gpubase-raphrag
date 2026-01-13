/**
 * External Connectors Modal Component
 *
 * Modal dialog for managing external service connections (Notion, Confluence, etc.)
 * All connectors use SSO (OAuth 2.0) for authentication.
 * Allows users to connect external services and select resources for chat context.
 */

import React, { useCallback, useState } from 'react';
import {
  X,
  Loader2,
  AlertCircle,
  Check,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  Link2,
  Link2Off,
  FileText,
  Database,
  Folder,
  ExternalLink,
  Clock,
  CheckCircle2,
  Circle,
  Construction,
  Calendar,
  LogIn,
  Shield,
  User,
  Key,
  Globe,
  Play,
  Zap,
  XCircle,
} from 'lucide-react';
import {
  useExternalConnectorsStore,
  CONNECTOR_CONFIGS,
  type ConnectorType,
  type ConnectedResource,
  type ExternalConnector,
  type SSOState,
  type DocumentProcessingStatus,
} from '../../store/externalConnectorsStore';

// =============================================================================
// Types
// =============================================================================

export interface ExternalConnectorsModalProps {
  isOpen: boolean;
  onClose: () => void;
  t: (key: string) => string;
}

// =============================================================================
// Connector Icons
// =============================================================================

const ConnectorIcon: React.FC<{ type: ConnectorType; size?: number }> = ({ type, size = 24 }) => {
  const iconStyle = { width: size, height: size };

  switch (type) {
    case 'notion':
      return (
        <svg style={iconStyle} viewBox="0 0 24 24" fill="currentColor">
          <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 2.01c-.466-.373-.98-.56-2.054-.466l-12.8.934c-.467.046-.56.28-.374.466l1.827 1.264zm.793 3.31v13.6c0 .746.373 1.026 1.213.98l14.522-.84c.84-.046.933-.56.933-1.166V6.58c0-.606-.233-.933-.746-.886l-15.176.84c-.56.046-.746.326-.746.886zm14.335.653c.093.42 0 .84-.42.886l-.7.14v10.033c-.606.326-1.166.513-1.632.513-.747 0-.934-.234-1.494-.933l-4.572-7.186v6.953l1.446.327s0 .84-1.166.84l-3.218.187c-.093-.187 0-.653.327-.746l.84-.233V8.638l-1.166-.093c-.093-.42.14-1.026.793-1.073l3.451-.234 4.759 7.28V8.078l-1.213-.14c-.093-.514.28-.887.746-.933l3.218-.187z" />
        </svg>
      );
    case 'confluence':
      return (
        <svg style={iconStyle} viewBox="0 0 24 24" fill="currentColor">
          <path d="M2.047 18.859c-.23.376-.455.8-.66 1.173a.541.541 0 0 0 .178.718l3.683 2.313a.568.568 0 0 0 .776-.162c.182-.303.404-.672.653-1.058 1.774-2.79 3.574-2.475 6.803-.998l3.349 1.535a.57.57 0 0 0 .752-.266l1.759-3.933a.543.543 0 0 0-.267-.71l-3.29-1.501c-5.582-2.56-10.384-2.428-13.736 2.889zM21.953 5.141c.23-.376.455-.8.66-1.173a.541.541 0 0 0-.178-.718l-3.683-2.313a.568.568 0 0 0-.776.162c-.182.303-.404.672-.653 1.058-1.774 2.79-3.574 2.475-6.803.998l-3.349-1.535a.57.57 0 0 0-.752.266L4.66 5.82a.543.543 0 0 0 .267.71l3.29 1.501c5.582 2.56 10.384 2.428 13.736-2.889z" />
        </svg>
      );
    case 'github':
      return (
        <svg style={iconStyle} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
        </svg>
      );
    case 'google_drive':
      return (
        <svg style={iconStyle} viewBox="0 0 24 24" fill="currentColor">
          <path d="M7.71 3.5L1.15 15l4.58 7.5H12l-4.29-7.5L14.29 3.5H7.71zm8.58 0l-6.58 12 4.29 7.5h6.58l-4.29-7.5L22.87 3.5H16.29zm-4.29 9L7.71 19h8.58l-4.29-6.5z" />
        </svg>
      );
    default:
      return <Link2 size={size} />;
  }
};

// =============================================================================
// Resource Icon
// =============================================================================

const ResourceIcon: React.FC<{ type: ConnectedResource['type']; size?: number }> = ({
  type,
  size = 16,
}) => {
  switch (type) {
    case 'page':
      return <FileText size={size} />;
    case 'database':
      return <Database size={size} />;
    case 'folder':
    case 'repository':
      return <Folder size={size} />;
    default:
      return <FileText size={size} />;
  }
};

// =============================================================================
// Development Status Badge
// =============================================================================

const StatusBadge: React.FC<{ status: string; t: (key: string) => string }> = ({ status, t }) => {
  const getStatusConfig = () => {
    switch (status) {
      case 'available':
        return {
          icon: <CheckCircle2 size={12} />,
          label: t('common.externalConnectors.status.available') || 'Available',
          className: 'status-available',
        };
      case 'in_development':
        return {
          icon: <Construction size={12} />,
          label: t('common.externalConnectors.status.inDevelopment') || 'In Development',
          className: 'status-in-development',
        };
      case 'planned':
        return {
          icon: <Calendar size={12} />,
          label: t('common.externalConnectors.status.planned') || 'Planned',
          className: 'status-planned',
        };
      default:
        return {
          icon: <Circle size={12} />,
          label: status,
          className: '',
        };
    }
  };

  const config = getStatusConfig();

  return (
    <span className={`connector-status-badge ${config.className}`}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};

// =============================================================================
// Document Status Badge
// =============================================================================

const DocumentStatusBadge: React.FC<{
  status?: DocumentProcessingStatus;
  chunkCount?: number;
  isProcessing?: boolean;
  t: (key: string) => string;
}> = ({ status, chunkCount, isProcessing, t }) => {
  const getStatusConfig = () => {
    if (isProcessing) {
      return {
        icon: <Loader2 size={12} className="spin" />,
        label: t('common.externalConnectors.docStatus.processing') || 'Processing...',
        className: 'doc-status-processing',
      };
    }

    switch (status) {
      case 'ready':
        return {
          icon: <CheckCircle2 size={12} />,
          label: `${chunkCount || 0} ${t('common.externalConnectors.docStatus.chunks') || 'chunks'}`,
          className: 'doc-status-ready',
        };
      case 'chunking':
      case 'embedding':
        return {
          icon: <Loader2 size={12} className="spin" />,
          label: t('common.externalConnectors.docStatus.processing') || 'Processing...',
          className: 'doc-status-processing',
        };
      case 'error':
        return {
          icon: <XCircle size={12} />,
          label: t('common.externalConnectors.docStatus.error') || 'Error',
          className: 'doc-status-error',
        };
      case 'discovered':
      default:
        return {
          icon: <Circle size={12} />,
          label: t('common.externalConnectors.docStatus.notProcessed') || 'Not processed',
          className: 'doc-status-discovered',
        };
    }
  };

  const config = getStatusConfig();

  return (
    <span className={`document-status-badge ${config.className}`}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};

// =============================================================================
// Connector List View
// =============================================================================

interface ConnectorListViewProps {
  connectors: ExternalConnector[];
  onSelectConnector: (type: ConnectorType) => void;
  activeResources: ConnectedResource[];
  t: (key: string) => string;
}

const ConnectorListView: React.FC<ConnectorListViewProps> = ({
  connectors,
  onSelectConnector,
  activeResources,
  t,
}) => {
  return (
    <div className="connector-list">
      {connectors.map((connector) => {
        const config = CONNECTOR_CONFIGS[connector.type];
        const activeCount = activeResources.filter((r) =>
          r.id.startsWith(`${connector.type}_`)
        ).length;

        return (
          <div
            key={connector.id}
            className={`connector-item ${connector.status === 'active' ? 'connected' : ''}`}
            onClick={() => onSelectConnector(connector.type)}
          >
            <div className="connector-item-icon">
              <ConnectorIcon type={connector.type} size={32} />
            </div>
            <div className="connector-item-info">
              <div className="connector-item-header">
                <span className="connector-item-name">{connector.name}</span>
                <StatusBadge status={connector.developmentStatus} t={t} />
              </div>
              <p className="connector-item-description">{config.description}</p>
              {connector.status === 'active' && (
                <div className="connector-item-stats">
                  <span className="connector-resource-count">
                    {connector.connectedResources.length}{' '}
                    {t('common.externalConnectors.resources') || 'resources'}
                  </span>
                  {activeCount > 0 && (
                    <span className="connector-active-count">
                      <CheckCircle2 size={12} />
                      {activeCount} {t('common.externalConnectors.selected') || 'selected'}
                    </span>
                  )}
                </div>
              )}
            </div>
            <div className="connector-item-status">
              {connector.status === 'active' ? (
                <span className="connector-connected-badge">
                  <Check size={14} />
                  {t('common.externalConnectors.connected') || 'Connected'}
                </span>
              ) : connector.status === 'connecting' ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <ChevronRight size={20} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// =============================================================================
// Connector Detail View
// =============================================================================

interface ConnectorDetailViewProps {
  connector: ExternalConnector;
  onBack: () => void;
  onInitiateSSO: () => void;
  onCancelSSO: () => void;
  onConnectWithToken: (apiToken: string, siteUrl?: string, email?: string) => void;
  onDisconnect: () => void;
  onSync: () => void;
  onToggleResource: (resource: ConnectedResource) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onProcessDocument: (resourceId: string) => void;
  onProcessSelected: () => void;
  activeResources: ConnectedResource[];
  isConnecting: boolean;
  ssoState: SSOState;
  ssoError: string | null;
  t: (key: string) => string;
}

const ConnectorDetailView: React.FC<ConnectorDetailViewProps> = ({
  connector,
  onBack,
  onInitiateSSO,
  onCancelSSO,
  onConnectWithToken,
  onDisconnect,
  onSync,
  onToggleResource,
  onSelectAll,
  onDeselectAll,
  onProcessDocument,
  onProcessSelected,
  activeResources,
  isConnecting,
  ssoState,
  ssoError,
  t,
}) => {
  const config = CONNECTOR_CONFIGS[connector.type];

  // State for API token input (Confluence)
  const [apiToken, setApiToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [confluenceSiteUrl, setConfluenceSiteUrl] = useState('');
  const [confluenceEmail, setConfluenceEmail] = useState('');

  // Count documents needing processing
  const unprocessedCount = connector.connectedResources.filter(
    (r) => r.status === 'discovered' || !r.status
  ).length;
  const selectedUnprocessedCount = activeResources.filter((r) => {
    const resource = connector.connectedResources.find((cr) => cr.id === r.id);
    return resource && (resource.status === 'discovered' || !resource.status);
  }).length;

  const isResourceActive = (resourceId: string) => {
    return activeResources.some((r) => r.id === resourceId);
  };

  // Count selected resources from this connector
  const selectedCount = activeResources.filter((r) =>
    connector.connectedResources.some((cr) => cr.id === r.id)
  ).length;
  const totalCount = connector.connectedResources.length;
  const allSelected = totalCount > 0 && selectedCount === totalCount;

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  // Get provider-specific button text and colors
  const getProviderButtonConfig = () => {
    switch (connector.type) {
      case 'notion':
        return {
          text: t('common.externalConnectors.sso.signInWithNotion') || 'Sign in with Notion',
          className: 'sso-btn-notion',
        };
      case 'confluence':
        return {
          text: t('common.externalConnectors.sso.signInWithAtlassian') || 'Sign in with Atlassian',
          className: 'sso-btn-atlassian',
        };
      case 'github':
        return {
          text: t('common.externalConnectors.sso.signInWithGitHub') || 'Sign in with GitHub',
          className: 'sso-btn-github',
        };
      case 'google_drive':
        return {
          text: t('common.externalConnectors.sso.signInWithGoogle') || 'Sign in with Google',
          className: 'sso-btn-google',
        };
      default:
        return {
          text: t('common.externalConnectors.sso.signIn') || 'Sign in',
          className: '',
        };
    }
  };

  const providerConfig = getProviderButtonConfig();

  return (
    <div className="connector-detail">
      {/* Header */}
      <div className="connector-detail-header">
        <button className="connector-back-btn" onClick={onBack}>
          <ChevronLeft size={20} />
        </button>
        <div className="connector-detail-title">
          <ConnectorIcon type={connector.type} size={28} />
          <h3>{connector.name}</h3>
          <StatusBadge status={connector.developmentStatus} t={t} />
        </div>
      </div>

      {/* Content */}
      <div className="connector-detail-content">
        {connector.status === 'active' || connector.status === 'connecting' ? (
          // Connected state - show SSO profile and resources (also shown during sync)
          <>
            {/* SSO Profile Section */}
            {connector.ssoProfile && (
              <div className="connector-sso-profile">
                <div className="connector-sso-profile-header">
                  <Shield size={16} />
                  <span>{t('common.externalConnectors.sso.connectedAs') || 'Connected as'}</span>
                </div>
                <div className="connector-sso-profile-info">
                  {connector.ssoProfile.avatar ? (
                    <img
                      src={connector.ssoProfile.avatar}
                      alt={connector.ssoProfile.name}
                      className="connector-sso-avatar"
                    />
                  ) : (
                    <div className="connector-sso-avatar-placeholder">
                      <User size={20} />
                    </div>
                  )}
                  <div className="connector-sso-profile-details">
                    <span className="connector-sso-name">{connector.ssoProfile.name}</span>
                    <span className="connector-sso-email">{connector.ssoProfile.email}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="connector-detail-actions">
              <button className="connector-sync-btn" onClick={onSync} disabled={isConnecting}>
                <RefreshCw size={16} className={isConnecting ? 'spin' : ''} />
                {t('common.externalConnectors.sync') || 'Sync'}
              </button>
              <button className="connector-disconnect-btn" onClick={onDisconnect}>
                <Link2Off size={16} />
                {t('common.externalConnectors.disconnect') || 'Disconnect'}
              </button>
            </div>

            {connector.lastConnected && (
              <div className="connector-last-sync">
                <Clock size={14} />
                <span>
                  {t('common.externalConnectors.lastSync') || 'Last synced'}:{' '}
                  {formatDate(connector.lastConnected)}
                </span>
              </div>
            )}

            <div className="connector-resources">
              <h4>
                {t('common.externalConnectors.selectResources') || 'Select resources for chat context'}
              </h4>
              <p className="connector-resources-hint">
                {t('common.externalConnectors.selectHint') ||
                  'Selected resources will be available as context in your conversations'}
              </p>
              <div className="connector-resources-list">
                {connector.status === 'connecting' ? (
                  // Syncing state - show spinner
                  <div className="connector-resources-loading">
                    <Loader2 size={32} className="spin" />
                    <span className="connector-resources-loading-text">
                      {t('common.externalConnectors.syncing') || 'Syncing resources...'}
                    </span>
                    <span className="connector-resources-loading-hint">
                      {t('common.externalConnectors.syncingHint') || 'This may take a minute'}
                    </span>
                  </div>
                ) : connector.connectedResources.length === 0 ? (
                  // No resources
                  <div className="connector-resources-empty">
                    <FileText size={32} />
                    <span>{t('common.externalConnectors.noResources') || 'No resources found'}</span>
                  </div>
                ) : (
                  // Resources list
                  <>
                    {/* Selection header */}
                    <div className="connector-selection-header">
                      <span className="connector-selection-count">
                        {selectedCount > 0 ? (
                          <>
                            <CheckCircle2 size={14} />
                            {selectedCount} / {totalCount} {t('common.externalConnectors.selected') || 'selected'}
                          </>
                        ) : (
                          <>
                            <Circle size={14} />
                            {totalCount} {t('common.externalConnectors.resources') || 'resources'}
                          </>
                        )}
                      </span>
                      <div className="connector-selection-actions">
                        {!allSelected && (
                          <button
                            className="connector-select-all-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectAll();
                            }}
                          >
                            {t('common.externalConnectors.selectAll') || 'Select All'}
                          </button>
                        )}
                        {selectedCount > 0 && (
                          <button
                            className="connector-deselect-all-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeselectAll();
                            }}
                          >
                            {t('common.externalConnectors.deselectAll') || 'Deselect All'}
                          </button>
                        )}
                      </div>
                    </div>
                    {/* Process actions bar */}
                    {unprocessedCount > 0 && (
                      <div className="connector-process-actions">
                        <span className="connector-process-info">
                          <Zap size={14} />
                          {unprocessedCount} {t('common.externalConnectors.needsProcessing') || 'documents need processing'}
                        </span>
                        {selectedUnprocessedCount > 0 && (
                          <button
                            className="connector-process-selected-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              onProcessSelected();
                            }}
                          >
                            <Play size={14} />
                            {t('common.externalConnectors.processSelected') || 'Process selected'} ({selectedUnprocessedCount})
                          </button>
                        )}
                      </div>
                    )}
                    {connector.connectedResources.map((resource) => (
                      <div
                        key={resource.id}
                        className={`connector-resource-item ${isResourceActive(resource.id) ? 'active' : ''} ${resource.status === 'ready' ? 'ready' : ''}`}
                        onClick={() => onToggleResource(resource)}
                      >
                        <div className="connector-resource-checkbox">
                          {isResourceActive(resource.id) ? (
                            <CheckCircle2 size={18} />
                          ) : (
                            <Circle size={18} />
                          )}
                        </div>
                        <ResourceIcon type={resource.type} />
                        <div className="connector-resource-info">
                          <span className="connector-resource-title">{resource.title}</span>
                          <div className="connector-resource-meta">
                            <span className="connector-resource-type">{resource.type}</span>
                            <DocumentStatusBadge
                              status={resource.status}
                              chunkCount={resource.chunkCount}
                              isProcessing={resource.isProcessing}
                              t={t}
                            />
                          </div>
                        </div>
                        <div className="connector-resource-actions">
                          {/* Debug: Always show button for non-ready status */}
                          {resource.status !== 'ready' && !resource.isProcessing && (
                            <button
                              className="connector-process-btn"
                              style={{ pointerEvents: 'auto', gap: '4px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                                console.log('[ExternalConnectors] Process button clicked for:', resource.id, resource.title, 'status:', resource.status);
                                onProcessDocument(resource.id);
                              }}
                              onMouseDown={(e) => {
                                e.stopPropagation();
                                console.log('[ExternalConnectors] Process button mousedown');
                              }}
                              title={t('common.externalConnectors.processDoc') || 'Process this document'}
                            >
                              <Play size={14} fill="currentColor" />
                              <span style={{ fontSize: '11px', fontWeight: 500 }}>Process</span>
                            </button>
                          )}
                          {resource.url && (
                            <a
                              href={resource.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="connector-resource-link"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          </>
        ) : connector.developmentStatus === 'planned' ? (
          // Planned connector
          <div className="connector-planned">
            <Calendar size={48} />
            <h4>{t('common.externalConnectors.comingSoon') || 'Coming Soon'}</h4>
            <p>
              {t('common.externalConnectors.plannedDescription') ||
                'This connector is planned for future development.'}
            </p>
          </div>
        ) : (
          // Not connected - show SSO login
          <div className="connector-sso-connect">
            <p className="connector-connect-description">{config.description}</p>

            {/* SSO Security Info */}
            <div className="connector-sso-info">
              <Shield size={18} />
              <div className="connector-sso-info-text">
                <span className="connector-sso-info-title">
                  {t('common.externalConnectors.sso.secureAuth') || 'Secure Authentication'}
                </span>
                <span className="connector-sso-info-desc">
                  {t('common.externalConnectors.sso.secureAuthDesc') ||
                    'We use OAuth 2.0 to securely connect to your account. We never store your password.'}
                </span>
              </div>
            </div>

            {/* SSO Error */}
            {(ssoError || connector.error) && (
              <div className="connector-error">
                <AlertCircle size={16} />
                <span>{ssoError || connector.error}</span>
              </div>
            )}

            {/* SSO States */}
            {ssoState === 'authorizing' ? (
              // Authorizing state
              <div className="connector-sso-authorizing">
                <Loader2 size={32} className="spin" />
                <h4>{t('common.externalConnectors.sso.authorizing') || 'Authorizing...'}</h4>
                <p>
                  {t('common.externalConnectors.sso.authorizingDesc') ||
                    'Please complete the login in the popup window.'}
                </p>
                <button className="connector-sso-cancel-btn" onClick={onCancelSSO}>
                  {t('common.externalConnectors.sso.cancel') || 'Cancel'}
                </button>
              </div>
            ) : config.authType === 'api_token' ? (
              // API Token authentication (for Confluence)
              <div className="connector-api-token-form">
                {/* Site URL */}
                <div className="connector-api-token-field">
                  <label htmlFor="site-url">
                    {t('common.externalConnectors.fields.siteUrl') || 'Site URL'}
                  </label>
                  <div className="connector-api-token-input-wrapper">
                    <Globe size={16} />
                    <input
                      id="site-url"
                      type="text"
                      value={confluenceSiteUrl}
                      onChange={(e) => setConfluenceSiteUrl(e.target.value)}
                      placeholder={t('common.externalConnectors.fields.siteUrlPlaceholder') || 'e.g., your-domain.atlassian.net'}
                      disabled={isConnecting}
                    />
                  </div>
                </div>

                {/* Email */}
                <div className="connector-api-token-field">
                  <label htmlFor="email">
                    {t('common.externalConnectors.fields.email') || 'Email'}
                  </label>
                  <div className="connector-api-token-input-wrapper">
                    <User size={16} />
                    <input
                      id="email"
                      type="email"
                      value={confluenceEmail}
                      onChange={(e) => setConfluenceEmail(e.target.value)}
                      placeholder={t('common.externalConnectors.fields.emailPlaceholder') || 'Enter your Atlassian email'}
                      disabled={isConnecting}
                    />
                  </div>
                </div>

                {/* API Token */}
                <div className="connector-api-token-field">
                  <label htmlFor="api-token">
                    {t('common.externalConnectors.apiToken.label') || 'API Token'}
                  </label>
                  <div className="connector-api-token-input-wrapper">
                    <Key size={16} />
                    <input
                      id="api-token"
                      type={showToken ? 'text' : 'password'}
                      value={apiToken}
                      onChange={(e) => setApiToken(e.target.value)}
                      placeholder={t('common.externalConnectors.apiToken.placeholder') || 'Enter your API token'}
                      disabled={isConnecting}
                    />
                    <button
                      type="button"
                      className="connector-api-token-toggle"
                      onClick={() => setShowToken(!showToken)}
                    >
                      {showToken ? 'Hide' : 'Show'}
                    </button>
                  </div>
                  <p className="connector-api-token-hint">
                    {t('common.externalConnectors.fields.confluenceHint') ||
                      'Get your API token from id.atlassian.com/manage-profile/security/api-tokens'}
                  </p>
                </div>

                <button
                  className="connector-api-token-submit"
                  onClick={() => onConnectWithToken(apiToken, confluenceSiteUrl, confluenceEmail)}
                  disabled={!apiToken.trim() || !confluenceSiteUrl.trim() || !confluenceEmail.trim() || isConnecting}
                >
                  {isConnecting ? (
                    <>
                      <Loader2 size={18} className="spin" />
                      <span>{t('common.externalConnectors.connecting') || 'Connecting...'}</span>
                    </>
                  ) : (
                    <>
                      <Link2 size={18} />
                      <span>{t('common.externalConnectors.connect') || 'Connect'}</span>
                    </>
                  )}
                </button>
              </div>
            ) : (
              // Ready to connect with SSO
              <div className="connector-sso-buttons">
                <button
                  className={`connector-sso-btn ${providerConfig.className}`}
                  onClick={onInitiateSSO}
                  disabled={isConnecting}
                >
                  <ConnectorIcon type={connector.type} size={20} />
                  <span>{providerConfig.text}</span>
                  <LogIn size={18} />
                </button>

                {/* Scopes Info */}
                <div className="connector-sso-scopes">
                  <span className="connector-sso-scopes-label">
                    {t('common.externalConnectors.sso.permissions') || 'Requested permissions'}:
                  </span>
                  <ul className="connector-sso-scopes-list">
                    {config.scopes.map((scope, index) => (
                      <li key={index}>
                        <Check size={12} />
                        <span>{scope}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// =============================================================================
// Main Component
// =============================================================================

export const ExternalConnectorsModal: React.FC<ExternalConnectorsModalProps> = ({
  isOpen,
  onClose,
  t,
}) => {
  const {
    connectors,
    selectedConnectorType,
    isConnecting,
    ssoState,
    ssoError,
    activeResources,
    selectConnectorType,
    initiateSSO,
    cancelSSO,
    connectService,
    disconnectService,
    syncResources,
    toggleResourceActive,
    processDocument,
    processSelectedDocuments,
  } = useExternalConnectorsStore();

  const selectedConnector = selectedConnectorType
    ? connectors.find((c) => c.type === selectedConnectorType)
    : null;

  const handleClose = useCallback(() => {
    cancelSSO();
    selectConnectorType(null);
    onClose();
  }, [cancelSSO, selectConnectorType, onClose]);

  const handleInitiateSSO = useCallback(() => {
    if (selectedConnectorType) {
      initiateSSO(selectedConnectorType);
    }
  }, [selectedConnectorType, initiateSSO]);

  const handleDisconnect = useCallback(() => {
    if (selectedConnectorType) {
      disconnectService(selectedConnectorType);
    }
  }, [selectedConnectorType, disconnectService]);

  const handleSync = useCallback(() => {
    if (selectedConnectorType) {
      syncResources(selectedConnectorType);
    }
  }, [selectedConnectorType, syncResources]);

  const handleConnectWithToken = useCallback((apiToken: string, siteUrl?: string, email?: string) => {
    if (selectedConnectorType && apiToken.trim()) {
      // For Confluence, include site URL and email in config
      if (selectedConnectorType === 'confluence' && siteUrl && email) {
        // Format Confluence URL: ensure https:// prefix and /wiki suffix
        let formattedUrl = siteUrl.trim();
        if (!formattedUrl.startsWith('http')) {
          formattedUrl = `https://${formattedUrl}`;
        }
        // Remove trailing slash if present
        if (formattedUrl.endsWith('/')) {
          formattedUrl = formattedUrl.slice(0, -1);
        }
        // Append /wiki if not present (Confluence Cloud API requires this)
        if (!formattedUrl.endsWith('/wiki')) {
          formattedUrl = `${formattedUrl}/wiki`;
        }

        connectService(selectedConnectorType, {
          apiKey: apiToken,
        }, {
          base_url: formattedUrl,
          user_email: email,
        });
      } else {
        connectService(selectedConnectorType, { apiKey: apiToken });
      }
    }
  }, [selectedConnectorType, connectService]);

  const handleProcessDocument = useCallback((resourceId: string) => {
    console.log('[ExternalConnectors] handleProcessDocument called:', { resourceId, selectedConnectorType });
    if (selectedConnectorType) {
      processDocument(selectedConnectorType, resourceId);
    } else {
      console.error('[ExternalConnectors] No selectedConnectorType!');
    }
  }, [selectedConnectorType, processDocument]);

  const handleProcessSelected = useCallback(() => {
    if (selectedConnectorType && selectedConnector) {
      const unprocessedIds = activeResources
        .filter((r) => {
          const resource = selectedConnector.connectedResources.find((cr) => cr.id === r.id);
          return resource && (resource.status === 'discovered' || !resource.status);
        })
        .map((r) => r.id);
      if (unprocessedIds.length > 0) {
        processSelectedDocuments(selectedConnectorType, unprocessedIds);
      }
    }
  }, [selectedConnectorType, selectedConnector, activeResources, processSelectedDocuments]);

  const handleSelectAll = useCallback(() => {
    if (selectedConnector) {
      // Add all resources from this connector that are not already selected
      selectedConnector.connectedResources.forEach((resource) => {
        if (!activeResources.some((r) => r.id === resource.id)) {
          toggleResourceActive(resource);
        }
      });
    }
  }, [selectedConnector, activeResources, toggleResourceActive]);

  const handleDeselectAll = useCallback(() => {
    if (selectedConnector) {
      // Remove all resources from this connector
      activeResources
        .filter((r) => selectedConnector.connectedResources.some((cr) => cr.id === r.id))
        .forEach((resource) => {
          toggleResourceActive(resource);
        });
    }
  }, [selectedConnector, activeResources, toggleResourceActive]);

  if (!isOpen) return null;

  return (
    <div className="external-connectors-modal-overlay" onClick={handleClose}>
      <div className="external-connectors-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="external-connectors-modal-header">
          <div className="external-connectors-modal-title">
            <Link2 size={20} />
            <h3>{t('common.externalConnectors.title') || 'External Connectors'}</h3>
          </div>
          <button className="external-connectors-modal-close" onClick={handleClose}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="external-connectors-modal-body">
          {selectedConnector ? (
            <ConnectorDetailView
              connector={selectedConnector}
              onBack={() => selectConnectorType(null)}
              onInitiateSSO={handleInitiateSSO}
              onCancelSSO={cancelSSO}
              onConnectWithToken={handleConnectWithToken}
              onDisconnect={handleDisconnect}
              onSync={handleSync}
              onToggleResource={toggleResourceActive}
              onSelectAll={handleSelectAll}
              onDeselectAll={handleDeselectAll}
              onProcessDocument={handleProcessDocument}
              onProcessSelected={handleProcessSelected}
              activeResources={activeResources}
              isConnecting={isConnecting}
              ssoState={ssoState}
              ssoError={ssoError}
              t={t}
            />
          ) : (
            <>
              <p className="external-connectors-description">
                {t('common.externalConnectors.description') ||
                  'Connect external services to use their content as context in your conversations.'}
              </p>
              <ConnectorListView
                connectors={connectors}
                onSelectConnector={selectConnectorType}
                activeResources={activeResources}
                t={t}
              />
            </>
          )}
        </div>

        {/* Footer with active resources count and Done button */}
        {activeResources.length > 0 && (
          <div className="external-connectors-modal-footer">
            <div className="active-resources-summary">
              <CheckCircle2 size={16} />
              <span>
                {activeResources.length}{' '}
                {t('common.externalConnectors.resourcesSelected') || 'resources selected for context'}
              </span>
            </div>
            <button
              className="external-connectors-done-btn"
              onClick={handleClose}
            >
              {t('common.confirm') || 'Done'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExternalConnectorsModal;
