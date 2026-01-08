/**
 * SettingsPage Component
 *
 * ChatGPT-style settings page with sidebar navigation
 * Features:
 * - General settings (Appearance, Language)
 * - Notifications (mock)
 * - Security (mock)
 * - Account (mock)
 * - Subscription (with pricing tiers)
 */
import React, { useState, memo } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useTheme } from '../hooks/useTheme';
import { LanguageCode } from '../i18n/types';
import { Theme } from '../store/preferencesStore';

// Settings sections
type SettingsSection = 'general' | 'notifications' | 'security' | 'account' | 'subscription';

// Subscription plan types
interface SubscriptionPlan {
  id: string;
  name: string;
  price: string;
  priceNote?: string;
  features: string[];
  highlight?: boolean;
  badge?: string;
}

const subscriptionPlans: SubscriptionPlan[] = [
  {
    id: 'free',
    name: 'Free Tier',
    price: '$0',
    priceNote: 'forever',
    features: [
      'Up to 200 queries per month',
      'Product evaluation and validation',
      'Basic knowledge search',
      'Community support',
    ],
  },
  {
    id: 'standard',
    name: 'Standard',
    price: '$20',
    priceNote: 'per month',
    features: [
      'Up to 1,000 queries per month',
      'IMS Knowledge Search Service',
      'Technical documentation search',
      'Email support',
    ],
    highlight: true,
    badge: 'Popular',
  },
  {
    id: 'professional',
    name: 'Professional',
    price: '$200',
    priceNote: 'per month',
    features: [
      'Unlimited queries',
      'Source code-based technical search',
      'Implementation-level analysis',
      'Code-aware AI assistance',
      'Priority support',
    ],
  },
  {
    id: 'expert',
    name: 'Expert Service',
    price: '$2,000',
    priceNote: 'per engagement',
    features: [
      'Remote expert consulting',
      'Architecture reviews',
      'Root cause analysis',
      'Advanced troubleshooting',
      'Dedicated technical specialist',
    ],
    badge: 'Premium',
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    priceNote: 'contact us',
    features: [
      'High-volume query usage',
      'Dedicated/on-premise deployment',
      'Enhanced security & compliance',
      'SLA-backed support',
      'Custom integrations',
    ],
  },
];

// Section icons
const sectionIcons: Record<SettingsSection, string> = {
  general: '⚙️',
  notifications: '🔔',
  security: '🔒',
  account: '👤',
  subscription: '💳',
};

// Section labels (fallback)
const sectionLabels: Record<SettingsSection, string> = {
  general: 'General',
  notifications: 'Notifications',
  security: 'Security',
  account: 'Account',
  subscription: 'Subscription',
};

// Translation function type for components
type TFunc = (key: string) => string;

