/**
 * API Module Index
 *
 * Central export point for all API-related modules.
 *
 * Usage:
 * ```typescript
 * import { apiClient, authApi, isApiError } from '@/api';
 *
 * // Using auth API
 * const user = await authApi.login({ username: 'user', password: 'pass' });
 *
 * // Using raw client for custom endpoints
 * const data = await apiClient.get('/custom/endpoint');
 *
 * // Error handling
 * try {
 *   await authApi.login(credentials);
 * } catch (error) {
 *   if (isApiError(error)) {
 *     console.log(error.code, error.message);
 *   }
 * }
 * ```
 */

// API Client
export { default as apiClient } from './client';
export {
  setSessionExpiredCallback,
  isApiError,
  getErrorMessage,
  type ApiError,
} from './client';

// Auth API
export { default as authApi } from './auth.api';
export {
  login,
  register,
  verifyEmail,
  resendVerification,
  loginWithGoogle,
  initiateSSOLogin,
  getCurrentUser,
  refreshToken,
  logout,
} from './auth.api';

// Agent API
export { default as agentApi } from './agent.api';
export {
  executeAgent,
  streamAgent,
  getAgentTypes,
  getAgentTools,
  classifyTask,
  checkAgentHealth,
} from './agent.api';
export type {
  AgentType,
  AgentExecuteRequest,
  AgentExecuteResponse,
  AgentSource,
  AgentStreamChunk,
  AgentStreamChunkType,
  ToolDefinition,
  AgentHealthResponse,
  ClassifyTaskResponse,
} from './agent.api';

// FAQ API
export { default as faqApi } from './faq.api';
export {
  getFAQItems,
  getFAQCategories,
  recordFAQView,
  recordFAQFeedback,
  getPopularQueries,
  syncDynamicFAQItems,
  createFAQItem,
} from './faq.api';
export type {
  FAQItemAPI,
  FAQCategory,
  PopularQuery,
  FAQListResponse,
  FAQCategoriesResponse,
  PopularQueriesResponse,
  GetFAQItemsOptions,
  CreateFAQItemRequest,
  CreateFAQItemResponse,
} from './faq.api';

// Feedback API
export { default as feedbackApi } from './feedback.api';
export { submitQuickFeedback } from './feedback.api';
export type { QuickFeedbackRequest, FeedbackResponse } from './feedback.api';

// API Key API
export { default as apiKeyApi } from './apiKey.api';
export {
  createApiKey,
  listApiKeys,
  getApiKey,
  updateApiKey,
  deleteApiKey,
} from './apiKey.api';
export type {
  ApiKeyCreateRequest,
  ApiKeyUpdateRequest,
  ApiKeyResponse,
  ApiKeyCreatedResponse,
  ApiKeyListResponse,
} from './apiKey.api';

// Types
export type {
  // Common
  ApiResponse,
  ApiErrorResponse,
  // User
  UserRole,
  AuthProvider,
  UserProfile,
  // Auth Requests
  LoginRequest,
  RegisterRequest,
  VerifyEmailRequest,
  ResendVerificationRequest,
  GoogleAuthRequest,
  SSORequest,
  RefreshTokenRequest,
  // Auth Responses
  TokenResponse,
  LoginResponse,
  RegisterResponse,
  VerifyEmailResponse,
  GoogleAuthResponse,
  SSOResponse,
  RefreshResponse,
  // Error
  AuthErrorCode,
} from './types';

export { AUTH_ERROR_CODES } from './types';

// Adaptive Documents API
export { default as adaptiveDocumentsApi } from './adaptiveDocuments.api';
export {
  processAdaptivePDF,
  getAdaptiveChunks,
  getChunkDetail,
  getCoverage,
  getQuality,
  getStructure,
  searchAdaptiveChunks,
  getProcessingStatus,
  deleteAdaptiveDocument,
  uploadPdfOnly,
  listPendingUploads,
  startBatchEmbed,
  deletePendingUpload,
  evaluateQuality,
} from './adaptiveDocuments.api';
export type {
  ChunkType,
  DocumentType,
  ProcessingStatus,
  QualityLevel,
  AdaptiveProcessOptions,
  AdaptiveProcessResponse,
  ChunkListItem,
  ChunkDetail,
  CoverageResponse,
  QualityResponse,
  StructureAnalysisResponse,
  SearchAdaptiveChunksRequest,
  SearchResultItem,
  SearchAdaptiveChunksResponse,
  ProcessingStatusResponse,
  DeleteResponse,
  AdaptiveDocumentListItem,
  PendingUploadItem,
  PendingUploadsResponse,
  UploadOnlyResponse,
  BatchEmbedResultItem,
  BatchEmbedResponse,
  EvaluateQualityResponse,
} from './adaptiveDocuments.api';

// External Connectors API
export { default as externalConnectorsApi } from './externalConnectors.api';
export {
  getAvailableResources,
  listConnections,
  createConnection,
  getConnection,
  disconnectConnection,
  getOAuthUrl,
  completeOAuth,
  syncConnection,
  listConnectionDocuments,
  getUserStats,
  searchExternalResources,
} from './externalConnectors.api';
export type {
  ExternalResourceType,
  ConnectionStatus,
  SyncStatus,
  AuthType,
  AvailableResource,
  ExternalConnection,
  ExternalDocument,
  ExternalSearchResult,
  UserStats,
  SyncStats,
  CreateConnectionRequest,
  SearchRequest,
  SyncRequest,
  AvailableResourcesResponse,
  ConnectionListResponse,
  OAuthUrlResponse,
  DocumentListResponse,
  SearchResponse,
} from './externalConnectors.api';

// Mindmap API
export { default as mindmapApi } from './mindmap.api';
export {
  generateMindmap,
  listMindmaps,
  getMindmap,
  deleteMindmap,
  expandNode,
  queryNode,
  getNodeDetail,
  generateFromAllDocuments,
} from './mindmap.api';
export type {
  NodeType,
  RelationType,
  MindmapNode,
  MindmapEdge,
  MindmapData,
  MindmapInfo,
  MindmapFull,
  GenerateMindmapRequest,
  ExpandNodeRequest,
  QueryNodeRequest,
  GenerateMindmapResponse,
  ExpandNodeResponse,
  QueryNodeResponse,
  NodeDetailResponse,
  MindmapListResponse,
} from './mindmap.api';

// Web Pages API
export { default as webPagesApi } from './webPages.api';
export {
  listWebSources,
  getWebSource,
  createWebSource,
  createBulkWebSources,
  refreshWebSource,
  deleteWebSource,
  getWebSourceContent,
  getWebSourceLinks,
  getWebSourceImages,
  searchWebSources,
} from './webPages.api';
export type {
  WebSourceStatus,
  ExtractorType,
  ContentType,
  WebSourceListItem,
  WebSource,
  WebSourceMetadata,
  WebSourceStats,
  LinkInfo,
  ImageInfo,
  CreateWebSourceRequest,
  BulkCreateWebSourceRequest,
  ListWebSourcesParams,
  WebSourceResponse,
  WebSourceListResponse,
  BulkCreateResponse,
  ContentResponse,
  LinksResponse,
  ImagesResponse,
  SearchResponse as WebSourceSearchResponse,
  RefreshResponse as WebSourceRefreshResponse,
  DeleteResponse as WebSourceDeleteResponse,
} from './webPages.api';
