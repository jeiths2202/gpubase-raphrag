/**
 * External Connectors Store
 *
 * Manages external service connectors state for the AI Agent chat.
 * Supports: Notion, Confluence (in development), GitHub, Google Drive (planned)
 * All connectors use SSO (OAuth 2.0) for authentication.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import {
  externalConnectorsApi,
  type ExternalDocument,
  type ExternalResourceType,
  type ConnectionStatus,
} from '../api/externalConnectors.api';
import type { AgentType } from '../api/agent.api';

// =============================================================================
// Types
// =============================================================================

/**
 * Connector types supported by the system
 */
export type ConnectorType = 'notion' | 'confluence' | 'github' | 'google_drive' | 'onenote';

/**
 * Implementation status of connectors
 */
export type ConnectorStatus = 'active' | 'inactive' | 'connecting' | 'error';

/**
 * Development status of connector feature
 */
export type DevelopmentStatus = 'available' | 'in_development' | 'planned';

/**
 * SSO Authentication state
 */
export type SSOState = 'idle' | 'authorizing' | 'success' | 'error';

/**
 * Document processing status
 */
export type DocumentProcessingStatus = 'discovered' | 'chunking' | 'embedding' | 'ready' | 'error';

/**
 * Connected page/document from external service
 */
export interface ConnectedResource {
  id: string;
  title: string;
  url: string;
  type: 'page' | 'database' | 'document' | 'repository' | 'folder';
  lastSynced?: string;
  content?: string;
  metadata?: Record<string, unknown>;
  status?: DocumentProcessingStatus;
  chunkCount?: number;
  errorMessage?: string;
  isProcessing?: boolean;
}

/**
 * SSO User profile from OAuth provider
 */
export interface SSOProfile {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  provider: ConnectorType;
}

/**
 * External connector configuration
 */
export interface ExternalConnector {
  id: string;
  type: ConnectorType;
  name: string;
  status: ConnectorStatus;
  developmentStatus: DevelopmentStatus;
  ssoProfile?: SSOProfile;
  credentials?: {
    apiKey?: string;
    accessToken?: string;
    refreshToken?: string;
    workspaceId?: string;
    email?: string;
    expiresAt?: string;
  };
  connectedResources: ConnectedResource[];
  lastConnected?: string;
  error?: string;
  // Backend connection info
  connectionId?: string;
  documentCount?: number;
  chunkCount?: number;
}

/**
 * Connector configuration metadata
 */
export interface ConnectorConfig {
  type: ConnectorType;
  name: string;
  icon: string;
  description: string;
  developmentStatus: DevelopmentStatus;
  authType: 'sso' | 'api_token';
  oauthUrl: string;
  scopes: string[];
}

/**
 * Active resources stored per agent type
 */
type ActiveResourcesByAgent = Partial<Record<AgentType, ConnectedResource[]>>;

/**
 * Store state
 */
interface ExternalConnectorsState {
  // Connectors list
  connectors: ExternalConnector[];

  // Currently selected connector for configuration
  selectedConnectorType: ConnectorType | null;

  // Modal states
  isModalOpen: boolean;
  isConnecting: boolean;
  isLoading: boolean;

  // SSO state
  ssoState: SSOState;
  ssoError: string | null;

  // OAuth flow state
  pendingOAuthConnectionId: string | null;

  // Active resources for chat context (per agent type)
  activeResourcesByAgent: ActiveResourcesByAgent;

  // Current agent type for resource scoping
  currentAgentType: AgentType;

  // Current user ID (needed for API calls)
  currentUserId: string | null;

  // Currently selected/viewed document (auto-included in context)
  selectedDocument: ConnectedResource | null;

  // Actions
  openModal: () => void;
  closeModal: () => void;
  selectConnectorType: (type: ConnectorType | null) => void;
  setCurrentUserId: (userId: string | null) => void;
  setCurrentAgentType: (agentType: AgentType) => void;
  setSelectedDocument: (doc: ConnectedResource | null) => void;

  // Backend API integration
  loadConnections: () => Promise<void>;
  initiateSSO: (type: ConnectorType) => void;
  handleSSOCallback: (type: ConnectorType, authCode: string, state: string) => Promise<void>;
  completeOAuthFlow: (connectionId: string, code: string, state: string) => Promise<void>;
  cancelSSO: () => void;

  // Connector management
  connectService: (type: ConnectorType, credentials: ExternalConnector['credentials'], config?: Record<string, unknown>) => Promise<void>;
  disconnectService: (type: ConnectorType) => void;
  testConnection: (type: ConnectorType) => Promise<boolean>;

