# OpenFrame KMS 구축 - 주간업무 보고 (W7~W8)

## a. Release : v1.2.0-agentic-rag

주요 개선사항:

1. Agentic RAG: 기존 8개 → 19개 제품으로 확장, 제품별 독립 Agent 아키텍처 전환
2. Hallucination 방지: 구조화 질문은 LLM 미사용(Template 응답), E2E 40/40 전건 통과
3. QLoRA 3-Phase 학습: CPT(지식주입) + SFT(제품별 어댑터) + DPO(선호도 정렬) 파이프라인 구축

---

## b. 7~8주차 : Agentic RAG 고도화 + QLoRA 학습 파이프라인 구축 완료

1. Agentic RAG 시스템 (19개 제품 자동 탐색, Agent별 지식 격리)
2. Anti-Hallucination API: Direct/Hybrid/LLM 3가지 모드 (구조화 질문 70~80%는 LLM 미사용)
3. Web Doc Fast Path: docs.tmaxsoft.com 연계, 고신뢰 매칭(score≥0.9) 시 즉시 응답
4. CPT+SFT+DPO 3단계 QLoRA 학습 파이프라인 및 22개 제품별 Multi-LoRA 어댑터 학습
5. PDF 렌더링 품질 개선: 계층 파싱(L3 TOC), 코드블록 추출, 테이블 인라인 렌더링
6. Mindmap 다국어(EN/KO/JA) 지원 및 E2E 테스트

---

## c. 주요 기술 이슈 및 개선 사항

### i. Hallucination 근본 대책 수립

문제: 기존 Smarter RAG(3단계 파이프라인)로도 E2E 테스트 53% 실패(21/45건), 제품 간 정보 혼입이 주요 원인

조치:

- 구조화 질문(명령어, 에러코드, 파라미터, 설정파일) 판별 시 LLM을 거치지 않고 검색 결과를 Template으로 직접 출력
- 19개 제품을 각각 독립 Agent로 분리하여 교차 오염 원천 차단
- 자유형 질문만 Learning LLM 사용 (컨텍스트 4,000자 제한, temperature 0.3)
- ResponseVerifier로 응답 신뢰도 3단계 표시 (Verified / Inferred / Unverified)

효과:

- E2E Hallucination 테스트 40/40 전건 통과 (기존 24/45 → 40/40)
- 전체 질문의 70~80%가 Template 모드로 처리되어 Hallucination 원천 차단

---

### ii. QLoRA 3-Phase 학습 파이프라인 구축

문제: 범용 LLM(Qwen 2.5)이 TmaxSoft 도메인 용어를 학습한 적 없어, 자유형 질문에서 부정확한 답변 생성

조치:

| Phase | 내용 | 포맷 | 주요 결과 |
|-------|------|------|----------|
| Phase 1 - CPT | 19개 제품 PDF 원문(72MB) 도메인 지식 주입 | Plain Text | Perplexity 1.65 |
| Phase 2 - SFT | 22개 제품별 Q&A 학습, Multi-LoRA 어댑터 생성 | ChatML | 22개 어댑터 생성 완료 |
| Phase 3 - DPO | 2,000개 chosen/rejected 쌍으로 할루시네이션 회피 학습 | ChatML | 선호도 정확도 95% |

- RAFT 논문(Cornell Univ., arXiv:2403.10131) 참고하여 학습 데이터에 Oracle/Distractor 문서 혼합 → 무관 문서 무시 능력 강화
- 학습 포맷은 용도에 따라 분리: CPT는 Plain Text(원문 패턴 보존), SFT/DPO는 ChatML(명령-응답 구조)

효과:

- 학습 데이터 v4→v9까지 6회 PDCA 반복으로 품질 안정화
- DPO Loss 75% 감소(0.69→0.17), 올바른 답변 선호율 95% 달성

---

### iii. PDF 검색 및 렌더링 품질 개선

문제: 기존 PDF 검색이 TOC 1단계만 파싱하여 하위 명령어 구분 불가, 표/코드블록 누락

조치:

- 3단계 TOC 계층 파싱 + 서브커맨드 분리로 정밀 검색 지원
- PDF 음영 영역을 코드블록으로 자동 추출
- 표지, 목차 등 Front Matter 검색 결과에서 자동 제외
- ChatGPT 수준의 마크다운 렌더링 적용 (구문 강조, 접이식 출처)

효과:

- 명령어별 정확한 검색 가능 (예: "tjesmgr BOOT"만 정확히 반환)
- 응답에 표, 코드블록이 원문과 동일하게 포함

---

## d. 다음 주 계획

1. Agent Teams 기능 검증 및 점진적 활성화 (5개 패턴 Feature Flag 개별 테스트)
2. 문서 관리 화면 개발 (W7 마일스톤, 이월)
3. QLoRA 학습 데이터 v10 정제 (E2E 실패 케이스 기반 보정)
4. vLLM Multi-LoRA 런타임 어댑터 전환 성능 최적화

---

## e. 요청사항

### i. AI 연구/개발 전용 GPU 인프라(DGX급) 확보 요청 (지속)

현재 운영 환경에서 다음과 같은 구조적 제약이 확인되었으며, 독립 인프라가 필요한 상황입니다.

| 제약 사항 | 상세 |
|----------|------|
| GPU 경합 | CPT(72B) 학습 시 GPU 4장 전량 점유, 추론 서비스 중단 불가피 |
| 메모리 제약 | DPO 학습 시 O(n^2) attention으로 시퀀스 2048→512 축소 필요 |
| 서빙 요건 | 22개 어댑터 동시 서빙에 최소 GPU 2장 상시 필요 |
| 인프라 제약 | 디스크 공간 부족, root 권한 부재로 환경 설정 변경 불가 |

### ii. 기대효과

- 학습(CPT/SFT/DPO)과 추론(vLLM 서빙)을 분리하여 24시간 RAG 서비스 가용성 확보
- 시퀀스 길이 제약 해소로 DPO 학습 품질 향상 (512→2048 복원 가능)
