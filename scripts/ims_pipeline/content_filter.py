"""
IMS 이슈 텍스트 콘텐츠 필터.
RAG 임베딩 품질을 위해 기술적으로 유의미한 정보만 추출.

보존: 타이틀, 제품명, 모듈명, 버전, 문의내용, 응답내용, 최종 진행상태
제거: 고객사명, 프로젝트명, 인사말, 인명, 조직명, 워크플로우 요청
"""

import html
import re
from pathlib import Path

# ── 제거 대상 패턴 ────────────────────────────────────────────────

# Subject에서 제거할 대괄호 태그 (프로젝트명, 고객사명)
_RE_SUBJECT_BRACKETS = re.compile(
    r'\[(Project|PoC|Enhancement|Bug|일본[^\]]*|한국[^\]]*|미국[^\]]*|중국[^\]]*|'
    r'[^\]]*법인[^\]]*|[^\]]*은행[^\]]*|[^\]]*보험[^\]]*|[^\]]*증권[^\]]*|'
    r'[^\]]*프로젝트[^\]]*|[^\]]*사이트[^\]]*)\]\s*',
    re.IGNORECASE,
)

# 인사말/자기소개 패턴 (행 시작부)
_RE_GREETING = re.compile(
    r'^(?:'
    r'안녕하세요[\.\s,]*(?:[가-힣A-Za-z\s]*(?:입니다|입니다\.|입니다\s))?|'
    r'수고하십니다[\.\s,]*(?:[가-힣A-Za-z\s]*(?:입니다|입니다\.|입니다\s))?|'
    r'수고하세요[\.\s,]*|'
    r'[가-힣A-Za-z\s]{2,20}입니다[\.\s]*'
    r')',
    re.MULTILINE,
)

# @멘션 (이름 + 직함) — 조직 포함
_RE_MENTION = re.compile(
    r'@\s*(?:GBSC\s*(?:개발\s*)?\d*\s*파트\s*)?'
    r'[가-힣A-Za-z_\s]{2,15}'
    r'(?:연구원|매니저|파트장|팀장|수석|책임|선임|대리)님?',
)

# 조직+자기소개 패턴
_RE_ORG = re.compile(
    r'(?:GBSC\s*(?:개발\s*)?\d*\s*파트|일본\s*법인|한국\s*법인|사업수행\s*\d*파트)\s*'
    r'[가-힣]{2,5}(?:입니다|입니다\.)',
)

# 순수 워크플로우 노이즈 (행 전체가 이것만인 경우)
_WORKFLOW_PHRASES = [
    '이슈 종료 합니다',
    '이슈 종료합니다',
    'close 부탁',
    'CLOSE 부탁',
    'close부탁',
    'close 하도록',
    'close하도록',
    '핸들러 인계',
    '핸들러를 인계',
    '확인 부탁드립니다',
    '확인부탁드립니다',
    '확인 부탁 드립니다',
    '잘부탁드리겠습니다',
    '잘 부탁드리겠습니다',
    '지원 감사합니다',
    '지원해 주셔서 감사',
    '지원 해 주셔서 감사',
    '대응 감사드립니다',
    '답변 감사드립니다',
    '답변 주셔서 감사',
]

# 기술 콘텐츠 지표 (이런 패턴이 있으면 기술적 가치가 있는 항목)
_TECH_INDICATORS = [
    # 에러/로그
    r'(?:error|에러|오류|에러코드|rc=|ABEND|abend)',
    r'(?<![A-Za-z])-\d{4,5}(?!\d)',        # 에러 코드 -5212
    r'\bS[0-9][0-9A-F]{2}\b',               # ABEND S0C7
    r'(?:syntax error|runtime error|compile error|compilation error)',
    # 명령어/도구
    r'\b[a-z]{2,10}mgr\b',
    r'\b(?:dsmigin|dsmigout|cobgensch|ofcob|ofasm|jybfg000|aimcmd)\b',
    r'\b(?:IDCAMS|IEBGENER|IEBCOPY|SORT|DFSORT)\b',
    # 설정/파일
    r'\b(?:oframe|tjes|hidb|osc|tacf|ds|batch)\.conf\b',
    r'\b(?:OPENFRAME_HOME|COBDIR|TMAXDIR)\b',
    # 코드/기술 상세
    r'(?:패치|patch|PATCH|핫패치)',
    r'(?:원인|원인은|문제는|현상은|증상)',
    r'(?:수정|수정하|해결|조치|대응)',
    r'(?:컴파일|compile|COMPILE)',
    r'(?:버전|version|VERSION)\s*[:=]?\s*[\d.]+',
    r'(?:module|MODULE)\s*[:=]?\s*\w+',
    r'<<git log>>',
    r'commit\s+[0-9a-f]{10,}',
    r'\b(?:COBOL|JCL|PSAM|VSAM|CICS|BMS|REXX|PL/I|ASM)\b',
    r'\b(?:VALUE|FIELD|POS|FD|EXEC|DD|JOB)\s*[=(]',
    # 로그 출력
    r'\[\d{4}-\d{2}-\d{2}T',
    r'\b(?:slog|syslog|ofrcmsvr|err로그)\b',
    # 재현/테스트
    r'(?:재현|동일 현상|정상 동작|정상적으로|비정상)',
    r'(?:기능테스트|회귀테스트|검증|QA 환경)',
]
_RE_TECH_INDICATORS = [re.compile(p, re.IGNORECASE) for p in _TECH_INDICATORS]

