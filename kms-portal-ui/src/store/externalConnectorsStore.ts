/**
 * External Connectors Store
 *
 * Manages external service connectors state for the AI Agent chat.
 * Supports: Notion, Confluence (in development), GitHub, Google Drive (planned)
 * All connectors use SSO (OAuth 2.0) for authentication.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// =============================================================================
// Types
// =============================================================================

/**
 * Connector types supported by the system
 */
export type ConnectorType = 'notion' | 'confluence' | 'github' | 'google_drive';

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
  authType: 'sso';
  oauthUrl: string;
  scopes: string[];
}

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

  // SSO state
  ssoState: SSOState;
  ssoError: string | null;

  // Active resources for chat context
  activeResources: ConnectedResource[];

  // Actions
  openModal: () => void;
  closeModal: () => void;
  selectConnectorType: (type: ConnectorType | null) => void;

  // SSO Authentication
  initiateSSO: (type: ConnectorType) => void;
  handleSSOCallback: (type: ConnectorType, authCode: string) => Promise<void>;
  cancelSSO: () => void;

  // Connector management (legacy - kept for compatibility)
  connectService: (type: ConnectorType, credentials: ExternalConnector['credentials']) => Promise<void>;
  disconnectService: (type: ConnectorType) => void;
  testConnection: (type: ConnectorType) => Promise<boolean>;

  // Resource management
  addResource: (type: ConnectorType, resource: ConnectedResource) => void;
  removeResource: (type: ConnectorType, resourceId: string) => void;
  syncResources: (type: ConnectorType) => Promise<void>;

  // Active resources for chat
  toggleResourceActive: (resource: ConnectedResource) => void;
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
    developmentStatus: 'in_development',
    authType: 'sso',
    oauthUrl: 'https://api.notion.com/v1/oauth/authorize',
    scopes: ['read_content', 'read_user'],
  },
  confluence: {
    type: 'confluence',
    name: 'Confluence',
    icon: 'confluence',
    description: 'Connect to Atlassian Confluence spaces',
    developmentStatus: 'in_development',
    authType: 'sso',
    oauthUrl: 'https://auth.atlassian.com/authorize',
    scopes: ['read:confluence-content.all', 'read:confluence-space.summary'],
  },
  github: {
    type: 'github',
    name: 'GitHub',
    icon: 'github',
    description: 'Connect to GitHub repositories',
    developmentStatus: 'planned',
    authType: 'sso',
    oauthUrl: 'https://github.com/login/oauth/authorize',
    scopes: ['repo', 'read:user'],
  },
  google_drive: {
    type: 'google_drive',
    name: 'Google Drive',
    icon: 'google-drive',
    description: 'Connect to Google Drive files and folders',
    developmentStatus: 'planned',
    authType: 'sso',
    oauthUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
    scopes: ['https://www.googleapis.com/auth/drive.readonly'],
  },
};

// =============================================================================
// Mock SSO Profiles for Development
// =============================================================================

const MOCK_SSO_PROFILES: Record<ConnectorType, SSOProfile> = {
  notion: {
    id: 'notion_user_123',
    email: 'user@example.com',
    name: 'Demo User',
    avatar: 'https://www.notion.so/images/meta/default.png',
    provider: 'notion',
  },
  confluence: {
    id: 'confluence_user_456',
    email: 'user@company.atlassian.net',
    name: 'Demo User',
    avatar: 'https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/default-avatar.png',
    provider: 'confluence',
  },
  github: {
    id: 'github_user_789',
    email: 'user@github.com',
    name: 'Demo User',
    avatar: 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png',
    provider: 'github',
  },
  google_drive: {
    id: 'google_user_012',
    email: 'user@gmail.com',
    name: 'Demo User',
    avatar: 'https://www.gstatic.com/images/branding/product/2x/drive_2020q4_48dp.png',
    provider: 'google_drive',
  },
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
];

// =============================================================================
// Mock Data for Development
// =============================================================================

