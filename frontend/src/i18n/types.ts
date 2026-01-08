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
  'auth.signIn': string;
  'auth.register': string;
  'auth.userId': string;
  'auth.userIdPlaceholder': string;
  'auth.password': string;
  'auth.passwordPlaceholder': string;
  'auth.orContinueWith': string;
  'auth.corporateSSO': string;
  'auth.chooseUserId': string;
  'auth.emailForVerification': string;
  'auth.emailPlaceholder': string;
  'auth.passwordMinLength': string;
  'auth.confirmPassword': string;
  'auth.confirmPasswordPlaceholder': string;
  'auth.createAccount': string;
  'auth.verificationHint': string;
  'auth.verificationSent': string;
  'auth.verificationEmailSent': string;
  'auth.verificationCode': string;
  'auth.verificationCodePlaceholder': string;
  'auth.verifyEmail': string;
  'auth.accountVerified': string;
  'auth.backToRegistration': string;
  'auth.enterCorporateEmail': string;
  'auth.corporateEmail': string;
  'auth.corporateEmailPlaceholder': string;
  'auth.continueWithSSO': string;
  'auth.backToLogin': string;
  'auth.termsOfService': string;
  'auth.privacyPolicy': string;
  'auth.errors.enterIdAndPassword': string;
  'auth.errors.invalidUserId': string;
  'auth.errors.fillAllFields': string;
  'auth.errors.passwordsDoNotMatch': string;
  'auth.errors.passwordTooShort': string;
  'auth.errors.passwordComplexity': string;
  'auth.errors.registrationFailed': string;
  'auth.errors.networkError': string;
  'auth.errors.enterVerificationCode': string;
  'auth.errors.verificationFailed': string;
  'auth.errors.googleLoginFailed': string;
  'auth.errors.invalidCorporateEmail': string;
  'auth.errors.ssoInitiationFailed': string;

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
  'dashboard.timeAgo.minutesAgo': string;
  'dashboard.timeAgo.hoursAgo': string;
  'dashboard.timeAgo.daysAgo': string;
  'dashboard.aria.openMenu': string;
  'dashboard.aria.notifications': string;
  'dashboard.notifications.title': string;
  'dashboard.notifications.markAllRead': string;
  'dashboard.notifications.empty': string;
  'dashboard.statusValues.normal': string;
  'dashboard.statusValues.ready': string;
  'dashboard.statusValues.connected': string;
  'dashboard.statusValues.disconnected': string;
  'dashboard.sources.documentCount': string;
  'dashboard.actions.knowledge.label': string;
  'dashboard.actions.knowledge.description': string;
  'dashboard.actions.mindmap.label': string;
  'dashboard.actions.mindmap.description': string;
  'dashboard.actions.documents.label': string;
  'dashboard.actions.documents.description': string;
  'dashboard.actions.analytics.label': string;
  'dashboard.actions.analytics.description': string;

  // Knowledge
  'knowledge.title': string;
  'knowledge.searchPlaceholder': string;
  'knowledge.askQuestion': string;
  'knowledge.noResults': string;
  'knowledge.sources': string;
  'knowledge.relevance': string;
  'knowledge.newConversation': string;
  'knowledge.conversationHistory': string;
  'knowledge.relatedDocuments': string;
  'knowledge.feedback.helpful': string;
  'knowledge.feedback.yes': string;
  'knowledge.feedback.no': string;
  'knowledge.feedback.thanks': string;
  'knowledge.chat.title': string;
  'knowledge.chat.subtitle': string;
  'knowledge.chat.startPrompt': string;
  'knowledge.chat.inputPlaceholder': string;
  'knowledge.chat.send': string;
  'knowledge.chat.quickPrompts.summarize': string;
  'knowledge.chat.quickPrompts.keyConcepts': string;
  'knowledge.chat.quickPrompts.showExamples': string;
  'knowledge.sidebar.chat': string;
  'knowledge.sidebar.documents': string;
  'knowledge.sidebar.webSources': string;
  'knowledge.sidebar.notes': string;
  'knowledge.sidebar.aiContent': string;
  'knowledge.sidebar.projects': string;
  'knowledge.sidebar.mindmap': string;
  'knowledge.sidebar.knowledgeGraph': string;
  'knowledge.sidebar.knowledgeBase': string;
  'knowledge.sidebar.settings': string;
  'knowledge.sidebar.logout': string;
  'knowledge.sidebar.admin': string;
  'knowledge.sidebar.dark': string;
  'knowledge.sidebar.light': string;
  'knowledge.notifications.title': string;
  'knowledge.notifications.markAllRead': string;
  'knowledge.notifications.empty': string;
  'knowledge.upload.fileAttach': string;
  'knowledge.upload.pasteText': string;

  // Mindmap
  'mindmap.title': string;
  'mindmap.createNew': string;
  'mindmap.addNode': string;
  'mindmap.deleteNode': string;
  'mindmap.editNode': string;
  'mindmap.sidebar.title': string;
  'mindmap.sidebar.subtitle': string;
  'mindmap.sidebar.newMindmap': string;
  'mindmap.sidebar.titlePlaceholder': string;
  'mindmap.sidebar.focusPlaceholder': string;
  'mindmap.sidebar.maxNodes': string;
  'mindmap.sidebar.generating': string;
  'mindmap.sidebar.generate': string;
  'mindmap.sidebar.cancel': string;
  'mindmap.sidebar.savedMindmaps': string;
  'mindmap.sidebar.noMindmaps': string;
  'mindmap.sidebar.deleteConfirm': string;
  'mindmap.panel.importance': string;
  'mindmap.panel.expand': string;
  'mindmap.panel.summarize': string;
  'mindmap.panel.sourceDocuments': string;
  'mindmap.panel.askPlaceholder': string;
  'mindmap.panel.ask': string;
  'mindmap.panel.generatingAnswer': string;
  'mindmap.panel.answer': string;
  'mindmap.panel.relatedConcepts': string;
  'mindmap.panel.noRelatedNodes': string;
  'mindmap.header.nodes': string;
  'mindmap.header.edges': string;
  'mindmap.header.processing': string;
  'mindmap.header.admin': string;
  'mindmap.header.logout': string;
  'mindmap.empty.title': string;
  'mindmap.empty.description': string;
  'mindmap.empty.generating': string;
  'mindmap.empty.generateAll': string;

  // Admin
  'admin.title': string;
  'admin.users': string;
  'admin.system': string;
  'admin.logs': string;
  'admin.menu': string;

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
