# Security Keys Setup Guide

**KMS 시스템 보안 키 설정 가이드**

이 문서는 KMS 시스템 운영에 필요한 보안 환경변수 설정 방법을 설명합니다.

---

## 필수 환경변수

| 환경변수 | 용도 | 최소 길이 |
|---------|------|----------|
| `JWT_SECRET_KEY` | JWT 토큰 서명 | 32자 이상 |
| `ENCRYPTION_MASTER_KEY` | OAuth 토큰 암호화 (Fernet/AES) | 32자 이상 |
| `ENCRYPTION_SALT` | PBKDF2 키 유도 솔트 | 16자 이상 |

---

## 보안 키 생성 방법

### 방법 1: OpenSSL (권장)

```bash
# JWT_SECRET_KEY (32바이트)
openssl rand -base64 32

# ENCRYPTION_MASTER_KEY (32바이트)
openssl rand -base64 32

# ENCRYPTION_SALT (16바이트)
openssl rand -base64 16
```

**전체 명령어 (한번에 생성):**
```bash
echo "JWT_SECRET_KEY=$(openssl rand -base64 32)"
echo "ENCRYPTION_MASTER_KEY=$(openssl rand -base64 32)"
echo "ENCRYPTION_SALT=$(openssl rand -base64 16)"
```

### 방법 2: Python

```python
import secrets
import base64

# 모든 키를 한번에 생성
print(f"JWT_SECRET_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}")
print(f"ENCRYPTION_MASTER_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}")
print(f"ENCRYPTION_SALT={base64.urlsafe_b64encode(secrets.token_bytes(16)).decode()}")
```

**명령줄에서 실행:**
```bash
python -c "import secrets; import base64; print(f'JWT_SECRET_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}'); print(f'ENCRYPTION_MASTER_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}'); print(f'ENCRYPTION_SALT={base64.urlsafe_b64encode(secrets.token_bytes(16)).decode()}')"
```

### 방법 3: Node.js

```javascript
const crypto = require('crypto');

console.log(`JWT_SECRET_KEY=${crypto.randomBytes(32).toString('base64')}`);
console.log(`ENCRYPTION_MASTER_KEY=${crypto.randomBytes(32).toString('base64')}`);
console.log(`ENCRYPTION_SALT=${crypto.randomBytes(16).toString('base64')}`);
```

**명령줄에서 실행:**
```bash
node -e "const c=require('crypto'); console.log('JWT_SECRET_KEY='+c.randomBytes(32).toString('base64')); console.log('ENCRYPTION_MASTER_KEY='+c.randomBytes(32).toString('base64')); console.log('ENCRYPTION_SALT='+c.randomBytes(16).toString('base64'))"
```

---

## .env 파일 설정

생성된 키를 프로젝트 루트의 `.env` 파일에 추가합니다:

```env
# Security Keys (반드시 프로덕션 배포 전 교체)
JWT_SECRET_KEY=<생성된_키>
ENCRYPTION_MASTER_KEY=<생성된_키>
ENCRYPTION_SALT=<생성된_솔트>
```

**예시:**
```env
JWT_SECRET_KEY=3wMKsbhmJy59fTCxaY9dOcRLvEpnXKG2xPIk5YjumRk=
ENCRYPTION_MASTER_KEY=PWCQRmso1YfS3IJdFT6npT-JyrgPrFaCAcc1_CF1Zj0=
ENCRYPTION_SALT=-3RglcjMPQ5uIX2D3BXF9g==
```

---

## 보안 주의사항

### 반드시 지켜야 할 사항

| 항목 | 설명 |
|------|------|
| **Git 제외** | `.env` 파일은 `.gitignore`에 포함하여 저장소에 커밋하지 않음 |
| **키 백업** | 키 분실 시 기존 암호화 데이터 복구 불가 - 안전한 장소에 백업 |
| **환경 분리** | 개발/스테이징/프로덕션 환경마다 다른 키 사용 |
| **접근 제한** | 키는 필요한 담당자만 접근 가능하도록 관리 |

### 키 변경 시 영향

| 키 | 변경 시 영향 |
|----|-------------|
| `JWT_SECRET_KEY` | 기존 로그인 세션 무효화 → 사용자 재로그인 필요 |
| `ENCRYPTION_MASTER_KEY` | 기존 암호화된 OAuth 토큰 복호화 불가 → 외부 연결 재인증 필요 |
| `ENCRYPTION_SALT` | ENCRYPTION_MASTER_KEY와 동일 |

### 키 순환 (Key Rotation)

프로덕션 환경에서는 정기적인 키 순환을 권장합니다:

1. **JWT_SECRET_KEY**: 3-6개월 주기 (사용자 재로그인 필요)
2. **ENCRYPTION_MASTER_KEY/SALT**: 연 1회 또는 보안 사고 시 (외부 연결 재인증 필요)

---

## 암호화 기술 상세

### OAuth 토큰 암호화 (Fernet)

KMS는 OAuth 토큰을 다음 방식으로 암호화합니다:

```
PBKDF2-HMAC-SHA256 (100,000 iterations)
    ↓
Fernet Key (32 bytes)
    ↓
AES-128-CBC + HMAC-SHA256
```

**보안 특성:**
- AES-128-CBC 대칭 암호화
- HMAC-SHA256 무결성 검증
- PBKDF2 키 유도 (OWASP 권장 100,000 반복)
- 각 암호화마다 고유 IV 사용

---

## 트러블슈팅

### "Invalid token" 오류

**원인:** JWT_SECRET_KEY 변경 후 기존 토큰으로 접근 시도

**해결:** 브라우저 캐시/쿠키 삭제 후 재로그인

### "Decryption failed" 오류

**원인:** ENCRYPTION_MASTER_KEY 또는 ENCRYPTION_SALT 변경

**해결:** 영향받는 외부 연결(Notion, GitHub 등) 재인증

### 환경변수 미설정 시

서버 시작 시 다음 경고가 표시됩니다:
```
WARNING: ENCRYPTION_MASTER_KEY not set. Token encryption disabled.
```

**해결:** `.env` 파일에 필수 환경변수 설정

---

## 참고 문서

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Fernet Specification](https://github.com/fernet/spec/blob/master/Spec.md)
- [Security Review Report](./security-review-report.md)

---

*최종 수정: 2026-01-14*
