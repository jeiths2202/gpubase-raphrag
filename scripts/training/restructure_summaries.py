#!/usr/bin/env python3
"""
요약본 완전 재구조화 및 학습 데이터 재생성

이 스크립트는 다음 문제를 해결합니다:
1. "## BOOT" → "tjesmgr BOOT" 매핑 (Manager-서브명령어 연결)
2. 모든 명령어에 정확한 syntax 포함
3. 43,147개 키워드 완전 매핑
4. 중복 제거 및 품질 검증

Usage:
    python scripts/training/restructure_summaries.py all
    python scripts/training/restructure_summaries.py parse
    python scripts/training/restructure_summaries.py validate
"""

import re
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = get_project_root()


# =============================================================================
# 파일명-Manager 매핑 규칙
# =============================================================================

MANAGER_MAPPING = {
    # TJES 관련 파일 → tjesmgr
    "OpenFrame_TJES_MVS": "tjesmgr",
    "OpenFrame_TJES_MSP": "tjesmgr",
    "OpenFrame_TJES_XSP": "tjesmgr",
    "OpenFrame_TJES_VOS3": "tjesmgr",
    "OpenFrame_Batch_MVS": "tjesmgr",
    "OpenFrame_Batch_MSP": "tjesmgr",
    "OpenFrame_Batch_XSP": "tjesmgr",
    "OpenFrame_Batch_VOS3": "tjesmgr",

    # OSC 관련 파일 → oscmgr
    "OpenFrame_OSC_MVS": "oscmgr",
    "OpenFrame_OSC_MSP": "oscmgr",
    "OpenFrame_OSC_XSP": "oscmgr",
    "OpenFrame_OSC_VOS3": "oscmgr",

    # TACF 관련 파일 → tacfmgr
    "OpenFrame_TACF_MVS": "tacfmgr",
    "OpenFrame_TACF_MSP": "tacfmgr",
    "OpenFrame_TACF_XSP": "tacfmgr",
    "OpenFrame_TACF_VOS3": "tacfmgr",

    # HiDB 관련 파일 → hidbmgr
    "OpenFrame_HiDB_MVS": "hidbmgr",
    "OpenFrame_HiDB_MSP": "hidbmgr",
    "OpenFrame_HiDB_XSP": "hidbmgr",

    # OSI 관련 파일 → osimgr
    "OpenFrame_OSI_MVS": "osimgr",
    "OpenFrame_OSI_MSP": "osimgr",
    "OpenFrame_OSI_XSP": "osimgr",

    # Common → tconmgr (일부)
    "OpenFrame_Common_MVS": None,
    "OpenFrame_Common_MSP": None,
    "OpenFrame_Common_XSP": None,

    # Base → 독립 명령어 (dsmigin, idcams 등)
    "OpenFrame_Base_MVS": None,
    "OpenFrame_Base_MSP": None,
    "OpenFrame_Base_XSP": None,
    "OpenFrame_Base_VOS3": None,

    # AIM → 참조 문서 (다른 Manager 참조)
    "OpenFrame_AIM_MVS": None,
    "OpenFrame_AIM_MSP": None,
    "OpenFrame_AIM_XSP": None,

    # 기타 제품
    "Tibero": None,
    "Tmax": None,
    "JEUS": None,
    "WebtoB": None,
}

# Manager 명령어 목록 (이 명령어들은 자체가 Manager)
MANAGER_COMMANDS = {
    'tjesmgr', 'oscmgr', 'tacfmgr', 'hidbmgr', 'osimgr', 'ndbmgr',
    'volmgr', 'tconmgr', 'smfmgr', 'cpmmgr', 'obmtsmgr', 'aimdtsmgr',
    'hidbptrmgr', 'tbrmgr', 'catmgr',
}

