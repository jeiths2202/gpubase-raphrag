"""
Structured Knowledge Store

파일 시스템 기반 구조화 지식 검색 (LLM 없음).
요약본 파일에서 명령어, 에러코드, 설정, 용어를 검색합니다.
"""
import glob
import json as json_module
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 프로젝트 루트 기준 경로
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SUMMARIES_BASE = os.path.join(_PROJECT_ROOT, "uploads", "summaries")
IMAGES_BASE = os.path.join(_PROJECT_ROOT, "uploads", "pdf_images")


@dataclass
class SearchResult:
    """구조화 검색 결과"""
    title: str
    content: str
    source_file: str
    source_page: str = ""
    relevance_score: float = 0.0
    domain: str = ""  # commands, error_codes, configs, glossary
    product: str = ""  # 검색 출처 Agent (cross-agent 검색 시 사용)
    source_path: str = ""  # 원본 PDF 전체 경로 (lazy table/image extraction용)


@dataclass
class ProductSearchContext:
    """제품별 검색 결과 컨테이너"""
    product: str = ""
    structured_results: List[SearchResult] = field(default_factory=list)
    vector_results: List[dict] = field(default_factory=list)
    graph_results: List[dict] = field(default_factory=list)

    @property
    def has_results(self) -> bool:
        return bool(self.structured_results or self.vector_results or self.graph_results)