  // Resource management
  addResource: (type: ConnectorType, resource: ConnectedResource) => void;
  removeResource: (type: ConnectorType, resourceId: string) => void;
  syncResources: (type: ConnectorType, specificConnectionId?: string) => Promise<void>;
  loadDocuments: (type: ConnectorType) => Promise<void>;
  loadDocumentsById: (connectionId: string, type: ConnectorType) => Promise<void>;
  processDocument: (type: ConnectorType, resourceId: string) => Promise<void>;
  processSelectedDocuments: (type: ConnectorType, resourceIds: string[]) => Promise<void>;

  // Active resources for chat
  toggleResourceActive: (resource: ConnectedResource) => void;
  toggleResourceActiveWithContent: (resource: ConnectedResource, type: ConnectorType) => Promise<void>;
  clearActiveResources: () => void;
  getActiveResourcesContext: () => string;

  // Getters
  getConnector: (type: ConnectorType) => ExternalConnector | undefined;
  getAvailableConnectors: () => ConnectorConfig[];
  getConnectedCount: () => number;
}

// =============================================================================
// Connector Configurations
// =============================================================================

export const CONNECTOR_CONFIGS: Record<ConnectorType, ConnectorConfig> = {
  notion: {
    type: 'notion',
    name: 'Notion',
    icon: 'notion',
    description: 'Connect to Notion workspaces and pages',
    developmentStatus: 'available',
    authType: 'sso',
    oauthUrl: 'https://api.notion.com/v1/oauth/authorize',
    scopes: ['read_content', 'read_user'],
  },
  confluence: {
    type: 'confluence',
    name: 'Confluence',
    icon: 'confluence',
    description: 'Connect to Atlassian Confluence spaces',
    developmentStatus: 'available',
    authType: 'sso',
    oauthUrl: 'https://auth.atlassian.com/authorize',
    scopes: ['read:confluence-content.all', 'read:confluence-space.summary', 'offline_access'],
  },
  github: {
    type: 'github',
    name: 'GitHub',
    icon: 'github',
    description: 'Connect to GitHub repositories',
    developmentStatus: 'available',
    authType: 'sso',
    oauthUrl: 'https://github.com/login/oauth/authorize',
    scopes: ['repo', 'read:user'],
  },
  google_drive: {
    type: 'google_drive',
    name: 'Google Drive',
    icon: 'google-drive',
    description: 'Connect to Google Drive files and folders',
    developmentStatus: 'available',
    authType: 'sso',
    oauthUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
    scopes: ['https://www.googleapis.com/auth/drive.readonly'],
  },
  onenote: {
    type: 'onenote',
    name: 'OneNote',
    icon: 'onenote',
    description: 'Connect to Microsoft OneNote notebooks',
    developmentStatus: 'available',
    authType: 'sso',
    oauthUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
    scopes: ['Notes.Read', 'Notes.Read.All', 'User.Read', 'offline_access'],
  },
};

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Map backend resource type to frontend connector type
 */
const mapResourceType = (resourceType: ExternalResourceType): ConnectorType | null => {
  const mapping: Record<string, ConnectorType> = {
    notion: 'notion',
    confluence: 'confluence',
    github: 'github',
    google_drive: 'google_drive',
    onenote: 'onenote',
  };
  return mapping[resourceType] || null;
};

/**
 * Map backend connection status to frontend status
 */
const mapConnectionStatus = (status: ConnectionStatus): ConnectorStatus => {
  switch (status) {
    case 'connected':
      return 'active';
    case 'connecting':
    case 'syncing':
      return 'connecting';
    case 'error':
    case 'expired':
      return 'error';
    default:
      return 'inactive';
  }
};

/**
 * Map backend document to frontend resource
 */
const mapDocumentToResource = (doc: ExternalDocument): ConnectedResource => ({
  id: doc.id,
  title: doc.title,
  url: doc.external_url || '',
  type: 'page',
  lastSynced: doc.last_synced_at || undefined,
  content: undefined,
  status: doc.status as DocumentProcessingStatus || 'discovered',
  chunkCount: doc.chunk_count || 0,
});

/**
 * Get OAuth redirect URI
 */
const getOAuthRedirectUri = (): string => {
  const baseUrl = window.location.origin;
  return `${baseUrl}/oauth/callback`;
};

// =============================================================================
// Initial State
// =============================================================================

