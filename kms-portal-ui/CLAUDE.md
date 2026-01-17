# Frontend CLAUDE.md

React 프론트엔드 상세 가이드입니다.

## Tech Stack

- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **State Management**: Zustand
- **Styling**: CSS Modules + CSS Variables
- **i18n**: Custom context-based (en, ko, ja)
- **HTTP Client**: Axios

## Directory Structure

```
src/
├── main.tsx                  # React entry point
├── App.tsx                   # Main app with routing (50+ routes)
├── pages/                    # Route components (15+ pages)
│   ├── LoginPage.tsx
│   ├── HomePage.tsx
│   ├── AdminDashboardPage.tsx
│   ├── KnowledgeBasePage.tsx
│   ├── DocumentsPage.tsx
│   ├── IMSPage.tsx
│   ├── FAQPage.tsx
│   ├── AIStudioPage.tsx
│   ├── SettingsPage.tsx
│   └── improvements/         # Enhancement workflow
│       ├── SubmitImprovementPage.tsx
│       ├── ImprovementDetailPage.tsx
│       └── ImprovementsPage.tsx
├── components/               # Reusable UI
│   ├── AgentChat/            # AI chat interface
│   │   ├── AgentChat.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── MessageContent.tsx
│   │   ├── IMSCredentialsModal.tsx
│   │   └── hooks/
│   │       ├── useStreamingChat.ts
│   │       ├── useFileAttachment.ts
│   │       └── useUrlAttachment.ts
│   ├── admin/                # Admin components
│   │   ├── UserManagementTable.tsx
│   │   ├── UserDetailsModal.tsx
│   │   └── enhance/          # Enhancement management
│   │       ├── EnhanceRequestsTable.tsx
│   │       ├── EnhanceDetailModal.tsx
│   │       ├── AgentQueueMonitor.tsx
│   │       └── useEnhanceRequests.ts
│   ├── auth/                 # Authentication
│   │   ├── LoginForm.tsx
│   │   ├── RegisterForm.tsx
│   │   ├── SSOForm.tsx
│   │   └── GoogleLoginButton.tsx
│   ├── guards/               # Route guards
│   │   ├── AuthGuard.tsx
│   │   └── PublicGuard.tsx
│   ├── TracePanel/           # Execution trace visualization
│   │   ├── TracePanel.tsx
│   │   ├── DAGView.tsx
│   │   ├── TimelineView.tsx
│   │   └── EvaluationsView.tsx
│   ├── Sidebar.tsx           # Navigation sidebar
│   ├── Header.tsx            # Page header
│   ├── ConversationSidebar.tsx
│   └── ThemeToggle.tsx       # Dark/light theme
├── features/                 # Feature modules
│   └── ims/                  # IMS feature
│       ├── components/
│       │   ├── IMSSearchBar.tsx
│       │   ├── IMSSearchResults.tsx
│       │   ├── IMSTableView.tsx
│       │   ├── IMSCardView.tsx
│       │   ├── IMSGraphView.tsx
│       │   ├── IMSProgressTracker.tsx
│       │   └── IMSAIAssistant.tsx
│       ├── services/
│       │   └── ims-api.ts
│       ├── store/
│       │   └── imsStore.ts
│       ├── hooks/
│       │   └── useSSEStream.ts
│       └── types/
├── store/                    # Zustand state (9 stores)
│   ├── authStore.ts          # Authentication state
│   ├── conversationStore.ts  # Conversation state
│   ├── apiKeyStore.ts        # API key management
│   ├── traceStore.ts         # Execution trace state
│   ├── contextStore.ts       # Context management
│   ├── artifactStore.ts      # Artifact handling
│   ├── preferencesStore.ts   # User preferences
│   └── uiStore.ts            # UI state
├── hooks/                    # Custom React hooks
│   ├── useAuth.ts
│   ├── useTheme.ts
│   ├── useTranslation.ts
│   ├── useSessionRefresh.ts
│   └── usePageContext.ts
├── api/                      # Backend API clients
│   ├── client.ts             # Axios HTTP client
│   ├── agent.api.ts
│   ├── auth.api.ts
│   ├── conversation.api.ts
│   ├── improvements.api.ts
│   ├── faq.api.ts
│   └── types.ts
├── i18n/                     # Internationalization
│   ├── I18nContext.tsx
│   ├── index.ts
│   └── locales/
│       ├── en/               # English (10 JSON files)
│       │   ├── common.json
│       │   ├── auth.json
│       │   ├── portal.json
│       │   ├── studio.json
│       │   ├── knowledge.json
│       │   ├── ims.json
│       │   ├── improvements.json
│       │   ├── faq.json
│       │   ├── settings.json
│       │   └── mindmap.json
│       ├── ko/               # Korean
│       └── ja/               # Japanese
├── layouts/                  # Page layouts
│   ├── MainLayout.tsx        # Authenticated layout
│   └── AuthLayout.tsx        # Auth pages layout
├── styles/                   # Global styles
│   ├── index.css
│   └── themes.css            # Theme definitions
├── config/                   # Configuration
│   └── constants.ts
├── types/                    # TypeScript types
├── services/                 # Utility services
├── providers/                # React providers
└── mocks/                    # MSW mock handlers
    ├── browser.ts
    └── handlers/
```

