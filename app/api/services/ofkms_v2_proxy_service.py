"""
OFKMS v2 Proxy Service

사용자 질의응답을 OFKMS v2 API로 위임하는 프록시 서비스.
OFKMS v2의 SSE 이벤트를 기존 프론트엔드 형식으로 변환합니다.
"""
import json
import logging
import re
from typing import AsyncGenerator, Optional

import httpx

from ..models.agentic_rag import (
    AgenticRAGRequest,
    AgenticRAGResponse,
    QueryType,
    RouterDecision,
    RouterResult,
)
from ..models.openframe_rag import ConfidenceLevel, ProductSources

logger = logging.getLogger(__name__)

# OFKMS v2 intent → QueryType 매핑
_INTENT_TO_QUERY_TYPE = {
    "error_code": QueryType.ERROR_CODE,
    "command": QueryType.COMMAND,
    "config": QueryType.CONFIG,
    "code": QueryType.FREEFORM,
    "comparison": QueryType.FREEFORM,
    "general": QueryType.FREEFORM,
}

# Phase 진행률 계산용 (phase 0~5 + response)
_PHASE_TOTAL = 6


def _map_confidence(score: float) -> ConfidenceLevel:
    if score >= 0.8:
        return ConfidenceLevel.HIGH
    elif score >= 0.5:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