class StructuredKnowledgeStore:
    """
    파일 시스템 기반 구조화 지식 저장소

    특징:
    - LLM 없이 키워드 기반 검색
    - Markdown 파일 파싱, 섹션 단위 검색
    - 메모리 캐시 (로딩 시 1회, 이후 <10ms)
    """

    def __init__(
        self,
        product_id: str,
        summary_paths: Dict[str, List[str]],
    ):
        self.product_id = product_id
        self.summary_paths = summary_paths
        self._cache: Dict[str, List[Dict]] = {}  # domain → parsed sections
        self._loaded = False

    def _ensure_loaded(self):
        """캐시가 로딩되지 않았으면 로딩"""
        if self._loaded:
            return
        for domain, path_patterns in self.summary_paths.items():
            sections = []
            for pattern in path_patterns:
                full_pattern = os.path.join(SUMMARIES_BASE, pattern) if not os.path.isabs(pattern) else pattern
                for filepath in glob.glob(full_pattern):
                    try:
                        if filepath.lower().endswith(".json"):
                            parsed = self._parse_learning_json(filepath, domain)
                        elif filepath.lower().endswith(".pdf"):
                            parsed = self._parse_pdf(filepath, domain)
                        else:
                            parsed = self._parse_markdown(filepath, domain)
                        sections.extend(parsed)
                    except Exception as e:
                        logger.warning(f"Failed to parse {filepath}: {e}")
            self._cache[domain] = sections
        self._loaded = True
        total = sum(len(v) for v in self._cache.values())
        logger.info(f"StructuredKnowledgeStore loaded for {self.product_id}: {total} sections")

    def _parse_markdown(self, filepath: str, domain: str) -> List[Dict]:
        """Markdown 파일을 섹션 단위로 파싱"""
        sections = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return sections

        filename = os.path.basename(filepath)
        current_title = ""
        current_content = []
        current_source = ""

        for line in content.split("\n"):
            # ## 레벨 헤더를 섹션 구분자로 사용
            if line.startswith("## "):
                # 이전 섹션 저장
                if current_title and current_content:
                    sections.append({
                        "title": current_title,
                        "content": "\n".join(current_content).strip(),
                        "source_file": filename,
                        "source_page": current_source,
                        "domain": domain,
                    })
                current_title = line[3:].strip()
                current_content = []
                current_source = ""
            elif line.startswith("### "):
                # ### 레벨도 별도 섹션으로 추가 (에러코드 등)
                if current_title and current_content:
                    sections.append({
                        "title": current_title,
                        "content": "\n".join(current_content).strip(),
                        "source_file": filename,
                        "source_page": current_source,
                        "domain": domain,
                    })
                current_title = line[4:].strip()
                current_content = []
                current_source = ""
            else:
                current_content.append(line)
                # 소스 페이지 추출
                source_match = re.search(r"소스:\s*(.+?)(?:\s*\(p\.(\d+)\))?$", line.strip())
                if source_match:
                    current_source = source_match.group(0)

        # 마지막 섹션 저장
        if current_title and current_content:
            sections.append({
                "title": current_title,
                "content": "\n".join(current_content).strip(),
                "source_file": filename,
                "source_page": current_source,
                "domain": domain,
            })

        return sections

    # PDF 섹션 구분용 heading 패턴
    _HEADING_PATTERN = re.compile(r'^(\d+\.)+\s+\S')
    _MAX_SECTION_CHARS = 8000  # 메모리 관리: 섹션당 최대 문자 수

    # 서브커맨드 감지: 단독 줄에 대문자 3-30자 (ALTER, DEFINE, DEFINE CLUSTER 등)
    _SUBCOMMAND_RE = re.compile(r'^([A-Z][A-Z0-9]+(?: [A-Z0-9]+)*)$', re.MULTILINE)
    # 노이즈 제외 (목차·페이지·일반 라벨)
    _SUBCOMMAND_NOISE = frozenset({
        "TABLE OF CONTENTS", "PAGE", "CHAPTER", "SECTION", "FIGURE",
        "EXAMPLE", "NOTE", "WARNING", "CONTENTS", "INDEX", "APPENDIX",
        "DD", "JCL", "JOB", "EXEC", "DATA", "INDEX",
    })
    # 번호 접두사 제거 패턴: "1.4.2. 機能コマンド" → "機能コマンド"
    _NUM_PREFIX_RE = re.compile(r'^[\d.]+\s+')

    @staticmethod
    def _table_to_markdown(table_data: list) -> str:
        """PyMuPDF table.extract() 결과를 GFM Markdown 테이블로 변환"""
        if not table_data or len(table_data) < 2:
            return ""
        rows = [[str(c).replace("\n", " ") if c else "" for c in row] for row in table_data]
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]
        header = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join("---" for _ in range(max_cols)) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        return f"{header}\n{sep}\n{body}"

    @staticmethod
    def _get_shaded_rects(page) -> tuple:
        """페이지에서 음영(코드블록) 영역의 rect 목록 + 총 드로잉 수 반환.

        PDF 매뉴얼의 명령어 예시, 출력 결과 등은 회색 배경의 사각형으로
        표시됩니다. page.get_drawings()를 사용하여 이 영역들을 감지합니다.

        Returns:
            (shaded_rects, drawing_count): 음영 rect 목록과 전체 드로잉 수.
            drawing_count는 테이블 보더 감지 pre-filter에 사용됩니다.
        """
        rects = []
        drawing_count = 0
        try:
            for d in page.get_drawings():
                drawing_count += 1
                fill = d.get("fill")
                if fill is None:
                    continue
                rect = d.get("rect")
                if rect is None:
                    continue
                w = rect.width
                h = rect.height
                # 코드블록 조건: 폭 > 200, 높이 >= 15, 회색 계열
                if w < 200 or h < 15:
                    continue
                r, g, b = fill[0], fill[1], fill[2] if len(fill) >= 3 else (fill[0], fill[0], fill[0])
                # 흰색(>0.98)이나 검정(<0.05) 제외, 회색 계열만
                if r > 0.98 and g > 0.98 and b > 0.98:
                    continue
                if r < 0.05 and g < 0.05 and b < 0.05:
                    continue
                rects.append(rect)
        except Exception:
            pass
        return rects, drawing_count

    @staticmethod
    def _extract_page_text_with_codeblocks(page, extract_tables: bool = False) -> str:
        """페이지 텍스트를 추출: 음영 → 코드블록, 테이블 → 마크다운 테이블 변환.

        1. page.get_drawings()로 음영 rect 감지 → 코드블록
        2. extract_tables=True일 때: page.find_tables()로 테이블 인라인 변환
        3. page.get_text("dict")로 블록별 위치+텍스트 추출
        4. 테이블 영역 텍스트는 스킵, 마크다운 테이블로 교체
        5. 인접 코드 행은 하나의 ``` 블록으로 병합

        Args:
            extract_tables: True이면 find_tables() 호출 (검색 시 lazy extraction용).
                           False(기본)이면 테이블 스킵 (초기 파싱 고속화).
        """
        shaded_rects, drawing_count = StructuredKnowledgeStore._get_shaded_rects(page)

        # 테이블 감지: extract_tables=True + drawing pre-filter 일 때만
        # find_tables()는 ~50-200ms/page → 초기 파싱 시 호출하면 4000+페이지에서 ~400초
        # 검색 시에만 1-5페이지 대상으로 호출 (lazy extraction)
        table_regions: list = []  # [(x0, y0, x1, y1, markdown)]
        if extract_tables and drawing_count >= 5:
            try:
                tables = page.find_tables()
                for table in tables:
                    data = table.extract()
                    md = StructuredKnowledgeStore._table_to_markdown(data)
                    if md:
                        b = table.bbox  # (x0, y0, x1, y1)
                        table_regions.append((b[0], b[1], b[2], b[3], md))
            except Exception:
                pass

        if not shaded_rects and not table_regions:
            return page.get_text("text") or ""

        try:
            page_dict = page.get_text("dict")
        except Exception:
            return page.get_text("text") or ""

        # 테이블 영역 판정 함수
        def _in_table(cy: float, cx: float) -> bool:
            for tx0, ty0, tx1, ty1, _ in table_regions:
                if ty0 - 2 <= cy <= ty1 + 2 and tx0 - 5 <= cx <= tx1 + 5:
                    return True
            return False

        # 각 텍스트 라인을 (y좌표, 텍스트, is_code, is_table) 튜플로 수집
        lines_with_info: list = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 텍스트 블록만
                continue
            for line_info in block.get("lines", []):
                bbox = line_info.get("bbox", (0, 0, 0, 0))
                cy = (bbox[1] + bbox[3]) / 2
                cx = (bbox[0] + bbox[2]) / 2

                text = ""
                for span in line_info.get("spans", []):
                    text += span.get("text", "")
                text = text.rstrip()
                if not text:
                    continue

                # 테이블 영역 내 텍스트는 스킵 (마크다운 테이블로 대체)
                if _in_table(cy, cx):
                    continue

                # 음영 rect 내에 있는지 판정
                is_code = False
                for rect in shaded_rects:
                    if rect.x0 - 5 <= cx <= rect.x1 + 5 and rect.y0 - 2 <= cy <= rect.y1 + 2:
                        is_code = True
                        break

                lines_with_info.append((bbox[1], text, is_code, False))

        # 테이블 마크다운을 y좌표 위치에 삽입
        for _, ty0, _, _, md in table_regions:
            lines_with_info.append((ty0, md, False, True))

        # y좌표 순으로 정렬
        lines_with_info.sort(key=lambda x: x[0])

        # 마크다운 출력 생성
        result: list = []
        in_code_block = False

        for _, text, is_code, is_table in lines_with_info:
            if is_table:
                # 코드블록 내부라면 먼저 닫기
                if in_code_block:
                    result.append("```\n")
                    in_code_block = False
                result.append("\n" + text + "\n")
                continue

            if is_code and not in_code_block:
                result.append("\n```")
                in_code_block = True
            elif not is_code and in_code_block:
                result.append("```\n")
                in_code_block = False
            result.append(text)

        if in_code_block:
            result.append("```")

        return "\n".join(result)

    @staticmethod
    def _extract_page_images(doc, page_num: int, product_id: str) -> List[str]:
        """페이지에서 이미지를 추출하여 파일로 저장, Markdown 이미지 참조 반환"""
        import pymupdf
        results = []
        page = doc[page_num]
        images = page.get_images(full=True)

        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n > 4:  # CMYK → RGB
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

                # 너무 작은 이미지 스킵 (아이콘 등)
                if pix.width < 50 or pix.height < 50:
                    continue

                img_dir = os.path.join(IMAGES_BASE, product_id)
                os.makedirs(img_dir, exist_ok=True)
                filename = f"p{page_num + 1}_img{img_idx}.png"
                filepath = os.path.join(img_dir, filename)

                if not os.path.exists(filepath):
                    pix.save(filepath)

                img_url = f"/uploads/pdf_images/{product_id}/{filename}"
                results.append(f"![Figure (p.{page_num + 1})]({img_url})")
            except Exception:
                continue
        return results

    def _parse_pdf(self, filepath: str, domain: str) -> List[Dict]:
        """PDF 파일을 섹션 단위로 파싱 (PyMuPDF 사용)"""
        sections = []
        try:
            import pymupdf
        except ImportError:
            logger.warning("PyMuPDF not installed, skipping PDF parsing")
            return sections

        try:
            doc = pymupdf.open(filepath)
        except Exception as e:
            logger.warning(f"Failed to open PDF {filepath}: {e}")
            return sections

        filename = os.path.basename(filepath)

        # TOC 기반 섹션 분할 시도
        toc = doc.get_toc()
        if toc and len(toc) >= 3:
            sections = self._parse_pdf_by_toc(doc, toc, filename, domain, filepath)
        else:
            # TOC 없으면 heading 패턴 기반 fallback
            sections = self._parse_pdf_by_headings(doc, filename, domain, filepath)

        doc.close()
        return sections

    def _parse_pdf_by_toc(
        self, doc, toc: list, filename: str, domain: str, filepath: str = "",
    ) -> List[Dict]:
        """TOC 기반 PDF 섹션 분할 (L1→L2→L3 계층 처리, 자식 있는 부모 스킵)"""
        sections = []
        total_pages = len(doc)

        # 부모-자식 관계 분석: L1→L2 및 L2→L3 모두 추적
        parents_with_children: set = set()
        for i, (level, title, page_num) in enumerate(toc):
            if level > 3:
                continue
            for j in range(i + 1, len(toc)):
                next_level = toc[j][0]
                if next_level <= level:
                    break  # 동일/상위 레벨 → 더 이상 자식 없음
                if next_level == level + 1:
                    parents_with_children.add(i)
                    break

        for i, (level, title, page_num) in enumerate(toc):
            if level > 3:
                continue  # L4 이하 무시

            # 자식이 있는 부모는 스킵 (자식이 세분화된 콘텐츠 제공)
            if i in parents_with_children:
                # 단, 첫 자식 이전의 "개요" 텍스트는 별도 저장
                overview = self._extract_overview_before_children(
                    doc, toc, i, page_num, total_pages,
                )
                if overview and len(overview) > 100:
                    hier_title = self._build_hierarchical_title(toc, i)
                    sections.append({
                        "title": f"{hier_title} (概要)",
                        "content": overview[:self._MAX_SECTION_CHARS],
                        "source_file": filename,
                        "source_page": f"p.{page_num}",
                        "domain": domain,
                        "source_path": filepath,
                    })
                continue

            # 다음 동일/상위 레벨 TOC 항목의 페이지 번호 (섹션 끝)
            next_page = total_pages
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    next_page = toc[j][2]
                    break

            # 해당 범위 텍스트 추출 (음영 영역 → 코드블록 변환 포함)
            content_parts = []
            for p in range(max(0, page_num - 1), min(next_page, total_pages)):
                try:
                    page_text = self._extract_page_text_with_codeblocks(doc[p])
                    if page_text:
                        content_parts.append(page_text.strip())
                except Exception:
                    continue

            content = "\n".join(content_parts)
            content = self._clean_pdf_text(content)

            if not content or len(content) < 30:
                continue

            hier_title = self._build_hierarchical_title(toc, i)

            # 대규모 섹션은 서브커맨드 분할 시도
            if len(content) > self._MAX_SECTION_CHARS:
                subsections = self._split_by_subcommands(
                    content, hier_title, filename, domain, filepath, page_num,
                    total_pages=next_page - page_num,
                )
                if subsections:
                    sections.extend(subsections)
                    continue

            sections.append({
                "title": hier_title,
                "content": content[:self._MAX_SECTION_CHARS],
                "source_file": filename,
                "source_page": f"p.{page_num}",
                "domain": domain,
                "source_path": filepath,
            })

        return sections

    def _build_hierarchical_title(self, toc: list, index: int) -> str:
        """TOC 항목의 계층 타이틀 생성 (번호 접두사 제거).

        예: index → L3 "1.4.2. 機能コマンド"
            parent → L2 "1.4. IDCAMS"
            result → "IDCAMS > 機能コマンド"
        """
        current_level = toc[index][0]
        current_title = self._NUM_PREFIX_RE.sub("", toc[index][1].strip())

        if current_level <= 1:
            return current_title

        # 역방향으로 직계 부모(level - 1) 탐색
        for j in range(index - 1, -1, -1):
            if toc[j][0] == current_level - 1:
                parent_title = self._build_hierarchical_title(toc, j)
                return f"{parent_title} > {current_title}"

        return current_title

    def _extract_overview_before_children(
        self, doc, toc: list, parent_idx: int, parent_page: int, total_pages: int,
    ) -> str:
        """부모 섹션의 첫 자식 이전 텍스트 추출 (개요/도입부).

        예: "1.4. IDCAMS" (p.37) ~ "1.4.1. DDの設定" (p.40) → p.37-39 텍스트
        """
        parent_level = toc[parent_idx][0]
        first_child_page = total_pages

        for j in range(parent_idx + 1, len(toc)):
            if toc[j][0] <= parent_level:
                break
            if toc[j][0] == parent_level + 1:
                first_child_page = toc[j][2]
                break

        if first_child_page <= parent_page:
            return ""

        content_parts = []
        for p in range(max(0, parent_page - 1), min(first_child_page - 1, total_pages)):
            try:
                page_text = self._extract_page_text_with_codeblocks(doc[p])
                if page_text:
                    content_parts.append(page_text.strip())
            except Exception:
                continue

        return self._clean_pdf_text("\n".join(content_parts))

    def _split_by_subcommands(
        self,
        content: str,
        parent_title: str,
        filename: str,
        domain: str,
        filepath: str,
        start_page: int,
        total_pages: int = 1,
    ) -> List[Dict]:
        """대규모 섹션에서 대문자 heading(ALTER, DEFINE 등)을 감지하여 서브섹션 분할.

        Returns:
            서브섹션 리스트 (빈 리스트 = 분할 불가 → 호출측에서 원본 사용)
        """
        lines = content.split('\n')
        # 대문자 heading 후보 탐색
        command_positions: list = []  # (line_idx, command_name)

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            m = self._SUBCOMMAND_RE.match(stripped)
            if not m:
                continue
            cmd = m.group(1)
            if cmd in self._SUBCOMMAND_NOISE:
                continue
            if len(cmd) < 3:
                continue
            # heading 판정: 직전/직후 공백 줄 필수 (파라미터 이름 필터링)
            prev_blank = idx == 0 or not lines[idx - 1].strip()
            next_blank = idx >= len(lines) - 1 or not lines[idx + 1].strip()
            if not (prev_blank or next_blank):
                continue  # 문장 중간의 약어/파라미터 이름 제외
            command_positions.append((idx, cmd))

        if len(command_positions) < 2:
            return []

        # 밀집 필터: 10줄 이내 5개 이상 연속 → 테이블/파라미터 목록 (heading 아님)
        filtered_positions: list = []
        for ci, (lidx, cmd) in enumerate(command_positions):
            nearby = sum(
                1 for oj, _ in command_positions
                if abs(oj - lidx) <= 10 and oj != lidx
            )
            if nearby >= 4:
                continue  # 밀집 영역 → 테이블 항목으로 판단
            filtered_positions.append((lidx, cmd))
        command_positions = filtered_positions

        if len(command_positions) < 2:
            return []

        subsections: list = []
        total_lines = len(lines)

        # Preamble: 첫 heading 이전 콘텐츠 (ALTER처럼 TOC에 없는 첫 번째 커맨드 포함)
        if command_positions[0][0] > 0:
            preamble = '\n'.join(lines[:command_positions[0][0]]).strip()
            if len(preamble) > 100:
                # Preamble 내에서 첫 번째 커맨드명 추출 → 타이틀에 반영
                preamble_title = parent_title
                for pl in lines[:command_positions[0][0]]:
                    ps = pl.strip()
                    if not ps:
                        continue
                    pm = self._SUBCOMMAND_RE.match(ps)
                    if pm and pm.group(1) not in self._SUBCOMMAND_NOISE and len(pm.group(1)) >= 3:
                        preamble_title = f"{parent_title} > {pm.group(1)}"
                        break
                subsections.append({
                    "title": preamble_title,
                    "content": preamble[:self._MAX_SECTION_CHARS],
                    "source_file": filename,
                    "source_page": f"p.{start_page}",
                    "domain": domain,
                    "source_path": filepath,
                })

        for ci, (line_idx, cmd) in enumerate(command_positions):
            # 다음 명령어까지의 콘텐츠
            next_idx = (
                command_positions[ci + 1][0]
                if ci + 1 < len(command_positions)
                else total_lines
            )
            cmd_lines = lines[line_idx:next_idx]
            cmd_content = '\n'.join(cmd_lines).strip()

            if len(cmd_content) < 80:
                continue

            # 페이지 번호 추정
            ratio = line_idx / total_lines if total_lines > 0 else 0
            est_page = start_page + int(ratio * total_pages)

            subsections.append({
                "title": f"{parent_title} > {cmd}",
                "content": cmd_content[:self._MAX_SECTION_CHARS],
                "source_file": filename,
                "source_page": f"p.{est_page}",
                "domain": domain,
                "source_path": filepath,
            })

        return subsections

    def _parse_pdf_by_headings(
        self, doc, filename: str, domain: str, filepath: str = "",
    ) -> List[Dict]:
        """Heading 패턴 기반 PDF 섹션 분할 (TOC 없을 때)"""
        sections = []
        current_title = filename.replace('.pdf', '')
        current_content: List[str] = []
        current_page = 1

        for page_num in range(len(doc)):
            try:
                page_text = self._extract_page_text_with_codeblocks(doc[page_num])
            except Exception:
                continue
            if not page_text:
                continue

            for line in page_text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                # heading 패턴 감지
                if self._HEADING_PATTERN.match(stripped) and len(stripped) < 200:
                    # 이전 섹션 저장
                    if current_content:
                        content = self._clean_pdf_text("\n".join(current_content))
                        if content and len(content) > 30:
                            sections.append({
                                "title": current_title,
                                "content": content[:self._MAX_SECTION_CHARS],
                                "source_file": filename,
                                "source_page": f"p.{current_page}",
                                "domain": domain,
                                "source_path": filepath,
                            })
                    current_title = stripped
                    current_content = []
                    current_page = page_num + 1
                else:
                    current_content.append(stripped)

        # 마지막 섹션
        if current_content:
            content = self._clean_pdf_text("\n".join(current_content))
            if content and len(content) > 30:
                sections.append({
                    "title": current_title,
                    "content": content[:self._MAX_SECTION_CHARS],
                    "source_file": filename,
                    "source_page": f"p.{current_page}",
                    "domain": domain,
                    "source_path": filepath,
                })

        return sections

    @staticmethod
    def _clean_pdf_text(text: str) -> str:
        """PDF 텍스트 정리 (코드블록 내부는 보존)"""
        if not text:
            return ""

        # 코드블록(```)을 분리하여 보존
        parts = re.split(r'(```[\s\S]*?```)', text)
        cleaned_parts = []
        for part in parts:
            if part.startswith('```'):
                # 코드블록은 그대로 유지
                cleaned_parts.append(part)
            else:
                # 일반 텍스트만 정리
                p = re.sub(r'[ \t]+', ' ', part)
                p = re.sub(r'\n\s*-?\s*\d+\s*-?\s*\n', '\n', p)
                p = re.sub(r'\n{3,}', '\n\n', p)
                cleaned_parts.append(p)

        text = ''.join(cleaned_parts)

        # 반복되는 헤더/푸터 제거 (같은 줄이 3회 이상 등장, 코드블록 외부만)
        lines = text.split('\n')
        line_counts: Dict[str, int] = {}
        in_code = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('```'):
                in_code = not in_code
                continue
            if not in_code and stripped and len(stripped) > 5:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1
        repeated = {line for line, count in line_counts.items() if count >= 3}
        if repeated:
            in_code = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('```'):
                    in_code = not in_code
                    new_lines.append(line)
                elif in_code or stripped not in repeated:
                    new_lines.append(line)
            text = '\n'.join(new_lines)
        return text.strip()

    # ChatML 파싱용 정규식
    _CHATML_USER = re.compile(r"<\|im_start\|>user\n(.*?)<\|im_end\|>", re.DOTALL)
    _CHATML_ASSISTANT = re.compile(r"<\|im_start\|>assistant\n(.*?)<\|im_end\|>", re.DOTALL)

    def _parse_learning_json(self, filepath: str, domain: str) -> List[Dict]:
        """QLoRA 학습 JSON (ChatML 형식)을 섹션으로 파싱

        각 Q&A 쌍을 하나의 섹션으로 변환:
        - title: 사용자 질문
        - content: 어시스턴트 답변
        """
        sections = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json_module.load(f)
        except Exception:
            return sections

        if not isinstance(data, list):
            return sections

        filename = os.path.basename(filepath)

        for entry in data:
            text = entry.get("text", "")
            user_match = self._CHATML_USER.search(text)
            assistant_match = self._CHATML_ASSISTANT.search(text)

            if user_match and assistant_match:
                question = user_match.group(1).strip()
                answer = assistant_match.group(1).strip()
                if question and answer and len(answer) > 20:
                    sections.append({
                        "title": question,
                        "content": answer,
                        "source_file": filename,
                        "source_page": "",
                        "domain": domain,
                    })

        return sections

    # 불용어 (일본어 조사/기능어구 + 영어 관사/전치사)
    _STOPWORDS = frozenset([
        # 일본어 조사·접속사
        "の", "は", "が", "を", "に", "で", "と", "も", "や", "か",
        "へ", "から", "まで", "より", "ね", "よ", "わ", "な", "け",
        "って", "ので", "のに", "けど", "だけ", "しか", "ばかり",
        # 일본어 기능어구 (검색 질의에서 토픽 의미 없음)
        "について", "してください", "ください", "とは", "ことが",
        "ている", "された", "される", "している", "できる",
        "ものです", "ことです", "あります", "ありません",
        "ですか", "ますか", "ません", "でしょう",
        "ました", "しました", "なります", "おける",
        "どのよう", "どうすれ", "なぜ", "いつ",
        "教えて", "説明して", "知りたい",
        # 영어 불용어
        "the", "a", "an", "of", "in", "on", "at", "to", "for",
        "is", "are", "was", "were", "be", "and", "or", "not",
        "it", "this", "that", "with", "from", "by", "as",
        "about", "what", "how", "do", "does",
        "tell", "me", "explain", "please", "describe",
    ])

    def _tokenize_query(self, query: str) -> List[str]:
        """
        쿼리를 의미 있는 토큰으로 분리.

        - 영문/숫자: 2자 이상
        - 카타카나: 2자 이상
        - 한자: 1자 이상
        - 한국어: 2자 이상
        - 불용어 제거
        """
        query_lower = query.lower()
        # 영문+숫자+하이픈/언더스코어, 카타카나, 한자, 한국어, 히라가나
        raw_tokens = re.findall(
            r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'  # 영문숫자 (1자 이상)
            r'|[\u30a0-\u30ff]{2,}'   # 카타카나 (2자 이상)
            r'|[\u4e00-\u9fff]+'      # 한자 (1자 이상)
            r'|[\uac00-\ud7af]{2,}'   # 한국어 (2자 이상)
            r'|[\u3040-\u309f]{2,}',  # 히라가나 (2자 이상)
            query_lower,
        )
        # 불용어 제거 + 1자 영문 제거
        tokens = []
        for t in raw_tokens:
            if t in self._STOPWORDS:
                continue
            # 영문 1자는 의미 없으므로 제거
            if len(t) == 1 and t.isascii():
                continue
            tokens.append(t)
        return tokens

    def _calc_document_frequencies(
        self, tokens: List[str], search_domains: List[str]
    ) -> Dict[str, float]:
        """
        각 토큰의 IDF 가중치 계산.

        IDF = log((N + 1) / (DF + 1)) + 1.0
        - N: 전체 섹션 수
        - DF: 해당 토큰이 출현하는 섹션 수
        """
        total_sections = 0
        df_counts: Dict[str, int] = {t: 0 for t in tokens}

        for domain in search_domains:
            if domain not in self._cache:
                continue
            for section in self._cache[domain]:
                total_sections += 1
                title_lower = section["title"].lower()
                content_lower = section["content"].lower()
                combined = title_lower + " " + content_lower
                for token in tokens:
                    if token in combined:
                        df_counts[token] += 1

        idf_weights: Dict[str, float] = {}
        for token in tokens:
            df = df_counts[token]
            idf_weights[token] = math.log((total_sections + 1) / (df + 1)) + 1.0

        return idf_weights

    async def search(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """
        Progressive Token + IDF 기반 구조화 검색 (LLM 없음)

        Args:
            query: 검색 쿼리
            domains: 검색할 도메인 (None이면 전체)
            top_k: 반환할 최대 결과 수

        Returns:
            검색 결과 리스트 (relevance_score 내림차순)
        """
        self._ensure_loaded()

        search_domains = domains or list(self._cache.keys())

        # 토큰 추출 + IDF 계산
        tokens = self._tokenize_query(query)
        if not tokens:
            return []

        idf_weights = self._calc_document_frequencies(tokens, search_domains)

        # 에러코드 패턴 추출
        error_codes = re.findall(r'-?\d{4,5}', query)

        # 전체 후보 섹션 수집 + 점진적 스코어링
        # {(domain, idx): {"score": float, "matched_tokens": set}}
        candidates: Dict[tuple, dict] = {}

        for domain in search_domains:
            if domain not in self._cache:
                continue
            for idx, section in enumerate(self._cache[domain]):
                candidates[(domain, idx)] = {
                    "score": 0.0,
                    "matched_tokens": set(),
                    "section": section,
                }

        # 순차 토큰 처리: IDF 가중치 적용
        prune_threshold = top_k * 20  # 점진적 축소 임계값

        for i, token in enumerate(tokens):
            idf = idf_weights[token]
            for key, cand in candidates.items():
                section = cand["section"]
                title_lower = section["title"].lower()
                content_lower = section["content"].lower()

                if token in title_lower:
                    cand["score"] += 3.0 * idf
                    cand["matched_tokens"].add(token)
                elif token in content_lower:
                    cand["score"] += 1.0 * idf
                    cand["matched_tokens"].add(token)

            # 중간 프루닝: 2번째 토큰 이후, 후보가 임계값 초과 시 축소
            if i > 0 and len(candidates) > prune_threshold:
                sorted_keys = sorted(
                    candidates.keys(),
                    key=lambda k: candidates[k]["score"],
                    reverse=True,
                )
                candidates = {k: candidates[k] for k in sorted_keys[:prune_threshold]}

        # 에러코드 정확 매칭 보너스
        if error_codes:
            for key, cand in candidates.items():
                section = cand["section"]
                domain = key[0]
                if domain in ("error_codes",):
                    title_lower = section["title"].lower()
                    content_lower = section["content"].lower()
                    for code in error_codes:
                        if code in title_lower or code in content_lower:
                            cand["score"] += 10.0

        # 커버리지 보정: 매칭된 토큰 비율로 점수 조정
        total_tokens = len(tokens)
        for cand in candidates.values():
            if cand["score"] > 0 and total_tokens > 1:
                coverage = len(cand["matched_tokens"]) / total_tokens
                # coverage 0.0~1.0 → 보정계수 0.5~1.0
                coverage_factor = 0.5 + 0.5 * coverage
                cand["score"] *= coverage_factor

        # 도메인 우선순위 보정: 권위 있는 소스를 learning_qa보다 우선 배치.
        # error_codes는 에러코드 패턴(-XXXX)이 있을 때만 부스트 (일반 질문에서 에러코드 오염 방지)
        _has_error_pattern = bool(error_codes)
        _DOMAIN_BOOST = {
            "pdf_manuals": 1.5,  # PDF 원본 최우선 (정확한 원본 데이터)
            "commands": 1.3,
            "configs": 1.2,
            "error_codes": 1.3 if _has_error_pattern else 0.7,  # 에러 질문이 아니면 감점
            "glossary": 0.6,  # 요약본은 중복/노이즈 → PDF 우선 + 상위 계층 분리
            "learning_qa": 0.4,  # cross-product 오염 가능성 → 강하게 감점
        }
        for key, cand in candidates.items():
            domain = key[0]
            boost = _DOMAIN_BOOST.get(domain, 1.0)
            if boost != 1.0 and cand["score"] > 0:
                cand["score"] *= boost

        # 최종 결과 수집 + content 중복 제거
        results: List[SearchResult] = []
        seen_content: set = set()

        # 점수 내림차순으로 정렬하여 최고 점수 우선 채택
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda c: c["score"],
            reverse=True,
        )

        for cand in sorted_candidates:
            if cand["score"] <= 0:
                continue
            section = cand["section"]
            # content 앞 120자를 정규화 fingerprint로 사용 (동일 답변 중복 제거)
            # 구두점/슬래시/공백 차이 무시 → 알파벳+숫자+CJK만 추출
            raw_fp = section["content"][:120].strip().lower()
            content_fp = re.sub(r"[^a-z0-9\u3040-\u9fff\uac00-\ud7af]", "", raw_fp)
            if content_fp in seen_content:
                continue
            seen_content.add(content_fp)

            results.append(SearchResult(
                title=section["title"],
                content=section["content"],
                source_file=section["source_file"],
                source_page=section.get("source_page", ""),
                relevance_score=cand["score"],
                domain=section["domain"],
                product=self.product_id,
                source_path=section.get("source_path", ""),
            ))

            if len(results) >= top_k:
                break

        return results

    def get_stats(self) -> Dict[str, int]:
        """도메인별 섹션 수 반환"""
        self._ensure_loaded()
        return {domain: len(sections) for domain, sections in self._cache.items()}