## Key Components

### AgentChat (`components/AgentChat/`)
AI 에이전트와의 채팅 인터페이스
- SSE 기반 스트리밍 응답
- 파일/URL 첨부 지원
- IMS 자격 증명 모달

### TracePanel (`components/TracePanel/`)
에이전트 실행 추적 시각화
- DAG 뷰: 작업 의존성 그래프
- Timeline 뷰: 실행 순서
- Evaluations 뷰: 결과 평가

### Zustand Stores

| Store | 용도 |
|-------|------|
| `authStore` | 로그인 상태, 사용자 정보 |
| `conversationStore` | 대화 목록, 현재 대화 |
| `traceStore` | 에이전트 실행 추적 |
| `uiStore` | 사이드바 상태, 모달 등 |
| `preferencesStore` | 사용자 설정 |

## Commands

```bash
npm install          # Install dependencies
npm run dev          # Dev server (port 3000)
npm run build        # Production build
npm run test:run     # Run tests
npm run lint         # ESLint check
npm run preview      # Preview production build
```

## Adding New Page

1. `pages/` 에 페이지 컴포넌트 생성
2. `App.tsx` 에 라우트 추가
3. `i18n/locales/*/` 에 번역 추가 (en, ko, ja)
4. `components/Sidebar.tsx` 에 네비게이션 추가

```tsx
// pages/MyPage.tsx
import { useTranslation } from '../hooks/useTranslation';

export const MyPage = () => {
  const { t } = useTranslation();

  return (
    <div>
      <h1>{t('myPage.title')}</h1>
    </div>
  );
};
```

```tsx
// App.tsx에 추가
<Route path="/my-page" element={<MyPage />} />
```

## Adding New Component

1. `components/` 에 컴포넌트 생성
2. Props 인터페이스 정의
3. CSS Module 또는 inline styles 사용

```tsx
// components/MyComponent.tsx
interface MyComponentProps {
  title: string;
  onClick?: () => void;
}

export const MyComponent = ({ title, onClick }: MyComponentProps) => {
  return (
    <div
      onClick={onClick}
      style={{
        padding: 'var(--spacing-md)',
        background: 'var(--bg-secondary)'
      }}
    >
      {title}
    </div>
  );
};
```

## Styling Guidelines

### CSS Variables (themes.css)
```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --text-primary: #333333;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
}

[data-theme="dark"] {
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --text-primary: #ffffff;
}
```

### Theme Support
- 모든 색상은 CSS 변수 사용
- Dark/Light 테마 모두 테스트 필요
- `ThemeToggle` 컴포넌트로 전환

## i18n Guidelines

번역 파일 구조:
```
locales/
├── en/
│   ├── common.json    # 공통 텍스트
│   ├── auth.json      # 인증 관련
│   └── ...
├── ko/
└── ja/
```

사용법:
```tsx
import { useTranslation } from '../hooks/useTranslation';

const { t } = useTranslation();
<span>{t('common.save')}</span>
```

**UI 변경 시 반드시 3개 언어 모두 번역 추가!**

## API Client Pattern

```tsx
// api/my.api.ts
import { client } from './client';

export const myApi = {
  getItems: () => client.get('/api/v1/items'),
  createItem: (data: ItemData) => client.post('/api/v1/items', data),
};
```

## Troubleshooting

### Build fails
```bash
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Type errors
```bash
npm run lint
npx tsc --noEmit
```

### API connection issues
- Check `vite.config.ts` proxy settings
- Verify backend is running on port 9000

## Key Files Reference

| 작업 | 파일 |
|------|------|
| 새 페이지 추가 | `pages/*.tsx`, `App.tsx` |
| 컴포넌트 추가 | `components/*.tsx` |
| 상태 관리 | `store/*.ts` |
| API 연동 | `api/*.ts` |
| 번역 추가 | `i18n/locales/*/` |
| 테마 수정 | `styles/themes.css` |
| 라우트 설정 | `App.tsx` |
