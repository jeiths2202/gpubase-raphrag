"""HTML Report Template Service

DiagnosisReport (Pydantic) → report_schema JSON → self-contained HTML.
템플릿은 __REPORT_DATA_PLACEHOLDER__ / __LABELS_PLACEHOLDER__ 를
Python str.replace()로 치환합니다.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.api.models.jcl_diagnosis import (
    DiagnosisReport, JobAnalysis, DiagnosisResult, KnowledgeResult,
    StepStatus, ErrorSeverity,
)
from .abend_code_registry import ABEND_REGISTRY
from .locales import get_labels

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "diagnosis_report.html"

# StepStatus → report_schema status 매핑
_STATUS_MAP: Dict[StepStatus, str] = {
    StepStatus.NORMAL: "COMPLETED",
    StepStatus.WARNING: "COMPLETED",
    StepStatus.ERROR: "COMPLETED",
    StepStatus.ABEND_SYSTEM: "ABEND",
    StepStatus.ABEND_USER: "ABEND",
    StepStatus.ABEND_APP: "ABEND",
    StepStatus.SKIPPED: "SKIPPED",
    StepStatus.NOT_RUN: "SKIPPED",
}

# ErrorSeverity → report_schema severity 매핑 (대문자)
_SEVERITY_MAP: Dict[ErrorSeverity, str] = {
    ErrorSeverity.CRITICAL: "CRITICAL",
    ErrorSeverity.HIGH: "HIGH",
    ErrorSeverity.MEDIUM: "MEDIUM",
    ErrorSeverity.LOW: "LOW",
    ErrorSeverity.INFO: "LOW",
}


class HTMLReportService:
    """DiagnosisReport → self-contained HTML 변환 서비스"""

    def __init__(self) -> None:
        self._template_cache: Optional[str] = None

    def render(self, report: DiagnosisReport) -> str:
        """DiagnosisReport → 완전한 HTML 문자열 반환

        1. Pydantic → report_schema JSON 변환
        2. 언어별 LABELS 로드
        3. HTML 템플릿에 JSON + LABELS 주입
        """
        report_data = self._convert_to_report_schema(report)
        labels = get_labels(report.language)
        template = self._load_template()

        html = template.replace(
            "__REPORT_DATA_PLACEHOLDER__",
            json.dumps(report_data, ensure_ascii=False, indent=2),
        )
        html = html.replace(
            "__LABELS_PLACEHOLDER__",
            json.dumps(labels, ensure_ascii=False),
        )

        return html

    def render_data_only(self, report: DiagnosisReport) -> Dict:
        """report_schema JSON만 반환 (SSE 이벤트용, HTML 없이)"""
        return self._convert_to_report_schema(report)

    # ─── Schema Conversion ──────────────────────────────

    def _convert_to_report_schema(self, report: DiagnosisReport) -> Dict:
        """DiagnosisReport → report_schema.json 형식 변환"""
        job = report.job_analysis
        diag = report.diagnosis_result
        knowledge = report.knowledge_result

        # 완료된 STEP 수 계산
        completed_steps = sum(
            1 for s in job.steps
            if s.status in (StepStatus.NORMAL, StepStatus.WARNING, StepStatus.ERROR)
        )

        # 실패한 STEP 번호
        failed_step_number = (
            diag.failed_step.step_number if diag.failed_step else None
        )

        return {
            "report_meta": self._build_report_meta(report),
            "job_summary": self._build_job_summary(
                job, completed_steps, failed_step_number
            ),
            "step_flow": self._build_step_flow(job),
            "error_diagnosis": self._build_error_diagnosis(report, diag),
            "resolutions": self._build_resolutions(knowledge),
            "related_documents": self._build_related_documents(knowledge),
            "similar_cases": self._build_similar_cases(knowledge),
        }

    def _build_report_meta(self, report: DiagnosisReport) -> Dict:
        generated_at = report.created_at or datetime.now().isoformat()
        return {
            "report_id": f"RPT-{report.diagnosis_id}",
            "generated_at": generated_at,
            "generated_by": "JCL Diagnosis Agent v1.0",
            "kms_version": "TmaxSoft KMS 2.0",
        }

    def _build_job_summary(
        self, job: JobAnalysis, completed_steps: int, failed_step_number: Optional[int]
    ) -> Dict:
        # elapsed 계산 (start_time, end_time이 있는 STEP들에서)
        elapsed = self._calculate_elapsed(job)

        return {
            "job_name": job.job_name,
            "job_id": f"JOB-{job.job_name}",
            "job_class": job.job_class or "A",
            "priority": 10,
            "submit_time": self._get_first_step_time(job),
            "end_time": self._get_last_step_time(job),
            "elapsed": elapsed,
            "submitter": "BATCH",
            "system": "OFSYS01",
            "description": self._generate_job_description(job),
            "total_steps": job.total_steps,
            "completed_steps": completed_steps,
            "failed_step_number": failed_step_number,
        }

    def _build_step_flow(self, job: JobAnalysis) -> List[Dict]:
        steps = []
        for s in job.steps:
            schema_status = _STATUS_MAP.get(s.status, "SKIPPED")

            # input/output datasets 분류 (DD statements 기반)
            input_ds: list[str] = []
            output_ds: list[str] = []
            for dd in s.dd_statements:
                if dd.dsn:
                    disp = (dd.disp or "").upper()
                    if any(k in disp for k in ("OLD", "SHR")):
                        input_ds.append(dd.dsn)
                    elif any(k in disp for k in ("NEW", "OUT", "MOD")):
                        output_ds.append(dd.dsn)
                    else:
                        input_ds.append(dd.dsn)

            steps.append({
                "step_number": s.step_number,
                "step_name": s.step_name,
                "program": s.program or "UNKNOWN",
                "procedure": s.procedure,
                "description": f"STEP{s.step_number}: {s.step_name} ({s.program or s.procedure or '?'})",
                "status": schema_status,
                "cond_code": s.return_code,
                "elapsed": self._format_step_elapsed(s.cpu_time),
                "input_datasets": input_ds or None,
                "output_datasets": output_ds or None,
            })
        return steps

    def _build_error_diagnosis(
        self, report: DiagnosisReport, diag: DiagnosisResult
    ) -> Dict:
        primary = diag.primary_error
        error_code = primary.code if primary else "UNKNOWN"
        error_type = primary.error_type if primary else "unknown"

        # ABEND registry에서 카테고리 조회
        registry_entry = ABEND_REGISTRY.get(error_code, {})
        error_category = registry_entry.get("description", error_type)

        # severity 매핑
        severity = _SEVERITY_MAP.get(diag.severity, "MEDIUM")

        # 에러 메시지 수집
        error_messages = []
        for err in diag.all_errors[:5]:
            error_messages.append({
                "message_id": err.code,
                "text": err.message_line[:200],
                "timestamp": "",
            })

        # failed step 정보
        failed_step_str = ""
        failed_program = ""
        if diag.failed_step:
            failed_step_str = f"STEP{diag.failed_step.step_number} ({diag.failed_step.step_name})"
            failed_program = diag.failed_step.program or diag.failed_step.procedure or ""

        return {
            "error_code": error_code,
            "error_type": "ABEND" if "abend" in error_type else error_type.upper(),
            "error_category": error_category,
            "failed_step": failed_step_str,
            "failed_program": failed_program,
            "severity": severity,
            "error_messages": error_messages,
            "root_cause_analysis": report.report_text[:1000] if report.report_text else "",
            "impact": diag.summary or "",
        }

    def _build_resolutions(self, knowledge: KnowledgeResult) -> List[Dict]:
        resolutions = []
        for i, guide in enumerate(knowledge.error_guides[:5], start=1):
            # confidence → priority 매핑
            if guide.confidence > 0.9:
                priority = "HIGH"
            elif guide.confidence > 0.5:
                priority = "MEDIUM"
            else:
                priority = "LOW"

            resolutions.append({
                "step": i,
                "priority": priority,
                "action": guide.description[:100] if guide.description else guide.code,
                "detail": guide.solution or guide.cause or "",
                "command": None,
            })

        if not resolutions:
            resolutions.append({
                "step": 1,
                "priority": "MEDIUM",
                "action": "Refer to error documentation",
                "detail": "No specific resolution found. Please check the error code documentation.",
            })

        return resolutions

    def _build_related_documents(self, knowledge: KnowledgeResult) -> List[Dict]:
        docs = []
        for doc in knowledge.related_documents[:5]:
            docs.append({
                "title": doc.get("title", "Document"),
                "doc_id": doc.get("doc_id", doc.get("id", "")),
                "url": doc.get("url", "#"),
                "relevance": doc.get("relevance", 0.5),
            })
        # error guide 소스 파일도 문서로 추가
        for guide in knowledge.error_guides[:3]:
            if guide.source_file:
                docs.append({
                    "title": f"{guide.code} Error Guide",
                    "doc_id": f"DOC-ERR-{guide.code}",
                    "url": "#",
                    "relevance": guide.confidence,
                })
        return docs[:5]

    def _build_similar_cases(self, knowledge: KnowledgeResult) -> List[Dict]:
        cases = []
        for i, case in enumerate(knowledge.similar_cases[:3]):
            cases.append({
                "case_id": f"CASE-{datetime.now().year}-{1000 + i}",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "job_name": "",
                "error_code": case.error_code or "",
                "summary": case.description[:300],
                "resolution": case.resolution[:300],
            })
        return cases

    # ─── Helper Methods ─────────────────────────────────

    def _load_template(self) -> str:
        """HTML 템플릿 로드 (캐싱)"""
        if self._template_cache is None:
            try:
                self._template_cache = _TEMPLATE_PATH.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.error(f"Template not found: {_TEMPLATE_PATH}")
                raise
        return self._template_cache

    def _calculate_elapsed(self, job: JobAnalysis) -> str:
        """STEP들의 cpu_time 합산"""
        total_seconds = 0
        for s in job.steps:
            if s.cpu_time:
                try:
                    parts = s.cpu_time.replace("s", "").split("m")
                    if len(parts) == 2:
                        total_seconds += int(parts[0]) * 60 + int(parts[1])
                except (ValueError, IndexError):
                    pass
        if total_seconds > 0:
            m, s = divmod(total_seconds, 60)
            return f"{m}m {s}s"
        return "-"

    def _get_first_step_time(self, job: JobAnalysis) -> Optional[str]:
        for s in job.steps:
            if s.start_time:
                return s.start_time
        return None

    def _get_last_step_time(self, job: JobAnalysis) -> Optional[str]:
        for s in reversed(job.steps):
            if s.end_time:
                return s.end_time
        return None

    def _format_step_elapsed(self, cpu_time: Optional[str]) -> Optional[str]:
        return cpu_time if cpu_time else None

    def _generate_job_description(self, job: JobAnalysis) -> str:
        """JOB의 STEP 구성에서 설명 생성"""
        step_names = [s.step_name for s in job.steps[:4]]
        if step_names:
            return f"Batch Job: {' → '.join(step_names)}"
        return f"Batch Job: {job.job_name}"


# ─── Singleton ────────────────────────────────────

_instance: Optional[HTMLReportService] = None


def get_html_report_service() -> HTMLReportService:
    global _instance
    if _instance is None:
        _instance = HTMLReportService()
    return _instance
