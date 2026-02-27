#!/usr/bin/env python3
"""
Plain Text Extractor for LLM Pre-training
==========================================
PDF 매뉴얼에서 plain text를 추출합니다.
ChatML 형식이 아닌 순수 텍스트로 출력하여 Continued Pre-training에 사용합니다.

Usage:
  # Extract all PDFs in a directory
  python extract_plain_text.py --input "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP"

  # Extract a single PDF
  python extract_plain_text.py --input "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP/OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf"

  # Specify output dir + merge into single corpus
  python extract_plain_text.py --input "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --output uploads/training_text --merge

  # Stats only (no file output)
  python extract_plain_text.py --input "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --stats

Output:
  - 개별 파일: <output_dir>/<pdf_name>.txt
  - 합본 파일: <output_dir>/corpus.txt (--merge 옵션)
  - 통계 파일: <output_dir>/extraction_stats.json
"""

import json
import re
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        print("Error: PyMuPDF 필요. pip install PyMuPDF")
        sys.exit(1)

# Windows CP932 encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# 텍스트 정제 유틸리티
# ============================================================================

# 문서 헤더/푸터 패턴 (PDF 페이지 상하단에 반복되는 텍스트)
HEADER_FOOTER_PATTERNS = [
    # OpenFrame 매뉴얼 헤더: "OpenFrame XXX Guide" / "第N章 タイトル"
    re.compile(r"^OpenFrame.*Guide.*$", re.MULTILINE),
    re.compile(r"^Tibero.*Guide.*$", re.MULTILINE),
    re.compile(r"^Tmax.*Guide.*$", re.MULTILINE),
    # 페이지 번호 패턴
    re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE),
    re.compile(r"^\s*[ivxlc]+\s*$", re.MULTILINE),  # 로마 숫자
    # 구분선 패턴 (| 숫자, 숫자 |)
    re.compile(r"^\s*\|\s*\d+\s*$", re.MULTILINE),
    re.compile(r"^\s*\d+\s*\|\s*$", re.MULTILINE),
    # Copyright/TmaxSoft 푸터
    re.compile(r"^.*TmaxSoft\s+Co\..*$", re.MULTILINE),
    re.compile(r"^.*Copyright.*TmaxSoft.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*All\s+rights\s+reserved.*$", re.MULTILINE | re.IGNORECASE),
]

# TOC 페이지 감지 패턴
TOC_PATTERNS = [
    re.compile(r"目\s*次", re.MULTILINE),
    re.compile(r"Table\s+of\s+Contents", re.IGNORECASE),
]

# 프론트매터 패턴 (표지, 저작권 등)
FRONT_MATTER_PATTERNS = [
    re.compile(r"発行日", re.MULTILINE),
    re.compile(r"ガイドバージョン", re.MULTILINE),
    re.compile(r"著作権者", re.MULTILINE),
    re.compile(r"Publication\s+Date", re.IGNORECASE),
]

# 섹션 제목 패턴
SECTION_PATTERNS = [
    re.compile(r"^第(\d+)章\s+(.+)$", re.MULTILINE),                   # 第1章 概要
    re.compile(r"^付録\s*([A-Z])\.?\s+(.+)$", re.MULTILINE),           # 付録A 設定
    re.compile(r"^(\d+\.\d+\.\d+\.?)\s+(.+)$", re.MULTILINE),         # 1.1.1 XXX
    re.compile(r"^(\d+\.\d+\.?)\s+(.+)$", re.MULTILINE),              # 1.1 XXX
]


@dataclass
class ExtractionStats:
    """추출 통계"""
    total_pdfs: int = 0
    success: int = 0
    failed: int = 0
    total_pages: int = 0
    total_chars: int = 0
    total_lines: int = 0
    skipped_front_pages: int = 0
    files: List[Dict[str, Any]] = field(default_factory=list)