# 순수 노이즈 항목 판별 패턴 (기술 지표 없이 이것만 있으면 제거)
_NOISE_ONLY_PATTERNS = [
    r'^[\s@가-힣A-Za-z,.\s]*(?:감사합니다|감사드립니다)[\.\s]*$',
    r'^[\s@가-힣A-Za-z,.\s]*(?:close|CLOSE|종료)[\s]*(?:부탁|하도록|합니다|하겠습니다)[\s\.]*(?:감사합니다)?[\.\s]*$',
    r'^[\s@가-힣A-Za-z,.\s]*(?:핸들러|handler)[\s]*(?:인계|전달)[\s가-힣A-Za-z@,.\s]*$',
    r'^[\s@가-힣A-Za-z,.\s]*(?:잘\s*부탁|확인\s*부탁|확인\s*감사|개발일정\s*확인\s*감사)[\s가-힣A-Za-z@,.\s]*$',
]
_RE_NOISE_ONLY = [re.compile(p, re.DOTALL) for p in _NOISE_ONLY_PATTERNS]


# ── HTML 엔티티 디코딩 ────────────────────────────────────────────

def _decode_html_entities(text: str) -> str:
    """HTML 엔티티 + 숫자 참조 디코딩."""
    text = html.unescape(text)
    # html.unescape가 놓칠 수 있는 추가 패턴
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)
    return text


# ── 라인 레벨 클리닝 ─────────────────────────────────────────────

def _clean_line(line: str) -> str:
    """단일 라인에서 인사말, @멘션, 조직 소속 제거."""
    line = _RE_MENTION.sub('', line)
    line = _RE_ORG.sub('', line)
    line = _RE_GREETING.sub('', line)
    # 정리 후 남은 공백/구두점
    line = re.sub(r'^[\s,.\s]+', '', line)
    return line.strip()


def _has_tech_content(text: str) -> bool:
    """기술적 내용이 포함되어 있는지 판별."""
    for pat in _RE_TECH_INDICATORS:
        if pat.search(text):
            return True
    return False


def _is_noise_only(text: str) -> bool:
    """순수 노이즈(인사+워크플로우만) 항목인지 판별."""
    cleaned = text.strip()
    if len(cleaned) < 10:
        return True

    for pat in _RE_NOISE_ONLY:
        if pat.match(cleaned):
            return True

    # 워크플로우 문구만으로 구성된 경우
    lower = cleaned.lower()
    for phrase in _WORKFLOW_PHRASES:
        if phrase.lower() in lower:
            # 워크플로우 문구 제거 후 실질 콘텐츠가 남는지 확인
            remaining = lower.replace(phrase.lower(), '').strip()
            remaining = re.sub(r'[\s@가-힣,.。、\s감사합니다드립니다입니다님]+', '', remaining)
            if len(remaining) < 15:
                return True

    return False


# ── Subject 클리닝 ───────────────────────────────────────────────

def _clean_subject(subject: str) -> str:
    """Subject에서 프로젝트/고객사 태그 제거, 공백 정리."""
    subject = _RE_SUBJECT_BRACKETS.sub('', subject)
    subject = re.sub(r'\s+', ' ', subject).strip()
    return subject


# ── 조치 이력 필터링 ─────────────────────────────────────────────

def _filter_action_entries(action_text: str) -> list[str]:
    """
    조치 이력을 --- 기준으로 분할하고 기술적 가치가 있는 항목만 반환.
    각 항목 내 인사말/멘션도 제거.
    """
    entries = re.split(r'\n---\n|\n---$|^---\n', action_text)
    filtered = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # 순수 노이즈면 스킵
        if _is_noise_only(entry):
            continue

        # 기술 콘텐츠가 없으면 스킵
        if not _has_tech_content(entry):
            # 길이가 충분히 길면 (200자+) 유지 — 상세 설명일 수 있음
            if len(entry) < 200:
                continue

        # 라인 단위 클리닝
        lines = entry.split('\n')
        cleaned_lines = []
        for line in lines:
            cl = _clean_line(line)
            if cl:
                cleaned_lines.append(cl)

        if cleaned_lines:
            cleaned_entry = '\n'.join(cleaned_lines)
            # 클리닝 후에도 실질 콘텐츠가 있는지 재확인
            if len(cleaned_entry.strip()) > 15:
                filtered.append(cleaned_entry)

    return filtered


# ── 상세 내용 클리닝 ─────────────────────────────────────────────