const createInitialConnector = (type: ConnectorType): ExternalConnector => ({
  id: `connector_${type}`,
  type,
  name: CONNECTOR_CONFIGS[type].name,
  status: 'inactive',
  developmentStatus: CONNECTOR_CONFIGS[type].developmentStatus,
  connectedResources: [],
});

const initialConnectors: ExternalConnector[] = [
  createInitialConnector('notion'),
  createInitialConnector('confluence'),
  createInitialConnector('github'),
  createInitialConnector('google_drive'),
  createInitialConnector('onenote'),
];

// =============================================================================
// Store
// =============================================================================

export const useExternalConnectorsStore = create<ExternalConnectorsState>()(
  persist(
    (set, get) => ({
      // Initial state
      connectors: initialConnectors,
      selectedConnectorType: null,
      isModalOpen: false,
      isConnecting: false,
      isLoading: false,
      ssoState: 'idle',
      ssoError: null,
      pendingOAuthConnectionId: null,
      activeResourcesByAgent: {},
      currentAgentType: 'rag' as AgentType,
      currentUserId: null,
      selectedDocument: null,

      // Modal actions
      openModal: () => set({ isModalOpen: true }),
      closeModal: () =>
        set({
          isModalOpen: false,
          selectedConnectorType: null,
          ssoState: 'idle',
          ssoError: null,
        }),
      selectConnectorType: (type) =>
        set({ selectedConnectorType: type, ssoState: 'idle', ssoError: null }),
      setCurrentUserId: (userId) => set({ currentUserId: userId }),
      setCurrentAgentType: (agentType) => set({ currentAgentType: agentType }),
      setSelectedDocument: (doc) => set({ selectedDocument: doc }),

      // Load connections from backend
      loadConnections: async () => {
        const { currentUserId } = get();
        if (!currentUserId) {
          console.warn('Cannot load connections: no user ID');
          return;
        }

        set({ isLoading: true });

        try {
          const response = await externalConnectorsApi.listConnections(currentUserId);

          // Update connectors with backend data
          set((state) => ({
            isLoading: false,
            connectors: state.connectors.map((connector) => {
              const backendConn = response.connections.find(
                (c) => mapResourceType(c.resource_type) === connector.type
              );

              if (backendConn) {
                return {
                  ...connector,
                  status: mapConnectionStatus(backendConn.status),
                  connectionId: backendConn.id,
                  documentCount: backendConn.document_count,
                  chunkCount: backendConn.chunk_count,
                  lastConnected: backendConn.last_sync_at || backendConn.created_at,
                  error: backendConn.error_message || undefined,
                };
              }

              return connector;
            }),
          }));
        } catch (error) {
          console.error('Failed to load connections:', error);
          set({ isLoading: false });
        }
      },

      // SSO Authentication - Initiate OAuth flow
      initiateSSO: async (type: ConnectorType) => {
        const config = CONNECTOR_CONFIGS[type];
        const { currentUserId } = get();

        // Check if connector is available
        if (config.developmentStatus === 'planned') {
          set({ ssoError: 'This connector is not yet available' });
          return;
        }

        if (!currentUserId) {
          set({ ssoError: 'User not authenticated' });
          return;
        }

        set({ ssoState: 'authorizing', ssoError: null, isConnecting: true });

        try {
          // Create connection in backend
          const connection = await externalConnectorsApi.createConnection(currentUserId, {
            resource_type: type as ExternalResourceType,
          });

          // Get OAuth URL
          const redirectUri = getOAuthRedirectUri();
          const oauthResponse = await externalConnectorsApi.getOAuthUrl(connection.id, redirectUri);

          // Store pending connection ID for OAuth callback
          set({ pendingOAuthConnectionId: connection.id });

          // Open OAuth popup or redirect
          const width = 600;
          const height = 700;
          const left = window.screenX + (window.outerWidth - width) / 2;
          const top = window.screenY + (window.outerHeight - height) / 2;

          const popup = window.open(
            oauthResponse.oauth_url,
            'OAuth',
            `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no`
          );

          // Check if popup was blocked
          if (!popup) {
            // Fallback: redirect in same window
            window.location.href = oauthResponse.oauth_url;
          }
        } catch (error) {
          console.error('Failed to initiate SSO:', error);
          set({
            ssoState: 'error',
            ssoError: error instanceof Error ? error.message : 'Failed to initiate SSO',
            isConnecting: false,
          });
        }
      },

      // Handle SSO callback (from OAuth redirect)
      // SECURITY: state parameter is required for CSRF protection
      handleSSOCallback: async (_type, authCode, state) => {
        const { pendingOAuthConnectionId } = get();

        if (!pendingOAuthConnectionId) {
          set({
            ssoState: 'error',
            ssoError: 'No pending OAuth connection',
            isConnecting: false,
          });
          return;
        }

        try {
          await get().completeOAuthFlow(pendingOAuthConnectionId, authCode, state);
        } catch (error) {
          set({
            ssoState: 'error',
            ssoError: error instanceof Error ? error.message : 'SSO authentication failed',
            isConnecting: false,
          });
        }
      },

      // Complete OAuth flow with authorization code
      // SECURITY: state parameter is required to prevent CSRF attacks
      completeOAuthFlow: async (connectionId, code, state) => {
        try {
          const redirectUri = getOAuthRedirectUri();
          const connection = await externalConnectorsApi.completeOAuth(connectionId, code, redirectUri, state);

          const connectorType = mapResourceType(connection.resource_type);
          if (!connectorType) {
            throw new Error('Unknown resource type');
          }

          // Update connector state
          set((state) => ({
            ssoState: 'success',
            isConnecting: false,
            pendingOAuthConnectionId: null,
            connectors: state.connectors.map((c) =>
              c.type === connectorType
                ? {
                    ...c,
                    status: 'active',
                    connectionId: connection.id,
                    documentCount: connection.document_count,
                    chunkCount: connection.chunk_count,
                    lastConnected: new Date().toISOString(),
                    error: undefined,
                  }
                : c
            ),
          }));

          // Load documents after successful connection
          await get().loadDocuments(connectorType);
        } catch (error) {
          set({
            ssoState: 'error',
            ssoError: error instanceof Error ? error.message : 'OAuth completion failed',
            isConnecting: false,
          });
          throw error;
        }
      },

      // Cancel SSO flow
      cancelSSO: () => {
        set({
          ssoState: 'idle',
          ssoError: null,
          isConnecting: false,
          pendingOAuthConnectionId: null,
        });
      },

      // Connect to service (for API token auth like Confluence)
      connectService: async (type, credentials, config) => {
        const { currentUserId } = get();
        if (!currentUserId) {
          throw new Error('User not authenticated');
        }

        set({ isConnecting: true });

        try {
          const connection = await externalConnectorsApi.createConnection(currentUserId, {
            resource_type: type as ExternalResourceType,
            api_token: credentials?.apiKey || credentials?.accessToken,
            config: config,
          });

          // Capture the connectionId before state update to pass to syncResources
          const newConnectionId = connection.id;

          set((state) => ({
            isConnecting: false,
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'active',
                    connectionId: connection.id,
                    documentCount: connection.document_count,
                    chunkCount: connection.chunk_count,
                    lastConnected: new Date().toISOString(),
                    credentials,
                    error: undefined,
                  }
                : c
            ),
          }));

          // Trigger sync and load documents after successful connection
          // Pass the specific connectionId to avoid race condition if user clicks Connect again
          await get().syncResources(type, newConnectionId);
        } catch (error) {
          set((state) => ({
            isConnecting: false,
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'error',
                    error: error instanceof Error ? error.message : 'Connection failed',
                  }
                : c
            ),
          }));
          throw error;
        }
      },

      // Disconnect from service
      disconnectService: async (type) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector?.connectionId) {
          // If no backend connection, just reset local state
          // Remove resources from all agent types when disconnecting
          const filterResourcesFromAllAgents = (resourcesByAgent: ActiveResourcesByAgent): ActiveResourcesByAgent => {
            const result: ActiveResourcesByAgent = {};
            for (const [agentType, resources] of Object.entries(resourcesByAgent)) {
              result[agentType as AgentType] = resources.filter((r) => !r.id.startsWith(`${type}_`));
            }
            return result;
          };

          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'inactive',
                    ssoProfile: undefined,
                    credentials: undefined,
                    connectedResources: [],
                    lastConnected: undefined,
                    connectionId: undefined,
                  }
                : c
            ),
            activeResourcesByAgent: filterResourcesFromAllAgents(state.activeResourcesByAgent),
            ssoState: 'idle',
            ssoError: null,
          }));
          return;
        }

        try {
          await externalConnectorsApi.disconnect(connector.connectionId);
        } catch (error) {
          console.error('Failed to disconnect:', error);
        }

        // Update local state
        // Remove resources from all agent types when disconnecting
        const filterResourcesFromAllAgents = (resourcesByAgent: ActiveResourcesByAgent): ActiveResourcesByAgent => {
          const result: ActiveResourcesByAgent = {};
          for (const [agentType, resources] of Object.entries(resourcesByAgent)) {
            result[agentType as AgentType] = resources.filter((r) => !r.id.startsWith(`${type}_`));
          }
          return result;
        };

        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  status: 'inactive',
                  ssoProfile: undefined,
                  credentials: undefined,
                  connectedResources: [],
                  lastConnected: undefined,
                  connectionId: undefined,
                  documentCount: undefined,
                  chunkCount: undefined,
                }
              : c
          ),
          activeResourcesByAgent: filterResourcesFromAllAgents(state.activeResourcesByAgent),
          ssoState: 'idle',
          ssoError: null,
        }));
      },

      // Test connection
      testConnection: async (type) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector?.connectionId) {
          return false;
        }

        try {
          const connection = await externalConnectorsApi.getConnection(connector.connectionId);
          return connection.status === 'connected';
        } catch {
          return false;
        }
      },

      // Load documents for a connector
      loadDocuments: async (type) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector?.connectionId) {
          return;
        }
        await get().loadDocumentsById(connector.connectionId, type);
      },

      // Load documents by specific connectionId (avoids race condition)
      loadDocumentsById: async (connectionId: string, type: ConnectorType) => {
        try {
          const response = await externalConnectorsApi.listDocuments(connectionId);
          console.log(`[ExternalConnectors] Loaded ${response.documents.length} documents for ${type}`);

          const resources: ConnectedResource[] = response.documents.map((doc) => ({
            ...mapDocumentToResource(doc),
            id: `${type}_${doc.id}`, // Prefix with type for unique IDs
          }));

          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    connectedResources: resources,
                    documentCount: response.total,
                  }
                : c
            ),
          }));
        } catch (error) {
          console.error('Failed to load documents:', error);
        }
      },

      // Process a single document (fetch content, chunk, embed)
      processDocument: async (type: ConnectorType, resourceId: string) => {
        console.log('[ExternalConnectors Store] processDocument called:', { type, resourceId });
        const connector = get().connectors.find((c) => c.type === type);
        console.log('[ExternalConnectors Store] Found connector:', connector ? { type: connector.type, connectionId: connector.connectionId, status: connector.status } : 'null');
        if (!connector?.connectionId) {
          console.error('[ExternalConnectors Store] No connection found for type:', type, 'connector:', connector);
          return;
        }

        // Extract actual document ID from prefixed resource ID
        const documentId = resourceId.startsWith(`${type}_`)
          ? resourceId.substring(`${type}_`.length)
          : resourceId;

        // Mark resource as processing
        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  connectedResources: c.connectedResources.map((r) =>
                    r.id === resourceId
                      ? { ...r, isProcessing: true, status: 'chunking' as DocumentProcessingStatus }
                      : r
                  ),
                }
              : c
          ),
        }));

        try {
          const result = await externalConnectorsApi.processDocument(
            connector.connectionId,
            documentId
          );

          // Update resource with result
          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    connectedResources: c.connectedResources.map((r) =>
                      r.id === resourceId
                        ? {
                            ...r,
                            isProcessing: false,
                            status: result.status,
                            chunkCount: result.chunk_count,
                            errorMessage: result.error_message || undefined,
                          }
                        : r
                    ),
                    chunkCount: (c.chunkCount || 0) + result.chunk_count,
                  }
                : c
            ),
          }));

          console.log(`[ExternalConnectors] Processed document ${documentId}: status=${result.status}, chunks=${result.chunk_count}`);

          // If this document is already in activeResourcesByAgent (any agent), refresh its content
          const { activeResourcesByAgent } = get();
          const isSelectedInAnyAgent = Object.values(activeResourcesByAgent).some(
            (resources) => resources.some((r) => r.id === resourceId)
          );
          if (isSelectedInAnyAgent && result.status === 'ready') {
            try {
              console.log(`[ExternalConnectors] Refreshing content for selected document: ${documentId}`);
              const contentResponse = await externalConnectorsApi.getDocumentContent(
                connector.connectionId,
                documentId
              );

              if (contentResponse.content) {
                // Update connectedResources, activeResourcesByAgent, and selectedDocument with the content
                const fetchedContent = contentResponse.content; // Capture for closure
                set((state) => {
                  const updatedResource = state.connectors
                    .find((c) => c.type === type)
                    ?.connectedResources.find((r) => r.id === resourceId);

                  if (updatedResource) {
                    const resourceWithContent: ConnectedResource = {
                      ...updatedResource,
                      content: fetchedContent,
                    };

                    // Update activeResourcesByAgent for all agent types that have this resource
                    const updatedActiveResourcesByAgent: ActiveResourcesByAgent = {};
                    for (const [agentType, resources] of Object.entries(state.activeResourcesByAgent)) {
                      updatedActiveResourcesByAgent[agentType as AgentType] = resources.map((r) =>
                        r.id === resourceId ? resourceWithContent : r
                      );
                    }

                    // Also update selectedDocument if it's the same document
                    const updatedSelectedDocument =
                      state.selectedDocument?.id === resourceId
                        ? resourceWithContent
                        : state.selectedDocument;

                    return {
                      connectors: state.connectors.map((c) =>
                        c.type === type
                          ? {
                              ...c,
                              connectedResources: c.connectedResources.map((r) =>
                                r.id === resourceId ? resourceWithContent : r
                              ),
                            }
                          : c
                      ),
                      activeResourcesByAgent: updatedActiveResourcesByAgent,
                      selectedDocument: updatedSelectedDocument,
                    };
                  }
                  return state;
                });
                console.log(`[ExternalConnectors] Content refreshed for ${resourceId}: ${contentResponse.content.length} chars`);
              }
            } catch (contentError) {
              console.error('[ExternalConnectors] Failed to refresh content after processing:', contentError);
            }
          }
        } catch (error) {
          // Mark as error
          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    connectedResources: c.connectedResources.map((r) =>
                      r.id === resourceId
                        ? {
                            ...r,
                            isProcessing: false,
                            status: 'error' as DocumentProcessingStatus,
                            errorMessage: error instanceof Error ? error.message : 'Processing failed',
                          }
                        : r
                    ),
                  }
                : c
            ),
          }));
          console.error('Failed to process document:', error);
        }
      },

      // Process multiple documents
      processSelectedDocuments: async (type: ConnectorType, resourceIds: string[]) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector?.connectionId) {
          console.error('No connection found for type:', type);
          return;
        }

        // Extract actual document IDs from prefixed resource IDs
        const documentIds = resourceIds.map((id) =>
          id.startsWith(`${type}_`) ? id.substring(`${type}_`.length) : id
        );

        // Mark all resources as processing
        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  connectedResources: c.connectedResources.map((r) =>
                    resourceIds.includes(r.id)
                      ? { ...r, isProcessing: true, status: 'chunking' as DocumentProcessingStatus }
                      : r
                  ),
                }
              : c
          ),
        }));

        try {
          const result = await externalConnectorsApi.processDocumentsBatch(
            connector.connectionId,
            documentIds
          );

          console.log(`[ExternalConnectors] Batch processing: processed=${result.processed}, failed=${result.failed}, skipped=${result.skipped}`);

          // Reload documents to get updated statuses
          await get().loadDocumentsById(connector.connectionId, type);
        } catch (error) {
          // Mark all as error
          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    connectedResources: c.connectedResources.map((r) =>
                      resourceIds.includes(r.id)
                        ? {
                            ...r,
                            isProcessing: false,
                            status: 'error' as DocumentProcessingStatus,
                            errorMessage: error instanceof Error ? error.message : 'Processing failed',
                          }
                        : r
                    ),
                  }
                : c
            ),
          }));
          console.error('Failed to process documents batch:', error);
        }
      },

      // Add resource to connector
      addResource: (type, resource) => {
        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  connectedResources: [...c.connectedResources, resource],
                }
              : c
          ),
        }));
      },

      // Remove resource from connector (removes from all agent types)
      removeResource: (type, resourceId) => {
        set((state) => {
          // Remove from activeResourcesByAgent for all agent types
          const updatedActiveResourcesByAgent: ActiveResourcesByAgent = {};
          for (const [agentType, resources] of Object.entries(state.activeResourcesByAgent)) {
            updatedActiveResourcesByAgent[agentType as AgentType] = resources.filter((r) => r.id !== resourceId);
          }

          return {
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    connectedResources: c.connectedResources.filter((r) => r.id !== resourceId),
                  }
                : c
            ),
            activeResourcesByAgent: updatedActiveResourcesByAgent,
          };
        });
      },

      // Sync resources from backend
      syncResources: async (type, specificConnectionId?: string) => {
        const connector = get().connectors.find((c) => c.type === type);

        // Prevent duplicate sync requests - don't sync if already syncing
        if (connector?.status === 'connecting') {
          console.log(`[ExternalConnectors] Already syncing ${type}, skipping duplicate request`);
          return;
        }

        // Use specific connectionId if provided, otherwise use connector's connectionId
        const connectionId = specificConnectionId || connector?.connectionId;
        if (!connectionId) {
          return;
        }

        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type ? { ...c, status: 'connecting' } : c
          ),
        }));

        try {
          await externalConnectorsApi.sync(connectionId);
          // Use the same connectionId for loading documents to avoid race condition
          await get().loadDocumentsById(connectionId, type);

          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'active',
                    lastConnected: new Date().toISOString(),
                  }
                : c
            ),
          }));
        } catch (error) {
          set((state) => ({
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'error',
                    error: error instanceof Error ? error.message : 'Sync failed',
                  }
                : c
            ),
          }));
        }
      },

      // Toggle resource active state for chat context
      // Toggle resource active state for chat context (scoped by current agent type)
      toggleResourceActive: (resource) => {
        set((state) => {
          const currentResources = state.activeResourcesByAgent[state.currentAgentType] || [];
          const isActive = currentResources.some((r) => r.id === resource.id);
          return {
            activeResourcesByAgent: {
              ...state.activeResourcesByAgent,
              [state.currentAgentType]: isActive
                ? currentResources.filter((r) => r.id !== resource.id)
                : [...currentResources, resource],
            },
          };
        });
      },

      // Toggle resource active with content fetch (for RAG context)
      // This version fetches document content if not already loaded
      // Also sets the selected document as the "currently viewing" document
      toggleResourceActiveWithContent: async (resource: ConnectedResource, type: ConnectorType) => {
        const { activeResourcesByAgent, currentAgentType, connectors } = get();
        const currentResources = activeResourcesByAgent[currentAgentType] || [];
        const isActive = currentResources.some((r) => r.id === resource.id);

        if (isActive) {
          // Deselecting - remove from active and clear selectedDocument if it was this one
          set((state) => {
            const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
            return {
              activeResourcesByAgent: {
                ...state.activeResourcesByAgent,
                [state.currentAgentType]: resources.filter((r) => r.id !== resource.id),
              },
              // Clear selectedDocument if it was the deselected document
              selectedDocument: state.selectedDocument?.id === resource.id ? null : state.selectedDocument,
            };
          });
          return;
        }

        // Check if document is processed - warn if not ready
        if (resource.status !== 'ready') {
          console.warn(`[ExternalConnectors] Document "${resource.title}" is not processed (status: ${resource.status}). Process it first for RAG context.`);
          // Still add to selection, but content won't be available
        }

        // Selecting - check if content is already loaded
        if (resource.content) {
          // Content already loaded, just add to active and set as selected document
          set((state) => {
            const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
            return {
              activeResourcesByAgent: {
                ...state.activeResourcesByAgent,
                [state.currentAgentType]: [...resources, resource],
              },
              selectedDocument: resource, // Set as currently viewing document
            };
          });
          return;
        }

        // Need to fetch content
        const connector = connectors.find((c) => c.type === type);
        if (!connector?.connectionId) {
          console.error('[ExternalConnectors] No connection found for type:', type);
          // Add without content but still set as selected
          set((state) => {
            const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
            return {
              activeResourcesByAgent: {
                ...state.activeResourcesByAgent,
                [state.currentAgentType]: [...resources, resource],
              },
              selectedDocument: resource, // Set as currently viewing document
            };
          });
          return;
        }

        // Extract actual document ID from prefixed resource ID
        const documentId = resource.id.startsWith(`${type}_`)
          ? resource.id.substring(`${type}_`.length)
          : resource.id;

        try {
          console.log(`[ExternalConnectors] Fetching content for document: ${documentId}`);
          const contentResponse = await externalConnectorsApi.getDocumentContent(
            connector.connectionId,
            documentId
          );

          if (contentResponse.content) {
            // Update resource with content
            const updatedResource: ConnectedResource = {
              ...resource,
              content: contentResponse.content,
            };

            // Update in connectedResources, activeResourcesByAgent, and set as selectedDocument
            set((state) => {
              const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
              return {
                connectors: state.connectors.map((c) =>
                  c.type === type
                    ? {
                        ...c,
                        connectedResources: c.connectedResources.map((r) =>
                          r.id === resource.id ? updatedResource : r
                        ),
                      }
                    : c
                ),
                activeResourcesByAgent: {
                  ...state.activeResourcesByAgent,
                  [state.currentAgentType]: [...resources, updatedResource],
                },
                selectedDocument: updatedResource, // Set as currently viewing document
              };
            });

            console.log(`[ExternalConnectors] Loaded content for ${resource.title}: ${contentResponse.content.length} chars`);
          } else {
            // No content available, add resource without content but still set as selected
            console.warn(`[ExternalConnectors] No content available for document: ${documentId}`);
            set((state) => {
              const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
              return {
                activeResourcesByAgent: {
                  ...state.activeResourcesByAgent,
                  [state.currentAgentType]: [...resources, resource],
                },
                selectedDocument: resource, // Set as currently viewing document
              };
            });
          }
        } catch (error) {
          console.error('[ExternalConnectors] Failed to fetch document content:', error);
          // Add resource without content but still set as selected
          set((state) => {
            const resources = state.activeResourcesByAgent[state.currentAgentType] || [];
            return {
              activeResourcesByAgent: {
                ...state.activeResourcesByAgent,
                [state.currentAgentType]: [...resources, resource],
              },
              selectedDocument: resource, // Set as currently viewing document
            };
          });
        }
      },

      // Clear all active resources for current agent type
      clearActiveResources: () => {
        set((state) => ({
          activeResourcesByAgent: {
            ...state.activeResourcesByAgent,
            [state.currentAgentType]: [],
          },
          selectedDocument: null, // Also clear selected document
        }));
      },

      // Get context string from active resources for chat
      // Includes both explicitly selected resources AND the currently viewed document
      getActiveResourcesContext: () => {
        const { activeResourcesByAgent, currentAgentType, selectedDocument } = get();
        const activeResources = activeResourcesByAgent[currentAgentType] || [];

        // Combine active resources with selectedDocument (avoid duplicates)
        const allResources = [...activeResources];
        if (selectedDocument && !activeResources.some((r) => r.id === selectedDocument.id)) {
          allResources.push(selectedDocument);
        }

        if (allResources.length === 0) {
          return '';
        }

        const contextParts = allResources.map((resource) => {
          // selectedDocument가 현재 조회 중인 문서임을 표시
          const isCurrentlyViewing = selectedDocument?.id === resource.id;
          const header = isCurrentlyViewing
            ? `--- ${resource.title} (${resource.type}) [현재 조회 중] ---`
            : `--- ${resource.title} (${resource.type}) ---`;
          return `${header}\nSource: ${resource.url}\n\n${resource.content || 'No content available'}\n`;
        });

        return `[External Resources Context]\n\n${contextParts.join('\n')}`;
      },

      // Getters
      getConnector: (type) => {
        return get().connectors.find((c) => c.type === type);
      },

      getAvailableConnectors: () => {
        return Object.values(CONNECTOR_CONFIGS);
      },

      getConnectedCount: () => {
        return get().connectors.filter((c) => c.status === 'active').length;
      },
    }),
    {
      name: 'external-connectors-storage',
      storage: createJSONStorage(() => localStorage),
      // SECURITY: Only persist non-sensitive connector state to localStorage
      // OAuth tokens/credentials are stored server-side only to prevent XSS token theft
      partialize: (state) => ({
        connectors: state.connectors.map((c) => ({
          id: c.id,
          type: c.type,
          name: c.name,
          status: c.status,
          developmentStatus: c.developmentStatus,
          ssoProfile: c.ssoProfile,
          // SECURITY: Do NOT persist credentials (tokens) to localStorage
          // credentials: c.credentials, // Removed - stored server-side only
          connectedResources: c.connectedResources,
          lastConnected: c.lastConnected,
          connectionId: c.connectionId,
          documentCount: c.documentCount,
          chunkCount: c.chunkCount,
        })),
        activeResourcesByAgent: state.activeResourcesByAgent,
        currentUserId: state.currentUserId,
      }),
      // Merge persisted state with initial state to ensure new connectors are added
      merge: (persistedState, currentState) => {
        const persisted = persistedState as Partial<ExternalConnectorsState>;
        const persistedConnectors = persisted.connectors || [];

        // Get all connector types from initial connectors
        const allConnectorTypes = initialConnectors.map((c) => c.type);

        // Merge: keep persisted data for existing connectors, add new ones
        const mergedConnectors = allConnectorTypes.map((type) => {
          const persistedConnector = persistedConnectors.find((c) => c.type === type);
          const initialConnector = initialConnectors.find((c) => c.type === type)!;

          if (persistedConnector) {
            // Update developmentStatus from config (in case it changed)
            return {
              ...persistedConnector,
              developmentStatus: CONNECTOR_CONFIGS[type].developmentStatus,
            };
          }

          // New connector - use initial state
          return initialConnector;
        });

        return {
          ...currentState,
          ...persisted,
          connectors: mergedConnectors,
        };
      },
    }
  )
);

export default useExternalConnectorsStore;
