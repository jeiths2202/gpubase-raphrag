# Plan: Modernization AI - History & Notes PostgreSQL Persistence

## Overview

| Item | Value |
|------|-------|
| Feature | modernization-ai-persistence |
| Phase | Plan |
| Priority | High |
| Scope | Backend API + Frontend integration |

## Problem Statement

Modernization AI Assistant의 히스토리(채팅 이력)와 메모 기능이 현재:
- **히스토리**: React state(메모리) → 새로고침 시 소멸
- **메모**: localStorage → 브라우저/기기 종속, 사용자 간 공유 불가

## Goal

기존 PostgreSQL 대화 시스템(Conversation/Message/Note)을 **재사용**하여:
1. 채팅 히스토리를 서버에 영속 저장
2. 메모를 PostgreSQL Note 테이블에 저장
3. 세션 간, 기기 간 데이터 유지

## Architecture Decision: Reuse Existing Infrastructure

### Already Available (No New Tables Needed)

| Component | Existing File | Reuse Strategy |
|-----------|---------------|----------------|
| **Conversation** model | `app/api/models/conversation.py` | `agent_type="modernization"` 으로 필터 |
| **Message** model | `app/api/models/conversation.py` | `role`, `content`, `sources(JSON)` 그대로 사용 |
| **Note** model | `app/api/models/note.py` | `source=AI_CHAT`, `note_type=ANNOTATION` |
| **ConversationRepository** | `app/api/repositories/conversation_repository.py` | `get_by_user()`, `add_message()` 등 |
| **NoteRepository** | `app/api/repositories/note_repository.py` | `get_by_user()`, `create()`, `delete()` |
| **ConversationService** | `app/api/services/conversation_service.py` | `create_conversation()`, `add_user_message()`, `add_assistant_message()` |
| **Conversation API** | `app/api/routers/conversations.py` | GET/POST /conversations, messages |
| **Frontend API client** | `kms-portal-ui/src/api/conversation.api.ts` | `list()`, `create()`, `get()`, `addMessage()` |
| **Frontend Store** | `kms-portal-ui/src/store/conversationStore.ts` | agentStates per agent_type |

### New Metadata Fields (Conversation.metadata JSON)

```json
{
  "system_type": "host" | "openframe" | "all",
  "analysis_id": "optional-analysis-session-id",
  "source_system_responses": ["host", "openframe"]
}
```

## Implementation Plan

### Phase 1: Backend - Chat Service with Persistence (chat_service.py)

**변경 파일**: `app/api/legacy_modernization/services/chat_service.py`

현재 chat_service는 stateless 스트리밍만 수행. 다음을 추가:

1. 스트리밍 시작 전: `conversation_service.create_conversation()` 또는 기존 conversation 재사용
2. 사용자 메시지 저장: `conversation_service.add_user_message()`
3. 스트리밍 완료 후: `conversation_service.add_assistant_message()` (전체 응답 + sources)
4. SSE에 `conversation_id` 포함하여 프론트엔드에 전달

```python
# Pseudocode flow
async def stream_chat(request, user_id):
    # 1. Get or create conversation
    conv_id = request.conversation_id
    if not conv_id:
        conv = await conversation_service.create_conversation(
            user_id=user_id,
            agent_type="modernization",
            metadata={"system_type": request.system_type.value}
        )
        conv_id = conv.id

    # 2. Save user message
    await conversation_service.add_user_message(conv_id, request.message)

    # 3. Stream + accumulate response
    yield {"type": "conversation_id", "conversation_id": str(conv_id)}

    full_response = ""
    sources = []
    async for event in self._route_stream(request, user_id):
        if event["type"] == "llm_token":
            full_response += event["token"]
        elif event["type"] == "sources":
            sources = event.get("results", [])
        yield event

    # 4. Save assistant response
    await conversation_service.add_assistant_message(
        conv_id, full_response, sources=sources
    )
```

### Phase 2: Backend - Notes API Endpoints

**새 파일**: `app/api/legacy_modernization/routers/notes.py` (또는 chat.py에 추가)

기존 NoteRepository를 사용하여:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/legacy/notes` | GET | 사용자의 modernization 메모 목록 |
| `/legacy/notes` | POST | 새 메모 생성 |
| `/legacy/notes/{id}` | DELETE | 메모 삭제 |

```python
@router.get("/notes")
async def list_notes(current_user = Depends(get_current_user)):
    notes = await note_repo.get_by_user(
        user_id=current_user["user_id"],
        source="AI_CHAT",  # Filter modernization notes
    )
    return notes

@router.post("/notes")
async def create_note(body: NoteCreate, current_user = Depends(get_current_user)):
    return await note_repo.create(
        user_id=current_user["user_id"],
        content=body.content,
        note_type="ANNOTATION",
        source="AI_CHAT",
    )