export const SettingsPage: React.FC = memo(() => {
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();
  const [activeSection, setActiveSection] = useState<SettingsSection>('general');
  const [currentPlan] = useState<string>('free'); // Mock current plan

  // Language options for inline toggle
  const languageOptions: { code: LanguageCode; label: string }[] = [
    { code: 'en', label: 'US English' },
    { code: 'ko', label: 'KR 한국어' },
    { code: 'ja', label: 'JP 日本語' },
  ];

  // Theme options for dropdown
  const themeOptions: { value: Theme; label: string }[] = [
    { value: 'light', label: t('settings.theme.light') || 'Light' },
    { value: 'dark', label: t('settings.theme.dark') || 'Dark' },
    { value: 'system', label: t('settings.theme.system') || 'System' },
  ];

  // Render section content
  const renderSectionContent = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSection
          language={language}
          setLanguage={setLanguage}
          theme={theme}
          setTheme={setTheme}
          languageOptions={languageOptions}
          themeOptions={themeOptions}
          t={t}
        />;
      case 'notifications':
        return <NotificationsSection t={t} />;
      case 'security':
        return <SecuritySection t={t} />;
      case 'account':
        return <AccountSection t={t} />;
      case 'subscription':
        return <SubscriptionSection currentPlan={currentPlan} t={t} />;
      default:
        return null;
    }
  };

  return (
    <>
      <style>{`
        .settings-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
        }

        .settings-modal {
          background: var(--color-bg-primary);
          border-radius: 16px;
          width: 100%;
          max-width: 900px;
          max-height: 90vh;
          display: flex;
          overflow: hidden;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }

        .settings-container {
          display: flex;
          width: 100%;
          height: 100%;
          min-height: 600px;
          background: var(--color-bg-primary);
          border-radius: 12px;
          overflow: hidden;
        }

        .settings-sidebar {
          width: 220px;
          background: var(--color-bg-secondary);
          border-right: 1px solid var(--color-border);
          padding: 16px 0;
          flex-shrink: 0;
        }

        .settings-sidebar-header {
          padding: 0 16px 16px;
          border-bottom: 1px solid var(--color-border);
          margin-bottom: 8px;
        }

        .settings-sidebar-title {
          font-size: 13px;
          font-weight: 600;
          color: var(--color-text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .settings-nav {
          list-style: none;
          margin: 0;
          padding: 0 8px;
        }

        .settings-nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 12px;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.15s ease;
          color: var(--color-text-secondary);
          font-size: 14px;
          margin-bottom: 2px;
        }

        .settings-nav-item:hover {
          background: var(--color-bg-hover);
          color: var(--color-text-primary);
        }

        .settings-nav-item.active {
          background: var(--color-primary-transparent, rgba(99, 102, 241, 0.1));
          color: var(--color-primary);
        }

        .settings-nav-icon {
          font-size: 18px;
          width: 24px;
          text-align: center;
        }

        .settings-content {
          flex: 1;
          padding: 24px 32px;
          overflow-y: auto;
        }

        .settings-section-title {
          font-size: 24px;
          font-weight: 600;
          color: var(--color-text-primary);
          margin-bottom: 24px;
        }

        .settings-group {
          margin-bottom: 32px;
        }

        .settings-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 0;
          border-bottom: 1px solid var(--color-border);
        }

        .settings-row:last-child {
          border-bottom: none;
        }

        .settings-label {
          font-size: 15px;
          font-weight: 500;
          color: var(--color-text-primary);
        }

        .settings-description {
          font-size: 13px;
          color: var(--color-text-secondary);
          margin-top: 4px;
        }

        .settings-control {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        /* Dropdown select */
        .settings-select {
          padding: 8px 32px 8px 12px;
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          color: var(--color-text-primary);
          font-size: 14px;
          cursor: pointer;
          appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M3 4.5L6 7.5L9 4.5'/%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 10px center;
          min-width: 120px;
        }

        .settings-select:hover {
          border-color: var(--color-border-focus);
        }

        .settings-select:focus {
          outline: none;
          border-color: var(--color-primary);
          box-shadow: 0 0 0 2px var(--color-primary-transparent, rgba(99, 102, 241, 0.2));
        }

        /* Inline language toggle */
        .language-toggle-group {
          display: flex;
          gap: 4px;
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          padding: 4px;
        }

        .language-toggle-btn {
          padding: 6px 12px;
          border: none;
          background: transparent;
          color: var(--color-text-secondary);
          font-size: 13px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
          white-space: nowrap;
        }

        .language-toggle-btn:hover {
          color: var(--color-text-primary);
          background: var(--color-bg-hover);
        }

        .language-toggle-btn.active {
          background: var(--color-primary);
          color: white;
        }

        .language-toggle-btn.active::before {
          content: '✓ ';
        }

        /* Toggle switch */
        .toggle-switch {
          position: relative;
          width: 44px;
          height: 24px;
          background: var(--color-bg-tertiary);
          border-radius: 12px;
          cursor: pointer;
          transition: background 0.2s ease;
        }

        .toggle-switch.active {
          background: var(--color-primary);
        }

        .toggle-switch::after {
          content: '';
          position: absolute;
          top: 2px;
          left: 2px;
          width: 20px;
          height: 20px;
          background: white;
          border-radius: 50%;
          transition: transform 0.2s ease;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
        }

        .toggle-switch.active::after {
          transform: translateX(20px);
        }

        /* Subscription cards */
        .subscription-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 16px;
          margin-top: 16px;
        }

        .subscription-card {
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 20px;
          transition: all 0.2s ease;
          position: relative;
        }

        .subscription-card:hover {
          border-color: var(--color-primary);
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
        }

        .subscription-card.highlight {
          border-color: var(--color-primary);
          background: linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-primary-transparent, rgba(99, 102, 241, 0.05)) 100%);
        }

        .subscription-card.current {
          border-color: var(--color-success);
        }

        .subscription-badge {
          position: absolute;
          top: -10px;
          right: 16px;
          background: var(--color-primary);
          color: white;
          font-size: 11px;
          font-weight: 600;
          padding: 4px 10px;
          border-radius: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .subscription-badge.current {
          background: var(--color-success);
        }

        .subscription-name {
          font-size: 16px;
          font-weight: 600;
          color: var(--color-text-primary);
          margin-bottom: 8px;
        }

        .subscription-price {
          font-size: 28px;
          font-weight: 700;
          color: var(--color-primary);
          margin-bottom: 4px;
        }

        .subscription-price-note {
          font-size: 12px;
          color: var(--color-text-secondary);
          margin-bottom: 16px;
        }

        .subscription-features {
          list-style: none;
          margin: 0;
          padding: 0;
        }

        .subscription-feature {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          font-size: 13px;
          color: var(--color-text-secondary);
          margin-bottom: 8px;
        }

        .subscription-feature::before {
          content: '✓';
          color: var(--color-success);
          font-weight: 600;
          flex-shrink: 0;
        }

        .subscription-btn {
          width: 100%;
          margin-top: 16px;
          padding: 10px 16px;
          border: 1px solid var(--color-border);
          background: var(--color-bg-primary);
          color: var(--color-text-primary);
          font-size: 14px;
          font-weight: 500;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .subscription-btn:hover {
          background: var(--color-bg-hover);
          border-color: var(--color-primary);
        }

        .subscription-btn.primary {
          background: var(--color-primary);
          border-color: var(--color-primary);
          color: white;
        }

        .subscription-btn.primary:hover {
          filter: brightness(1.1);
        }

        .subscription-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* Mock account info */
        .account-info {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px;
          background: var(--color-bg-secondary);
          border-radius: 12px;
          margin-bottom: 24px;
        }

        .account-avatar {
          width: 64px;
          height: 64px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--color-primary) 0%, #8b5cf6 100%);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          color: white;
          font-weight: 600;
        }

        .account-details {
          flex: 1;
        }

        .account-name {
          font-size: 18px;
          font-weight: 600;
          color: var(--color-text-primary);
        }

        .account-email {
          font-size: 14px;
          color: var(--color-text-secondary);
        }

        @media (max-width: 768px) {
          .settings-container {
            flex-direction: column;
            min-height: auto;
          }

          .settings-sidebar {
            width: 100%;
            border-right: none;
            border-bottom: 1px solid var(--color-border);
            padding: 12px 0;
          }

          .settings-nav {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
          }

          .settings-nav-item {
            padding: 8px 12px;
          }

          .settings-content {
            padding: 16px;
          }

          .subscription-grid {
            grid-template-columns: 1fr;
          }

          .language-toggle-group {
            flex-wrap: wrap;
          }
        }
      `}</style>

      <div className="settings-container">
        {/* Sidebar */}
        <div className="settings-sidebar">
          <div className="settings-sidebar-header">
            <span className="settings-sidebar-title">{t('settings.title') || 'Settings'}</span>
          </div>
          <ul className="settings-nav">
            {(['general', 'notifications', 'security', 'account', 'subscription'] as SettingsSection[]).map((section) => (
              <li
                key={section}
                className={`settings-nav-item ${activeSection === section ? 'active' : ''}`}
                onClick={() => setActiveSection(section)}
              >
                <span className="settings-nav-icon">{sectionIcons[section]}</span>
                <span>{t(`settings.nav.${section}`) || sectionLabels[section]}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Content */}
        <div className="settings-content">
          {renderSectionContent()}
        </div>
      </div>
    </>
  );
});

