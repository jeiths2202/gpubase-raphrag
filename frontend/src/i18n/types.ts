/**
 * i18n Type Definitions
 *
 * Type-safe internationalization for KMS Platform
 */

// Supported language codes
export type LanguageCode = 'en' | 'ko' | 'ja';

// Locale codes with region
export type LocaleCode = 'en-US' | 'ko-KR' | 'ja-JP';

// Map language codes to full locale codes
export const LOCALE_MAP: Record<LanguageCode, LocaleCode> = {
  en: 'en-US',
  ko: 'ko-KR',
  ja: 'ja-JP',
};

// Language metadata
export interface LanguageInfo {
  code: LanguageCode;
  name: string;
  nativeName: string;
  flag: string;
}

// Available languages configuration
export const LANGUAGES: Record<LanguageCode, LanguageInfo> = {
  en: {
    code: 'en',
    name: 'English',
    nativeName: 'English',
    flag: '🇺🇸',
  },
  ko: {
    code: 'ko',
    name: 'Korean',
    nativeName: '한국어',
    flag: '🇰🇷',
  },
  ja: {
    code: 'ja',
    name: 'Japanese',
    nativeName: '日本語',
    flag: '🇯🇵',
  },
};

// Default language
export const DEFAULT_LANGUAGE: LanguageCode = 'en';

// Translation namespace keys
export type TranslationNamespace =
  | 'common'
  | 'auth'
  | 'dashboard'
  | 'knowledge'
  | 'mindmap'
  | 'admin'
  | 'errors';

// Translation key paths (for type safety)
export interface TranslationKeys {
  // Common
  'common.appName': string;
  'common.loading': string;
  'common.error': string;
  'common.success': string;
  'common.cancel': string;
  'common.confirm': string;
  'common.save': string;
  'common.delete': string;
  'common.edit': string;
  'common.create': string;
  'common.search': string;
  'common.filter': string;
  'common.sort': string;
  'common.refresh': string;
  'common.close': string;
  'common.back': string;
  'common.next': string;
  'common.previous': string;
  'common.submit': string;
  'common.reset': string;
  'common.viewAll': string;
  'common.noData': string;
  'common.actions': string;

  // Navigation
  'common.nav.home': string;
  'common.nav.knowledge': string;
  'common.nav.mindmap': string;
  'common.nav.documents': string;
  'common.nav.analytics': string;
  'common.nav.admin': string;
  'common.nav.settings': string;
  'common.nav.logout': string;

  // Auth
  'auth.login': string;
  'auth.logout': string;
  'auth.loginTitle': string;
  'auth.loginSubtitle': string;
  'auth.googleLogin': string;
  'auth.loggingIn': string;
  'auth.logoutConfirm': string;

  // Dashboard
  'dashboard.welcome': string;
  'dashboard.welcomeMessage': string;
  'dashboard.systemStatus': string;
  'dashboard.quickActions': string;
  'dashboard.knowledgeSources': string;
  'dashboard.recentActivity': string;
  'dashboard.gpu': string;
  'dashboard.model': string;
  'dashboard.vectorIndex': string;
  'dashboard.graphDb': string;
  'dashboard.memory': string;
  'dashboard.utilization': string;
  'dashboard.temperature': string;
  'dashboard.version': string;
  'dashboard.status': string;
  'dashboard.inferenceTime': string;
  'dashboard.documents': string;
  'dashboard.chunks': string;
  'dashboard.nodes': string;
  'dashboard.relationships': string;
  'dashboard.todaySearches': string;
  'dashboard.newDocuments': string;
  'dashboard.aiResponses': string;
  'dashboard.avgResponse': string;

  // Knowledge
  'knowledge.title': string;
  'knowledge.searchPlaceholder': string;
  'knowledge.askQuestion': string;
  'knowledge.noResults': string;
  'knowledge.sources': string;
  'knowledge.relevance': string;

  // Mindmap
  'mindmap.title': string;
  'mindmap.createNew': string;
  'mindmap.addNode': string;
  'mindmap.deleteNode': string;
  'mindmap.editNode': string;

  // Admin
  'admin.title': string;
  'admin.users': string;
  'admin.system': string;
  'admin.logs': string;

  // Errors
  'errors.generic': string;
  'errors.network': string;
  'errors.unauthorized': string;
  'errors.notFound': string;
  'errors.serverError': string;

  // Time
  'time.justNow': string;
  'time.minutesAgo': string;
  'time.hoursAgo': string;
  'time.daysAgo': string;
  'time.weeksAgo': string;

  // Status
  'status.online': string;
  'status.offline': string;
  'status.loading': string;
  'status.ready': string;
  'status.error': string;
  'status.syncing': string;
  'status.connected': string;
  'status.disconnected': string;
  'status.active': string;
  'status.inactive': string;
}

// Translation function type
export type TranslateFunction = (
  key: keyof TranslationKeys,
  params?: Record<string, string | number>
) => string;

// i18n Context type
export interface I18nContextType {
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  t: TranslateFunction;
  isLoading: boolean;
}