def _resolve_pdf_path_and_page(result: SearchResult):
    """
    SearchResult에서 PDF 경로와 페이지 번호를 해석.

    두 가지 소스를 처리:
    1. PDF 직접 파싱 결과: source_path 있음, source_page="p.45"
    2. 요약본(.md) 결과: source_path 없음, source_page="소스: XXX.pdf (p.45)"

    Returns:
        (pdf_path, page_num_0indexed) or (None, -1)
    """
    # Case 1: PDF 직접 파싱 결과
    if result.source_path and result.source_file.lower().endswith(".pdf"):
        page_match = re.match(r"p\.(\d+)", result.source_page or "")
        if page_match:
            return result.source_path, int(page_match.group(1)) - 1
        return None, -1

    # Case 2: 요약본(.md) → source_page에서 PDF 파일명과 페이지 추출
    source_page = result.source_page or ""
    # "소스: OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf (p.21)" 패턴
    pdf_ref = re.search(r"([A-Za-z0-9_\-][A-Za-z0-9_.\-]+\.pdf)\s*\(p\.(\d+)\)", source_page)
    if not pdf_ref:
        # content 내 "- 소스: ..." 패턴도 검색
        pdf_ref = re.search(r"([A-Za-z0-9_\-][A-Za-z0-9_.\-]+\.pdf)\s*\(p\.(\d+)\)", result.content or "")
    if not pdf_ref:
        return None, -1

    pdf_filename = pdf_ref.group(1)
    page_num = int(pdf_ref.group(2)) - 1

    # ManualRegistry에서 PDF 전체 경로 찾기
    from .manual_registry_service import get_manual_registry_service, MANUALS_BASE

    registry = get_manual_registry_service()
    all_products = registry.get_all_products()

    # product 힌트가 있으면 해당 제품 디렉토리 먼저 검색
    search_order = []
    if result.product and result.product in all_products:
        search_order.append(all_products[result.product])
    for pid, prod in all_products.items():
        if pid != result.product:
            search_order.append(prod)

    for prod in search_order:
        candidate = os.path.join(prod.directory_path, pdf_filename)
        if os.path.exists(candidate):
            return candidate, page_num

    # MANUALS_BASE 전체에서 재귀 검색 (fallback)
    for root, _dirs, files in os.walk(MANUALS_BASE):
        if pdf_filename in files:
            return os.path.join(root, pdf_filename), page_num

    return None, -1


