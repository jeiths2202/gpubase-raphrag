# Conversation Deletion Feature - Test Guide

## ✅ Implementation Complete

대화 삭제 기능이 완전히 구현되었습니다. PostgreSQL 데이터베이스와 연동되어 정상 작동합니다.

---

## 🔧 구현된 기능

### 1. **UI 컴포넌트**
- 대화 항목에 마우스 오버 시 삭제 버튼(🗑️) 표시
- 삭제 확인 대화상자
- 삭제 진행 중 상태 표시
- 삭제 실패 시 에러 메시지

### 2. **백엔드 통합**
- API 엔드포인트: `DELETE /api/v1/conversations/{conversation_id}`
- 기본: **Soft Delete** (복구 가능)
- 옵션: **Hard Delete** (영구 삭제)

### 3. **데이터베이스**
- **Soft Delete**: `is_deleted = TRUE` 플래그 설정
  - `deleted_at`: 삭제 시각 기록
  - `deleted_by`: 삭제한 사용자 ID 기록
  - 데이터베이스에 데이터는 유지 (복구 가능)

- **Hard Delete**: 테이블에서 완전 삭제
  - 복구 불가능

### 4. **다국어 지원**
- 영어 (English)
- 한국어 (Korean)
- 일본어 (Japanese)

---

## 🧪 수동 테스트 방법

### Step 1: 로그인
```
URL: http://localhost:3000
Email: edelweise@naver.com
Password: SecureTest123!
```

### Step 2: 대화 생성
1. **Chat** 탭으로 이동
2. 질문 입력 (예: "Hello, what is 2+2?")
3. **Send** 버튼 클릭
4. AI 응답 대기

### Step 3: 대화 목록 열기
1. **Conversation** 또는 **대화 일람** 버튼 클릭
2. 오른쪽에서 사이드바가 슬라이드 인

### Step 4: 삭제 기능 테스트
1. 대화 항목에 **마우스 오버**
2. 빨간색 🗑️ 아이콘이 우측 상단에 나타남
3. 🗑️ 아이콘 **클릭**
4. 확인 대화상자 표시:
   - 한국어: "이 대화를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."
   - 영어: "Are you sure you want to delete this conversation? This action cannot be undone."
5. **삭제** 또는 **Delete** 클릭
6. 대화가 목록에서 **즉시 사라짐**

### Step 5: 취소 테스트
1. 다른 대화 항목 삭제 시도
2. 확인 대화상자에서 **취소** 또는 **Cancel** 클릭
3. 대화가 **유지됨**

---

## 🔍 데이터베이스 확인

### 방법 1: Python 검증 스크립트 사용

```bash
# 전체 대화 상태 확인
python verify_deletion.py

# 특정 대화 확인 (conversation_id는 UUID)
python verify_deletion.py <conversation_id>
```

**출력 예시:**
```
================================================================================
1️⃣  ALL CONVERSATIONS (including soft-deleted)
================================================================================

✅ ACTIVE
  ID: 550e8400-e29b-41d4-a716-446655440000
  Title: Hello conversation
  User ID: user123
  Messages: 5
  Created: 2024-12-29 10:30:00

🗑️ DELETED
  ID: 6ba7b810-9dad-11d1-80b4-00c04fd430c8
  Title: Test conversation
  User ID: user123
  Messages: 3
  Created: 2024-12-29 09:00:00
  Deleted At: 2024-12-29 11:00:00
  Deleted By: user123

================================================================================
2️⃣  CONVERSATION STATUS SUMMARY
================================================================================
✅ Active: 15
🗑️ Soft-deleted: 3
📊 Total: 18
```

### 방법 2: SQL 직접 쿼리

PostgreSQL에 직접 연결하여 쿼리:

```bash
# PostgreSQL 접속
psql -h localhost -p 5432 -U raguser -d ragdb

# 모든 대화 조회 (삭제된 것 포함)
SELECT id, title, is_deleted, deleted_at, deleted_by, created_at
FROM conversations
ORDER BY updated_at DESC
LIMIT 10;

# 활성 대화만 조회
SELECT id, title, message_count, created_at
FROM conversations
WHERE is_deleted = FALSE
ORDER BY updated_at DESC;

# 삭제된 대화만 조회
SELECT id, title, deleted_at, deleted_by
FROM conversations
WHERE is_deleted = TRUE
ORDER BY deleted_at DESC;
```

### 방법 3: SQL 파일 사용

준비된 SQL 파일을 사용하여 확인:

```bash
psql -h localhost -p 5432 -U raguser -d ragdb -f verify_conversation_deletion.sql
```

---

## 🧪 자동화된 E2E 테스트

Playwright 테스트가 구현되어 있습니다:

```bash
cd frontend

# 전체 테스트 실행 (헤드리스)
npx playwright test conversation-deletion.spec.ts

# 브라우저 UI로 테스트 실행
npx playwright test conversation-deletion.spec.ts --headed

# 특정 테스트만 실행
npx playwright test conversation-deletion.spec.ts -g "should delete conversation"
```

