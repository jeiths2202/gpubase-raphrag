"""JCL Analyzer Agent

JCL 파싱 + STEP 흐름 분석을 수행합니다.

주요 역할:
  - JOB 카드 파싱 → JOB 이름/클래스/MSGCLASS
  - EXEC 문 기준 STEP 순서 + 프로그램 + DD 매핑
  - PROC 참조 확인
  - JESMSG에서 STEP별 RC 추출 (파싱 보완)
  - JESMSG/SYSMSG에서 JOB 정보 복원 (JCL 미발견 시)

참조: OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf 第4章 スプール
  - INPJCL: 원본 JCL
  - JESJCL: JCL 구문해석 트리 (표준 JCL 아님)
  - CONVJCL: 프로시저 전개된 JCL (XX/++/X/ prefix)
  - JESMSG: JOB INFO + STEP INFO (JOB NAME, STATUS, STEP별 DD/IO)
  - SYSMSG: JRN 메시지 (RC, ABEND, EXEC PGM 정보)
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, JobAnalysis, JobStep, DDStatement, StepStatus, JobStatus
)

logger = logging.getLogger(__name__)


class JCLAnalyzer:
    """JCL 파싱 + STEP 흐름 분석"""

    # STEP RC 추출 패턴 (JESMSG에서)
    _RC_PATTERN = re.compile(
        r'(\w+)\s+(?:RC=(\d{4})|COND\s+CODE\s*=?\s*(\d{4})|(S[0-9A-F]{3,4})|(U\d{4}))'
    )

    # JOB 카드 패턴
    _JOB_PATTERN = re.compile(
        r'^//(\w+)\s+JOB\s+(.*)', re.MULTILINE
    )

    # EXEC 문 패턴
    _EXEC_PATTERN = re.compile(
        r'^//(\w*)\s+EXEC\s+(.*)', re.MULTILINE
    )

    # DD 문 패턴
    _DD_PATTERN = re.compile(
        r'^//(\w+)\s+DD\s+(.*)', re.MULTILINE
    )

    async def analyze(
        self,
        jcl_files: List[ClassifiedFile],
        proc_files: List[ClassifiedFile],
        jesjcl_files: List[ClassifiedFile],
    ) -> JobAnalysis:
        """JCL 파싱 → JobAnalysis 생성

        우선순위: JESJCL (전개済) > JCL (원본) > PROC
        """
        jcl_content = self._select_best_jcl(jcl_files, jesjcl_files)
        if not jcl_content:
            return JobAnalysis(job_name="UNKNOWN", total_steps=0)

        job_name, job_params = self._parse_job_card(jcl_content)
        steps = self._parse_steps(jcl_content)
        procs = [s.procedure for s in steps if s.procedure]
        datasets = self._extract_datasets(jcl_content)

        return JobAnalysis(
            job_name=job_name,
            job_class=job_params.get("CLASS"),
            msgclass=job_params.get("MSGCLASS"),
            msglevel=job_params.get("MSGLEVEL"),
            notify=job_params.get("NOTIFY"),
            steps=steps,
            procs_referenced=list(set(procs)),
            datasets_used=datasets,
            total_steps=len(steps),
            raw_jcl=jcl_content,
        )

    def _select_best_jcl(
        self,
        jcl_files: List[ClassifiedFile],
        jesjcl_files: List[ClassifiedFile],
    ) -> Optional[str]:
        """JCL 선택 (OpenFrame TJES SPOOL 구조 기반)

        OpenFrame JESJCL = JCL 구문해석 트리 (표준 JCL 아님)
        → "JOB STREAM=[...], JOBPOS=[0]" 형식의 트리 표현
        CONVJCL = 프로시저 전개된 JCL (XX/++/X/ prefix)
        INPJCL = 원본 JCL (//JOBNAME JOB ... 표준 형식)

        우선순위: 표준 JCL 형식 포함 JESJCL > INPJCL > None
        """
        # JESJCL이 표준 JCL 형식인지 검증 (CONVJCL은 여기에 포함될 수 있음)
        for f in jesjcl_files:
            if self._JOB_PATTERN.search(f.content):
                return f.content
        # OpenFrame JESJCL은 parse tree → INPJCL(원본 JCL) 사용
        if jcl_files:
            return jcl_files[0].content
        return None

    def _parse_job_card(self, jcl: str) -> tuple:
        """JOB 문 파싱 → (job_name, params_dict)"""
        match = self._JOB_PATTERN.search(jcl)
        if not match:
            return "UNKNOWN", {}

        job_name = match.group(1)
        params_str = match.group(2)
        params = self._parse_keyword_params(params_str)
        return job_name, params

    def _parse_steps(self, jcl: str) -> List[JobStep]:
        """EXEC 문 기준 STEP 파싱"""
        steps = []
        step_num = 0

        for match in self._EXEC_PATTERN.finditer(jcl):
            step_num += 1
            step_name = match.group(1) or f"STEP{step_num:02d}"
            exec_params = match.group(2).strip()

            program = None
            procedure = None

            if exec_params.startswith("PGM="):
                program = exec_params.split("PGM=")[1].split(",")[0].split()[0]
            elif exec_params.startswith("PROC="):
                procedure = exec_params.split("PROC=")[1].split(",")[0].split()[0]
            else:
                # EXEC procname (PROC= 생략 형태)
                procedure = exec_params.split(",")[0].split()[0]

            # COND 파라미터 추출
            cond = None
            params = self._parse_keyword_params(exec_params)
            if "COND" in params:
                cond = params["COND"]

            dd_stmts = self._extract_dd_for_step(jcl, step_name)

            steps.append(JobStep(
                step_number=step_num,
                step_name=step_name,
                program=program,
                procedure=procedure,
                dd_statements=dd_stmts,
                cond_parameter=cond,
            ))

        return steps

    def update_step_results_from_jesmsg(
        self,
        job_analysis: JobAnalysis,
        jesmsg_content: str,
    ) -> JobAnalysis:
        """JESMSG에서 STEP별 RC를 추출하여 JobAnalysis에 반영

        JESMSG 포맷 (tjes_runner_step.c 참조):
        - 정상: "STEP01  RC=0000"
        - ABEND: "STEP03  S0C7"
        """
        rc_map = {}
        for match in self._RC_PATTERN.finditer(jesmsg_content):
            step_name = match.group(1)
            rc = match.group(2) or match.group(3)  # RC= or COND CODE=
            abend_s = match.group(4)  # System ABEND
            abend_u = match.group(5)  # User ABEND

            if rc:
                rc_map[step_name] = rc
            elif abend_s:
                rc_map[step_name] = abend_s
            elif abend_u:
                rc_map[step_name] = abend_u

        # STEP에 RC 반영
        found_failure = False
        for step in job_analysis.steps:
            rc_value = rc_map.get(step.step_name)
            if rc_value:
                step.return_code = rc_value
                step.status = self._rc_to_status(rc_value)
                if step.status in (StepStatus.ABEND_SYSTEM, StepStatus.ABEND_USER, StepStatus.ERROR):
                    found_failure = True
            elif found_failure:
                step.status = StepStatus.NOT_RUN

        job_analysis.job_status = (
            JobStatus.ERROR if found_failure else JobStatus.DONE
        )
        return job_analysis

    def _rc_to_status(self, rc: str) -> StepStatus:
        """RC 값 → StepStatus 변환 (tjesdef.h 매핑)"""
        if rc.startswith("S"):
            return StepStatus.ABEND_SYSTEM
        if rc.startswith("U"):
            return StepStatus.ABEND_USER
        try:
            code = int(rc)
            if code == 0:
                return StepStatus.NORMAL
            elif code <= 4:
                return StepStatus.WARNING
            else:
                return StepStatus.ERROR
        except ValueError:
            return StepStatus.ERROR

    def _parse_keyword_params(self, params_str: str) -> dict:
        """JCL 키워드 파라미터 파싱 (KEY=VALUE 형식)"""
        result = {}
        # 괄호 내부는 쉼표 분리 제외
        parts = re.split(r',(?![^()]*\))', params_str)
        for part in parts:
            part = part.strip()
            if "=" in part:
                key, _, value = part.partition("=")
                result[key.strip()] = value.strip()
        return result

    def _extract_dd_for_step(self, jcl: str, step_name: str) -> List[DDStatement]:
        """특정 STEP에 속하는 DD 문 추출"""
        dd_stmts = []
        in_step = False
        for line in jcl.split("\n"):
            if re.match(rf'^//{re.escape(step_name)}\s+EXEC\s', line):
                in_step = True
                continue
            if in_step and re.match(r'^//\w+\s+EXEC\s', line):
                break
            if in_step:
                dd_match = self._DD_PATTERN.match(line)
                if dd_match:
                    dd_name = dd_match.group(1)
                    dd_params = self._parse_keyword_params(dd_match.group(2))
                    dd_stmts.append(DDStatement(
                        dd_name=dd_name,
                        dsn=dd_params.get("DSN"),
                        disp=dd_params.get("DISP"),
                        sysout=dd_params.get("SYSOUT"),
                    ))
        return dd_stmts

    def _extract_datasets(self, jcl: str) -> List[str]:
        """JCL 전체에서 DSN= 값 추출"""
        return list(set(re.findall(r'DSN=([A-Z0-9.&()]+)', jcl, re.IGNORECASE)))

    # ─── JESMSG/SYSMSG 기반 JOB 정보 복원 ────────────────────────

    # JESMSG 포맷 (TJES Guide 第4章):
    #   JOB  NAME  : J077305A
    #   JOB  CLASS : A , JOB STATUS : F(+09551) , JOB  PRTY : 5
    #   STEP : [EZTPTST]  또는  STEP : [STEP01/PS010]
    _JESMSG_JOB_NAME = re.compile(r'JOB\s+NAME\s*:\s*(\S+)')
    _JESMSG_JOB_STATUS = re.compile(r'JOB\s+STATUS\s*:\s*([A-Z])\(([^)]*)\)')
    _JESMSG_JOB_CLASS = re.compile(r'JOB\s+CLASS\s*:\s*(\S+)')
    _JESMSG_JOB_ID = re.compile(r'JOB\s+ID\s*:\s*(\S+)')
    _JESMSG_STEP = re.compile(r'STEP\s*:\s*\[([^\]]+)\]')

    # SYSMSG 포맷:
    #   --- EZTPTST EXEC PGM step ---  또는  --- STEP01 EXEC PROC step ---
    #   EXEC PGM=EZTPA00
    #   (JRN0065I) PS010 EXEC PGM step done with RC=0
    #   (JRN3011E) CPU TIME OVER. Cpu time(3600s) exceed JOB TIME value(3600s)
    #   (JRN0333I) JOB is enqueued for output processing - JOBID=JOB02235, ABEND=1
    _SYSMSG_STEP_HEADER = re.compile(
        r'-+\s+(\w+)\s+EXEC\s+(PGM|PROC)\s+step\s+-+'
    )
    _SYSMSG_EXEC_PGM = re.compile(r'^\s*EXEC\s+PGM=(\S+)', re.MULTILINE)
    _SYSMSG_RC_DONE = re.compile(
        r'\(JRN0065I\)\s+(\w+)\s+EXEC\s+PGM\s+step\s+done\s+with\s+RC=(\d+)'
    )
    _SYSMSG_ABEND_FLAG = re.compile(
        r'\(JRN0333I\).*ABEND=(\d+)'
    )
    _SYSMSG_JRN_ERROR = re.compile(
        r'\((JRN\d{4}E)\)\s+(.*)'
    )

    async def analyze_from_spool_metadata(
        self,
        jesmsg_files: List[ClassifiedFile],
        sysmsg_files: List[ClassifiedFile],
    ) -> JobAnalysis:
        """JCL 파일 없이 JESMSG/SYSMSG에서 JOB 정보를 복원

        TJES Guide 第4章 기반:
        - JESMSG: JOB INFO (JOB NAME, STATUS), STEP INFO (STEP명, DD/IO)
        - SYSMSG: JRN 메시지 (STEP 실행 흐름, RC, ABEND, EXEC PGM)
        """
        jesmsg = "\n".join(f.content for f in jesmsg_files)
        sysmsg = "\n".join(f.content for f in sysmsg_files)

        # ── JESMSG에서 JOB 메타데이터 추출 ──
        job_name = "UNKNOWN"
        job_class = None
        job_status_code = None
        job_status_detail = None

        m = self._JESMSG_JOB_NAME.search(jesmsg)
        if m:
            job_name = m.group(1)

        m = self._JESMSG_JOB_CLASS.search(jesmsg)
        if m:
            job_class = m.group(1).rstrip(",")

        m = self._JESMSG_JOB_STATUS.search(jesmsg)
        if m:
            job_status_code = m.group(1)   # D=Done, F=Failed
            job_status_detail = m.group(2)  # R00000, +09551 등

        # ── SYSMSG에서 STEP 실행 흐름 추출 ──
        steps = self._parse_steps_from_sysmsg(sysmsg)

        # ── JESMSG STEP INFO로 보완 (DD/IO 정보) ──
        jesmsg_steps = [m.group(1) for m in self._JESMSG_STEP.finditer(jesmsg)]
        if not steps and jesmsg_steps:
            for i, sname in enumerate(jesmsg_steps, 1):
                # "STEP01/PS010" → step_name="STEP01", sub="PS010"
                parts = sname.split("/")
                steps.append(JobStep(
                    step_number=i,
                    step_name=parts[0],
                    program=None,
                    procedure=parts[1] if len(parts) > 1 else None,
                ))

        # ── JOB 상태 결정 ──
        job_status = JobStatus.DONE
        if job_status_code == "F":
            job_status = JobStatus.ERROR
        elif any(s.status in (StepStatus.ABEND_SYSTEM, StepStatus.ABEND_USER,
                              StepStatus.ERROR) for s in steps):
            job_status = JobStatus.ERROR

        # ABEND 플래그 확인
        abend_match = self._SYSMSG_ABEND_FLAG.search(sysmsg)
        if abend_match and int(abend_match.group(1)) > 0:
            job_status = JobStatus.ERROR

        logger.info(
            "Recovered JOB info from SPOOL metadata: "
            f"name={job_name}, status={job_status.value}, "
            f"steps={len(steps)}, status_detail={job_status_detail}"
        )

        return JobAnalysis(
            job_name=job_name,
            job_class=job_class,
            steps=steps,
            total_steps=len(steps),
            job_status=job_status,
        )

    def _parse_steps_from_sysmsg(self, sysmsg: str) -> List[JobStep]:
        """SYSMSG에서 STEP 실행 흐름 파싱

        패턴:
          --- EZTPTST EXEC PGM step ---
          EXEC PGM=EZTPA00
          ...
          (JRN0065I) EZTPTST EXEC PGM step done with RC=0
        """
        steps: List[JobStep] = []
        step_num = 0
        lines = sysmsg.split("\n")

        # Pass 1: STEP 헤더에서 step_name + type(PGM/PROC) 추출
        step_entries: List[Dict] = []
        for i, line in enumerate(lines):
            m = self._SYSMSG_STEP_HEADER.search(line)
            if m:
                step_entries.append({
                    "step_name": m.group(1),
                    "exec_type": m.group(2),  # PGM or PROC
                    "line_idx": i,
                    "program": None,
                    "rc": None,
                })

        # Pass 2: 각 STEP 영역에서 EXEC PGM=xxx 와 RC 추출
        for idx, entry in enumerate(step_entries):
            start = entry["line_idx"]
            end = step_entries[idx + 1]["line_idx"] if idx + 1 < len(step_entries) else len(lines)
            block = "\n".join(lines[start:end])

            pgm_match = self._SYSMSG_EXEC_PGM.search(block)
            if pgm_match:
                entry["program"] = pgm_match.group(1)

            rc_match = self._SYSMSG_RC_DONE.search(block)
            if rc_match:
                entry["rc"] = rc_match.group(2)

        # 중복 제거: 같은 step_name이 두 번 나타남
        # (SYSMSG에서 scan pass + exec pass로 2회 출력)
        # 마지막 출현 (exec pass)을 사용
        seen: Dict[str, Dict] = {}
        for entry in step_entries:
            existing = seen.get(entry["step_name"])
            if existing is None or entry["program"] is not None:
                seen[entry["step_name"]] = entry

        for sname, entry in seen.items():
            step_num += 1
            rc_str = entry.get("rc")
            status = StepStatus.NOT_RUN
            if rc_str is not None:
                status = self._rc_to_status(rc_str)

            program = entry.get("program")
            procedure = None
            if entry["exec_type"] == "PROC":
                procedure = program
                program = None

            steps.append(JobStep(
                step_number=step_num,
                step_name=sname,
                program=program,
                procedure=procedure,
                return_code=rc_str,
                status=status,
            ))

        # JRN 에러 → SYSMSG 내 위치로 실제 발생 STEP 특정
        error_step_names: set = set()
        for m in self._SYSMSG_JRN_ERROR.finditer(sysmsg):
            error_msg = m.group(2)
            if "TIME OVER" in error_msg or "ABEND" in error_msg:
                error_pos = m.start()
                error_line = sysmsg[:error_pos].count("\n")
                # step_entries에서 에러 라인이 속하는 STEP 찾기
                owning_step = None
                for entry in step_entries:
                    if entry["line_idx"] <= error_line:
                        owning_step = entry["step_name"]
                    else:
                        break
                if owning_step:
                    error_step_names.add(owning_step)

        for step in steps:
            if step.step_name in error_step_names:
                step.status = StepStatus.ERROR

        # ABEND 플래그 → 에러 STEP을 ABEND로 승격
        abend_match = self._SYSMSG_ABEND_FLAG.search(sysmsg)
        if abend_match and int(abend_match.group(1)) > 0:
            if error_step_names:
                for step in steps:
                    if step.step_name in error_step_names:
                        step.status = StepStatus.ABEND_SYSTEM
            else:
                # 폴백: 프로그램이 있는 마지막 실행 STEP
                for step in reversed(steps):
                    if step.program is not None:
                        step.status = StepStatus.ABEND_SYSTEM
                        break

        return steps

    def update_step_results_from_sysmsg(
        self,
        job_analysis: JobAnalysis,
        sysmsg_content: str,
    ) -> JobAnalysis:
        """SYSMSG JRN 메시지에서 STEP별 RC를 보완

        JRN0065I 패턴: (JRN0065I) <step> EXEC PGM step done with RC=<n>
        JRN####E 에러: SYSMSG 내 step 섹션 위치로 발생 STEP 특정
        """
        for m in self._SYSMSG_RC_DONE.finditer(sysmsg_content):
            step_name = m.group(1)
            rc = m.group(2)
            for step in job_analysis.steps:
                if step.step_name == step_name and not step.return_code:
                    step.return_code = rc
                    step.status = self._rc_to_status(rc)

        # SYSMSG 내 step 섹션 위치 맵 구축 (에러 발생 STEP 특정용)
        # SYSMSG는 "--- STEPNAME EXEC PGM step ---" 헤더로 섹션 구분
        step_sections: List[Tuple[str, int]] = []
        lines = sysmsg_content.split("\n")
        for i, line in enumerate(lines):
            m = self._SYSMSG_STEP_HEADER.search(line)
            if m:
                step_sections.append((m.group(1), i))

        def _find_step_at_line(line_num: int) -> Optional[str]:
            """특정 라인이 속하는 STEP 이름 반환"""
            result = None
            for sname, sline in step_sections:
                if sline <= line_num:
                    result = sname
                else:
                    break
            return result

        # JRN 에러 → SYSMSG 내 위치로 실제 발생 STEP 특정
        error_step_names: set = set()
        for m in self._SYSMSG_JRN_ERROR.finditer(sysmsg_content):
            error_msg = m.group(2)
            if "TIME OVER" in error_msg or "ABEND" in error_msg:
                # 에러가 발생한 라인 번호 계산
                error_pos = m.start()
                error_line = sysmsg_content[:error_pos].count("\n")
                step_name = _find_step_at_line(error_line)
                if step_name:
                    error_step_names.add(step_name)

        # 에러 STEP 마킹
        for step in job_analysis.steps:
            if step.step_name in error_step_names:
                step.status = StepStatus.ERROR

        # ABEND 플래그 → 에러 STEP을 ABEND로 승격
        abend_match = self._SYSMSG_ABEND_FLAG.search(sysmsg_content)
        if abend_match and int(abend_match.group(1)) > 0:
            job_analysis.job_status = JobStatus.ERROR
            if error_step_names:
                for step in job_analysis.steps:
                    if step.step_name in error_step_names:
                        step.status = StepStatus.ABEND_SYSTEM
            else:
                # 에러 STEP 특정 불가 시 최후 수단: EXEC PGM 이 있는 마지막 STEP
                for step in reversed(job_analysis.steps):
                    if step.status in (StepStatus.NOT_RUN, StepStatus.ERROR):
                        step.status = StepStatus.ABEND_SYSTEM
                        break

        return job_analysis