// General Section Component
interface GeneralSectionProps {
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  languageOptions: { code: LanguageCode; label: string }[];
  themeOptions: { value: Theme; label: string }[];
  t: TFunc;
}

const GeneralSection: React.FC<GeneralSectionProps> = memo(({
  language,
  setLanguage,
  theme,
  setTheme,
  languageOptions,
  themeOptions,
  t,
}) => (
  <div>
    <h2 className="settings-section-title">{t('settings.general.title') || 'General'}</h2>

    <div className="settings-group">
      {/* Appearance */}
      <div className="settings-row">
        <div>
          <div className="settings-label">{t('settings.general.appearance') || 'Appearance'}</div>
          <div className="settings-description">{t('settings.general.appearanceDesc') || 'Choose your preferred color theme'}</div>
        </div>
        <div className="settings-control">
          <select
            className="settings-select"
            value={theme}
            onChange={(e) => setTheme(e.target.value as Theme)}
          >
            {themeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Language */}
      <div className="settings-row">
        <div>
          <div className="settings-label">{t('settings.general.language') || 'Language'}</div>
          <div className="settings-description">{t('settings.general.languageDesc') || 'Select your display language'}</div>
        </div>
        <div className="settings-control">
          <div className="language-toggle-group">
            {languageOptions.map((opt) => (
              <button
                key={opt.code}
                className={`language-toggle-btn ${language === opt.code ? 'active' : ''}`}
                onClick={() => setLanguage(opt.code)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  </div>
));

// Notifications Section (Mock)
const NotificationsSection: React.FC<{ t: TFunc }> = memo(({ t }) => {
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [pushNotifications, setPushNotifications] = useState(false);
  const [weeklyDigest, setWeeklyDigest] = useState(true);

  return (
    <div>
      <h2 className="settings-section-title">{t('settings.notifications.title') || 'Notifications'}</h2>

      <div className="settings-group">
        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.notifications.email') || 'Email Notifications'}</div>
            <div className="settings-description">{t('settings.notifications.emailDesc') || 'Receive email updates about your account'}</div>
          </div>
          <div
            className={`toggle-switch ${emailNotifications ? 'active' : ''}`}
            onClick={() => setEmailNotifications(!emailNotifications)}
          />
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.notifications.push') || 'Push Notifications'}</div>
            <div className="settings-description">{t('settings.notifications.pushDesc') || 'Receive browser push notifications'}</div>
          </div>
          <div
            className={`toggle-switch ${pushNotifications ? 'active' : ''}`}
            onClick={() => setPushNotifications(!pushNotifications)}
          />
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.notifications.weekly') || 'Weekly Digest'}</div>
            <div className="settings-description">{t('settings.notifications.weeklyDesc') || 'Get a summary of your activity'}</div>
          </div>
          <div
            className={`toggle-switch ${weeklyDigest ? 'active' : ''}`}
            onClick={() => setWeeklyDigest(!weeklyDigest)}
          />
        </div>
      </div>
    </div>
  );
});

// Security Section (Mock)
const SecuritySection: React.FC<{ t: TFunc }> = memo(({ t }) => {
  const [twoFactor, setTwoFactor] = useState(false);

  return (
    <div>
      <h2 className="settings-section-title">{t('settings.security.title') || 'Security'}</h2>

      <div className="settings-group">
        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.security.password') || 'Password'}</div>
            <div className="settings-description">{t('settings.security.passwordDesc') || 'Last changed 30 days ago'}</div>
          </div>
          <button className="subscription-btn" style={{ width: 'auto' }}>
            {t('settings.security.changePassword') || 'Change Password'}
          </button>
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.security.twoFactor') || 'Two-Factor Authentication'}</div>
            <div className="settings-description">{t('settings.security.twoFactorDesc') || 'Add an extra layer of security'}</div>
          </div>
          <div
            className={`toggle-switch ${twoFactor ? 'active' : ''}`}
            onClick={() => setTwoFactor(!twoFactor)}
          />
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">{t('settings.security.sessions') || 'Active Sessions'}</div>
            <div className="settings-description">{t('settings.security.sessionsDesc') || '2 active sessions'}</div>
          </div>
          <button className="subscription-btn" style={{ width: 'auto' }}>
            {t('settings.security.manageSessions') || 'Manage'}
          </button>
        </div>
      </div>
    </div>
  );
});

// Account Section (Mock)
const AccountSection: React.FC<{ t: TFunc }> = memo(({ t }) => (
  <div>
    <h2 className="settings-section-title">{t('settings.account.title') || 'Account'}</h2>

    <div className="account-info">
      <div className="account-avatar">JD</div>
      <div className="account-details">
        <div className="account-name">John Doe</div>
        <div className="account-email">john.doe@example.com</div>
      </div>
      <button className="subscription-btn" style={{ width: 'auto' }}>
        {t('settings.account.editProfile') || 'Edit Profile'}
      </button>
    </div>

    <div className="settings-group">
      <div className="settings-row">
        <div>
          <div className="settings-label">{t('settings.account.email') || 'Email Address'}</div>
          <div className="settings-description">john.doe@example.com</div>
        </div>
        <button className="subscription-btn" style={{ width: 'auto' }}>
          {t('settings.account.change') || 'Change'}
        </button>
      </div>

      <div className="settings-row">
        <div>
          <div className="settings-label">{t('settings.account.timezone') || 'Timezone'}</div>
          <div className="settings-description">Asia/Tokyo (UTC+9)</div>
        </div>
        <select className="settings-select">
          <option>Asia/Tokyo</option>
          <option>Asia/Seoul</option>
          <option>America/New_York</option>
          <option>Europe/London</option>
        </select>
      </div>

      <div className="settings-row">
        <div>
          <div className="settings-label" style={{ color: 'var(--color-error)' }}>
            {t('settings.account.deleteAccount') || 'Delete Account'}
          </div>
          <div className="settings-description">{t('settings.account.deleteDesc') || 'Permanently delete your account and data'}</div>
        </div>
        <button className="subscription-btn" style={{ width: 'auto', borderColor: 'var(--color-error)', color: 'var(--color-error)' }}>
          {t('settings.account.delete') || 'Delete'}
        </button>
      </div>
    </div>
  </div>
));

// Subscription Section
const SubscriptionSection: React.FC<{ currentPlan: string; t: TFunc }> = memo(({ currentPlan, t }) => (
  <div>
    <h2 className="settings-section-title">{t('settings.subscription.title') || 'Subscription'}</h2>

    <p style={{ color: 'var(--color-text-secondary)', marginBottom: '24px' }}>
      {t('settings.subscription.description') || 'Choose the plan that best fits your needs. Upgrade or downgrade at any time.'}
    </p>

    <div className="subscription-grid">
      {subscriptionPlans.map((plan) => (
        <div
          key={plan.id}
          className={`subscription-card ${plan.highlight ? 'highlight' : ''} ${currentPlan === plan.id ? 'current' : ''}`}
        >
          {currentPlan === plan.id && (
            <span className="subscription-badge current">{t('settings.subscription.current') || 'Current'}</span>
          )}
          {plan.badge && currentPlan !== plan.id && (
            <span className="subscription-badge">{plan.badge}</span>
          )}

          <div className="subscription-name">{plan.name}</div>
          <div className="subscription-price">{plan.price}</div>
          <div className="subscription-price-note">{plan.priceNote}</div>

          <ul className="subscription-features">
            {plan.features.map((feature, idx) => (
              <li key={idx} className="subscription-feature">{feature}</li>
            ))}
          </ul>

          <button
            className={`subscription-btn ${plan.highlight && currentPlan !== plan.id ? 'primary' : ''}`}
            disabled={currentPlan === plan.id}
          >
            {currentPlan === plan.id
              ? (t('settings.subscription.currentPlan') || 'Current Plan')
              : plan.id === 'enterprise'
                ? (t('settings.subscription.contactSales') || 'Contact Sales')
                : (t('settings.subscription.upgrade') || 'Upgrade')
            }
          </button>
        </div>
      ))}
    </div>
  </div>
));

SettingsPage.displayName = 'SettingsPage';

export default SettingsPage;
