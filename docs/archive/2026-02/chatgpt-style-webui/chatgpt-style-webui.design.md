# Design: ChatGPT-Style Chat WebUI

**Feature**: chatgpt-style-webui
**Created**: 2026-02-03
**Status**: Design
**PDCA Phase**: Design
**Plan Reference**: [chatgpt-style-webui.plan.md](../../01-plan/features/chatgpt-style-webui.plan.md)

---

## 1. Component Architecture

### 1.1 Component Hierarchy

```
OpenFrameRAGPage.tsx
├── ChatContainer
│   ├── MessageList
│   │   └── ChatMessage (ChatGPT-style)
│   │       ├── MessageAvatar
│   │       ├── MessageContent (existing, enhanced)
│   │       │   ├── MarkdownRenderer (react-markdown)
│   │       │   │   ├── HeaderRenderer (##, ###)
│   │       │   │   ├── ParagraphRenderer
│   │       │   │   ├── CodeBlockRenderer (enhanced)
│   │       │   │   ├── ListRenderer
│   │       │   │   └── TableRenderer
│   │       │   └── TypingCursor (streaming indicator)
│   │       └── SourcesAccordion (new)
│   │           ├── AccordionHeader
│   │           └── AccordionContent
│   │               └── SourceCard[]
│   └── ChatInput
│       ├── TextArea
│       └── SendButton
└── StreamingHook (useStreamingChat, enhanced)
```

### 1.2 File Structure

```
kms-portal-ui/src/
├── components/AgentChat/
│   ├── MessageContent.tsx        # Enhanced - add syntax highlighting
│   ├── SourcesAccordion.tsx      # NEW - collapsible sources
│   ├── TypingCursor.tsx          # NEW - typing animation
│   └── hooks/
│       └── useStreamingChat.ts   # Enhanced - token buffering
├── pages/
│   └── OpenFrameRAGPage.tsx      # Enhanced - ChatGPT styling
└── styles/
    └── chatgpt-style.css         # NEW - ChatGPT-specific styles
```

---

## 2. Detailed Component Specifications

### 2.1 MessageContent Enhancement

**Current State**: `MessageContent.tsx` (lines 52-157)
- Already uses `react-markdown` + `remarkGfm`
- Has custom renderers for tables, code, links, headers

**Enhancements Required**:

1. **Add Syntax Highlighting**

```typescript
// Add to imports
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css'; // dark theme

// Update ReactMarkdown
<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  rehypePlugins={[rehypeHighlight]}  // ADD THIS
  components={{...}}
>
```

2. **Code Block Enhancement**

```typescript
code: ({ className, children, node }) => {
  const match = /language-(\w+)/.exec(className || '');
  const isInline = !match && !String(children).includes('\n');

  if (isInline) {
    return <code className="chatgpt-inline-code">{children}</code>;
  }

  const language = match ? match[1] : 'text';
  const codeString = String(children).replace(/\n$/, '');

  return (
    <pre className="chatgpt-code-block">
      <div className="chatgpt-code-header">
        <span className="chatgpt-code-lang">{language}</span>
        <CopyButton text={codeString} />
      </div>
      <code className={`hljs language-${language}`}>
        {codeString}
      </code>
    </pre>
  );
};
```

### 2.2 SourcesAccordion Component (New)

**Purpose**: RAG 소스를 접기/펼치기 UI로 분리 표시

```typescript
// components/AgentChat/SourcesAccordion.tsx

interface SourcesAccordionProps {
  sources: RAGSource[];
  defaultOpen?: boolean;
}

interface RAGSource {
  title: string;
  content: string;
  score: number;
  product?: string;
  document?: string;
}

export const SourcesAccordion: React.FC<SourcesAccordionProps> = ({
  sources,
  defaultOpen = false
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const { t } = useTranslation();

  if (!sources || sources.length === 0) return null;

  return (
    <div className="sources-accordion">
      <button
        className="sources-accordion-header"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <ChevronIcon direction={isOpen ? 'down' : 'right'} />
        <span>{t('chat.sources')} ({sources.length})</span>
      </button>

      {isOpen && (
        <div className="sources-accordion-content">
          {sources.map((source, index) => (
            <SourceCard key={index} source={source} />
          ))}
        </div>
      )}
    </div>
  );
};
```

