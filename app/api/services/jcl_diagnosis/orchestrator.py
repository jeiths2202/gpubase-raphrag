"""JCL Job Failure Diagnosis Orchestrator

5-Agent sequential pipeline:
  FileProcessor → JCLAnalyzer → ErrorDiagnosis → KnowledgeRetriever → ReportGenerator

SSE 이벤트를 yield하면서 각 Agent 단계를 실행합니다.
"""
import logging
import time
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, Optional, Tuple

from app.api.models.jcl_diagnosis import (
    ClassifiedFiles, JobAnalysis, DiagnosisResult, KnowledgeResult,
    DiagnosisReport, DiagnosisEventType, JCLDiagnosisRequest
)
from .file_processor import FileProcessor
from .jcl_analyzer import JCLAnalyzer
from .error_diagnosis import ErrorDiagnosisAgent
from .knowledge_retriever import KnowledgeRetriever
from .report_generator import ReportGenerator
from .report_template import get_html_report_service

logger = logging.getLogger(__name__)


_REPORT_CACHE_TTL = 3600  # 1시간


class JCLDiagnosisOrchestrator:
    """5-Agent 파이프라인 오케스트레이터

    각 Agent는 독립적인 서비스 클래스이며, 오케스트레이터가
    데이터 흐름을 관리하고 SSE 이벤트를 생성합니다.
    """

    def __init__(self):
        self.file_processor = FileProcessor()
        self.jcl_analyzer = JCLAnalyzer()
        self.error_diagnosis = ErrorDiagnosisAgent()
        self.knowledge_retriever = KnowledgeRetriever()
        self.report_generator = ReportGenerator()
        # in-memory cache: diagnosis_id → (html, timestamp)
        self._report_cache: Dict[str, Tuple[str, float]] = {}

    async def stream_diagnosis(
        self,
        zip_content: bytes,
        zip_filename: str,
        request: JCLDiagnosisRequest,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """전체 진단 파이프라인 실행 (SSE 스트리밍)

        Yields:
            Dict: SSE 이벤트 (type + payload)
        """
        diagnosis_id = f"diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        try:
            # ──── ① File Processor ────
            yield self._event(DiagnosisEventType.FILE_EXTRACTED, {
                "message": f"zip ファイル解凍中... ({zip_filename})",
                "diagnosis_id": diagnosis_id
            })

            classified = await self.file_processor.process(zip_content, zip_filename)

            yield self._event(DiagnosisEventType.FILE_CLASSIFIED, {
                "total_files": classified.total_files,
                "jcl": len(classified.jcl_files),
                "proc": len(classified.proc_files),
                "jesmsg": len(classified.jesmsg_files),
                "sysmsg": len(classified.sysmsg_files),
                "sysprint": len(classified.sysprint_files),
                "unknown": len(classified.unknown_files),
                "files": [f.filename for f in classified.files]
            })

            # ──── ② JCL Analyzer ────
            job_analysis = await self.jcl_analyzer.analyze(
                jcl_files=classified.jcl_files,
                proc_files=classified.proc_files,
                jesjcl_files=classified.jesjcl_files,
            )

            # JCL 파싱 실패 시 JESMSG/SYSMSG에서 JOB 정보 복원
            # (OpenFrame JESJCL은 parse tree 형식이라 JCL 파싱 실패 가능)
            if job_analysis.job_name == "UNKNOWN" and job_analysis.total_steps == 0:
                logger.info(
                    "JCL parsing returned UNKNOWN - "
                    "attempting recovery from JESMSG/SYSMSG"
                )
                job_analysis = await self.jcl_analyzer.analyze_from_spool_metadata(
                    jesmsg_files=classified.jesmsg_files,
                    sysmsg_files=classified.sysmsg_files,
                )

            # JESMSG에서 STEP별 RC 보완
            for jesmsg in classified.jesmsg_files:
                job_analysis = self.jcl_analyzer.update_step_results_from_jesmsg(
                    job_analysis, jesmsg.content
                )

            # SYSMSG에서 STEP별 RC 보완 (JRN0065I RC 패턴)
            for sysmsg in classified.sysmsg_files:
                job_analysis = self.jcl_analyzer.update_step_results_from_sysmsg(
                    job_analysis, sysmsg.content
                )

            yield self._event(DiagnosisEventType.JCL_PARSED, {
                "job_name": job_analysis.job_name,
                "total_steps": job_analysis.total_steps,
                "steps": [
                    {"name": s.step_name, "pgm": s.program, "proc": s.procedure}
                    for s in job_analysis.steps
                ]
            })

            yield self._event(DiagnosisEventType.STEP_FLOW, {
                "steps": [
                    {
                        "step_number": s.step_number,
                        "step_name": s.step_name,
                        "program": s.program or s.procedure,
                        "status": s.status.value,
                        "return_code": s.return_code
                    }
                    for s in job_analysis.steps
                ]
            })

            # ──── ③ Error Diagnosis ────
            diagnosis = await self.error_diagnosis.diagnose(
                jesmsg_files=classified.jesmsg_files,
                sysmsg_files=classified.sysmsg_files,
                sysprint_files=classified.sysprint_files,
                job_analysis=job_analysis,
            )

            if diagnosis.primary_error:
                yield self._event(DiagnosisEventType.ERROR_FOUND, {
                    "code": diagnosis.primary_error.code,
                    "type": diagnosis.primary_error.error_type,
                    "severity": diagnosis.severity.value,
                    "failed_step": diagnosis.failed_step.step_name if diagnosis.failed_step else None,
                    "message": diagnosis.primary_error.message_line,
                    "step_results": diagnosis.step_results,
                })

            # ──── ④ Knowledge Retriever ────
            yield self._event(DiagnosisEventType.SEARCHING_KNOWLEDGE, {
                "phase": "error_guide",
                "query": diagnosis.primary_error.code if diagnosis.primary_error else "general"
            })

            knowledge = await self.knowledge_retriever.search(diagnosis)

            for guide in knowledge.error_guides:
                yield self._event(DiagnosisEventType.SEARCH_RESULT, {
                    "source": guide.source_file or guide.module,
                    "code": guide.code,
                    "confidence": guide.confidence,
                    "description": guide.description[:200],
                })

            # ──── ⑤ Report Generator ────
            yield self._event(DiagnosisEventType.GENERATING_REPORT, {
                "phase": "llm_synthesis"
            })

            # LLM 토큰을 축적하면서 스트리밍
            accumulated_tokens: list[str] = []
            async for token_event in self.report_generator.stream_report(
                job_analysis=job_analysis,
                diagnosis=diagnosis,
                knowledge=knowledge,
                user_message=request.message,
                language=request.language,
            ):
                if token_event.get("type") == DiagnosisEventType.LLM_TOKEN.value:
                    accumulated_tokens.append(token_event.get("token", ""))
                yield token_event

            # ──── ⑥ HTML Report 생성 ────
            report_text = "".join(accumulated_tokens)
            full_report = DiagnosisReport(
                diagnosis_id=diagnosis_id,
                job_analysis=job_analysis,
                diagnosis_result=diagnosis,
                knowledge_result=knowledge,
                report_text=report_text,
                language=request.language,
                created_at=datetime.now().isoformat(),
            )

            html_service = get_html_report_service()
            try:
                report_data = html_service.render_data_only(full_report)
                report_html = html_service.render(full_report)
                full_report.report_data = report_data
                full_report.report_html = report_html
                # 캐시 저장
                self._report_cache[diagnosis_id] = (report_html, time.time())
                self._evict_expired_cache()
            except Exception as html_err:
                logger.warning(f"HTML report rendering failed: {html_err}")
                report_data = None

            # ──── 완료 ────
            complete_payload: Dict = {
                "diagnosis_id": diagnosis_id,
                "job_name": job_analysis.job_name,
                "severity": diagnosis.severity.value,
                "primary_error": diagnosis.primary_error.code if diagnosis.primary_error else None,
            }
            if report_data:
                complete_payload["report_data"] = report_data
            yield self._event(DiagnosisEventType.REPORT_COMPLETE, complete_payload)

        except Exception as e:
            logger.error(f"JCL diagnosis pipeline failed: {e}", exc_info=True)
            yield self._event(DiagnosisEventType.ERROR, {
                "message": str(e),
                "diagnosis_id": diagnosis_id,
            })

    def get_cached_report_html(self, diagnosis_id: str) -> Optional[str]:
        """캐시에서 HTML 리포트 조회. TTL 초과 시 None."""
        entry = self._report_cache.get(diagnosis_id)
        if entry is None:
            return None
        html, ts = entry
        if time.time() - ts > _REPORT_CACHE_TTL:
            del self._report_cache[diagnosis_id]
            return None
        return html

    def _evict_expired_cache(self) -> None:
        """만료된 캐시 엔트리 제거"""
        now = time.time()
        expired = [
            k for k, (_, ts) in self._report_cache.items()
            if now - ts > _REPORT_CACHE_TTL
        ]
        for k in expired:
            del self._report_cache[k]

    def _event(self, event_type: DiagnosisEventType, data: Dict) -> Dict:
        """SSE 이벤트 딕셔너리 생성"""
        return {"type": event_type.value, **data}


# ─── Singleton ────────────────────────────────────

_instance: Optional[JCLDiagnosisOrchestrator] = None

def get_jcl_diagnosis_orchestrator() -> JCLDiagnosisOrchestrator:
    global _instance
    if _instance is None:
        _instance = JCLDiagnosisOrchestrator()
    return _instance