```

### Phase 3: Frontend - Conversation API Integration

**변경 파일**: `kms-portal-ui/src/components/ModernizationAI/useModernizationChat.ts`

현재 in-memory messages를 DB 연동으로 변경:

1. 컴포넌트 마운트 시: 최근 conversation 목록 로드
2. 채팅 전송 시: SSE 스트림에서 `conversation_id` 수신 → state에 저장
3. 히스토리 탭: API에서 과거 대화 목록 로드 → 클릭 시 해당 대화 메시지 로드
4. 새 대화 시작: "새 대화" 버튼 추가

```typescript
// Key changes
const [conversationId, setConversationId] = useState<string | null>(null);
const [conversations, setConversations] = useState<Conversation[]>([]);

// On mount: load conversation list
useEffect(() => {
  conversationApi.list({ agent_type: 'modernization' }).then(setConversations);
}, []);

// During SSE: capture conversation_id
if (event.type === 'conversation_id') {
  setConversationId(event.conversation_id);
}

// Load specific conversation
const loadConversation = async (convId: string) => {
  const conv = await conversationApi.get(convId);
  setMessages(conv.messages.map(toLocalMessage));
  setConversationId(convId);
};
```

### Phase 4: Frontend - Notes API Integration

**변경 파일**: `kms-portal-ui/src/components/ModernizationAI/ModernizationAIAssistant.tsx`

localStorage → API 호출로 변경:

```typescript
// Replace localStorage with API
const [notes, setNotes] = useState<ChatNote[]>([]);

useEffect(() => {
  legacyApi.getNotes().then(setNotes);
}, []);

const addNote = async () => {
  const created = await legacyApi.createNote({ content: noteInput });
  setNotes(prev => [...prev, created]);
};

const deleteNote = async (id: string) => {
  await legacyApi.deleteNote(id);
  setNotes(prev => prev.filter(n => n.id !== id));
};
```

### Phase 5: Frontend - History Tab Enhancement

**변경 파일**: `ModernizationAIAssistant.tsx` History Tab 영역

현재: 현재 세션 user 메시지만 표시
변경: 과거 대화 세션 목록 → 클릭 시 해당 세션 메시지 로드

```
[History Tab]
├── "새 대화" 버튼
├── 대화 목록 (최신순)
│   ├── 2/18 14:07 - "tjesmgr BOOT..." (OpenFrame)
│   ├── 2/18 13:55 - "COBOL CALL文..." (HOST)
│   └── 2/17 16:30 - "VSAM migration..." (ALL)
└── 선택한 대화의 메시지 로드
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `app/api/legacy_modernization/services/chat_service.py` | **Modify** | conversation_service 연동, 메시지 저장 |
| `app/api/legacy_modernization/routers/chat.py` | **Modify** | conversation_id를 SSE 이벤트에 포함 |
| `app/api/legacy_modernization/routers/chat_schemas.py` | **Modify** | NoteCreate 스키마 추가 |
| `kms-portal-ui/src/api/legacy.api.ts` | **Modify** | notes CRUD + conversation list API 추가 |
| `kms-portal-ui/src/components/ModernizationAI/useModernizationChat.ts` | **Modify** | DB 연동, conversation lifecycle |
| `kms-portal-ui/src/components/ModernizationAI/ModernizationAIAssistant.tsx` | **Modify** | History tab 리뉴얼, Notes API 연동 |
| `kms-portal-ui/src/components/ModernizationAI/types.ts` | **Modify** | Conversation 타입 추가 |

## Dependencies

- 기존 `ConversationService` (conversation_service.py)
- 기존 `NoteRepository` (note_repository.py)
- 기존 `conversation.api.ts` (프론트엔드 API 클라이언트)
- PostgreSQL 연결 (`core/deps.py` → `get_db_session`)

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| conversation_service가 deps.py 의존성 체인 필요 | Medium | deps.py에서 기존 get_conversation_service() 재사용 |
| SSE 스트리밍 중 DB 저장 실패 | Low | 응답 완료 후 비동기 저장, 실패 시 로그만 기록 |
| Note model 필드 불일치 | Low | 기존 Note 스키마에 맞춰 구현 |

## Success Criteria

- [ ] 새로고침 후에도 이전 대화 히스토리가 History 탭에 표시됨
- [ ] 과거 대화 클릭 시 해당 대화의 전체 메시지가 로드됨
- [ ] 메모가 서버에 저장되어 다른 기기에서도 접근 가능
- [ ] 기존 KMS 대화 시스템(AgentChat)과 동일한 PostgreSQL 인프라 사용