### 2.3 TypingCursor Component (New)

**Purpose**: 스트리밍 중 타이핑 효과 표시

```typescript
// components/AgentChat/TypingCursor.tsx

interface TypingCursorProps {
  isStreaming: boolean;
}

export const TypingCursor: React.FC<TypingCursorProps> = ({ isStreaming }) => {
  if (!isStreaming) return null;

  return <span className="typing-cursor" aria-hidden="true">▌</span>;
};
```

### 2.4 useStreamingChat Hook Enhancement

**Current Issue**: 응답이 한 번에 덤프됨
**Solution**: 토큰 버퍼링 + 점진적 렌더링

```typescript
// hooks/useStreamingChat.ts - Enhanced

interface StreamingState {
  content: string;
  isStreaming: boolean;
  buffer: string[];
  renderQueue: string[];
}

const useStreamingChat = () => {
  const [state, setState] = useState<StreamingState>({
    content: '',
    isStreaming: false,
    buffer: [],
    renderQueue: [],
  });

  // Token-level rendering with RAF
  const processTokenQueue = useCallback(() => {
    if (state.renderQueue.length === 0) return;

    requestAnimationFrame(() => {
      setState(prev => {
        const nextToken = prev.renderQueue[0];
        return {
          ...prev,
          content: prev.content + nextToken,
          renderQueue: prev.renderQueue.slice(1),
        };
      });
    });
  }, []);

  // SSE event handler with buffering
  const handleSSEToken = useCallback((token: string) => {
    setState(prev => ({
      ...prev,
      buffer: [...prev.buffer, token],
      renderQueue: [...prev.renderQueue, token],
    }));
  }, []);

  // Code block safety: detect incomplete blocks
  const isCodeBlockIncomplete = useCallback((content: string) => {
    const codeBlockStarts = (content.match(/```/g) || []).length;
    return codeBlockStarts % 2 !== 0;
  }, []);

  return {
    content: state.content,
    isStreaming: state.isStreaming,
    isCodeBlockIncomplete: isCodeBlockIncomplete(state.content),
    // ... other methods
  };
};
```

---

## 3. CSS Design Specifications

### 3.1 ChatGPT Style Variables

```css
/* styles/chatgpt-style.css */

:root {
  /* ChatGPT Color Palette */
  --chatgpt-bg-primary: #ffffff;
  --chatgpt-bg-secondary: #f7f7f8;
  --chatgpt-bg-tertiary: #ececf1;
  --chatgpt-text-primary: #0d0d0d;
  --chatgpt-text-secondary: #6e6e80;
  --chatgpt-border: rgba(0, 0, 0, 0.1);

  /* Code Block Theme */
  --chatgpt-code-bg: #1e1e1e;
  --chatgpt-code-header-bg: #2d2d2d;
  --chatgpt-code-text: #d4d4d4;

  /* Typography */
  --chatgpt-font-family: 'Söhne', ui-sans-serif, system-ui, sans-serif;
  --chatgpt-font-mono: 'Söhne Mono', 'Menlo', 'Monaco', monospace;
  --chatgpt-line-height: 1.75;
  --chatgpt-content-width: 768px;

  /* Spacing */
  --chatgpt-spacing-xs: 4px;
  --chatgpt-spacing-sm: 8px;
  --chatgpt-spacing-md: 16px;
  --chatgpt-spacing-lg: 24px;
  --chatgpt-spacing-xl: 32px;
}

