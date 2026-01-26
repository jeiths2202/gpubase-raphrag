"""
Comprehensive Manual Parser

모든 매뉴얼에서 다양한 유형의 정보를 추출합니다:
- 명령어/유틸리티 (Commands/Utilities)
- 설정 파라미터 (Configuration Parameters)
- API/함수 (APIs/Functions)
- 개념/정의 (Concepts/Definitions)
- 프로시저 (Procedures)
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import pymupdf  # fitz

logger = logging.getLogger(__name__)


@dataclass
class ExtractedItem:
    """추출된 항목"""
    name: str
    item_type: str  # command, config, api, concept, procedure
    description: str
    syntax: Optional[str] = None
    parameters: List[Dict[str, str]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    source_file: str = ""
    source_page: int = 0
    product: str = ""
    category: str = ""


class ComprehensiveParser:
    """모든 매뉴얼 유형에서 정보를 추출하는 파서"""

    # 매뉴얼 유형별 추출 패턴
    MANUAL_TYPE_PATTERNS = {
        "Command-Reference": "command",
        "Tool-Reference": "command",
        "Utility-Reference": "command",
        "Reference-Guide": "command",
        "Configuration-Guide": "config",
        "Developer-Guide": "api",
        "Administrator-Guide": "concept",
        "User-Guide": "concept",
        "Installation-Guide": "procedure",
        "Migration-Guide": "procedure",
        "Guide": "concept",  # 기본값
    }

    # 명령어 추출 패턴
    COMMAND_PATTERNS = [
        # 명령어 섹션 헤더
        r"^(?:第?\d+[章節]?\.?\d*\.?\s*)?([a-z][a-z0-9_-]{2,})\s*(?:コマンド|command|ユーティリティ|utility)",
        # 명령어 정의
        r"^([a-z][a-z0-9_-]{2,})\s*[-–—]\s*(.+?)$",
        # 사용법 섹션
        r"^(?:使用法|Usage|構文|Syntax)[:：]?\s*\n?\s*([a-z][a-z0-9_-]+)",
        # 대문자 명령어 (OF 계열)
        r"^([A-Z][A-Z0-9_-]{2,})\s+(?:コマンド|command)",
    ]

    # 설정 파라미터 패턴
    CONFIG_PATTERNS = [
        # key=value 형식
        r"^([A-Z][A-Z0-9_]+)\s*[=:]\s*(.+?)(?:\s*#|$)",
        # 파라미터 설명
        r"^([A-Z][A-Z0-9_]+)\s*[-–—]\s*(.+?)$",
        # 설정 항목
        r"^(?:\d+\.\s*)?([A-Z][A-Z0-9_]+)\s*\n\s*(?:説明|Description|설명)[:：]?\s*(.+)",
    ]

    # API/함수 패턴
    API_PATTERNS = [
        # 함수 시그니처 (C 스타일)
        r"(?:int|void|char\*?|long)\s+([a-z_][a-z0-9_]*)\s*\([^)]*\)",
        # API 이름
        r"^([a-z_][a-z0-9_]+)\s*\([^)]*\)\s*[-–—]",
        # 메서드 정의
        r"^(?:public|private|protected)?\s*(?:static)?\s*\w+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        # OpenFrame API 패턴 (tcfh_*, tfcd_*, tdcb_* 등)
        r"([a-z]{2,6}_[a-z_]+)\s*\(\)",
        # 섹션 헤더 형식 (B.4.5. tcfh_stow())
        r"^[A-Z]\.\d+\.\d+\.\s*([a-z_][a-z0-9_]+)\s*\(\)",
    ]

    # 개념/정의 패턴
    CONCEPT_PATTERNS = [
        # 용어 정의
        r"^([A-Z][A-Za-z0-9_-]+(?:\s+[A-Z][A-Za-z0-9_-]+)*)\s*[:：]\s*(.+)",
        # 약어 정의
        r"^([A-Z]{2,})\s*\(([^)]+)\)",
        # 주요 개념
        r"^(?:■|●|◆|▶)\s*([^\n]+)",
    ]

    def __init__(self, manuals_dir: Path):
        self.manuals_dir = manuals_dir
        self.extracted_items: List[ExtractedItem] = []

    def detect_manual_type(self, filename: str) -> str:
        """파일명에서 매뉴얼 유형 감지"""
        for pattern, item_type in self.MANUAL_TYPE_PATTERNS.items():
            if pattern in filename:
                return item_type
        return "concept"

    # OpenFrame 제품명 패턴 (PDF 타이틀에서 추출)
    PRODUCT_PATTERNS = [
        r"OpenFrame\s+(Common|Batch|Base|TACF|OSC|OSI|HiDB|AIM|OFCOBOL|OFAsm|OFPLI|PROSORT)",
        r"(Tibero)\s+\d+",
        r"(Tmax)\s+\d+",
        r"(ProSort)",
        r"(OFManager)",
        r"(WebT)\s+\d+",
        r"(OFMiner)",
        r"(OFStudio)",
    ]

    def extract_product_from_content(self, first_pages_text: str, filename: str) -> Tuple[str, str]:
        """PDF 내용(타이틀 페이지)에서 제품명 추출

        제품명 예시:
        - OpenFrame Common
        - OpenFrame Batch
        - OpenFrame Base
        - OpenFrame TACF
        - OpenFrame OSC
        - OpenFrame OSI
        - Tibero 7
        - Tmax 6.0
        """
        product = ""
        category = ""

        # 제품명 패턴 검색
        for pattern in self.PRODUCT_PATTERNS:
            match = re.search(pattern, first_pages_text, re.IGNORECASE)
            if match:
                base = match.group(1) if match.lastindex else match.group(0)
                # OpenFrame 제품은 전체 이름 사용
                if "OpenFrame" in pattern:
                    product = f"OpenFrame {base}"
                else:
                    product = base
                break

        # 카테고리 추출 (가이드 유형)
        category_patterns = [
            r"(Batch|TJES|TSO|TACF|OSC|OSI|Tool|Installation|Configuration|Error|Migration)\s*[-_]?\s*(Guide|Reference|Manual)",
        ]
        for pattern in category_patterns:
            match = re.search(pattern, first_pages_text, re.IGNORECASE)
            if match:
                category = match.group(1)
                break

        # 제품명을 찾지 못한 경우 파일명에서 추출 (폴백)
        if not product:
            product = self._extract_product_from_filename(filename)

        return product, category

    def _extract_product_from_filename(self, filename: str) -> str:
        """파일명에서 제품명 추출 (폴백)"""
        parts = filename.replace(".pdf", "").split("_")

        if filename.startswith("OF_"):
            # OF_Common_*, OF_Batch_*, OF_Base_* 등
            if len(parts) > 1:
                component = parts[1]
                if component in ("Common", "Batch", "Base", "TACF", "OSC", "OSI", "HiDB", "AIM"):
                    return f"OpenFrame {component}"
                elif component in ("VOS3", "MSP", "MVS", "XSP"):
                    # 메인프레임 타입의 경우 Batch 등 컴포넌트와 조합
                    for p in parts:
                        if p in ("Batch", "Common", "TACF", "OSC"):
                            return f"OpenFrame {p}"
                    return f"OpenFrame {component}"
            return "OpenFrame"
        elif filename.startswith("Tibero"):
            return "Tibero"
        elif filename.startswith("Tmax"):
            return "Tmax"
        elif filename.startswith("OFManager"):
            return "OFManager"
        elif filename.startswith("WebT"):
            return "WebT"
        elif filename.startswith("OFCOBOL"):
            return "OpenFrame OFCOBOL"
        elif filename.startswith("OFAsm"):
            return "OpenFrame OFAsm"

        return parts[0] if parts else "Unknown"

    def parse_pdf(self, pdf_path: Path) -> List[ExtractedItem]:
        """PDF에서 정보 추출"""
        items = []
        filename = pdf_path.name
        manual_type = self.detect_manual_type(filename)

        try:
            doc = pymupdf.open(pdf_path)

            # 첫 3페이지에서 제품명 추출 (타이틀 페이지)
            first_pages_text = ""
            for i, page in enumerate(doc):
                if i >= 3:
                    break
                first_pages_text += page.get_text() + "\n"

            product, category = self.extract_product_from_content(first_pages_text, filename)
            logger.info(f"Parsing: {filename} (type={manual_type}, product={product})")

            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if not text.strip():
                    continue

                # 페이지별 항목 추출
                page_items = self._extract_from_page(
                    text, manual_type, filename, page_num, product, category
                )
                items.extend(page_items)

            doc.close()

        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")

        return items

    def _extract_from_page(
        self,
        text: str,
        manual_type: str,
        filename: str,
        page_num: int,
        product: str,
        category: str
    ) -> List[ExtractedItem]:
        """페이지에서 항목 추출"""
        items = []

        # 텍스트를 섹션으로 분리
        sections = self._split_into_sections(text)

        for section_title, section_content in sections:
            # 섹션 제목에서 항목 추출 시도
            item = self._extract_item_from_section(
                section_title, section_content, manual_type,
                filename, page_num, product, category
            )
            if item:
                items.append(item)

        # 추가로 인라인 항목 추출
        inline_items = self._extract_inline_items(
            text, manual_type, filename, page_num, product, category
        )
        items.extend(inline_items)

        return items

    def _split_into_sections(self, text: str) -> List[Tuple[str, str]]:
        """텍스트를 섹션으로 분리"""
        sections = []

        # 섹션 헤더 패턴
        header_patterns = [
            r"^((?:\d+\.)+\s*.+?)$",  # 1.2.3. Title
            r"^(第\d+[章節]\s*.+?)$",  # 第1章 Title
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$",  # Title Case Header
            r"^(■.+?)$",  # ■ Title
            r"^(●.+?)$",  # ● Title
        ]

        lines = text.split("\n")
        current_title = ""
        current_content = []

        for line in lines:
            is_header = False
            for pattern in header_patterns:
                if re.match(pattern, line.strip(), re.MULTILINE):
                    if current_title or current_content:
                        sections.append((current_title, "\n".join(current_content)))
                    current_title = line.strip()
                    current_content = []
                    is_header = True
                    break

            if not is_header:
                current_content.append(line)

        if current_title or current_content:
            sections.append((current_title, "\n".join(current_content)))

        return sections

    def _extract_item_from_section(
        self,
        title: str,
        content: str,
        manual_type: str,
        filename: str,
        page_num: int,
        product: str,
        category: str
    ) -> Optional[ExtractedItem]:
        """섹션에서 항목 추출"""

        # 명령어 추출
        if manual_type == "command":
            return self._extract_command(title, content, filename, page_num, product, category)

        # 설정 추출
        elif manual_type == "config":
            return self._extract_config(title, content, filename, page_num, product, category)

        # API 추출
        elif manual_type == "api":
            return self._extract_api(title, content, filename, page_num, product, category)

        # 개념/정의 추출
        else:
            return self._extract_concept(title, content, filename, page_num, product, category)

    def _extract_command(
        self, title: str, content: str, filename: str,
        page_num: int, product: str, category: str
    ) -> Optional[ExtractedItem]:
        """명령어 추출"""
        # 제목에서 명령어 이름 추출
        cmd_match = re.search(r"([a-zA-Z][a-zA-Z0-9_-]{2,})", title)
        if not cmd_match:
            return None

        cmd_name = cmd_match.group(1).lower()

        # 일반적인 단어 필터링
        skip_words = {
            "the", "and", "for", "with", "from", "this", "that", "chapter",
            "section", "guide", "reference", "manual", "page", "table",
            "figure", "example", "note", "warning", "appendix", "index",
            "overview", "introduction", "summary", "contents", "copyright"
        }
        if cmd_name.lower() in skip_words:
            return None

        # 설명 추출
        desc_match = re.search(
            r"(?:説明|Description|설명|概要|Overview)[:：]?\s*(.+?)(?:\n\n|\n(?:使用法|Usage|構文|Syntax)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        description = desc_match.group(1).strip() if desc_match else ""

        # 구문 추출
        syntax_match = re.search(
            r"(?:使用法|Usage|構文|Syntax)[:：]?\s*\n?\s*(.+?)(?:\n\n|\n(?:パラメータ|Parameters|引数|Arguments)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        syntax = syntax_match.group(1).strip() if syntax_match else ""

        # 파라미터 추출
        params = self._extract_parameters(content)

        # 예제 추출
        examples = self._extract_examples(content)

        if not description and not syntax:
            return None

        return ExtractedItem(
            name=cmd_name,
            item_type="command",
            description=description[:500] if description else title,
            syntax=syntax[:300] if syntax else None,
            parameters=params[:10],
            examples=examples[:3],
            source_file=filename,
            source_page=page_num,
            product=product,
            category=category
        )

    def _extract_config(
        self, title: str, content: str, filename: str,
        page_num: int, product: str, category: str
    ) -> Optional[ExtractedItem]:
        """설정 파라미터 추출"""
        # 파라미터 이름 추출
        param_match = re.search(r"([A-Z][A-Z0-9_]+)", title)
        if not param_match:
            return None

        param_name = param_match.group(1)

        # 너무 짧은 이름 필터링
        if len(param_name) < 3:
            return None

        # 설명 추출
        desc_match = re.search(
            r"(?:説明|Description|설명)[:：]?\s*(.+?)(?:\n\n|\n(?:デフォルト|Default|기본값)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        description = desc_match.group(1).strip() if desc_match else ""

        # 기본값 추출
        default_match = re.search(
            r"(?:デフォルト|Default|기본값)[:：]?\s*(.+?)(?:\n|$)",
            content, re.IGNORECASE
        )
        default_value = default_match.group(1).strip() if default_match else ""

        if not description:
            return None

        return ExtractedItem(
            name=param_name,
            item_type="config",
            description=description[:500],
            parameters=[{"default": default_value}] if default_value else [],
            source_file=filename,
            source_page=page_num,
            product=product,
            category=category
        )

    def _extract_api(
        self, title: str, content: str, filename: str,
        page_num: int, product: str, category: str
    ) -> Optional[ExtractedItem]:
        """API/함수 추출"""
        # 함수 시그니처 추출
        func_match = re.search(
            r"(?:int|void|char\*?|long|BOOL|boolean)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)",
            content
        )
        if not func_match:
            # 타이틀에서 함수명 추출 시도
            func_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]+)\s*\(", title)

        if not func_match:
            return None

        func_name = func_match.group(1)

        # 설명 추출
        desc_match = re.search(
            r"(?:説明|Description|설명|機能|Function)[:：]?\s*(.+?)(?:\n\n|\n(?:パラメータ|Parameters|引数|戻り値|Return)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        description = desc_match.group(1).strip() if desc_match else ""

        # 반환값 추출
        return_match = re.search(
            r"(?:戻り値|Return|返却値)[:：]?\s*(.+?)(?:\n\n|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        return_value = return_match.group(1).strip() if return_match else ""

        if not description:
            return None

        return ExtractedItem(
            name=func_name,
            item_type="api",
            description=description[:500],
            syntax=func_match.group(0) if func_match else None,
            parameters=[{"return": return_value}] if return_value else [],
            source_file=filename,
            source_page=page_num,
            product=product,
            category=category
        )

    def _extract_concept(
        self, title: str, content: str, filename: str,
        page_num: int, product: str, category: str
    ) -> Optional[ExtractedItem]:
        """개념/정의 추출"""
        # 제목에서 개념 이름 추출
        concept_match = re.search(r"([A-Za-z][A-Za-z0-9_-]+(?:\s+[A-Za-z][A-Za-z0-9_-]+)*)", title)
        if not concept_match:
            return None

        concept_name = concept_match.group(1)

        # 너무 짧거나 일반적인 단어 필터링
        if len(concept_name) < 3:
            return None

        skip_words = {
            "the", "and", "for", "with", "from", "this", "that", "chapter",
            "section", "guide", "reference", "manual", "page", "table",
            "figure", "example", "note", "warning", "appendix", "index",
            "overview", "introduction", "summary", "contents", "copyright",
            "はじめに", "概要", "目次", "付録", "索引"
        }
        if concept_name.lower() in skip_words:
            return None

        # 설명 추출 (첫 번째 단락)
        paragraphs = content.strip().split("\n\n")
        description = paragraphs[0][:500] if paragraphs else ""

        if not description or len(description) < 20:
            return None

        return ExtractedItem(
            name=concept_name,
            item_type="concept",
            description=description,
            source_file=filename,
            source_page=page_num,
            product=product,
            category=category
        )

    def _extract_inline_items(
        self, text: str, manual_type: str, filename: str,
        page_num: int, product: str, category: str
    ) -> List[ExtractedItem]:
        """인라인 항목 추출 (명령어, 파라미터, API 함수 등)

        주의: 각 항목의 설명만 정확히 추출하고, 다른 항목 내용은 포함하지 않음
        """
        items = []

        # API 함수 추출 (tcfh_*, tfcd_*, tdcb_* 등)
        # 섹션 헤더 형식: B.4.5. tcfh_stow()
        api_section_pattern = r"[A-Z]\.\d+\.\d+\.\s*([a-z]{2,6}_[a-z_]+)\s*\(\)\s*\n(.+?)(?=\n[A-Z]\.\d+|\n●|\n•|\Z)"
        for match in re.finditer(api_section_pattern, text, re.DOTALL):
            api_name = match.group(1)
            api_content = match.group(2).strip()

            # 첫 문장을 설명으로 추출
            first_line = api_content.split('\n')[0].strip()
            if first_line and len(first_line) > 5:
                # 프로토타입 추출
                proto_match = re.search(r"(?:int|void|char\*?)\s+" + re.escape(api_name) + r"\s*\([^)]*\)", api_content)
                syntax = proto_match.group(0) if proto_match else ""

                items.append(ExtractedItem(
                    name=api_name,
                    item_type="api",
                    description=first_line[:300],
                    syntax=syntax[:200] if syntax else None,
                    source_file=filename,
                    source_page=page_num,
                    product=product,
                    category=category
                ))

        # 테이블 형식 API 추출 (api_name()\n설명)
        api_table_pattern = r"([a-z]{2,6}_[a-z_]+)\s*\(\)\s*\n([^\n]+(?:です|ます|します|行います)[^\n]*)"
        for match in re.finditer(api_table_pattern, text):
            api_name = match.group(1)
            description = match.group(2).strip()

            if description and len(description) > 10:
                items.append(ExtractedItem(
                    name=api_name,
                    item_type="api",
                    description=description[:300],
                    source_file=filename,
                    source_page=page_num,
                    product=product,
                    category=category
                ))

        # 명령어 패턴 매칭
        if manual_type in ("command", "concept"):
            # 소문자 명령어 (tjesinit, oscboot 등)
            cmd_pattern = r"\b([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b"

            # 테이블 형식 명령어 설명 추출 (툴명\n설명 형식)
            table_pattern = r"([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\s*\n([^\n]+(?:です|ます|する|である|します)[^\n]*)"

            # 먼저 테이블 형식 추출 시도
            for match in re.finditer(table_pattern, text, re.IGNORECASE):
                cmd_name = match.group(1).lower()
                description = match.group(2).strip()

                # 다른 명령어 이름이 포함되어 있으면 해당 부분까지만 사용
                other_cmd = re.search(r"\b([a-z]{3,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b", description)
                if other_cmd and other_cmd.group(1).lower() != cmd_name:
                    description = description[:other_cmd.start()].strip()

                if description and len(description) > 10:
                    items.append(ExtractedItem(
                        name=cmd_name,
                        item_type="command",
                        description=description[:300],
                        source_file=filename,
                        source_page=page_num,
                        product=product,
                        category=category
                    ))

            # 일반 명령어 추출 (정의 형식)
            def_pattern = r"([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\s*[-–—:：]\s*([^\n]+)"
            for match in re.finditer(def_pattern, text, re.IGNORECASE):
                cmd_name = match.group(1).lower()
                description = match.group(2).strip()

                if description and len(description) > 10:
                    items.append(ExtractedItem(
                        name=cmd_name,
                        item_type="command",
                        description=description[:300],
                        source_file=filename,
                        source_page=page_num,
                        product=product,
                        category=category
                    ))

        return items

    def _extract_parameters(self, content: str) -> List[Dict[str, str]]:
        """파라미터 추출"""
        params = []
        param_section = re.search(
            r"(?:パラメータ|Parameters|引数|Arguments|オプション|Options)[:：]?\s*\n(.+?)(?:\n\n|\n(?:例|Example|戻り値|Return)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        if param_section:
            # 파라미터 라인 파싱
            for line in param_section.group(1).split("\n"):
                param_match = re.match(r"^\s*[-•]\s*([^\s:：]+)[:：]?\s*(.+)?$", line)
                if param_match:
                    params.append({
                        "name": param_match.group(1),
                        "description": param_match.group(2) or ""
                    })
        return params

    def _extract_examples(self, content: str) -> List[str]:
        """예제 추출"""
        examples = []
        example_section = re.search(
            r"(?:例|Example|使用例|サンプル|Sample)[:：]?\s*\n(.+?)(?:\n\n(?:[^例])|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        if example_section:
            examples.append(example_section.group(1).strip()[:500])
        return examples

    def process_all_manuals(self) -> List[ExtractedItem]:
        """모든 매뉴얼 처리"""
        all_items = []
        pdf_files = list(self.manuals_dir.rglob("*.pdf"))

        logger.info(f"Processing {len(pdf_files)} PDF files...")

        for pdf_path in pdf_files:
            items = self.parse_pdf(pdf_path)
            all_items.extend(items)
            logger.info(f"  {pdf_path.name}: {len(items)} items extracted")

        # 중복 제거
        unique_items = self._deduplicate_items(all_items)

        logger.info(f"Total: {len(unique_items)} unique items extracted")
        return unique_items

    def _deduplicate_items(self, items: List[ExtractedItem]) -> List[ExtractedItem]:
        """중복 항목 제거 (같은 이름+타입+제품은 가장 긴 설명 유지)

        중요: product를 키에 포함하여 MSP/MVS/VOS3/XSP 각각의 버전 유지
        """
        seen = {}
        for item in items:
            # 제품별로 항목 유지 (동일 명령어가 여러 제품에 있을 수 있음)
            key = (item.name.lower(), item.item_type, item.product)
            if key not in seen or len(item.description) > len(seen[key].description):
                seen[key] = item
        return list(seen.values())