def enrich_content_with_tables(result: SearchResult) -> str:
    """
    검색 결과의 content를 테이블 Markdown으로 보강 (lazy inline extraction).

    PDF 테이블을 인라인 마크다운으로 변환하여 평문 테이블 텍스트를 교체.
    초기 파싱 시 테이블 추출을 건너뛰고(성능), 검색 시점에 1-5 페이지만 처리.

    전략:
    - 해당 페이지를 extract_tables=True로 재추출 → 인라인 마크다운 테이블
    - 기존 content(평문 테이블)을 재추출 결과로 교체
    - content가 2000자 제한으로 잘려도 테이블이 자연 위치에 표시됨
    """
    content = result.content

    # 이미 인라인 테이블이 있으면 스킵
    if "| ---" in content or "|---" in content:
        return content

    pdf_path, page_num = _resolve_pdf_path_and_page(result)
    if not pdf_path or page_num < 0:
        return content

    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return content

        page = doc[page_num]

        # drawing pre-filter: 테이블 보더가 없는 페이지 빠르게 스킵
        _, drawing_count = StructuredKnowledgeStore._get_shaded_rects(page)

        if drawing_count >= 5:
            # 인라인 테이블로 재추출 (extract_tables=True)
            enriched = StructuredKnowledgeStore._extract_page_text_with_codeblocks(
                page, extract_tables=True,
            )
            has_tables = "| ---" in enriched or "|---" in enriched

            if has_tables:
                # 해당 페이지의 평문 버전 → content에서 찾아 교체
                flat_page = StructuredKnowledgeStore._extract_page_text_with_codeblocks(
                    page, extract_tables=False,
                )
                flat_stripped = flat_page.strip()
                enriched_stripped = enriched.strip()

                if flat_stripped and flat_stripped in content:
                    # 정확히 일치하는 부분만 교체
                    content = content.replace(flat_stripped, enriched_stripped, 1)
                else:
                    # 정확 매칭 실패 → content 전체를 재추출 결과로 교체
                    # (해당 페이지가 검색 결과의 핵심 페이지이므로)
                    content = enriched_stripped

        # 이미지 보강
        images_md = []
        try:
            imgs = StructuredKnowledgeStore._extract_page_images(
                doc, page_num, result.product or "unknown",
            )
            images_md.extend(imgs)
        except Exception:
            pass

        doc.close()

        if images_md:
            content += "\n\n" + "\n".join(images_md)

    except Exception as e:
        logger.debug(f"Lazy table extraction failed for {result.source_file}: {e}")

    return content