[data-theme="dark"] {
  --chatgpt-bg-primary: #212121;
  --chatgpt-bg-secondary: #2f2f2f;
  --chatgpt-bg-tertiary: #444654;
  --chatgpt-text-primary: #ececf1;
  --chatgpt-text-secondary: #8e8ea0;
  --chatgpt-border: rgba(255, 255, 255, 0.1);
}
```

### 3.2 Message Container Styles

```css
/* Message container - ChatGPT style */
.chatgpt-message {
  display: flex;
  flex-direction: column;
  padding: var(--chatgpt-spacing-lg) 0;
  border-bottom: 1px solid var(--chatgpt-border);
}

.chatgpt-message-content {
  max-width: var(--chatgpt-content-width);
  margin: 0 auto;
  width: 100%;
  padding: 0 var(--chatgpt-spacing-lg);
}

/* User message - right aligned, no avatar */
.chatgpt-message-user {
  background: var(--chatgpt-bg-secondary);
}

/* Assistant message - left aligned with avatar */
.chatgpt-message-assistant {
  background: var(--chatgpt-bg-primary);
}
```

### 3.3 Typography Styles

```css
/* Paragraph spacing - ChatGPT style */
.chatgpt-markdown p {
  margin-bottom: var(--chatgpt-spacing-md);
  line-height: var(--chatgpt-line-height);
  color: var(--chatgpt-text-primary);
}

.chatgpt-markdown p:last-child {
  margin-bottom: 0;
}

/* Headers - clear hierarchy */
.chatgpt-markdown h1 {
  font-size: 1.875rem;
  font-weight: 600;
  margin: var(--chatgpt-spacing-xl) 0 var(--chatgpt-spacing-md);
  line-height: 1.3;
}

.chatgpt-markdown h2 {
  font-size: 1.5rem;
  font-weight: 600;
  margin: var(--chatgpt-spacing-lg) 0 var(--chatgpt-spacing-sm);
  line-height: 1.4;
  border-bottom: 1px solid var(--chatgpt-border);
  padding-bottom: var(--chatgpt-spacing-sm);
}

.chatgpt-markdown h3 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: var(--chatgpt-spacing-md) 0 var(--chatgpt-spacing-xs);
  line-height: 1.5;
}

/* Bold text for emphasis */
.chatgpt-markdown strong {
  font-weight: 600;
  color: var(--chatgpt-text-primary);
}
```

### 3.4 Code Block Styles

```css
/* Inline code - ChatGPT style */
.chatgpt-inline-code {
  font-family: var(--chatgpt-font-mono);
  font-size: 0.875em;
  background: var(--chatgpt-bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--chatgpt-text-primary);
}

/* Code block - dark theme */
.chatgpt-code-block {
  background: var(--chatgpt-code-bg);
  border-radius: 8px;
  margin: var(--chatgpt-spacing-md) 0;
  overflow: hidden;
}

.chatgpt-code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--chatgpt-spacing-sm) var(--chatgpt-spacing-md);
  background: var(--chatgpt-code-header-bg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.chatgpt-code-lang {
  font-family: var(--chatgpt-font-mono);
  font-size: 0.75rem;
  color: #8e8ea0;
  text-transform: lowercase;
}

.chatgpt-code-block pre {
  margin: 0;
  padding: var(--chatgpt-spacing-md);
  overflow-x: auto;
}

.chatgpt-code-block code {
  font-family: var(--chatgpt-font-mono);
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--chatgpt-code-text);
}

/* Copy button */
.chatgpt-code-copy {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: #8e8ea0;
  cursor: pointer;
  font-size: 0.75rem;
  border-radius: 4px;
  transition: all 0.2s;
}

.chatgpt-code-copy:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

.chatgpt-code-copy.copied {
  color: #10a37f;
}
```

### 3.5 List Styles

```css
/* Unordered list - ChatGPT style */
.chatgpt-markdown ul {
  list-style: disc;
  padding-left: var(--chatgpt-spacing-lg);
  margin: var(--chatgpt-spacing-sm) 0;
}