def _clean_description(desc: str) -> str:
    """상세 내용에서 노이즈 제거, 기술 내용만 보존."""
    # 'Issue Description' 접두사 제거
    desc = re.sub(r'^Issue\s*Description\s*', '', desc, flags=re.IGNORECASE)

    # 라인 단위 클리닝
    lines = desc.split('\n')
    cleaned = []
    for line in lines:
        cl = _clean_line(line)
        if cl:
            cleaned.append(cl)

    result = '\n'.join(cleaned).strip()

    # 끝부분 감사/부탁 문구 제거
    result = re.sub(
        r'[\s]*(?:많이\s*바쁘시겠지만\s*)?(?:확인\s*)?부탁[드하]?[리]?[겠]?[습니다.]*\s*'
        r'(?:감사합니다|감사드립니다)?[.\s]*$',
        '', result,
    )
    result = re.sub(r'[\s]*감사합니다[.\s]*$', '', result)

    return result.strip()


# ── 메인 필터 함수 ───────────────────────────────────────────────

def filter_issue_text(raw_text: str) -> str:
    """
    IMS 이슈 원본 텍스트 → 임베딩용 클린 텍스트.

    출력 형식:
        === IMS Issue {id} ===
        Product: {product}
        Version: {version}
        Module: {module}
        Status: {status}
        Subject: {cleaned title}

        ## 문의 내용
        {cleaned description}

        ## 응답 및 조치
        {filtered technical responses}
    """
    raw_text = _decode_html_entities(raw_text)

    # ── 헤더 블록 분리 (## 상세 내용 이전 전체를 헤더로 취급) ──
    header_block = raw_text
    body_start = ''
    for marker in ('## 상세 내용', '## 조치 이력'):
        idx = raw_text.find(marker)
        if idx >= 0:
            header_block = raw_text[:idx]
            body_start = raw_text[idx:]
            break

    # ── 헤더 파싱 (regex로 키-값 추출) ──
    header: dict[str, str] = {}

    # IMS ID
    m = re.search(r'=== IMS Issue (\d+) ===', header_block)
    if m:
        header['ims_id'] = m.group(1)

    # 키-값 쌍: "Key: Value" (값은 다음 Key 시작까지 모든 텍스트)
    _HEADER_KEYS = ['Product', 'Version', 'Module', 'Category', 'Subject',
                    'Customer', 'Status', 'Date']
    pattern = '|'.join(re.escape(k) for k in _HEADER_KEYS)
    # 각 키의 시작 위치 찾기
    key_positions = list(re.finditer(rf'^({pattern}):\s*', header_block, re.MULTILINE))

    for i, km in enumerate(key_positions):
        key = km.group(1)
        val_start = km.end()
        val_end = key_positions[i + 1].start() if i + 1 < len(key_positions) else len(header_block)
        val = header_block[val_start:val_end].strip()
        # 멀티라인 값 → 공백으로 합침
        val = re.sub(r'\s+', ' ', val).strip()
        header[key] = val

    # ── 본문 분할 ──
    rest = body_start
    description = ''
    action_log = ''

    if '## 상세 내용' in rest:
        parts = rest.split('## 상세 내용', maxsplit=1)
        remainder = parts[1] if len(parts) > 1 else ''
        if '## 조치 이력' in remainder:
            desc_part, action_part = remainder.split('## 조치 이력', maxsplit=1)
            description = desc_part.strip()
            action_log = action_part.strip()
        else:
            description = remainder.strip()
    elif '## 조치 이력' in rest:
        parts = rest.split('## 조치 이력', maxsplit=1)
        description = parts[0].strip()
        action_log = parts[1].strip() if len(parts) > 1 else ''
    else:
        description = rest.strip()

    # ── 클리닝 ──
    subject = _clean_subject(header.get('Subject', ''))
    description = _clean_description(description)
    filtered_actions = _filter_action_entries(action_log)

    # ── 출력 조립 ──
    out_lines = []
    ims_id = header.get('ims_id', '')
    out_lines.append(f'=== IMS Issue {ims_id} ===')
    out_lines.append(f'Product: {header.get("Product", "")}')
    if header.get('Version'):
        out_lines.append(f'Version: {header["Version"]}')
    if header.get('Module'):
        out_lines.append(f'Module: {header["Module"]}')
    out_lines.append(f'Status: {header.get("Status", "")}')
    out_lines.append(f'Subject: {subject}')
    out_lines.append('')

    if description:
        out_lines.append('## 문의 내용')
        out_lines.append(description)
        out_lines.append('')

    if filtered_actions:
        out_lines.append('## 응답 및 조치')
        out_lines.append('\n---\n'.join(filtered_actions))

    result = '\n'.join(out_lines).strip()

    # 최종 공백 정리
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


# ── 파일 단위 처리 ───────────────────────────────────────────────

def filter_issue_file(txt_path: Path) -> str:
    """파일 읽기 → 필터링 → 클린 텍스트 반환."""
    raw = txt_path.read_text(encoding='utf-8')
    return filter_issue_text(raw)