# Manager 명령어의 정확한 정보 (할루시네이션 방지)
# 제품명은 실제 OpenFrame 제품명 사용 (OF_Batch_MVS, OF_OSC_MVS 등)
MANAGER_DEFINITIONS = {
    'tjesmgr': {
        'syntax': 'tjesmgr <subcommand> [options]',
        'description': 'TJES (Tmax Job Entry Subsystem) Manager. TJESはOpenFrame Batchのジョブ管理サブシステムです。JES2ではありません。',
        'product': 'OF_Batch',  # 실제 제품명
        'sub_commands': ['BOOT', 'SHUTDOWN', 'CANCEL', 'CHANGE', 'HOLD', 'RELEASE', 'PS', 'PSJ', 'PR', 'PURGE'],
    },
    'oscmgr': {
        'syntax': 'oscmgr <subcommand> [options]',
        'description': 'OSC (Online System Controller) Manager. OSCはOpenFrameのオンライントランザクション処理システムです。CICSではありません。',
        'product': 'OF_OSC',  # 실제 제품명
        'sub_commands': ['START', 'STOP', 'STATUS', 'CEMT', 'CSMT'],
    },
    'tacfmgr': {
        'syntax': 'tacfmgr <subcommand> [options]',
        'description': 'TACF (Tmax Access Control Facility) Manager. TACFはOpenFrameのアクセス制御システムです。',
        'product': 'OF_TACF',  # 실제 제품명
        'sub_commands': ['ADDUSER', 'DELUSER', 'LISTUSER', 'PERMIT', 'CONNECT'],
    },
    'hidbmgr': {
        'syntax': 'hidbmgr <subcommand> [dbd_name] [options]',
        'description': 'HiDB (Hierarchical Database) Manager. HiDBはOpenFrameの階層型データベース管理システムです。',
        'product': 'OF_HiDB',  # 실제 제품명
        'sub_commands': ['segm', 'dbdgen', 'psbgen', 'acbgen'],
    },
    'osimgr': {
        'syntax': 'osimgr <subcommand> [options]',
        'description': 'OSI (Online System Interface) Manager. OSIはOpenFrameのIMS/DCエミュレーションシステムです。',
        'product': 'OF_OSI',  # 실제 제품명
        'sub_commands': ['start', 'stop', 'status'],
    },
}

# 독립 명령어 (Manager 접두사 불필요)
STANDALONE_COMMANDS = {
    'idcams', 'iebgener', 'iebcopy', 'dfsort', 'dsmigin', 'dsmigout',
    'textrun', 'tjclrun', 'ofboot', 'ofdown', 'tmboot', 'tmdown',
    'jesinit', 'jesdown', 'oscboot', 'oscdown', 'osctdlinit',
    'cobrun', 'plirun', 'asmrun', 'fortrun',
    'cp', 'cat', 'ls', 'grep', 'find', 'vi', 'cc', 'ar', 'ld',  # Unix 명령어
}


@dataclass
class CommandInfo:
    """명령어 정보"""
    name: str                          # 전체 명령어명 (예: "tjesmgr BOOT")
    sub_command: str = ""              # 서브명령어 (예: "BOOT")
    parent_command: str = ""           # 부모 명령어 (예: "tjesmgr")
    description: str = ""
    syntax: str = ""
    parameters: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    item_type: str = "command"         # command, config, api, error, concept
    product: str = "Unknown"
    source_file: str = ""
    source_page: int = 0
    aliases: List[str] = field(default_factory=list)
    from_summary: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# 요약본 파서
# =============================================================================