class OFKMSv2ProxyService:
    """OFKMS v2 API 프록시 — 질의응답을 OFKMS v2로 위임"""

    _instance: Optional["OFKMSv2ProxyService"] = None

    def __init__(self):
        from ..core.config import get_api_settings
        settings = get_api_settings()
        self._base_url = settings.OFKMS_V2_BASE_URL.rstrip("/")
        self._api_key = settings.OFKMS_V2_API_KEY
        self._timeout = settings.OFKMS_V2_TIMEOUT
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )
        logger.info(f"OFKMSv2ProxyService initialized: {self._base_url}")

    def _build_query_payload(self, request: AgenticRAGRequest) -> dict:
        """AgenticRAGRequest → OFKMS v2 QueryRequest 변환"""
        payload = {
            "query": request.message,
            "include_sources": True,
            "include_phases": False,
        }
        if request.language:
            payload["language"] = request.language

        # 제품 필터: effective_products의 첫 번째
        effective = request.effective_products
        if effective:
            payload["product"] = effective[0]

        return payload

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    # =========================================================================
    # SSE 이벤트 변환
    # =========================================================================

    def _convert_phase_event(self, data: dict) -> dict:
        """phase → search_progress"""
        phase_num = data.get("phase", 0)
        return {
            "type": "search_progress",
            "product": "auto",
            "step": data.get("name", f"phase_{phase_num}"),
            "progress": round((phase_num + 1) / _PHASE_TOTAL, 2),
        }

    @staticmethod
    def _normalize_markdown_newlines(text: str) -> str:
        """단일 \\n을 \\n\\n으로 변환하여 ReactMarkdown 호환성 확보.

        Markdown 표준에서 단일 개행은 공백으로 처리되므로,
        LLM 출력의 단일 개행을 단락 구분(\\n\\n)으로 정규화합니다.
        이미 \\n\\n인 부분이나 리스트/헤더 앞뒤는 보존합니다.
        """
        if not text:
            return text
        # 이미 \n\n인 부분을 placeholder로 보호
        text = text.replace("\n\n", "\x00DOUBLE_NL\x00")
        # 단일 \n → \n\n (리스트/헤더/코드블록 직전은 제외 — 이미 markdown 구문으로 처리됨)
        text = re.sub(
            r"\n(?![-*#|>`\x00])",
            "\n\n",
            text,
        )
        # placeholder 복원
        text = text.replace("\x00DOUBLE_NL\x00", "\n\n")
        return text

    def _convert_answer_event(self, data: dict) -> list:
        """answer → [template_response, sources]"""
        events = []

        # 답변 본문 (단일 개행 정규화)
        answer = self._normalize_markdown_newlines(data.get("answer", ""))
        events.append({
            "type": "template_response",
            "content": answer,
            "query_type": data.get("intent", "general"),
        })

        # 소스 정보
        sources = data.get("sources")
        if sources:
            events.append({
                "type": "sources",
                "results": [
                    {
                        "doc_name": s.get("document", ""),
                        "source_page": s.get("page"),
                        "score": s.get("score", 0),
                        "domain": s.get("type", "unknown"),
                        "product": data.get("product", ""),
                    }
                    for s in sources
                ],
                "total": len(sources),
            })

        return events

    def _convert_done_event(self, data: dict, answer_data: dict) -> dict:
        """done 이벤트 변환"""
        return {
            "type": "done",
            "processing_time_ms": data.get("total_time_ms", 0),
            "product": answer_data.get("product", ""),
            "query_type": answer_data.get("intent", "general"),
        }

    # =========================================================================
    # Public API
    # =========================================================================

    async def stream_query(
        self, request: AgenticRAGRequest
    ) -> AsyncGenerator[dict, None]:
        """SSE 스트리밍 프록시 — OFKMS v2 이벤트를 기존 형식으로 변환"""
        payload = self._build_query_payload(request)
        url = f"{self._base_url}/v1/query/stream"
        answer_data: dict = {}

        try:
            async with self._client.stream(
                "POST", url, json=payload, headers=self._headers(),
            ) as resp:
                if resp.status_code == 401:
                    yield {"type": "error", "message": "OFKMS v2 인증 실패 (API Key 확인 필요)"}
                    return
                resp.raise_for_status()

                event_type = ""
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            logger.warning(f"OFKMS v2 SSE parse error: {line[:100]}")
                            continue

                        if event_type == "phase":
                            yield self._convert_phase_event(data)
                        elif event_type == "answer":
                            answer_data = data
                            for ev in self._convert_answer_event(data):
                                yield ev
                        elif event_type == "done":
                            yield self._convert_done_event(data, answer_data)
                        elif event_type == "error":
                            yield {"type": "error", "message": data.get("error", "OFKMS v2 서버 에러")}

                        event_type = ""

        except httpx.ConnectError:
            logger.error(f"OFKMS v2 connection failed: {url}")
            yield {"type": "error", "message": f"OFKMS v2 서버에 연결할 수 없습니다 ({self._base_url})"}
        except httpx.ReadTimeout:
            logger.error(f"OFKMS v2 timeout: {url}")
            yield {"type": "error", "message": "OFKMS v2 응답 타임아웃"}
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:200] if e.response.text else ""
            logger.error(f"OFKMS v2 HTTP error: {e.response.status_code} {detail}")
            yield {"type": "error", "message": f"OFKMS v2 서버 에러 (HTTP {e.response.status_code}): {detail}"}
        except Exception as e:
            logger.error(f"OFKMS v2 proxy error: {e}", exc_info=True)
            yield {"type": "error", "message": f"OFKMS v2 프록시 에러: {str(e)}"}

    async def query(self, request: AgenticRAGRequest) -> AgenticRAGResponse:
        """동기식 프록시 — /v1/query 호출 후 AgenticRAGResponse로 변환"""
        payload = self._build_query_payload(request)
        url = f"{self._base_url}/v1/query"

        try:
            resp = await self._client.post(
                url, json=payload, headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            intent = data.get("intent", "general")
            confidence = data.get("confidence", 0.0)

            return AgenticRAGResponse(
                success=data.get("success", False),
                response=data.get("answer", ""),
                product=data.get("product", "auto"),
                query_type=_INTENT_TO_QUERY_TYPE.get(intent, QueryType.FREEFORM),
                router_result=RouterResult(
                    decision=RouterDecision.CONFIRMED,
                    product=data.get("product"),
                    confidence=confidence,
                ),
                verification=None,
                sources=ProductSources(),
                confidence=_map_confidence(confidence),
                processing_time_ms=data.get("usage", {}).get("total_time_ms"),
            )
        except httpx.ConnectError:
            raise ConnectionError(f"OFKMS v2 서버에 연결할 수 없습니다 ({self._base_url})")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"OFKMS v2 HTTP {e.response.status_code}: {e.response.text[:200]}")

    async def stream_analyze(
        self, command: str
    ) -> AsyncGenerator[dict, None]:
        """
        /analyze slash command 처리 — OFKMS v2 /v1/analyze 호출.

        command: "/analyze /path/to/dir [options]"
        """
        parts = command.strip().split(None, 1)
        arg = parts[1].strip() if len(parts) > 1 else ""

        if not arg:
            yield {
                "type": "slash_result",
                "content": (
                    "**Usage:** `/analyze <path> [options]`\n\n"
                    "Analyze legacy mainframe assets (COBOL, ASM, JCL, BMS, MFS, DBD, PSB) "
                    "and generate an interactive D3.js codemap.\n\n"
                    "**Examples:**\n"
                    "- `/analyze /opt/legacy/src`\n"
                    "- `/analyze /opt/legacy/src --depth 3`\n"
                ),
            }
            return

        # 진행 상태 표시
        yield {
            "type": "slash_result",
            "content": f"Analyzing legacy assets in `{arg}`...",
        }

        url = f"{self._base_url}/v1/analyze"
        payload = {
            "path": arg,
            "output_format": "html",
        }

        try:
            resp = await self._client.post(
                url, json=payload, headers=self._headers(),
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
            resp.raise_for_status()
            data = resp.json()

            stats = data.get("stats", {})
            # analysis_time_ms를 stats에 병합 (최상위 필드로도 제공됨)
            if "analysis_time_ms" not in stats and data.get("analysis_time_ms"):
                stats["analysis_time_ms"] = data["analysis_time_ms"]

            # html_path: OFKMS v2가 반환하는 codemap HTML 파일명
            html_path = data.get("html_path", "")

            # codemap URL 생성 (프록시 경로)
            codemap_url = ""
            if html_path:
                codemap_url = f"/api/v1/agentic-rag/codemap/{html_path}"

            yield {
                "type": "analyze_result",
                "stats": stats,
                "codemap_url": codemap_url,
            }

            yield {
                "type": "done",
                "product": "analyze",
                "query_type": "analyze",
            }

        except httpx.ConnectError:
            logger.error(f"OFKMS v2 analyze connection failed: {url}")
            yield {
                "type": "slash_result",
                "content": f"OFKMS v2 서버에 연결할 수 없습니다 ({self._base_url})",
            }
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:300] if e.response.text else ""
            logger.error(f"OFKMS v2 analyze HTTP error: {e.response.status_code} {detail}")
            yield {
                "type": "slash_result",
                "content": f"Analysis failed (HTTP {e.response.status_code}): {detail}",
            }
        except Exception as e:
            logger.error(f"OFKMS v2 analyze error: {e}", exc_info=True)
            yield {
                "type": "slash_result",
                "content": f"Analysis error: {str(e)}",
            }

    async def get_codemap(self, filename: str) -> str:
        """OFKMS v2에서 codemap HTML을 가져와 반환"""
        url = f"{self._base_url}/v1/analyze/codemap/{filename}"
        try:
            resp = await self._client.get(
                url, headers=self._headers(),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Codemap fetch failed (HTTP {e.response.status_code}): {e.response.text[:200]}"
            )
        except Exception as e:
            raise RuntimeError(f"Codemap fetch error: {str(e)}")

    async def health_check(self) -> dict:
        """OFKMS v2 /v1/health 호출"""
        try:
            resp = await self._client.get(
                f"{self._base_url}/v1/health",
                timeout=5.0,
            )
            return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    async def close(self):
        await self._client.aclose()


def get_ofkms_v2_proxy() -> OFKMSv2ProxyService:
    """Singleton factory"""
    if OFKMSv2ProxyService._instance is None:
        OFKMSv2ProxyService._instance = OFKMSv2ProxyService()
    return OFKMSv2ProxyService._instance