const MOCK_NOTION_PAGES: ConnectedResource[] = [
  {
    id: 'notion_page_1',
    title: 'Project Roadmap 2025',
    url: 'https://notion.so/workspace/roadmap-2025',
    type: 'page',
    lastSynced: new Date().toISOString(),
    content: `# Project Roadmap 2025

## Q1 Goals
- Launch v2.0 of the platform
- Implement new authentication system
- Add multi-language support (Korean, Japanese, English)

## Q2 Goals
- Mobile app beta release
- Integration with external services
- Performance optimization

## Key Metrics
- User acquisition: 10,000 new users
- Revenue target: $500K
- Customer satisfaction: 95%`,
  },
  {
    id: 'notion_page_2',
    title: 'API Documentation',
    url: 'https://notion.so/workspace/api-docs',
    type: 'page',
    lastSynced: new Date().toISOString(),
    content: `# API Documentation

## Authentication
All API requests require Bearer token authentication.

## Endpoints

### GET /api/v1/users
Returns list of users.

### POST /api/v1/documents
Creates a new document.

### PUT /api/v1/documents/:id
Updates an existing document.`,
  },
  {
    id: 'notion_db_1',
    title: 'Task Database',
    url: 'https://notion.so/workspace/tasks',
    type: 'database',
    lastSynced: new Date().toISOString(),
    content: `Task Database contains 150 items across 5 projects.
Status breakdown: 45 In Progress, 80 Completed, 25 Pending`,
  },
];