.chatgpt-markdown ol {
  list-style: decimal;
  padding-left: var(--chatgpt-spacing-lg);
  margin: var(--chatgpt-spacing-sm) 0;
}

.chatgpt-markdown li {
  margin-bottom: var(--chatgpt-spacing-xs);
  line-height: var(--chatgpt-line-height);
}

/* Nested lists */
.chatgpt-markdown ul ul,
.chatgpt-markdown ol ol {
  margin: var(--chatgpt-spacing-xs) 0;
}
```

### 3.6 Sources Accordion Styles

```css
/* Sources Accordion - collapsible */
.sources-accordion {
  margin-top: var(--chatgpt-spacing-lg);
  border-top: 1px solid var(--chatgpt-border);
  padding-top: var(--chatgpt-spacing-md);
}

.sources-accordion-header {
  display: flex;
  align-items: center;
  gap: var(--chatgpt-spacing-sm);
  padding: var(--chatgpt-spacing-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--chatgpt-text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  transition: color 0.2s;
}

.sources-accordion-header:hover {
  color: var(--chatgpt-text-primary);
}

.sources-accordion-content {
  padding: var(--chatgpt-spacing-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--chatgpt-spacing-sm);
}

/* Source Card */
.source-card {
  padding: var(--chatgpt-spacing-md);
  background: var(--chatgpt-bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--chatgpt-border);
}

.source-card-title {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--chatgpt-text-primary);
  margin-bottom: var(--chatgpt-spacing-xs);
}

.source-card-content {
  font-size: 0.8125rem;
  color: var(--chatgpt-text-secondary);
  line-height: 1.5;
}