**테스트 케이스:**
1. ✅ 마우스 오버 시 삭제 버튼 표시
2. ✅ 확인 후 대화 삭제
3. ✅ 취소 시 대화 유지
4. ✅ 활성 대화 삭제 시 자동 클리어
5. ✅ DELETE API 엔드포인트 호출 확인

---

## 📊 작동 원리

### Frontend Flow
```
User hovers → Delete button appears → User clicks → Confirmation dialog
                                                              ↓
                                               User confirms / cancels
                                                              ↓
                                         workspaceStore.deleteConversation()
                                                              ↓
                                    DELETE /api/v1/conversations/{id}?hard_delete=false
                                                              ↓
                                         Backend processes deletion
                                                              ↓
                                  UI updates: Remove from list + Clear if active
```

### Backend Flow
```
DELETE Request → Auth Validation → Check Ownership
                                           ↓
                               hard_delete parameter check
                                           ↓
                      ┌────────────────────┴────────────────────┐
                      ↓                                         ↓
              hard_delete=true                          hard_delete=false
                      ↓                                         ↓
        DELETE FROM conversations              UPDATE conversations SET
                                                  is_deleted = TRUE,
                                                  deleted_at = NOW(),
                                                  deleted_by = user_id
```

### Database Schema
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    title VARCHAR(255),
    user_id VARCHAR(255) NOT NULL,
    message_count INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT FALSE,      -- Soft delete flag
    deleted_at TIMESTAMP,                  -- When deleted
    deleted_by VARCHAR(255),               -- Who deleted
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🐛 트러블슈팅

### 문제 1: 삭제 버튼이 보이지 않음
**원인**: `showActions` 프롭이 `false`로 설정됨
**해결**: `ConversationHistorySidebar.tsx`에서 `showActions={true}` 확인

### 문제 2: 404 에러 발생
**원인**: API 엔드포인트 경로 오류
**해결**: ✅ 이미 수정됨 (`/api/v1/conversations/...` 사용)

### 문제 3: 데이터베이스 연결 실패
**원인**: `.env` 파일 설정 오류
**해결**:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb
```

### 문제 4: 삭제 후에도 대화가 목록에 남아있음
**원인**: 프론트엔드 상태 업데이트 미실행
**해결**: 브라우저 콘솔에서 에러 확인 및 새로고침

---

## 📝 파일 변경 사항

### 백엔드 (이미 존재)
- `app/api/routers/conversations.py` (line 222-260) - DELETE 엔드포인트
- `app/api/services/conversation_service.py` (line 308-342) - 삭제 비즈니스 로직
- `app/api/infrastructure/postgres/conversation_repository.py` - 데이터베이스 작업

### 프론트엔드 (신규/수정)
- ✅ `frontend/src/store/workspaceStore.ts` - API 통합 및 상태 관리
- ✅ `frontend/src/features/knowledge/components/ConversationListItem.tsx` - 삭제 버튼 UI
- ✅ `frontend/src/features/knowledge/components/ConversationList.tsx` - 프롭 드릴링
- ✅ `frontend/src/features/knowledge/hooks/useConversationHistory.ts` - 삭제 함수
- ✅ `frontend/src/features/knowledge/components/ConversationHistorySidebar.tsx` - 통합

### 번역 파일
- ✅ `frontend/src/i18n/locales/en/knowledge.json`
- ✅ `frontend/src/i18n/locales/ko/knowledge.json`
- ✅ `frontend/src/i18n/locales/ja/knowledge.json`

### 테스트
- ✅ `frontend/src/__tests__/e2e/conversation-deletion.spec.ts` - E2E 테스트

### 검증 도구
- ✅ `verify_deletion.py` - Python 데이터베이스 검증 스크립트
- ✅ `verify_conversation_deletion.sql` - SQL 쿼리 모음

---

## 🎯 다음 단계 (선택사항)

### 1. 복구 기능 추가
Soft delete된 대화를 복구하는 UI 추가:
- 휴지통 메뉴
- 복구 버튼
- 영구 삭제 옵션

### 2. 일괄 삭제
여러 대화를 선택하여 한번에 삭제:
- 체크박스 추가
- 일괄 삭제 버튼
- 진행 상황 표시

### 3. 자동 정리
오래된 삭제 대화 자동 정리:
- 백그라운드 작업
- 30일 이상 경과 시 hard delete
- 설정 가능한 정책

---

## ✅ 테스트 체크리스트

- [ ] 로그인 성공
- [ ] 대화 생성
- [ ] 대화 목록 열기
- [ ] 마우스 오버 시 삭제 버튼 표시
- [ ] 삭제 버튼 클릭 시 확인 대화상자
- [ ] 삭제 확인 시 대화 제거
- [ ] 취소 시 대화 유지
- [ ] 활성 대화 삭제 시 자동 클리어
- [ ] 데이터베이스에서 `is_deleted = TRUE` 확인
- [ ] 브라우저 콘솔에 에러 없음

---

## 📞 지원

문제가 발생하면:
1. 브라우저 콘솔 확인 (F12)
2. 백엔드 로그 확인
3. `python verify_deletion.py` 실행하여 데이터베이스 상태 확인
4. 스크린샷과 에러 메시지 제공

---

**구현 완료일**: 2024-12-29
**테스트 계정**: edelweise@naver.com / SecureTest123!