const MOCK_CONFLUENCE_PAGES: ConnectedResource[] = [
  {
    id: 'confluence_page_1',
    title: 'System Architecture Overview',
    url: 'https://company.atlassian.net/wiki/spaces/DEV/pages/123',
    type: 'page',
    lastSynced: new Date().toISOString(),
    content: `# System Architecture Overview

## Components
1. Frontend: React 18 + TypeScript
2. Backend: FastAPI (Python 3.10+)
3. Database: Neo4j (Graph) + PostgreSQL
4. AI/ML: NVIDIA NIM Containers

## Infrastructure
- GPU Server: NVIDIA A100 x 8
- Container Orchestration: Docker Compose
- Load Balancer: NGINX

## Security
- JWT Authentication with HttpOnly cookies
- Role-based access control (RBAC)
- Data encryption at rest and in transit`,
  },
  {
    id: 'confluence_page_2',
    title: 'Development Guidelines',
    url: 'https://company.atlassian.net/wiki/spaces/DEV/pages/456',
    type: 'page',
    lastSynced: new Date().toISOString(),
    content: `# Development Guidelines

## Code Style
- Python: Black formatter, type hints required
- TypeScript: ESLint + Prettier, strict mode
- Comments: Korean allowed for business logic

## Git Workflow
- Feature branches from develop
- PR reviews required (min 2 approvers)
- Squash merge to main

## Testing
- Unit tests: pytest (Python), Vitest (TS)
- Integration tests required for API endpoints
- E2E tests for critical user flows`,
  },
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
      ssoState: 'idle',
      ssoError: null,
      activeResources: [],

      // Modal actions
      openModal: () => set({ isModalOpen: true }),
      closeModal: () => set({ isModalOpen: false, selectedConnectorType: null, ssoState: 'idle', ssoError: null }),
      selectConnectorType: (type) => set({ selectedConnectorType: type, ssoState: 'idle', ssoError: null }),

      // SSO Authentication - Initiate OAuth flow
      initiateSSO: (type) => {
        const config = CONNECTOR_CONFIGS[type];

        // Check if connector is available
        if (config.developmentStatus === 'planned') {
          set({ ssoError: 'This connector is not yet available' });
          return;
        }

        set({ ssoState: 'authorizing', ssoError: null, isConnecting: true });

        // In a real implementation, this would open a popup or redirect
        // For mock, we simulate the OAuth flow with a timeout
        setTimeout(() => {
          // Simulate successful OAuth callback
          get().handleSSOCallback(type, 'mock_auth_code_' + Date.now());
        }, 2000);
      },

      // Handle SSO callback (exchange auth code for tokens)
      handleSSOCallback: async (type, _authCode) => {
        try {
          // Simulate token exchange delay
          await new Promise((resolve) => setTimeout(resolve, 1000));

          // Check if connector is available
          const config = CONNECTOR_CONFIGS[type];
          if (config.developmentStatus === 'planned') {
            set({
              ssoState: 'error',
              ssoError: 'This connector is not yet available',
              isConnecting: false,
            });
            return;
          }

          // Mock successful SSO with profile and resources
          const mockProfile = MOCK_SSO_PROFILES[type];
          const mockResources = type === 'notion' ? MOCK_NOTION_PAGES : MOCK_CONFLUENCE_PAGES;
          const mockCredentials = {
            accessToken: 'mock_access_token_' + Date.now(),
            refreshToken: 'mock_refresh_token_' + Date.now(),
            expiresAt: new Date(Date.now() + 3600000).toISOString(), // 1 hour
          };

          set((state) => ({
            ssoState: 'success',
            isConnecting: false,
            connectors: state.connectors.map((c) =>
              c.type === type
                ? {
                    ...c,
                    status: 'active',
                    ssoProfile: mockProfile,
                    credentials: mockCredentials,
                    connectedResources: mockResources,
                    lastConnected: new Date().toISOString(),
                    error: undefined,
                  }
                : c
            ),
          }));
        } catch (error) {
          set({
            ssoState: 'error',
            ssoError: error instanceof Error ? error.message : 'SSO authentication failed',
            isConnecting: false,
          });
        }
      },

      // Cancel SSO flow
      cancelSSO: () => {
        set({ ssoState: 'idle', ssoError: null, isConnecting: false });
      },

      // Connect to service (Legacy - uses SSO now)
      connectService: async (type, credentials) => {
        set({ isConnecting: true });

        // Simulate API call delay
        await new Promise((resolve) => setTimeout(resolve, 1500));

        // Check if connector is available for development
        const config = CONNECTOR_CONFIGS[type];
        if (config.developmentStatus === 'planned') {
          set((state) => ({
            isConnecting: false,
            connectors: state.connectors.map((c) =>
              c.type === type
                ? { ...c, status: 'error', error: 'This connector is not yet available' }
                : c
            ),
          }));
          return;
        }

        // Mock successful connection with mock data
        const mockResources = type === 'notion' ? MOCK_NOTION_PAGES : MOCK_CONFLUENCE_PAGES;

        set((state) => ({
          isConnecting: false,
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  status: 'active',
                  credentials,
                  connectedResources: mockResources,
                  lastConnected: new Date().toISOString(),
                  error: undefined,
                }
              : c
          ),
        }));
      },

      // Disconnect from service
      disconnectService: (type) => {
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
                }
              : c
          ),
          activeResources: state.activeResources.filter(
            (r) => !r.id.startsWith(`${type}_`)
          ),
          ssoState: 'idle',
          ssoError: null,
        }));
      },

      // Test connection (Mock)
      testConnection: async (type) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector || connector.status !== 'active') {
          return false;
        }

        // Simulate test delay
        await new Promise((resolve) => setTimeout(resolve, 500));
        return true;
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

      // Remove resource from connector
      removeResource: (type, resourceId) => {
        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  connectedResources: c.connectedResources.filter((r) => r.id !== resourceId),
                }
              : c
          ),
          activeResources: state.activeResources.filter((r) => r.id !== resourceId),
        }));
      },

      // Sync resources (Mock - refresh data)
      syncResources: async (type) => {
        const connector = get().connectors.find((c) => c.type === type);
        if (!connector || connector.status !== 'active') {
          return;
        }

        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type ? { ...c, status: 'connecting' } : c
          ),
        }));

        // Simulate sync delay
        await new Promise((resolve) => setTimeout(resolve, 1000));

        set((state) => ({
          connectors: state.connectors.map((c) =>
            c.type === type
              ? {
                  ...c,
                  status: 'active',
                  connectedResources: c.connectedResources.map((r) => ({
                    ...r,
                    lastSynced: new Date().toISOString(),
                  })),
                }
              : c
          ),
        }));
      },

      // Toggle resource active state for chat context
      toggleResourceActive: (resource) => {
        set((state) => {
          const isActive = state.activeResources.some((r) => r.id === resource.id);
          return {
            activeResources: isActive
              ? state.activeResources.filter((r) => r.id !== resource.id)
              : [...state.activeResources, resource],
          };
        });
      },

      // Clear all active resources
      clearActiveResources: () => {
        set({ activeResources: [] });
      },

      // Get context string from active resources for chat
      getActiveResourcesContext: () => {
        const { activeResources } = get();
        if (activeResources.length === 0) {
          return '';
        }

        const contextParts = activeResources.map((resource) => {
          return `--- ${resource.title} (${resource.type}) ---\nSource: ${resource.url}\n\n${resource.content || 'No content available'}\n`;
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
      // Only persist connector credentials, SSO profile, and active resources
      partialize: (state) => ({
        connectors: state.connectors.map((c) => ({
          id: c.id,
          type: c.type,
          name: c.name,
          status: c.status,
          developmentStatus: c.developmentStatus,
          ssoProfile: c.ssoProfile,
          credentials: c.credentials,
          connectedResources: c.connectedResources,
          lastConnected: c.lastConnected,
        })),
        activeResources: state.activeResources,
      }),
    }
  )
);

export default useExternalConnectorsStore;
