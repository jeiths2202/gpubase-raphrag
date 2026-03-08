"""
IMS Semantic Search Service

BGE-M3 임베딩 기반 자연어 IMS 이슈 검색 + 이슈 로딩 + LLM 채팅 통합 서비스.
일반 매뉴얼 RAG와 완전 분리된 IMS 전용 파이프라인.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx

from ..models.ims_semantic import (
    ActionLogEntry,
    IMSKnowledgeCreateRequest,
    IMSKnowledgeCreateResponse,
    IMSSearchRequest,
    IMSSearchResponse,
    IMSSearchResult,
    IMSSemanticChatRequest,
    IMSSummaryRequest,
    IMSSummaryResponse,
    IssueContent,
    IssueMetadata,
    RelatedIssue,
    RelatedIssuesResponse,
)

logger = logging.getLogger(__name__)


class IMSServiceUnavailableError(Exception):
    """BGE-M3 or Neo4j service is unavailable"""
    pass


class IMSLLMTimeoutError(Exception):
    """LLM service timed out"""
    pass

# ============================================================================
# Reference extraction patterns
# ============================================================================

_IMS_REF_PATTERN = re.compile(r'IMS#(\d{5,6})')
_ACTION_REF_PATTERN = re.compile(r'Action\s+No\.?\s*(\d{7})')
_URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+')
_ATTACHMENT_PATTERN = re.compile(
    r'첨부.*파일|첨부\s*참조|添付.*ファイル|attachment|添付参照',
    re.IGNORECASE,
)

# ============================================================================
# Issue file header parsing
# ============================================================================

_HEADER_FIELDS = {
    "Product": "product",
    "Version": "version",
    "Module": "module",
    "Category": "category",
    "Subject": "subject",
    "Customer": "customer",
    "Status": "status",
    "Date": "date",
}


class IMSSemanticSearchService:
    """
    IMS 시맨틱 검색 서비스 (Singleton)

    BGE-M3 임베딩 기반 자연어 검색 + 이슈 파일 로딩 + LLM 채팅 통합.
    """

    _instance: Optional["IMSSemanticSearchService"] = None

    def __init__(self):
        from ..core.config import api_settings
        from .bge_m3_ir_service import get_bge_m3_ir_service

        self._ir_service = get_bge_m3_ir_service()

        self._issues_dir = Path(
            getattr(api_settings, "IMS_ISSUES_DIR", "uploads/ims_issues")
        )
        self._issues_remote_dir = getattr(
            api_settings,
            "IMS_ISSUES_REMOTE_DIR",
            "/raid/users/ofuser/work/of7/ims_issues_20260302",
        )
        self._llm_url = getattr(
            api_settings, "LEARNING_LLM_URL",
            os.getenv("LEARNING_LLM_URL", "http://192.168.8.11:12810/v1"),
        )
        self._llm_model = getattr(
            api_settings, "LEARNING_LLM_MODEL",
            os.getenv("LEARNING_LLM_MODEL", "/opt/models/qwen3-32b"),
        )
        self._max_context_chars = int(
            getattr(api_settings, "IMS_CHAT_MAX_CONTEXT_CHARS", 48000)
        )
        self._max_context_issues = int(
            getattr(api_settings, "IMS_CHAT_MAX_CONTEXT_ISSUES", 15)
        )
        self._cache_size = int(
            getattr(api_settings, "IMS_ISSUE_CACHE_SIZE", 500)
        )

        # 파싱된 이슈 캐시
        self._issue_cache: Dict[str, IssueContent] = {}

        # 대화 히스토리 (in-memory)
        self._conversations: Dict[str, List[Dict[str, str]]] = {}

        logger.info(
            f"IMSSemanticSearchService initialized: "
            f"issues_dir={self._issues_dir}, llm_url={self._llm_url}"
        )

    # ========================================================================
    # 1. Issue File Parser
    # ========================================================================

    def get_issue_content(self, ims_id: str) -> Optional[IssueContent]:
        """이슈 텍스트 파일을 파싱하여 IssueContent 반환 (캐시 활용, 고객정보 제거)"""
        if ims_id in self._issue_cache:
            return self._issue_cache[ims_id]

        file_path = self._issues_dir / f"{ims_id}.txt"
        if not file_path.exists():
            return None

        content = self._parse_issue_file(file_path, ims_id)
        if content:
            content = self._redact_issue(content)
            # LRU-like: 캐시 사이즈 제한
            if len(self._issue_cache) > self._cache_size:
                oldest_key = next(iter(self._issue_cache))
                del self._issue_cache[oldest_key]
            self._issue_cache[ims_id] = content
        return content

    # 고객사명 필터 목록 (대소문자 무시 매칭)
    _CUSTOMER_NAMES = [
        "이나게야", "노무라", "노무라증권", "야마기와", "라이온", "LION",
        "이토요카도", "이토요카드", "LG화재", "삼성생명", "해경",
        "손보", "손보재팬", "Sonpo", "Sompo", "동경해상",
        "토야마", "Toyama", "Daiken", "다이켄",
        "Fukuyama", "후쿠야마", "PGF", "라이프카드", "Lifrecard",
        "스미노애", "SUMINOE", "suminoe", "스즈키", "suzuki",
        "일본예금보험기구", "GE Capital", "혼다", "HONDA", "Honda",
        "Itoyocado", "우오이치", "uoichi", "미스미", "MISUMI",
    ]
    _CUSTOMER_PATTERN = re.compile(
        '|'.join(re.escape(name) for name in _CUSTOMER_NAMES),
        re.IGNORECASE,
    )

    @classmethod
    def _filter_customer_names(cls, text: str) -> str:
        """텍스트에서 고객사명을 '***'로 대체"""
        return cls._CUSTOMER_PATTERN.sub('***', text)

    @classmethod
    def _redact_issue(cls, issue: IssueContent) -> IssueContent:
        """고객사명, 프로젝트명, 담당자명 제거"""
        # Subject에서 [고객사/프로젝트] 접두사 제거
        redacted_subject = re.sub(r'^\[.*?\]\s*', '', issue.metadata.subject)
        issue.metadata.subject = cls._filter_customer_names(redacted_subject)
        issue.metadata.customer = ""
        # description, action_log에서도 고객사명 필터링
        issue.description = cls._filter_customer_names(issue.description)
        for entry in issue.action_log:
            entry.content = cls._filter_customer_names(entry.content)
        issue.raw_text = cls._filter_customer_names(issue.raw_text)
        return issue

    def _parse_issue_file(self, path: Path, ims_id: str) -> Optional[IssueContent]:
        """텍스트 파일 → IssueContent 파싱"""
        raw_text = self._read_file_safe(path)
        if not raw_text:
            return None

        # 헤더 파싱
        meta_dict: Dict[str, str] = {"ims_id": ims_id}
        lines = raw_text.split("\n")

        description_start = -1
        action_start = -1

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 헤더 필드 파싱
            for prefix, field in _HEADER_FIELDS.items():
                if stripped.startswith(f"{prefix}:"):
                    meta_dict[field] = stripped[len(prefix) + 1:].strip()
                    break

            if stripped == "## 상세 내용":
                description_start = i + 1
            elif stripped == "## 조치 이력":
                action_start = i + 1

        # description 추출
        description = ""
        if description_start >= 0:
            end = action_start - 1 if action_start > 0 else len(lines)
            description = "\n".join(lines[description_start:end]).strip()

        # action_log 추출
        action_log: List[ActionLogEntry] = []
        if action_start >= 0:
            action_text = "\n".join(lines[action_start:]).strip()
            entries = [e.strip() for e in action_text.split("---") if e.strip()]
            for idx, entry in enumerate(entries, 1):
                action_log.append(ActionLogEntry(index=idx, content=entry))

        # 참조 추출
        ref_ims_ids, ref_urls, has_attachments = self._extract_references(raw_text)
        # 자기 자신 제외
        ref_ims_ids = [r for r in ref_ims_ids if r != ims_id]

        return IssueContent(
            metadata=IssueMetadata(**meta_dict),
            description=description,
            action_log=action_log,
            raw_text=raw_text,
            referenced_ims_ids=ref_ims_ids,
            referenced_urls=ref_urls,
            has_attachment_references=has_attachments,
        )

    @staticmethod
    def _extract_references(text: str) -> Tuple[List[str], List[str], bool]:
        """텍스트에서 IMS#, URL, 첨부파일 참조 추출"""
        ims_ids = list(dict.fromkeys(_IMS_REF_PATTERN.findall(text)))
        urls = list(dict.fromkeys(_URL_PATTERN.findall(text)))
        has_attachments = bool(_ATTACHMENT_PATTERN.search(text))
        return ims_ids, urls, has_attachments

    @staticmethod
    def _read_file_safe(path: Path) -> Optional[str]:
        """UTF-8 우선, 실패시 cp949/euc-kr fallback"""
        for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        logger.warning(f"Failed to read file: {path}")
        return None

    # ========================================================================
    # 2. Semantic Search
    # ========================================================================

    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
        product_filter: Optional[str] = None,
    ) -> IMSSearchResponse:
        """BGE-M3 벡터 검색으로 관련 IMS 이슈 검색"""
        t0 = time.monotonic()

        # BGE-M3 dense encoding
        try:
            query_vecs = await self._ir_service.encode_dense([query[:512]])
        except Exception as e:
            raise IMSServiceUnavailableError(f"BGE-M3 encoding service unavailable: {e}")
        if not query_vecs:
            raise IMSServiceUnavailableError("BGE-M3 encoding returned empty result")

        query_embedding = query_vecs[0]

        # Neo4j vector search (IMS 이슈 전용 필터)
        driver = self._ir_service._get_neo4j_driver()
        results: List[IMSSearchResult] = []

        try:
            with driver.session() as session:
                # IMS 이슈 Document 필터: filename에 숫자ID 패턴 or ims 포함
                cypher = """
                    CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
                    YIELD node, score
                    MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
                    WHERE d.filename =~ '.*\\\\d{5,6}\\\\.txt'
                    RETURN
                        node.content as content,
                        node.id as chunk_id,
                        d.filename as doc_name,
                        score
                    ORDER BY score DESC
                    LIMIT $limit
                """
                records = session.run(
                    cypher,
                    embedding=query_embedding,
                    k=limit * 5,  # 중복 ims_id 합산을 위한 여유분
                    limit=limit * 5,
                )

                # doc_name → ims_id 변환 및 중복 합산
                ims_scores: Dict[str, Tuple[float, str]] = {}  # ims_id → (best_score, snippet)
                for record in records:
                    doc_name = record["doc_name"] or ""
                    score = record["score"]
                    content = record["content"] or ""

                    # filename에서 ims_id 추출
                    ims_id = self._extract_ims_id_from_filename(doc_name)
                    if not ims_id:
                        continue

                    if ims_id not in ims_scores or score > ims_scores[ims_id][0]:
                        snippet = content[:200].replace("\n", " ").strip()
                        ims_scores[ims_id] = (score, snippet)

                # 제품 필터 적용 + 메타데이터 로드
                for ims_id, (score, snippet) in sorted(
                    ims_scores.items(), key=lambda x: x[1][0], reverse=True
                ):
                    if len(results) >= limit:
                        break

                    issue = self.get_issue_content(ims_id)
                    if not issue:
                        continue

                    # 제품 필터
                    if product_filter and product_filter.lower() not in issue.metadata.product.lower():
                        continue

                    results.append(
                        IMSSearchResult(
                            ims_id=ims_id,
                            score=round(score, 4),
                            subject=issue.metadata.subject,
                            product=issue.metadata.product,
                            status=issue.metadata.status,
                            date=issue.metadata.date,
                            snippet=snippet,
                        )
                    )

        except Exception as e:
            logger.error(f"IMS semantic search failed: {e}")
            raise IMSServiceUnavailableError(f"Neo4j search unavailable: {e}")

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            f"IMS semantic search: query='{query[:30]}...', "
            f"results={len(results)}, elapsed={elapsed_ms:.1f}ms"
        )

        return IMSSearchResponse(
            query=query,
            results=results,
            total=len(results),
            search_time_ms=round(elapsed_ms, 1),
        )

    @staticmethod
    def _extract_ims_id_from_filename(filename: str) -> Optional[str]:
        """파일명에서 IMS 이슈 번호 추출: '341013.txt' → '341013'"""
        match = re.search(r'(\d{5,6})\.txt', filename)
        return match.group(1) if match else None

    # ========================================================================
    # 3. Related Issues
    # ========================================================================

    def get_related_issues(self, ims_id: str, depth: int = 1) -> RelatedIssuesResponse:
        """이슈 내 참조된 관련 이슈 목록 (multi-depth 지원)"""
        issue = self.get_issue_content(ims_id)
        if not issue:
            return RelatedIssuesResponse(ims_id=ims_id, related_issues=[], total=0)

        related: List[RelatedIssue] = []
        visited = {ims_id}
        # BFS로 depth까지 탐색
        current_level = [issue]

        for d in range(depth):
            next_level: List[IssueContent] = []
            for src_issue in current_level:
                for ref_id in src_issue.referenced_ims_ids:
                    if ref_id in visited:
                        continue
                    visited.add(ref_id)

                    ref_issue = self.get_issue_content(ref_id)
                    context = self._find_reference_context(src_issue.raw_text, ref_id)

                    related.append(
                        RelatedIssue(
                            ims_id=ref_id,
                            relation_type="ims_reference",
                            subject=ref_issue.metadata.subject if ref_issue else "",
                            product=ref_issue.metadata.product if ref_issue else "",
                            status=ref_issue.metadata.status if ref_issue else "",
                            context=context,
                        )
                    )
                    if ref_issue:
                        next_level.append(ref_issue)
            current_level = next_level

        return RelatedIssuesResponse(
            ims_id=ims_id, related_issues=related, total=len(related)
        )

    @staticmethod
    def _find_reference_context(text: str, ref_id: str) -> str:
        """참조가 등장하는 주변 텍스트 추출 (전후 100자)"""
        pattern = f"IMS#{ref_id}"
        idx = text.find(pattern)
        if idx < 0:
            return ""
        start = max(0, idx - 80)
        end = min(len(text), idx + len(pattern) + 80)
        return text[start:end].replace("\n", " ").strip()

    # ========================================================================
    # 4. Summarize Issue
    # ========================================================================

    async def summarize_issue(self, request: IMSSummaryRequest) -> Optional[IMSSummaryResponse]:
        """LLM 기반 이슈 요약"""
        issue = self.get_issue_content(request.ims_id)
        if not issue:
            return None

        # 요약용 컨텍스트 구성
        issue_text = self._format_issue_for_llm(issue, include_action_log=request.include_action_log)

        lang_instruction = self._lang_instruction(request.language)

        system_prompt = f"""You are an expert at summarizing TmaxSoft IMS technical support issues.
Provide a structured summary with:
1. "summary": 2-3 sentence overview
2. "key_points": array of important facts (3-5 items)
3. "resolution": resolution method if the issue is resolved/closed, null otherwise

Output as JSON only. {lang_instruction}"""

        user_msg = f"Summarize this IMS issue:\n\n{issue_text}"

        response_text = await self._call_llm(system_prompt, user_msg)
        if not response_text:
            return None

        # JSON 파싱 시도
        try:
            data = json.loads(self._extract_json(response_text))
        except (json.JSONDecodeError, ValueError):
            # JSON 파싱 실패 → 전체 텍스트를 summary로
            data = {"summary": response_text, "key_points": [], "resolution": None}

        return IMSSummaryResponse(
            ims_id=request.ims_id,
            subject=issue.metadata.subject,
            summary=data.get("summary", response_text),
            key_points=data.get("key_points", []),
            resolution=data.get("resolution"),
            related_ims_ids=issue.referenced_ims_ids,
        )

    # ========================================================================
    # 5. Semantic Chat (Search + Chat)
    # ========================================================================

    async def chat_with_search(
        self, request: IMSSemanticChatRequest
    ) -> AsyncGenerator[Dict, None]:
        """
        시맨틱 검색 → 이슈 컨텍스트 구성 → LLM 스트리밍 채팅.
        SSE 이벤트 형태로 yield.
        """
        conv_id = request.conversation_id or str(uuid4())

        # 1. search_start 이벤트
        yield {"event": "search_start", "data": {"query": request.query, "limit": request.search_limit}}

        # 2. 시맨틱 검색
        search_result = await self.semantic_search(request.query, limit=request.search_limit)

        yield {
            "event": "search_results",
            "data": {
                "results": [r.model_dump() for r in search_result.results],
                "total": search_result.total,
                "search_time_ms": search_result.search_time_ms,
            },
        }

        if not search_result.results:
            yield {"event": "error", "data": {"message": "No matching IMS issues found"}}
            return

        # 3. 이슈 컨텐츠 로드 + 관련 이슈
        issues: List[IssueContent] = []
        related_ims_ids: List[str] = []

        for sr in search_result.results:
            issue = self.get_issue_content(sr.ims_id)
            if issue:
                issues.append(issue)
                if request.include_related:
                    related_ims_ids.extend(issue.referenced_ims_ids)

        # 관련 이슈도 로드 (중복 제거)
        loaded_ids = {i.metadata.ims_id for i in issues}
        for ref_id in dict.fromkeys(related_ims_ids):
            if ref_id not in loaded_ids and len(issues) < self._max_context_issues:
                ref_issue = self.get_issue_content(ref_id)
                if ref_issue:
                    issues.append(ref_issue)
                    loaded_ids.add(ref_id)

        # 4. LLM 컨텍스트 구성 (vLLM max_model_len=8192 기준)
        # max_tokens=2048 → 입력 예산 ~5600 tokens, 안전 마진 포함
        MAX_INPUT_CHARS = 14000  # ~5000 tokens (CJK 약 2.8 chars/token)
        context = self._build_chat_context(issues)

        # 컨텍스트가 너무 크면 이슈를 하나씩 줄여가며 재구성
        while len(context) > MAX_INPUT_CHARS and len(issues) > 1:
            issues.pop()  # 점수가 낮은 이슈(뒤쪽)부터 제거
            context = self._build_chat_context(issues)

        total_context_chars = len(context)

        yield {
            "event": "context_loaded",
            "data": {
                "issues_loaded": len(issues),
                "related_loaded": max(0, len(loaded_ids) - search_result.total),
                "total_context_chars": total_context_chars,
            },
        }
        lang_instruction = self._lang_instruction(request.language)

        system_prompt = f"""You are an AI assistant that analyzes TmaxSoft IMS (Issue Management System) issues.
Your knowledge is STRICTLY LIMITED to the following IMS issues found by semantic search.

RULES:
1. Only answer from the provided issue data. Never invent information.
2. Always cite IMS issue numbers (e.g., IMS#341013).
3. When multiple issues are related, explain the relationships.
4. If the answer is not in the provided issues, say so clearly.
5. {lang_instruction}

Found Issues ({len(issues)} total):
{context}"""

        # 대화 히스토리
        history = self._conversations.get(conv_id, [])
        messages = [{"role": "system", "content": system_prompt}]
        # 최근 4개 메시지만 포함 (컨텍스트 절약)
        for msg in history[-4:]:
            messages.append(msg)
        messages.append({"role": "user", "content": request.query})

        # 5. LLM 스트리밍
        full_response = ""
        token_count = 0
        async for token in self._call_llm_stream(messages):
            full_response += token
            token_count += 1
            yield {"event": "token", "data": {"content": token}}

        # 대화 히스토리 저장
        history.append({"role": "user", "content": request.query})
        history.append({"role": "assistant", "content": full_response})
        self._conversations[conv_id] = history

        # 6. sources 이벤트
        sources = [
            {
                "ims_id": sr.ims_id,
                "subject": sr.subject,
                "score": sr.score,
                "product": sr.product,
            }
            for sr in search_result.results
        ]
        yield {"event": "sources", "data": {"sources": sources}}

        # 7. done
        yield {
            "event": "done",
            "data": {
                "conversation_id": conv_id,
                "total_tokens": token_count,
            },
        }

    # ========================================================================
    # 6. Knowledge Creation
    # ========================================================================

    async def create_knowledge(
        self, request: IMSKnowledgeCreateRequest
    ) -> Optional[IMSKnowledgeCreateResponse]:
        """이슈 기반 지식 문서 생성"""
        issues: List[IssueContent] = []
        for ims_id in request.ims_ids:
            issue = self.get_issue_content(ims_id)
            if issue:
                issues.append(issue)

        if not issues:
            return None

        context = self._build_chat_context(issues)
        lang_instruction = self._lang_instruction(request.language)

        system_prompt = f"""Create a knowledge document based on the following IMS issues.
The document should be a practical guide that other engineers can reference.
Include: symptoms, root cause, resolution steps, related references.
Format as Markdown with clear headings.
Title: {request.title}
{lang_instruction}"""

        user_msg = f"Source Issues:\n\n{context}"
        content = await self._call_llm(system_prompt, user_msg)

        if not content:
            return None

        return IMSKnowledgeCreateResponse(
            title=request.title,
            content=content,
            source_issues=request.ims_ids,
            created_at=datetime.now(timezone.utc),
        )

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _build_chat_context(self, issues: List[IssueContent]) -> str:
        """이슈 목록 → LLM 컨텍스트 문자열"""
        parts: List[str] = []
        chars_budget = self._max_context_chars

        for i, issue in enumerate(issues):
            if i < 5:
                part = self._format_issue_for_llm(issue, max_chars=4000, include_action_log=True)
            else:
                part = self._format_issue_for_llm(issue, max_chars=800, include_action_log=False)

            if sum(len(p) for p in parts) + len(part) > chars_budget:
                break
            parts.append(part)

        return "\n\n".join(parts)

    @staticmethod
    def _format_issue_for_llm(
        issue: IssueContent,
        max_chars: int = 4000,
        include_action_log: bool = True,
    ) -> str:
        """이슈 → LLM용 포맷 문자열"""
        m = issue.metadata
        # Subject에서 [고객사/프로젝트] 접두사 제거
        subject = re.sub(r'^\[.*?\]\s*', '', m.subject)
        text = f"""--- IMS Issue #{m.ims_id} ---
Product: {m.product} | Version: {m.version} | Status: {m.status}
Subject: {subject}
Date: {m.date}

Description:
{issue.description[:max_chars]}"""

        if include_action_log and issue.action_log:
            action_text = "\n---\n".join(
                a.content[:500] for a in issue.action_log[:10]
            )
            remaining = max_chars - len(text) - 50
            if remaining > 200:
                text += f"\n\nAction Log:\n{action_text[:remaining]}"

        if issue.referenced_ims_ids:
            text += f"\nReferenced Issues: {', '.join('IMS#' + r for r in issue.referenced_ims_ids)}"

        return text[:max_chars]

    @staticmethod
    def _lang_instruction(language: str) -> str:
        lang_map = {
            "ko": "Respond in Korean.",
            "ja": "Respond in Japanese.",
            "en": "Respond in English.",
        }
        return lang_map.get(language, "Respond in the same language as the user's question.")

    async def _call_llm(self, system_prompt: str, user_msg: str) -> Optional[str]:
        """vLLM non-streaming 호출"""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._llm_url}/chat/completions",
                    json={
                        "model": self._llm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2048,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException as e:
            logger.error(f"LLM call timed out: {e}")
            raise IMSLLMTimeoutError(f"LLM service timed out: {e}")
        except httpx.ConnectError as e:
            logger.error(f"LLM connection failed: {e}")
            raise IMSServiceUnavailableError(f"LLM service unavailable: {e}")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def _call_llm_stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """vLLM streaming 호출"""
        try:
            payload = {
                "model": self._llm_model,
                "messages": messages,
                "stream": True,
                "temperature": 0.3,
                "max_tokens": 1536,
            }
            total_chars = sum(len(m.get("content", "")) for m in messages)
            logger.info(f"LLM request: model={self._llm_model}, url={self._llm_url}, messages={len(messages)}, total_chars={total_chars}")
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._llm_url}/chat/completions",
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        logger.error(f"LLM returned {resp.status_code}: {body[:500]}")
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"\n\n[Error: LLM service unavailable - {e}]"

    @staticmethod
    def _extract_json(text: str) -> str:
        """텍스트에서 JSON 블록 추출 (```json ... ``` 또는 { ... })"""
        # ```json ... ``` 패턴
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # { ... } 패턴
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        return text


# ============================================================================
# Singleton accessor
# ============================================================================

_ims_semantic_service: Optional[IMSSemanticSearchService] = None


def get_ims_semantic_search_service() -> IMSSemanticSearchService:
    """IMSSemanticSearchService 싱글톤 반환"""
    global _ims_semantic_service
    if _ims_semantic_service is None:
        _ims_semantic_service = IMSSemanticSearchService()
    return _ims_semantic_service
