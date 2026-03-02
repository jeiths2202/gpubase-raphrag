"""Error Diagnosis Agent

SYSMSG/JESMSG에서 에러코드를 추출하고 실패 STEP을 특정합니다.

에러 패턴 레지스트리는 OF7 C 소스를 기반으로 작성:
  - tjesdef.h: Step status codes (N/A/S/U)
  - executor.c: ABEND flag (_run_abend, _run_step_abend)
  - errcode_tjes.dat: TJES error code ranges (-1 ~ -951)
  - msgcode_tjclrun.dat: JRN prefix messages
"""
import re
from typing import List, Optional, Tuple

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, JobAnalysis, DiagnosisResult, ExtractedError,
    SpoolFileType, StepStatus, ErrorSeverity, JobStep
)
from .abend_code_registry import ABEND_REGISTRY


class ErrorDiagnosisAgent:
    """SPOOL 로그에서 에러 추출 + 진단"""

    # ─── 에러 패턴 레지스트리 (우선순위 순) ─────
    ERROR_PATTERNS: List[Tuple[str, re.Pattern]] = [
        # System ABEND (최고 우선순위)
        ("abend_system", re.compile(r'(?:ABEND\s+)?(S[0-9A-F]{3,4})\b')),
        # User ABEND
        ("abend_user", re.compile(r'(?:ABEND\s+)?(U\d{4})\b')),
        # OpenFrame 고유 에러코드
        ("openframe", re.compile(r'\b(OFR\d+[EWI]?)\b')),
        # TJES 에러코드
        ("tjes", re.compile(r'\b(TJES\d+[EWI]?)\b')),
        # OFCOBOL 에러
        ("ofcobol", re.compile(r'\b(OFCOBOL-\d+)\b')),
        # Condition Code (RC)
        ("cond_code", re.compile(r'(?:COND\s+CODE|RC)\s*=?\s*(\d{4})')),
        # JES 시스템 메시지 (IEF)
        ("jes_msg", re.compile(r'\b(IEF\d{3}[IWE])\b')),
        # SORT 메시지 (ICE)
        ("sort_msg", re.compile(r'\b(ICE\d{3}[A-Z])\b')),
        # VSAM/SMS 메시지 (IGD)
        ("vsam_msg", re.compile(r'\b(IGD\d{3}[A-Z])\b')),
        # OpenFrame 에러코드 (음수)
        ("batch_error", re.compile(r'\b(-\d{4,5})\b')),
    ]

    async def diagnose(
        self,
        jesmsg_files: List[ClassifiedFile],
        sysmsg_files: List[ClassifiedFile],
        sysprint_files: List[ClassifiedFile],
        job_analysis: JobAnalysis,
    ) -> DiagnosisResult:
        """에러 진단 실행

        1. 모든 SPOOL 파일에서 에러 패턴 추출
        2. 실패 STEP 특정 (에러 메시지 ↔ STEP 이름 교차 매칭)
        3. 심각도 분류 (ABEND > RC>=12 > RC>=8 > RC>=4)
        """
        all_errors: List[ExtractedError] = []

        # 파일 유형별 에러 추출 (우선순위: SYSMSG > JESMSG > SYSPRINT)
        for files, ftype in [
            (sysmsg_files, SpoolFileType.SYSMSG),
            (jesmsg_files, SpoolFileType.JESMSG),
            (sysprint_files, SpoolFileType.SYSPRINT),
        ]:
            for f in files:
                errors = self._extract_errors(f.content, f.filename, ftype)
                all_errors.extend(errors)

        if not all_errors:
            return DiagnosisResult(summary="エラーは検出されませんでした。")

        unique_errors = self._deduplicate(all_errors)
        primary = self._select_primary_error(unique_errors)
        failed_step = self._identify_failed_step(unique_errors, job_analysis.steps)
        step_results = self._build_step_results(unique_errors, job_analysis.steps)
        severity = self._assess_severity(primary)

        return DiagnosisResult(
            failed_step=failed_step,
            primary_error=primary,
            all_errors=unique_errors,
            step_results=step_results,
            severity=severity,
            summary=self._build_summary(primary, failed_step),
        )

    def _extract_errors(
        self, content: str, filename: str, source_type: SpoolFileType
    ) -> List[ExtractedError]:
        """단일 파일에서 에러 패턴 추출"""
        errors = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            for error_type, pattern in self.ERROR_PATTERNS:
                for match in pattern.finditer(line):
                    code = match.group(1)

                    # RC=0000은 에러가 아님
                    if error_type == "cond_code" and code == "0000":
                        continue

                    errors.append(ExtractedError(
                        code=code,
                        error_type=error_type,
                        message_line=line.strip(),
                        line_number=i + 1,
                        context_before=[
                            lines[j].strip()
                            for j in range(max(0, i - 2), i)
                        ],
                        context_after=[
                            lines[j].strip()
                            for j in range(i + 1, min(len(lines), i + 3))
                        ],
                        source_file=filename,
                        source_type=source_type,
                    ))

        return errors

    def _deduplicate(self, errors: List[ExtractedError]) -> List[ExtractedError]:
        """같은 에러코드는 최초 발견만 유지"""
        seen = set()
        result = []
        for e in errors:
            key = (e.code, e.error_type)
            if key not in seen:
                seen.add(key)
                result.append(e)
        return result

    def _select_primary_error(
        self, errors: List[ExtractedError]
    ) -> Optional[ExtractedError]:
        """심각도 순서로 주요 에러 선택"""
        priority = [
            "abend_system", "abend_user", "abend_app",
            "openframe", "tjes", "ofcobol",
            "cond_code", "batch_error",
            "jes_msg", "sort_msg", "vsam_msg",
        ]
        for ptype in priority:
            for e in errors:
                if e.error_type == ptype:
                    # cond_code는 RC>=8만 primary로 선택
                    if ptype == "cond_code":
                        try:
                            if int(e.code) < 8:
                                continue
                        except ValueError:
                            pass
                    return e
        return errors[0] if errors else None

    def _identify_failed_step(
        self,
        errors: List[ExtractedError],
        steps: List[JobStep],
    ) -> Optional[JobStep]:
        """에러 메시지에서 실패 STEP 특정"""
        step_names = {s.step_name: s for s in steps}

        for error in errors:
            if error.error_type in ("abend_system", "abend_user", "openframe", "tjes"):
                search_text = (
                    error.message_line + " " +
                    " ".join(error.context_before) + " " +
                    " ".join(error.context_after)
                )
                for sname, step in step_names.items():
                    if sname in search_text:
                        return step

        # 폴백: ABEND/ERROR 상태인 마지막 STEP
        for step in reversed(steps):
            if step.status in (
                StepStatus.ABEND_SYSTEM, StepStatus.ABEND_USER, StepStatus.ERROR
            ):
                return step

        return None

    def _build_step_results(
        self,
        errors: List[ExtractedError],
        steps: List[JobStep],
    ) -> dict:
        """STEP별 RC 딕셔너리 생성"""
        results = {}
        for step in steps:
            if step.return_code:
                results[step.step_name] = step.return_code
            else:
                results[step.step_name] = step.status.value
        return results

    def _assess_severity(self, primary: Optional[ExtractedError]) -> ErrorSeverity:
        """주요 에러의 심각도 판정"""
        if not primary:
            return ErrorSeverity.INFO

        if primary.error_type in ("abend_system", "abend_user", "abend_app"):
            return ErrorSeverity.CRITICAL

        if primary.error_type == "cond_code":
            try:
                rc = int(primary.code)
                if rc >= 12:
                    return ErrorSeverity.HIGH
                if rc >= 8:
                    return ErrorSeverity.MEDIUM
                return ErrorSeverity.LOW
            except ValueError:
                return ErrorSeverity.MEDIUM

        if primary.error_type in ("openframe", "tjes", "ofcobol"):
            return ErrorSeverity.HIGH

        return ErrorSeverity.MEDIUM

    def _build_summary(
        self,
        primary: Optional[ExtractedError],
        failed_step: Optional[JobStep],
    ) -> str:
        """진단 1줄 요약"""
        if not primary:
            return "エラーは検出されませんでした。"

        desc = ABEND_REGISTRY.get(primary.code, {}).get("description", "")

        step_info = ""
        if failed_step:
            pgm = failed_step.program or failed_step.procedure or ""
            step_info = f" (STEP: {failed_step.step_name}, PGM: {pgm})"

        return f"{primary.code}{' - ' + desc if desc else ''}{step_info}"