class PlainTextExtractor:
    """PDF → Plain Text 추출기"""

    def __init__(
        self,
        skip_front_matter: bool = True,
        skip_toc: bool = True,
        min_line_length: int = 2,
        remove_headers_footers: bool = True,
        use_toc_headers: bool = True,
    ):
        """
        Args:
            skip_front_matter: 프론트매터(표지, 저작권) 페이지 스킵
            skip_toc: 목차 페이지 스킵
            min_line_length: 최소 라인 길이 (이하는 제거)
            remove_headers_footers: 헤더/푸터 패턴 제거
            use_toc_headers: TOC 기반 섹션 헤더 삽입
        """
        self.skip_front_matter = skip_front_matter
        self.skip_toc = skip_toc
        self.min_line_length = min_line_length
        self.remove_headers_footers = remove_headers_footers
        self.use_toc_headers = use_toc_headers

    def extract_pdf(self, pdf_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        PDF에서 plain text 추출

        Args:
            pdf_path: PDF 파일 경로

        Returns:
            (추출된 텍스트, 파일 메타데이터)
        """
        doc = pymupdf.open(str(pdf_path))
        total_pages = len(doc)

        # TOC 추출
        toc = doc.get_toc()  # [(level, title, page_num), ...]
        toc_page_map = self._build_toc_page_map(toc)

        # 프론트매터/TOC 페이지 범위 결정
        content_start_page = self._find_content_start(doc, toc)

        meta = {
            "file": pdf_path.name,
            "total_pages": total_pages,
            "content_start_page": content_start_page,
            "toc_entries": len(toc),
        }

        # 페이지별 텍스트 추출
        sections: List[str] = []
        pages_processed = 0

        for page_num in range(total_pages):
            if page_num < content_start_page:
                continue

            page = doc[page_num]

            # 테이블 추출
            tables_md = self._extract_tables(page)

            # 텍스트 추출
            raw_text = page.get_text()

            # 정제
            cleaned = self._clean_page_text(raw_text)
            if not cleaned.strip():
                continue

            # TOC 기반 섹션 헤더 삽입
            if self.use_toc_headers and (page_num + 1) in toc_page_map:
                for entry in toc_page_map[page_num + 1]:
                    level, title = entry
                    # 레벨별 마크다운 헤딩 (plain text이지만 구조 표현)
                    prefix = "#" * min(level, 4)
                    header_line = f"\n{prefix} {title}\n"
                    # 텍스트 앞에 이미 해당 제목이 있으면 중복 삽입 방지
                    if title not in cleaned[:200]:
                        sections.append(header_line)

            # 단락 재구성
            paragraphs = self._reconstruct_paragraphs(cleaned)
            section_text = "\n\n".join(paragraphs)

            # 테이블 병합
            if tables_md:
                section_text += "\n\n" + "\n\n".join(tables_md)

            sections.append(section_text)
            pages_processed += 1

        doc.close()

        # 최종 텍스트 조합
        full_text = "\n\n".join(sections)

        # 후처리: 과도한 빈 줄 제거
        full_text = re.sub(r"\n{4,}", "\n\n\n", full_text)
        full_text = full_text.strip()

        meta["pages_processed"] = pages_processed
        meta["chars"] = len(full_text)
        meta["lines"] = full_text.count("\n") + 1

        return full_text, meta

    def _build_toc_page_map(self, toc: List) -> Dict[int, List[Tuple[int, str]]]:
        """TOC → 페이지별 섹션 헤더 매핑"""
        page_map: Dict[int, List[Tuple[int, str]]] = {}
        for level, title, page_num in toc:
            if page_num not in page_map:
                page_map[page_num] = []
            page_map[page_num].append((level, title))
        return page_map

    def _find_content_start(self, doc: pymupdf.Document, toc: List) -> int:
        """
        본문 시작 페이지 결정 (0-indexed)

        전략:
        1. TOC가 있으면 → 실제 챕터(第N章, 付録, 또는 "このガイドについて" 등) 시작 페이지
        2. "目次", 표지, 문서정보 등 프론트매터 페이지는 스킵
        3. TOC가 없으면 → 텍스트 패턴 스캔
        """
        if not self.skip_front_matter:
            return 0

        # TOC 기반 분석
        if toc:
            # 프론트매터 제목 패턴 (스킵 대상)
            skip_titles = {"目次", "OpenFrame", "文書情報", "図目次", "表目次",
                           "Table of Contents", "List of Figures", "List of Tables"}
            chapter_pattern = re.compile(r"第\d+章|付録\s*[A-Z]|Chapter\s+\d|Appendix\s+[A-Z]")

            # 첫 번째 실제 콘텐츠 챕터 찾기
            for level, title, page_num in toc:
                title_stripped = title.strip()
                # 프론트매터 제목이면 스킵
                if title_stripped in skip_titles:
                    continue
                # 챕터 패턴이면 본문 시작
                if chapter_pattern.search(title_stripped):
                    return max(0, page_num - 1)  # 0-indexed
                # "このガイドについて" 같은 서문도 유용한 콘텐츠
                if level == 1 and title_stripped not in skip_titles:
                    return max(0, page_num - 1)  # 0-indexed

            # fallback: 첫 번째 레벨 1 이후
            for level, title, page_num in toc:
                if level == 1 and title.strip() not in skip_titles:
                    return max(0, page_num - 1)

        # TOC 없음: 패턴 기반 스캔 (처음 15페이지)
        front_end = 0
        scan_limit = min(15, len(doc))

        for page_num in range(scan_limit):
            page_text = doc[page_num].get_text()

            is_toc_page = any(p.search(page_text) for p in TOC_PATTERNS)
            is_front = any(p.search(page_text) for p in FRONT_MATTER_PATTERNS)

            if is_toc_page or is_front:
                front_end = page_num + 1

        return front_end

    def _extract_tables(self, page) -> List[str]:
        """페이지에서 테이블 추출 → GFM Markdown"""
        result = []
        try:
            tables = page.find_tables()
            for table in tables:
                data = table.extract()
                if data and len(data) >= 2:
                    md = self._table_to_markdown(data)
                    if md:
                        result.append(md)
        except Exception:
            pass
        return result

    def _table_to_markdown(self, table_data: List[List]) -> str:
        """2D 테이블 → GFM Markdown"""
        if not table_data or len(table_data) < 2:
            return ""

        # None 치환
        table_data = [
            [str(cell).strip() if cell else "" for cell in row]
            for row in table_data
        ]

        # 열 수 정규화
        max_cols = max(len(row) for row in table_data)
        table_data = [row + [""] * (max_cols - len(row)) for row in table_data]

        lines = []
        header = table_data[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join("---" for _ in header) + "|")
        for row in table_data[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _clean_page_text(self, text: str) -> str:
        """페이지 텍스트 정제"""
        # 헤더/푸터 제거
        if self.remove_headers_footers:
            for pattern in HEADER_FOOTER_PATTERNS:
                text = pattern.sub("", text)

        # 탭 → 스페이스
        text = text.replace("\t", "    ")

        # 연속 스페이스 정리 (인덴트 보존을 위해 줄 시작은 유지)
        text = re.sub(r"[ ]{3,}", "  ", text)

        # 극단적으로 짧은 라인 필터링 (페이지 번호 등)
        lines = text.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip()
            if len(stripped) < self.min_line_length:
                if stripped:
                    continue  # 너무 짧은 내용 라인 스킵
                else:
                    filtered.append("")  # 빈 줄은 유지
            else:
                filtered.append(line)

        return "\n".join(filtered)

    def _reconstruct_paragraphs(self, text: str) -> List[str]:
        """
        PDF 줄바꿈을 의미있는 단락으로 재구성

        규칙:
        1. 빈 줄 → 단락 구분
        2. 문장 종결자(。.!?)로 끝나면 단락 완료
        3. 불릿/번호 리스트는 별도 라인
        4. 섹션 제목 패턴은 별도 라인
        5. 코드 블록 ($, KEY=VAL, [SECTION]) 보존
        """
        SENTENCE_ENDERS = frozenset(".!?。？！")
        LIST_MARKER = re.compile(r"^\s*[-•*·●]\s|^\s*\d+[.)]\s|^\s*\([0-9a-zA-Z]+\)")
        CODE_LINE = re.compile(r"^\s*[\$#>]\s|^[A-Z_]+=|^\[[\w_]+\]")
        HEADING = re.compile(r"^#{1,4}\s|^第\d+章|^付録\s*[A-Z]|^\d+\.\d+")

        paragraphs = []
        current: List[str] = []

        for line in text.split("\n"):
            stripped = line.strip()

            # 빈 줄 → 단락 종료
            if not stripped:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue

            # 섹션 제목 → 별도 단락
            if HEADING.match(stripped):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(stripped)
                continue

            # 리스트 항목 → 별도 라인
            if LIST_MARKER.match(stripped):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(stripped)
                continue

            # 코드 라인 → 별도 라인
            if CODE_LINE.match(stripped):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(stripped)
                continue

            current.append(stripped)

            # 문장 종결자로 끝나면 단락 완료
            if stripped[-1] in SENTENCE_ENDERS:
                paragraphs.append(" ".join(current))
                current = []

        if current:
            paragraphs.append(" ".join(current))

        return [p for p in paragraphs if p.strip()]


def extract_directory(
    input_dir: Path,
    output_dir: Path,
    merge: bool = False,
    extractor: Optional[PlainTextExtractor] = None,
    recursive: bool = False,
) -> ExtractionStats:
    """
    디렉토리 내 모든 PDF에서 plain text 추출

    Args:
        input_dir: PDF 디렉토리
        output_dir: 출력 디렉토리
        merge: True면 corpus.txt 합본 생성
        extractor: PlainTextExtractor 인스턴스
        recursive: True면 하위 디렉토리도 재귀 검색
    """
    if extractor is None:
        extractor = PlainTextExtractor()

    stats = ExtractionStats()
    output_dir.mkdir(parents=True, exist_ok=True)

    # PDF 파일 수집 (recursive면 하위 디렉토리도 탐색)
    if recursive:
        pdfs = sorted(input_dir.rglob("*.pdf"))
    else:
        pdfs = sorted(input_dir.glob("*.pdf"))
        # fallback: 상위에 PDF 없으면 하위도 탐색
        if not pdfs:
            pdfs = sorted(input_dir.rglob("*.pdf"))
            if pdfs:
                logger.info(f"  상위 디렉토리에 PDF 없음 → 하위 디렉토리에서 {len(pdfs)}개 발견")
    stats.total_pdfs = len(pdfs)

    if not pdfs:
        logger.warning(f"PDF 파일 없음: {input_dir}")
        return stats

    logger.info(f"대상 PDF: {len(pdfs)}개 ({input_dir.name})")

    corpus_parts: List[str] = []

    for i, pdf_path in enumerate(pdfs, 1):
        logger.info(f"[{i}/{len(pdfs)}] {pdf_path.name}")

        try:
            text, meta = extractor.extract_pdf(pdf_path)

            if not text.strip():
                logger.warning(f"  텍스트 없음, 스킵")
                stats.failed += 1
                continue

            # 개별 파일 저장
            txt_name = pdf_path.stem + ".txt"
            txt_path = output_dir / txt_name
            txt_path.write_text(text, encoding="utf-8")

            # 통계 갱신
            stats.success += 1
            stats.total_pages += meta["total_pages"]
            stats.total_chars += meta["chars"]
            stats.total_lines += meta["lines"]
            stats.skipped_front_pages += meta["content_start_page"]
            stats.files.append(meta)

            logger.info(
                f"  → {txt_name} ({meta['pages_processed']}/{meta['total_pages']} pages, "
                f"{meta['chars']:,} chars)"
            )

            # 합본용
            if merge:
                # 문서 구분자 삽입
                doc_header = (
                    f"\n{'='*80}\n"
                    f"Document: {pdf_path.name}\n"
                    f"{'='*80}\n\n"
                )
                corpus_parts.append(doc_header + text)

        except Exception as e:
            logger.error(f"  추출 실패: {e}")
            stats.failed += 1
            stats.files.append({"file": pdf_path.name, "error": str(e)})

    # 합본 저장
    if merge and corpus_parts:
        corpus_path = output_dir / "corpus.txt"
        corpus_text = "\n\n".join(corpus_parts)
        corpus_path.write_text(corpus_text, encoding="utf-8")
        logger.info(f"합본 저장: {corpus_path} ({len(corpus_text):,} chars)")

    # 통계 저장
    stats_dict = {
        "total_pdfs": stats.total_pdfs,
        "success": stats.success,
        "failed": stats.failed,
        "total_pages": stats.total_pages,
        "total_chars": stats.total_chars,
        "total_lines": stats.total_lines,
        "skipped_front_pages": stats.skipped_front_pages,
        "avg_chars_per_pdf": stats.total_chars // max(stats.success, 1),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "extracted_at": datetime.now().isoformat(),
        "files": stats.files,
    }
    stats_path = output_dir / "extraction_stats.json"
    stats_path.write_text(
        json.dumps(stats_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return stats


def _sanitize_dir_name(name: str) -> str:
    """디렉토리명 정규화 (스페이스 → 언더스코어, 특수문자 제거)"""
    sanitized = name.replace(" ", "_")
    # 연속 언더스코어 정리
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")


def extract_all_products(
    manuals_dir: Path,
    output_base: Path,
    merge: bool = True,
    extractor: Optional[PlainTextExtractor] = None,
    skip_existing: bool = False,
) -> Dict[str, Any]:
    """
    uploads/manuals/ 하위 모든 제품 디렉토리에서 plain text 일괄 추출

    Args:
        manuals_dir: uploads/manuals/ 경로
        output_base: uploads/training_text/ 경로
        merge: 제품별 corpus.txt 생성
        extractor: PlainTextExtractor 인스턴스
        skip_existing: True면 이미 corpus.txt가 있는 제품은 스킵
    """
    if extractor is None:
        extractor = PlainTextExtractor()

    product_dirs = sorted([
        d for d in manuals_dir.iterdir()
        if d.is_dir()
    ])

    all_results = {
        "manuals_dir": str(manuals_dir),
        "output_base": str(output_base),
        "total_products": len(product_dirs),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "total_pdfs": 0,
        "total_chars": 0,
        "products": [],
    }

    print(f"\n전체 제품: {len(product_dirs)}개")
    print(f"출력 디렉토리: {output_base}")
    print("-" * 70)

    for idx, product_dir in enumerate(product_dirs, 1):
        dir_name = _sanitize_dir_name(product_dir.name)
        output_dir = output_base / dir_name

        # 스킵 체크
        if skip_existing and (output_dir / "corpus.txt").exists():
            existing_corpus = output_dir / "corpus.txt"
            size = existing_corpus.stat().st_size
            print(f"[{idx:2d}/{len(product_dirs)}] {product_dir.name}")
            print(f"  → SKIP (corpus.txt 존재, {size:,} bytes)")
            all_results["skipped"] += 1

            # 기존 통계 로드
            stats_file = output_dir / "extraction_stats.json"
            if stats_file.exists():
                existing_stats = json.loads(stats_file.read_text(encoding="utf-8"))
                all_results["total_pdfs"] += existing_stats.get("total_pdfs", 0)
                all_results["total_chars"] += existing_stats.get("total_chars", 0)
                all_results["products"].append({
                    "name": product_dir.name,
                    "dir_name": dir_name,
                    "status": "skipped",
                    "pdfs": existing_stats.get("total_pdfs", 0),
                    "chars": existing_stats.get("total_chars", 0),
                })
            continue

        print(f"\n[{idx:2d}/{len(product_dirs)}] {product_dir.name}")

        try:
            stats = extract_directory(
                input_dir=product_dir,
                output_dir=output_dir,
                merge=merge,
                extractor=extractor,
                recursive=True,
            )

            all_results["processed"] += 1
            all_results["total_pdfs"] += stats.total_pdfs
            all_results["total_chars"] += stats.total_chars
            all_results["products"].append({
                "name": product_dir.name,
                "dir_name": dir_name,
                "status": "success",
                "pdfs": stats.total_pdfs,
                "success": stats.success,
                "failed": stats.failed,
                "pages": stats.total_pages,
                "chars": stats.total_chars,
                "lines": stats.total_lines,
            })

            if stats.total_pdfs == 0:
                print(f"  → PDF 없음")
            else:
                print(
                    f"  → {stats.success}/{stats.total_pdfs} PDFs, "
                    f"{stats.total_chars:,} chars"
                )
                if merge and stats.success > 0:
                    corpus_size = (output_dir / "corpus.txt").stat().st_size
                    print(f"  → corpus.txt: {corpus_size:,} bytes")

        except Exception as e:
            logger.error(f"  제품 처리 실패: {e}")
            all_results["failed"] += 1
            all_results["products"].append({
                "name": product_dir.name,
                "dir_name": dir_name,
                "status": "error",
                "error": str(e),
            })

    # 전체 통계 저장
    all_results["extracted_at"] = datetime.now().isoformat()
    summary_path = output_base / "all_products_stats.json"
    output_base.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="PDF 매뉴얼에서 Plain Text 추출 (LLM Pre-training용)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 제품 일괄 추출 (uploads/manuals/ 하위 전체)
  python extract_plain_text.py --all --merge

  # 이미 추출된 제품은 스킵
  python extract_plain_text.py --all --merge --skip-existing

  # MVS OpenFrame 매뉴얼 전체 추출
  python extract_plain_text.py -i uploads/manuals/MVS_Openframe\\ 7.1_v3.1.3_JP

  # 합본 파일도 생성
  python extract_plain_text.py -i uploads/manuals/MVS_Openframe\\ 7.1_v3.1.3_JP --merge

  # 출력 디렉토리 지정
  python extract_plain_text.py -i uploads/manuals/MVS_Openframe\\ 7.1_v3.1.3_JP -o uploads/training_text/mvs

  # 통계만 확인
  python extract_plain_text.py -i uploads/manuals/MVS_Openframe\\ 7.1_v3.1.3_JP --stats
        """,
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="입력 PDF 파일 또는 디렉토리 경로",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="uploads/manuals/ 하위 전체 제품 일괄 추출",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="출력 디렉토리 (기본: uploads/training_text/<input_dir_name>)",
    )
    parser.add_argument(
        "--merge", action="store_true",
        help="corpus.txt 합본 파일 생성",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="통계만 출력 (파일 저장 안 함)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="이미 corpus.txt가 존재하는 제품 스킵 (--all 모드)",
    )
    parser.add_argument(
        "--no-toc-headers", action="store_true",
        help="TOC 기반 섹션 헤더 삽입 비활성화",
    )
    parser.add_argument(
        "--keep-front-matter", action="store_true",
        help="프론트매터(표지, 목차) 포함",
    )
    parser.add_argument(
        "--min-line-length", type=int, default=2,
        help="최소 라인 길이 (기본: 2)",
    )
    args = parser.parse_args()

    # --all과 --input 중 하나는 필수
    if not args.all and not args.input:
        parser.error("--all 또는 --input/-i 중 하나를 지정하세요")

    extractor = PlainTextExtractor(
        skip_front_matter=not args.keep_front_matter,
        skip_toc=not args.keep_front_matter,
        min_line_length=args.min_line_length,
        remove_headers_footers=True,
        use_toc_headers=not args.no_toc_headers,
    )

    print("=" * 70)
    print("Plain Text Extractor for LLM Pre-training")
    print("=" * 70)

    # --all 모드: 전체 제품 일괄 추출
    if args.all:
        project_root = Path(__file__).resolve().parents[2]
        manuals_dir = project_root / "uploads" / "manuals"
        output_base = Path(args.output) if args.output else project_root / "uploads" / "training_text"

        if not manuals_dir.exists():
            logger.error(f"매뉴얼 디렉토리 없음: {manuals_dir}")
            sys.exit(1)

        results = extract_all_products(
            manuals_dir=manuals_dir,
            output_base=output_base,
            merge=args.merge,
            extractor=extractor,
            skip_existing=args.skip_existing,
        )

        print(f"\n{'='*70}")
        print("전체 추출 완료!")
        print(f"  제품 수: {results['total_products']}")
        print(f"  처리: {results['processed']}, 스킵: {results['skipped']}, 실패: {results['failed']}")
        print(f"  총 PDF: {results['total_pdfs']}")
        print(f"  총 문자: {results['total_chars']:,}")
        print(f"  통계: {output_base / 'all_products_stats.json'}")

        # 제품별 요약 테이블
        print(f"\n{'제품':<55} {'PDFs':>5} {'문자 수':>12} {'상태':>8}")
        print("-" * 84)
        for p in results["products"]:
            chars = p.get("chars", 0)
            pdfs = p.get("pdfs", 0)
            status = p.get("status", "?")
            print(f"  {p['name']:<53} {pdfs:>5} {chars:>12,} {status:>8}")

        print("=" * 70)
        sys.exit(0)

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"경로 없음: {input_path}")
        sys.exit(1)

    # 출력 디렉토리 결정
    if args.output:
        output_dir = Path(args.output)
    else:
        # 프로젝트 루트 기준
        project_root = Path(__file__).resolve().parents[2]
        if input_path.is_dir():
            dir_name = _sanitize_dir_name(input_path.name)
        else:
            dir_name = input_path.stem
        output_dir = project_root / "uploads" / "training_text" / dir_name

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        # 단일 PDF 모드
        logger.info(f"단일 PDF: {input_path.name}")
        text, meta = extractor.extract_pdf(input_path)

        if args.stats:
            print(f"\n파일: {meta['file']}")
            print(f"페이지: {meta['total_pages']} (본문 시작: {meta['content_start_page']+1})")
            print(f"처리 페이지: {meta['pages_processed']}")
            print(f"문자 수: {meta['chars']:,}")
            print(f"라인 수: {meta['lines']:,}")
            print(f"TOC 항목: {meta['toc_entries']}")
            # 처음 500자 미리보기
            print(f"\n--- 미리보기 (처음 500자) ---")
            print(text[:500])
            print("...")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            txt_path = output_dir / (input_path.stem + ".txt")
            txt_path.write_text(text, encoding="utf-8")
            print(f"\n저장: {txt_path}")
            print(f"문자 수: {meta['chars']:,}")

    elif input_path.is_dir():
        # 디렉토리 모드
        if args.stats:
            # 통계만 출력 (임시 디렉토리 사용하지 않고 메모리에서 처리)
            pdfs = sorted(input_path.glob("*.pdf"))
            if not pdfs:
                pdfs = sorted(input_path.rglob("*.pdf"))
            print(f"\n대상: {input_path}")
            print(f"PDF 수: {len(pdfs)}")
            total_chars = 0
            total_pages = 0
            for i, pdf in enumerate(pdfs, 1):
                try:
                    text, meta = extractor.extract_pdf(pdf)
                    total_chars += meta["chars"]
                    total_pages += meta["total_pages"]
                    print(
                        f"  [{i:2d}/{len(pdfs)}] {pdf.name:<60} "
                        f"{meta['pages_processed']:>3}/{meta['total_pages']:>3} pages  "
                        f"{meta['chars']:>8,} chars"
                    )
                except Exception as e:
                    print(f"  [{i:2d}/{len(pdfs)}] {pdf.name:<60} ERROR: {e}")
            print(f"\n합계: {total_pages} pages, {total_chars:,} chars")
        else:
            stats = extract_directory(
                input_dir=input_path,
                output_dir=output_dir,
                merge=args.merge,
                extractor=extractor,
                recursive=True,
            )
            print(f"\n{'='*70}")
            print(f"추출 완료!")
            print(f"  성공: {stats.success}/{stats.total_pdfs}")
            print(f"  실패: {stats.failed}")
            print(f"  총 페이지: {stats.total_pages}")
            print(f"  총 문자: {stats.total_chars:,}")
            print(f"  총 라인: {stats.total_lines:,}")
            print(f"  프론트매터 스킵: {stats.skipped_front_pages} pages")
            print(f"  출력: {output_dir}")
            if args.merge:
                print(f"  합본: {output_dir / 'corpus.txt'}")
            print(f"  통계: {output_dir / 'extraction_stats.json'}")
    else:
        logger.error(f"유효한 PDF 파일 또는 디렉토리가 아닙니다: {input_path}")
        sys.exit(1)

    print("=" * 70)


if __name__ == "__main__":
    main()