class SummaryParser:
    """요약본 파싱"""

    HEADER_PATTERN = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
    SYNTAX_PATTERN = re.compile(r'\*\*구문:\*\*\s*\n```\n?([\s\S]*?)\n?```', re.MULTILINE)
    SOURCE_PATTERN = re.compile(r'-\s*소스:\s*(.+?)(?:\s*\(p\.(\d+)\))?(?:\n|$)')
    PARAM_PATTERN = re.compile(r'\*\*파라미터:\*\*([\s\S]*?)(?=\*\*|---|$)')

    def __init__(self, summaries_dir: Path):
        self.summaries_dir = summaries_dir
        self.commands: List[CommandInfo] = []
        self.stats = {
            'files_parsed': 0,
            'commands_found': 0,
            'with_syntax': 0,
            'by_manager': defaultdict(int),
        }

    def parse_all(self) -> List[CommandInfo]:
        """모든 요약본 파일 파싱"""
        commands_dir = self.summaries_dir / "commands"
        if not commands_dir.exists():
            logger.error(f"commands 디렉토리 없음: {commands_dir}")
            return []

        md_files = list(commands_dir.glob("*.md"))
        logger.info(f"요약본 파일 {len(md_files)}개 파싱 시작...")

        for md_file in md_files:
            if md_file.name == "index.md":
                continue
            self._parse_file(md_file)
            self.stats['files_parsed'] += 1

        logger.info(f"파싱 완료: {self.stats['files_parsed']}개 파일, {len(self.commands)}개 명령어")
        return self.commands

    def _parse_file(self, file_path: Path) -> None:
        """단일 파일 파싱"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {file_path}: {e}")
            return

        # 파일명에서 정보 추출
        file_stem = file_path.stem
        manager = self._get_manager_for_file(file_stem)
        product = self._extract_product(file_stem)

        # 섹션 분리
        sections = re.split(r'\n---\n', content)

        for section in sections:
            cmd = self._parse_section(section, manager, product, file_path.name)
            if cmd:
                self.commands.append(cmd)
                self.stats['commands_found'] += 1
                if cmd.syntax:
                    self.stats['with_syntax'] += 1
                if cmd.parent_command:
                    self.stats['by_manager'][cmd.parent_command] += 1

    def _get_manager_for_file(self, file_stem: str) -> Optional[str]:
        """파일명에서 Manager 명령어 추출"""
        # 정확히 일치
        if file_stem in MANAGER_MAPPING:
            return MANAGER_MAPPING[file_stem]

        # 접두사 일치
        for prefix, manager in MANAGER_MAPPING.items():
            if file_stem.startswith(prefix):
                return manager

        return None

    def _extract_product(self, file_stem: str) -> str:
        """파일명에서 제품 추출 - 실제 OpenFrame 제품명 사용"""
        # MVS/MSP/XSP/VOS3 플랫폼 감지
        platform = ""
        if "MVS" in file_stem:
            platform = "_MVS"
        elif "MSP" in file_stem:
            platform = "_MSP"
        elif "XSP" in file_stem:
            platform = "_XSP"
        elif "VOS3" in file_stem:
            platform = "_VOS3"

        # 제품 감지 (실제 PDF 파일명 기준)
        if "Batch" in file_stem or "TJES" in file_stem:
            return f"OF_Batch{platform}" if platform else "OF_Batch"
        elif "OSC" in file_stem:
            return f"OF_OSC{platform}" if platform else "OF_OSC"
        elif "TACF" in file_stem:
            return f"OF_TACF{platform}" if platform else "OF_TACF"
        elif "HiDB" in file_stem:
            return f"OF_HiDB{platform}" if platform else "OF_HiDB"
        elif "OSI" in file_stem:
            return f"OF_OSI{platform}" if platform else "OF_OSI"
        elif "Base" in file_stem:
            return "OF_Base"
        elif "Common" in file_stem:
            return f"OF_Common{platform}" if platform else "OF_Common"
        elif "AIM" in file_stem:
            return f"OF_AIM{platform}" if platform else "OF_AIM"
        elif "Tibero" in file_stem:
            return "Tibero"
        elif "Tmax" in file_stem:
            return "Tmax"
        elif "JEUS" in file_stem:
            return "JEUS"
        elif "WebtoB" in file_stem:
            return "WebtoB"
        elif "OFCOBOL" in file_stem or "COBOL" in file_stem:
            return "OFCOBOL"
        elif "OFAsm" in file_stem or "ASM" in file_stem:
            return "OFAsm"
        return "OpenFrame"

    def _parse_section(self, section: str, manager: Optional[str],
                       product: str, source_file: str) -> Optional[CommandInfo]:
        """섹션 파싱"""
        # 헤더 추출
        header_match = self.HEADER_PATTERN.search(section)
        if not header_match:
            return None

        raw_name = header_match.group(1).strip()
        if not raw_name or raw_name.startswith('#'):
            return None

        # 헤더 이후 내용
        header_end = header_match.end()
        remaining = section[header_end:].strip()

        # syntax 추출
        syntax_match = self.SYNTAX_PATTERN.search(remaining)
        syntax = syntax_match.group(1).strip() if syntax_match else ""

        # 잘못된 syntax 필터링
        if syntax and self._is_invalid_syntax(syntax):
            syntax = ""

        # source 추출
        source_match = self.SOURCE_PATTERN.search(remaining)
        source_pdf = ""
        source_page = 0
        if source_match:
            source_pdf = source_match.group(1).strip()
            if source_match.group(2):
                source_page = int(source_match.group(2))

        # description 추출
        desc_end = len(remaining)
        if syntax_match:
            desc_end = min(desc_end, remaining.find('**구문:**'))
        if source_match:
            desc_end = min(desc_end, remaining.find('- 소스:'))
        description = remaining[:desc_end].strip() if desc_end > 0 else ""

        # 파라미터 추출
        parameters = self._extract_parameters(syntax, remaining)

        # Manager-서브명령어 처리
        name, sub_cmd, parent_cmd = self._process_command_name(raw_name, manager, syntax)

        if not name:
            return None

        # 별칭 생성
        aliases = self._generate_aliases(name, raw_name, sub_cmd, parent_cmd)

        return CommandInfo(
            name=name,
            sub_command=sub_cmd,
            parent_command=parent_cmd,
            description=description,
            syntax=syntax,
            parameters=parameters,
            item_type=self._detect_type(name, syntax),
            product=product,
            source_file=source_pdf if source_pdf else source_file,
            source_page=source_page,
            aliases=aliases,
        )

    def _is_invalid_syntax(self, syntax: str) -> bool:
        """유효하지 않은 syntax 필터링"""
        invalid_patterns = [
            r'^\s*\.*\s*$',           # 점만 있는 경우
            r'^\s*\.{3,}\s*$',        # 점 3개 이상
            r'^\d+$',                  # 숫자만
            r'^v?\d+\.\d+',            # 버전 문자열
            r'^\s*$',                  # 빈 문자열
            r'^[A-Z]$',                # 단일 문자
        ]
        for pattern in invalid_patterns:
            if re.match(pattern, syntax):
                return True
        return len(syntax) < 3

    def _process_command_name(self, raw_name: str, manager: Optional[str],
                              syntax: str) -> Tuple[str, str, str]:
        """명령어 이름 처리 - Manager 접두사 적용"""
        raw_lower = raw_name.lower()

        # 이미 Manager가 포함된 경우
        for mgr in MANAGER_COMMANDS:
            if raw_lower.startswith(mgr):
                # "tjesmgr BOOT" 형태
                parts = raw_name.split(maxsplit=1)
                parent = parts[0].lower()
                sub = parts[1] if len(parts) > 1 else ""
                return raw_name, sub, parent

        # 독립 명령어인 경우
        if raw_lower in STANDALONE_COMMANDS:
            return raw_name, "", ""

        # Unix 명령어 필터링
        if raw_lower in {'cp', 'cat', 'ls', 'grep', 'find', 'vi', 'cc', 'ar', 'ld', 'make'}:
            return raw_name, "", ""

        # Manager가 있고, syntax에 Manager가 포함된 경우
        if manager and syntax:
            if manager in syntax.lower():
                # syntax에서 전체 명령어 추출
                full_name = f"{manager} {raw_name}"
                return full_name, raw_name, manager

        # Manager가 있는 경우 - 서브명령어로 처리
        if manager:
            full_name = f"{manager} {raw_name}"
            return full_name, raw_name, manager

        # Manager가 없는 경우 - 그대로 반환
        return raw_name, "", ""

    def _extract_parameters(self, syntax: str, content: str) -> List[str]:
        """파라미터 추출"""
        params = []

        if syntax:
            # <param>
            params.extend(re.findall(r'<([^>]+)>', syntax))
            # [option]
            for match in re.findall(r'\[([^\]]+)\]', syntax):
                if not match.startswith('-'):
                    params.append(f"[{match}]")
            # KEY=value
            params.extend(re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=', syntax))

        # 파라미터 섹션에서 추출
        param_match = self.PARAM_PATTERN.search(content)
        if param_match:
            param_section = param_match.group(1)
            # - `param`: description 형태
            params.extend(re.findall(r'-\s*`([^`]+)`', param_section))

        return list(set(params))[:15]

    def _detect_type(self, name: str, syntax: str) -> str:
        """항목 타입 감지"""
        name_lower = name.lower()

        if re.search(r'mgr(\s|$)', name_lower):
            return 'command'
        if re.search(r'\.conf$|\.cfg$|\.properties$', name_lower):
            return 'config'
        if re.match(r'^[A-Z]+_[A-Z0-9_]+$', name):
            return 'api'
        if re.match(r'^ABEND|^-\d{4,}', name):
            return 'error'
        if syntax:
            return 'command'
        return 'concept'

    def _generate_aliases(self, name: str, raw_name: str,
                          sub_cmd: str, parent_cmd: str) -> List[str]:
        """별칭 생성"""
        aliases = set()

        # 대소문자 변형
        aliases.add(name.lower())
        aliases.add(name.upper())

        if sub_cmd:
            aliases.add(sub_cmd)
            aliases.add(sub_cmd.lower())
            aliases.add(sub_cmd.upper())

        if parent_cmd:
            aliases.add(parent_cmd)
            aliases.add(parent_cmd.upper())

        # 원본 이름
        aliases.add(raw_name)
        aliases.add(raw_name.lower())
        aliases.add(raw_name.upper())

        # 자기 자신 제외
        aliases.discard(name)

        return list(aliases)[:10]


# =============================================================================
# 키워드 매처
# =============================================================================

class KeywordMatcher:
    """키워드-명령어 매칭"""

    def __init__(self, commands: List[CommandInfo], keywords_path: Path):
        self.commands = commands
        self.keywords_path = keywords_path

        # 인덱스 구축
        self.exact_index: Dict[str, CommandInfo] = {}      # 정확히 일치
        self.lower_index: Dict[str, CommandInfo] = {}      # 소문자
        self.alias_index: Dict[str, CommandInfo] = {}      # 별칭
        self.manager_index: Dict[str, List[CommandInfo]] = defaultdict(list)  # Manager별

        self._build_indices()

    def _build_indices(self) -> None:
        """검색 인덱스 구축"""
        for cmd in self.commands:
            # 정확히 일치
            self.exact_index[cmd.name] = cmd
            # 소문자
            self.lower_index[cmd.name.lower()] = cmd
            # 별칭
            for alias in cmd.aliases:
                if alias not in self.alias_index:
                    self.alias_index[alias.lower()] = cmd
            # Manager별
            if cmd.parent_command:
                self.manager_index[cmd.parent_command].append(cmd)

        logger.info(f"인덱스 구축 완료: exact={len(self.exact_index)}, "
                    f"lower={len(self.lower_index)}, alias={len(self.alias_index)}, "
                    f"managers={len(self.manager_index)}")

    def load_keywords(self) -> List[str]:
        """키워드 로드"""
        keywords = []
        with open(self.keywords_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    keywords.append(line)
        logger.info(f"키워드 {len(keywords)}개 로드됨")
        return keywords

    def match_keyword(self, keyword: str) -> Optional[CommandInfo]:
        """키워드에 매칭되는 명령어 찾기"""
        # 1. 정확히 일치
        if keyword in self.exact_index:
            return self.exact_index[keyword]

        keyword_lower = keyword.lower()

        # 2. 소문자 일치
        if keyword_lower in self.lower_index:
            return self.lower_index[keyword_lower]

        # 3. 별칭 일치
        if keyword_lower in self.alias_index:
            return self.alias_index[keyword_lower]

        # 4. Manager만 일치 - 대표 명령어 생성
        if keyword_lower in self.manager_index:
            sub_commands = self.manager_index[keyword_lower]
            return self._create_manager_summary(keyword_lower, sub_commands)

        # 5. Manager 명령어 변형 (TJESMGR → tjesmgr)
        for mgr in MANAGER_COMMANDS:
            if keyword_lower == mgr or keyword_lower == mgr.upper():
                if mgr in self.manager_index:
                    sub_commands = self.manager_index[mgr]
                    return self._create_manager_summary(mgr, sub_commands)

        return None

    def _create_manager_summary(self, manager: str,
                                sub_commands: List[CommandInfo]) -> CommandInfo:
        """Manager 명령어의 요약 정보 생성"""
        # 대표적인 서브명령어 목록
        sub_cmd_names = sorted(set(c.sub_command for c in sub_commands if c.sub_command))[:20]
        sub_cmd_list = ", ".join(sub_cmd_names)

        # 제품 정보
        products = set(c.product for c in sub_commands)
        product = list(products)[0] if len(products) == 1 else "OpenFrame"

        # 설명 생성
        manager_upper = manager.upper()
        product_name = {
            'tjesmgr': 'TJES (Tmax Job Entry Subsystem)',
            'oscmgr': 'OSC (Online System Controller)',
            'tacfmgr': 'TACF (Tmax Access Control Facility)',
            'hidbmgr': 'HiDB (Hierarchical Database)',
            'osimgr': 'OSI (Online System Interface)',
        }.get(manager, manager.upper())

        description = f"{manager}は{product_name}を管理するコマンドラインツールです。"
        if sub_cmd_list:
            description += f" 主なサブコマンド: {sub_cmd_list}"

        # syntax 생성
        syntax = f"{manager} <subcommand> [options]"

        return CommandInfo(
            name=manager,
            sub_command="",
            parent_command="",
            description=description,
            syntax=syntax,
            parameters=["subcommand", "options"],
            item_type="command",
            product=product,
            source_file="summary",
            aliases=[manager.upper(), manager.lower()],
        )

    def match_all(self) -> Tuple[Dict[str, CommandInfo], List[str]]:
        """모든 키워드 매칭"""
        keywords = self.load_keywords()
        matched: Dict[str, CommandInfo] = {}
        unmatched: List[str] = []

        for keyword in keywords:
            cmd = self.match_keyword(keyword)
            if cmd:
                matched[keyword] = cmd
            else:
                unmatched.append(keyword)

        logger.info(f"매칭 완료: {len(matched)}개 매칭, {len(unmatched)}개 미매칭")
        return matched, unmatched


# =============================================================================
# 학습 데이터 생성기
# =============================================================================

class LearningDataGenerator:
    """최종 학습 데이터 생성"""

    def __init__(self, commands: List[CommandInfo],
                 matched: Dict[str, CommandInfo],
                 unmatched: List[str]):
        self.commands = commands
        self.matched = matched
        self.unmatched = unmatched

    def generate(self) -> Dict:
        """학습 데이터 생성"""
        items = []
        seen_names = set()

        # 1. 먼저 파싱된 모든 명령어 추가 (요약본에서 추출한 것들)
        #    이것이 핵심! tjesmgr BOOT 등 모든 서브명령어 포함
        #    중복 시 syntax가 있는 것을 우선 선택
        best_items: Dict[str, Dict] = {}

        for cmd in self.commands:
            name_lower = cmd.name.lower()
            item = self._create_item(cmd)

            if not self._validate(item):
                continue

            if name_lower not in best_items:
                best_items[name_lower] = item
            else:
                # 기존 항목과 비교하여 더 완전한 것 선택
                existing = best_items[name_lower]
                # syntax가 있는 것 우선
                if item.get('syntax') and not existing.get('syntax'):
                    best_items[name_lower] = item
                # syntax 길이가 더 긴 것 우선
                elif item.get('syntax') and existing.get('syntax'):
                    if len(item['syntax']) > len(existing['syntax']):
                        best_items[name_lower] = item

        # 2. Manager 명령어 정의 적용 (정확한 정보로 덮어쓰기)
        for mgr_name, mgr_def in MANAGER_DEFINITIONS.items():
            mgr_lower = mgr_name.lower()
            sub_cmds = ', '.join(mgr_def.get('sub_commands', [])[:10])
            item = {
                'name': mgr_name,
                'type': 'command',
                'description': mgr_def['description'] + f' 主なサブコマンド: {sub_cmds}',
                'syntax': mgr_def['syntax'],
                'parameters': ['subcommand', 'options'],
                'examples': [f'{mgr_name} --help', f'{mgr_name} status'],
                'related': [],
                'parent_command': '',
                'sub_command': '',
                'product': mgr_def['product'],
                'source_file': 'manager_definition',
                'source_page': 0,
                'aliases': [mgr_name.upper(), mgr_name.lower()],
                'from_summary': True,
            }
            best_items[mgr_lower] = item  # 기존 항목 덮어쓰기

        items = list(best_items.values())
        seen_names = set(best_items.keys())

        # 3. 키워드 파일에서 추가 항목 (요약본에 없는 것들만)
        for keyword in self.unmatched:
            keyword_lower = keyword.lower()
            if keyword_lower in seen_names:
                continue
            seen_names.add(keyword_lower)

            item = self._create_fallback_item(keyword)
            items.append(item)

        # 통계
        stats = self._calculate_stats(items)

        return {
            'metadata': {
                'total_items': len(items),
                'generated_at': datetime.now().isoformat(),
                'stats': stats,
            },
            'items': items,
        }

    def _create_item(self, cmd: CommandInfo) -> Dict:
        """명령어에서 학습 항목 생성"""
        syntax = cmd.syntax

        # 서브명령어의 경우 부모 명령어가 syntax에 없으면 추가
        if cmd.parent_command and syntax:
            if not syntax.lower().startswith(cmd.parent_command.lower()):
                # syntax에 부모 명령어 접두사 추가
                syntax = f"{cmd.parent_command} {syntax}"

        return {
            'name': cmd.name,
            'type': cmd.item_type,
            'description': cmd.description,
            'syntax': syntax if syntax else None,
            'parameters': cmd.parameters,
            'examples': cmd.examples,
            'related': [],
            'parent_command': cmd.parent_command,
            'sub_command': cmd.sub_command,
            'product': cmd.product,
            'source_file': cmd.source_file,
            'source_page': cmd.source_page,
            'aliases': cmd.aliases,
            'from_summary': cmd.from_summary,
        }

    def _create_fallback_item(self, keyword: str) -> Dict:
        """미매칭 키워드의 기본 항목 생성"""
        item_type = self._detect_type(keyword)
        return {
            'name': keyword,
            'type': item_type,
            'description': f"{keyword}はOpenFrameシステムの{item_type}です。",
            'syntax': None,
            'parameters': [],
            'examples': [],
            'related': [],
            'parent_command': "",
            'sub_command': "",
            'product': 'Unknown',
            'source_file': 'keyword_only',
            'source_page': 0,
            'aliases': [],
            'from_summary': False,
        }

    def _detect_type(self, keyword: str) -> str:
        """키워드 타입 감지"""
        if re.search(r'mgr$', keyword.lower()):
            return 'command'
        if re.search(r'\.conf$|\.cfg$', keyword.lower()):
            return 'config'
        if re.match(r'^[A-Z]+_[A-Z0-9_]+$', keyword):
            return 'api'
        if re.match(r'^ABEND|^-\d{4,}', keyword):
            return 'error'
        return 'concept'

    def _validate(self, item: Dict) -> bool:
        """항목 유효성 검증"""
        # 최소한의 정보가 있어야 함
        if not item.get('name'):
            return False
        if not item.get('description') and not item.get('syntax'):
            return False
        return True

    def _calculate_stats(self, items: List[Dict]) -> Dict:
        """통계 계산"""
        with_syntax = sum(1 for i in items if i.get('syntax'))
        by_type = defaultdict(int)
        by_product = defaultdict(int)
        with_parent = sum(1 for i in items if i.get('parent_command'))

        for item in items:
            by_type[item.get('type', 'unknown')] += 1
            by_product[item.get('product', 'Unknown')] += 1

        return {
            'total': len(items),
            'with_syntax': with_syntax,
            'syntax_rate': round(with_syntax / max(len(items), 1) * 100, 2),
            'with_parent_command': with_parent,
            'by_type': dict(by_type),
            'by_product': dict(by_product),
        }


# =============================================================================
# 품질 검증기
# =============================================================================

class QualityValidator:
    """품질 검증"""

    CRITICAL_COMMANDS = [
        'tjesmgr', 'oscmgr', 'tacfmgr', 'hidbmgr', 'osimgr',
        'tjesmgr BOOT', 'tjesmgr CANCEL', 'tjesmgr CHANGE',
        'oscmgr START', 'oscmgr STOP',
        'idcams', 'iebgener', 'iebcopy', 'dfsort',
    ]

    FORBIDDEN_TERMS = {
        'tjesmgr': ['JES2', 'z/OS JES', 'IBM JES'],  # TJES는 TmaxSoft 제품, JES2 아님
        'oscmgr': ['CICS', 'IBM CICS'],  # OSC는 TmaxSoft 제품, CICS 아님
    }

    def __init__(self, items: List[Dict]):
        self.items = items
        self.item_index = {i['name'].lower(): i for i in items}
        self.issues = []

    def validate_all(self) -> Dict:
        """전체 검증"""
        self._check_critical_commands()
        self._check_forbidden_terms()
        self._check_syntax_quality()
        self._check_duplicates()

        return {
            'total_items': len(self.items),
            'issues_count': len(self.issues),
            'issues': self.issues,
            'passed': len(self.issues) == 0,
        }

    def _check_critical_commands(self) -> None:
        """핵심 명령어 검증"""
        for cmd in self.CRITICAL_COMMANDS:
            cmd_lower = cmd.lower()
            if cmd_lower not in self.item_index:
                self.issues.append({
                    'type': 'missing_critical',
                    'command': cmd,
                    'message': f"핵심 명령어 '{cmd}'가 누락되었습니다.",
                })
            else:
                item = self.item_index[cmd_lower]
                if not item.get('syntax'):
                    self.issues.append({
                        'type': 'missing_syntax',
                        'command': cmd,
                        'message': f"'{cmd}'의 syntax가 없습니다.",
                    })

    def _check_forbidden_terms(self) -> None:
        """금지 용어 검증 (할루시네이션 방지)"""
        # 부정문 패턴 - 이런 표현은 허용 (할루시네이션 방지용)
        negation_patterns = ['ではありません', 'ではない', 'not', 'NOT', '아닙니다', '가 아닌']

        for cmd, forbidden in self.FORBIDDEN_TERMS.items():
            cmd_lower = cmd.lower()
            if cmd_lower in self.item_index:
                item = self.item_index[cmd_lower]
                desc = item.get('description', '')
                desc_upper = desc.upper()
                for term in forbidden:
                    if term.upper() in desc_upper:
                        # 부정문으로 사용된 경우는 허용
                        is_negation = False
                        for neg in negation_patterns:
                            if neg in desc:
                                is_negation = True
                                break
                        if not is_negation:
                            self.issues.append({
                                'type': 'forbidden_term',
                                'command': cmd,
                                'term': term,
                                'message': f"'{cmd}'의 설명에 금지 용어 '{term}'이 포함되어 있습니다.",
                            })

    def _check_syntax_quality(self) -> None:
        """syntax 품질 검증"""
        for item in self.items:
            syntax = item.get('syntax', '')
            if not syntax:
                continue

            # 잘못된 패턴
            if re.match(r'^\s*\.+\s*$', syntax):
                self.issues.append({
                    'type': 'invalid_syntax',
                    'command': item['name'],
                    'syntax': syntax,
                    'message': f"'{item['name']}'의 syntax가 유효하지 않습니다.",
                })

    def _check_duplicates(self) -> None:
        """중복 검증"""
        names = [i['name'].lower() for i in self.items]
        seen = set()
        for name in names:
            if name in seen:
                self.issues.append({
                    'type': 'duplicate',
                    'command': name,
                    'message': f"'{name}'이 중복되었습니다.",
                })
            seen.add(name)


# =============================================================================
# 메인 실행
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="요약본 재구조화")
    parser.add_argument("action", choices=['all', 'parse', 'match', 'generate', 'validate'],
                        default='all', nargs='?')
    parser.add_argument("--summaries", type=Path,
                        default=PROJECT_ROOT / "uploads" / "summaries")
    parser.add_argument("--keywords", type=Path,
                        default=PROJECT_ROOT / "docs" / "keyword.txt")
    parser.add_argument("--output", type=Path,
                        default=PROJECT_ROOT / "uploads" / "summaries" / "restructured_learning_dataset.json")

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("요약본 완전 재구조화 시작")
    logger.info(f"요약본: {args.summaries}")
    logger.info(f"키워드: {args.keywords}")
    logger.info(f"출력: {args.output}")
    logger.info(f"액션: {args.action}")
    logger.info("=" * 70)

    # Phase 1: 요약본 파싱
    logger.info("\n[Phase 1] 요약본 파싱...")
    summary_parser = SummaryParser(args.summaries)
    commands = summary_parser.parse_all()

    logger.info(f"  - 파싱된 명령어: {len(commands)}개")
    logger.info(f"  - syntax 있음: {summary_parser.stats['with_syntax']}개")
    logger.info(f"  - Manager별: {dict(summary_parser.stats['by_manager'])}")

    if args.action == 'parse':
        # 파싱 결과만 저장
        output_path = args.output.parent / "parsed_summaries.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([c.to_dict() for c in commands], f, ensure_ascii=False, indent=2)
        logger.info(f"파싱 결과 저장: {output_path}")
        return 0

    # Phase 2: 키워드 매칭
    logger.info("\n[Phase 2] 키워드 매칭...")
    matcher = KeywordMatcher(commands, args.keywords)
    matched, unmatched = matcher.match_all()

    logger.info(f"  - 매칭됨: {len(matched)}개")
    logger.info(f"  - 미매칭: {len(unmatched)}개")
    logger.info(f"  - 매칭률: {len(matched) / (len(matched) + len(unmatched)) * 100:.2f}%")

    if args.action == 'match':
        return 0

    # Phase 3: 학습 데이터 생성
    logger.info("\n[Phase 3] 학습 데이터 생성...")
    generator = LearningDataGenerator(commands, matched, unmatched)
    data = generator.generate()

    logger.info(f"  - 총 항목: {data['metadata']['stats']['total']}개")
    logger.info(f"  - syntax 포함: {data['metadata']['stats']['with_syntax']}개 "
                f"({data['metadata']['stats']['syntax_rate']}%)")

    # 저장
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"학습 데이터 저장: {args.output}")

    if args.action == 'generate':
        return 0

    # Phase 4: 품질 검증
    logger.info("\n[Phase 4] 품질 검증...")
    validator = QualityValidator(data['items'])
    validation = validator.validate_all()

    if validation['passed']:
        logger.info("  ✅ 모든 검증 통과!")
    else:
        logger.warning(f"  ⚠️ {validation['issues_count']}개 이슈 발견:")
        for issue in validation['issues'][:10]:
            logger.warning(f"    - [{issue['type']}] {issue['message']}")

    # 검증 결과 저장
    validation_path = args.output.parent / "validation_results.json"
    with open(validation_path, 'w', encoding='utf-8') as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    # 핵심 명령어 확인
    logger.info("\n[검증] 핵심 명령어 확인:")
    items_by_name = {i['name'].lower(): i for i in data['items']}
    for cmd in ['tjesmgr', 'tjesmgr boot', 'oscmgr', 'tacfmgr']:
        if cmd in items_by_name:
            item = items_by_name[cmd]
            syntax = item.get('syntax', 'N/A')[:50]
            logger.info(f"  ✅ {cmd}: syntax='{syntax}'")
        else:
            logger.warning(f"  ❌ {cmd}: 미발견")

    logger.info("\n" + "=" * 70)
    logger.info("완료!")
    logger.info("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