.source-card-meta {
  display: flex;
  gap: var(--chatgpt-spacing-md);
  margin-top: var(--chatgpt-spacing-sm);
  font-size: 0.75rem;
  color: var(--chatgpt-text-secondary);
}
```

### 3.7 Typing Cursor Animation

```css
/* Typing cursor - blink animation */
.typing-cursor {
  display: inline-block;
  color: var(--chatgpt-text-primary);
  animation: blink 1s step-end infinite;
  margin-left: 2px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
```

---

## 4. Streaming Implementation

### 4.1 Token Buffer Strategy

```
SSE Token Stream
    │
    ▼
┌─────────────────┐
│   Token Buffer  │ ← Accumulate tokens
└────────┬────────┘
         │
         ▼ (requestAnimationFrame)
┌─────────────────┐
│  Render Queue   │ ← Rate-limited rendering
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ React State     │ ← content += token
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Markdown Render │ ← react-markdown
└─────────────────┘
```

### 4.2 Code Block Safety

**Problem**: 스트리밍 중 불완전한 코드 블록이 깨짐

**Solution**:

```typescript
// Detect incomplete code block
const isCodeBlockIncomplete = (content: string): boolean => {
  const matches = content.match(/```/g) || [];
  return matches.length % 2 !== 0;
};

// During streaming, show raw text if incomplete
const renderContent = (content: string, isStreaming: boolean) => {
  if (isStreaming && isCodeBlockIncomplete(content)) {
    // Find last complete block boundary
    const lastCompleteIndex = content.lastIndexOf('\n```\n');
    if (lastCompleteIndex > 0) {
      const completeContent = content.substring(0, lastCompleteIndex + 5);
      const pendingContent = content.substring(lastCompleteIndex + 5);

      return (
        <>
          <MarkdownRenderer content={completeContent} />
          <pre className="pending-code">{pendingContent}</pre>
        </>
      );
    }
  }

  return <MarkdownRenderer content={content} />;
};
```

---

## 5. Integration with OpenFrameRAGPage

### 5.1 Message Rendering Update

```typescript
// OpenFrameRAGPage.tsx - Message rendering section

const renderMessage = (message: ChatMessage) => {
  const isUser = message.role === 'user';

  return (
    <div
      key={message.id}
      className={`chatgpt-message chatgpt-message-${message.role}`}
    >
      <div className="chatgpt-message-content">
        {!isUser && (
          <div className="chatgpt-message-avatar">
            <OpenFrameLogo size={24} />
          </div>
        )}

        <div className="chatgpt-message-body">
          <MessageContent content={message.content} />

          {/* Typing cursor during streaming */}
          {message.isStreaming && <TypingCursor isStreaming={true} />}

          {/* RAG Sources - separate section */}
          {!isUser && message.sources?.documents && (
            <SourcesAccordion
              sources={message.sources.documents}
              defaultOpen={false}
            />
          )}

          {/* Learning LLM Badge */}
          {!isUser && message.sources?.learning_llm && (
            <div className="learning-llm-badge">
              <span>{message.sources.learning_llm.model}</span>
              <span className="confidence">
                {Math.round(message.sources.learning_llm.confidence * 100)}%
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
```

---

## 6. Dependencies

### 6.1 Already Installed

| Package | Version | Status |
|---------|---------|--------|
| `react-markdown` | ^9.0.1 | Installed |
| `remark-gfm` | ^4.0.0 | Installed |
| `rehype-highlight` | ^7.0.0 | Installed |

### 6.2 Additional Required

```json
{
  "dependencies": {
    "highlight.js": "^11.9.0"
  }
}
```

**Install Command**:
```bash
cd kms-portal-ui && npm install highlight.js
```

---

## 7. Implementation Checklist

### Phase 1: Core Rendering (P0)

- [ ] Add `rehypeHighlight` to `MessageContent.tsx`
- [ ] Import highlight.js dark theme CSS
- [ ] Update code block renderer with new styles
- [ ] Create `chatgpt-style.css` with CSS variables
- [ ] Update paragraph/header spacing

### Phase 2: Streaming UX (P0)

- [ ] Create `TypingCursor.tsx` component
- [ ] Enhance `useStreamingChat.ts` with token buffering
- [ ] Implement code block safety (incomplete block handling)
- [ ] Add `requestAnimationFrame` based rendering

### Phase 3: RAG Integration (P1)

- [ ] Create `SourcesAccordion.tsx` component
- [ ] Add accordion styles to CSS
- [ ] Integrate with `OpenFrameRAGPage.tsx`
- [ ] Add i18n keys for sources section (en, ko, ja)

### Phase 4: Polish (P1)

- [ ] Test dark/light theme compatibility
- [ ] Test responsive design (mobile)
- [ ] Verify syntax highlighting for all languages
- [ ] Performance optimization (React.memo)

---

## 8. Acceptance Criteria

| Criteria | Test Method |
|----------|-------------|
| ChatGPT와 시각적으로 구분 불가 | 스크린샷 비교 |
| 응답이 점진적 타이핑 느낌 | 스트리밍 테스트 |
| 코드 블록 구문 강조 정상 | Python, JS, JCL 코드 테스트 |
| 소스 섹션 접기/펼치기 동작 | 클릭 테스트 |
| 다크/라이트 테마 모두 지원 | 테마 전환 테스트 |
| 문단 간격 ChatGPT 스타일 | 스크린샷 비교 |

---

## 9. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `MessageContent.tsx` | MODIFY | Add rehypeHighlight, update styles |
| `SourcesAccordion.tsx` | CREATE | Collapsible sources component |
| `TypingCursor.tsx` | CREATE | Streaming cursor animation |
| `useStreamingChat.ts` | MODIFY | Token buffering, code safety |
| `chatgpt-style.css` | CREATE | ChatGPT-specific styles |
| `OpenFrameRAGPage.tsx` | MODIFY | Integrate new components |
| `locales/*/chat.json` | MODIFY | Add i18n keys |

---

**PDCA Status**: Plan → Design → Do (next) → Check → Act
