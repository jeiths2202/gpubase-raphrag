#!/usr/bin/env python3
"""
키워드 기반 PDF 검색 엔진

43,147개 키워드를 245개 PDF에서 전수 검색하여
완전한 학습 데이터를 생성합니다.

Features:
1. 키워드별 PDF 전수 검색
2. 컨텍스트 추출 (전후 5줄)
3. syntax, parameters 자동 추출
4. 제품별 분류
5. 중복 제거 및 병합

Usage:
    python keyword_pdf_searcher.py
    python keyword_pdf_searcher.py --keywords docs/keyword.txt --batch-size 500
    python keyword_pdf_searcher.py --priority-only  # Manager 명령어만
"""

import re
import json
import logging
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import concurrent.futures
from functools import lru_cache

try:
    import pymupdf
except ImportError:
    print("pymupdf 필요: pip install pymupdf")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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
# 데이터 모델
# =============================================================================

@dataclass
class SearchOccurrence:
    """검색 결과 단일 항목"""
    pdf_file: str
    page_num: int
    context: str
    syntax: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    product: str = ""


@dataclass
class KeywordSearchResult:
    """키워드 검색 결과"""
    keyword: str
    total_occurrences: int
    occurrences: List[SearchOccurrence] = field(default_factory=list)
    best_syntax: Optional[str] = None
    all_parameters: List[str] = field(default_factory=list)
    primary_product: str = ""
    item_type: str = "concept"


@dataclass
class SearchStats:
    """검색 통계"""
    total_keywords: int = 0
    keywords_found: int = 0
    keywords_not_found: int = 0
    total_occurrences: int = 0
    pdfs_processed: int = 0
    syntax_extracted: int = 0
    by_product: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# 추출 패턴
# =============================================================================

class ExtractionPatterns:
    """구문 및 파라미터 추출 패턴"""

    # 구문 추출 패턴
    SYNTAX_PATTERNS = [
        # $ 시작 명령어
        re.compile(r'^\s*\$\s*(.+?)$', re.MULTILINE),
        # 구문: 또는 Syntax: 다음 줄
        re.compile(r'(?:구문|Syntax|構文|语法)[:\s]*\n?\s*(.+?)(?:\n|$)', re.IGNORECASE),
        # 대괄호 옵션 포함 명령어
        re.compile(r'^([A-Za-z][A-Za-z0-9_]*(?:\s+[\[<{].+?[\]>}])+)\s*$', re.MULTILINE),
        # KEY=value 형식
        re.compile(r'^([A-Z][A-Z0-9_]*\s*=\s*.+?)$', re.MULTILINE),
    ]

    # 파라미터 추출 패턴
    PARAM_ANGLE = re.compile(r'<([^>]+)>')  # <param>
    PARAM_BRACKET = re.compile(r'\[([^\]]+)\]')  # [option]
    PARAM_KEYVALUE = re.compile(r'\b([A-Z][A-Z0-9_]*)\s*=')  # KEY=

    # 예시 추출 패턴
    EXAMPLE_PATTERNS = [
        re.compile(r'(?:例|Example|예시)[:\s]*\n?\s*(.+?)(?:\n\n|\n[A-Z]|$)', re.IGNORECASE | re.DOTALL),
        re.compile(r'^\s*\$\s*[a-z][\w\s\-./]+$', re.MULTILINE),
    ]

    # 타입 감지 패턴
    TYPE_PATTERNS = {
        'command': re.compile(r'mgr$|run$|ctl$|cmd$|boot|down|^of|^tm|^tb', re.IGNORECASE),
        'config': re.compile(r'\.conf$|\.cfg$|\.properties$|\.xml$', re.IGNORECASE),
        'api': re.compile(r'^[A-Z]+_[A-Z0-9_]+$|^tp[a-z]+$|^tx[a-z]+$|^DS[A-Z]+'),
        'error': re.compile(r'^ABEND|^-\d{4,5}$|ERROR|ERR_'),
        'jcl': re.compile(r'^(JOB|EXEC|DD|PROC|PEND|IF|THEN|ELSE|ENDIF|SET)$'),
    }

    # 제품 추출 패턴 (파일명에서)
    PRODUCT_PATTERNS = {
        'OF_TJES': re.compile(r'TJES|Batch.*TJES', re.IGNORECASE),
        'OF_OSC': re.compile(r'OSC|Online.*CICS', re.IGNORECASE),
        'OF_OSI': re.compile(r'OSI|Online.*IMS|HiDB', re.IGNORECASE),
        'OF_TACF': re.compile(r'TACF|Security', re.IGNORECASE),
        'OF_Base': re.compile(r'Base|Dataset|Common', re.IGNORECASE),
        'OF_Batch': re.compile(r'Batch(?!.*TJES)|JCL|Sort', re.IGNORECASE),
        'OF_Gateway': re.compile(r'Gateway|GW|WebTerminal', re.IGNORECASE),
        'Tibero': re.compile(r'Tibero|TB\d', re.IGNORECASE),
        'Tmax': re.compile(r'Tmax(?!.*OpenFrame)', re.IGNORECASE),
        'JEUS': re.compile(r'JEUS', re.IGNORECASE),
        'WebtoB': re.compile(r'WebtoB|WebT', re.IGNORECASE),
        'OFCOBOL': re.compile(r'COBOL', re.IGNORECASE),
        'OFAsm': re.compile(r'Asm|Assembler', re.IGNORECASE),
    }


# =============================================================================
# PDF 검색 엔진
# =============================================================================

class KeywordPDFSearcher:
    """키워드 기반 PDF 검색 엔진"""

    def __init__(
        self,
        manuals_dir: Path,
        context_lines: int = 5,
        max_occurrences_per_keyword: int = 50,
    ):
        self.manuals_dir = manuals_dir
        self.context_lines = context_lines
        self.max_occurrences = max_occurrences_per_keyword
        self.patterns = ExtractionPatterns()
        self.stats = SearchStats()

        # PDF 파일 목록 캐싱
        self._pdf_files: List[Path] = []
        self._pdf_texts: Dict[str, List[Tuple[int, str]]] = {}  # {pdf_path: [(page_num, text), ...]}

    def load_pdf_files(self) -> List[Path]:
        """PDF 파일 목록 로드"""
        if not self._pdf_files:
            self._pdf_files = list(self.manuals_dir.rglob("*.pdf"))
            logger.info(f"PDF 파일 {len(self._pdf_files)}개 발견")
        return self._pdf_files

    def preload_pdf_texts(self, pdf_files: Optional[List[Path]] = None) -> None:
        """PDF 텍스트 미리 로드 (메모리 사용량 vs 속도 트레이드오프)"""
        if pdf_files is None:
            pdf_files = self.load_pdf_files()

        logger.info(f"PDF 텍스트 프리로딩 시작 ({len(pdf_files)}개)...")

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 50 == 0:
                logger.info(f"  프리로딩: {i}/{len(pdf_files)}")

            try:
                doc = pymupdf.open(pdf_path)
                pages = []
                for page_num, page in enumerate(doc, 1):
                    text = page.get_text()
                    if text.strip():
                        pages.append((page_num, text))
                doc.close()
                self._pdf_texts[str(pdf_path)] = pages
                self.stats.pdfs_processed += 1
            except Exception as e:
                logger.warning(f"PDF 로드 실패: {pdf_path.name}: {e}")

        logger.info(f"프리로딩 완료: {len(self._pdf_texts)}개 PDF")

    def search_keyword_in_pdf(
        self,
        keyword: str,
        pdf_path: Path,
    ) -> List[SearchOccurrence]:
        """단일 PDF에서 키워드 검색"""
        occurrences = []

        # 캐시된 텍스트 사용
        pdf_key = str(pdf_path)
        if pdf_key in self._pdf_texts:
            pages = self._pdf_texts[pdf_key]
        else:
            try:
                doc = pymupdf.open(pdf_path)
                pages = [(i + 1, page.get_text()) for i, page in enumerate(doc)]
                doc.close()
            except Exception:
                return occurrences

        # 키워드 검색 (대소문자 무시)
        keyword_pattern = re.compile(
            r'\b' + re.escape(keyword) + r'\b',
            re.IGNORECASE
        )

        product = self._extract_product(pdf_path.name)

        for page_num, text in pages:
            if not keyword_pattern.search(text):
                continue

            # 컨텍스트 추출
            context = self._extract_context(text, keyword)
            if not context:
                continue

            # 구문 추출
            syntax = self._extract_syntax(context, keyword)

            # 파라미터 추출
            parameters = self._extract_parameters(syntax) if syntax else []

            # 예시 추출
            examples = self._extract_examples(context)

            occ = SearchOccurrence(
                pdf_file=pdf_path.name,
                page_num=page_num,
                context=context[:1000],  # 최대 1000자
                syntax=syntax,
                parameters=parameters,
                examples=examples,
                product=product,
            )
            occurrences.append(occ)

            if len(occurrences) >= self.max_occurrences:
                break

        return occurrences

    def search_keyword(self, keyword: str) -> KeywordSearchResult:
        """키워드를 모든 PDF에서 검색"""
        all_occurrences = []

        pdf_files = self.load_pdf_files()

        for pdf_path in pdf_files:
            occs = self.search_keyword_in_pdf(keyword, pdf_path)
            all_occurrences.extend(occs)

            if len(all_occurrences) >= self.max_occurrences:
                break

        # 결과 병합
        result = self._merge_occurrences(keyword, all_occurrences)

        # 통계 업데이트
        if all_occurrences:
            self.stats.keywords_found += 1
            self.stats.total_occurrences += len(all_occurrences)
            if result.best_syntax:
                self.stats.syntax_extracted += 1
        else:
            self.stats.keywords_not_found += 1

        return result

    def _extract_context(self, text: str, keyword: str) -> str:
        """키워드 주변 컨텍스트 추출"""
        lines = text.split('\n')
        keyword_lower = keyword.lower()

        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                start = max(0, i - self.context_lines)
                end = min(len(lines), i + self.context_lines + 1)
                return '\n'.join(lines[start:end])

        return ""

    def _extract_syntax(self, context: str, keyword: str) -> Optional[str]:
        """구문 정보 추출"""
        # 무효 패턴 필터
        INVALID_PATTERNS = [
            re.compile(r'\.{5,}'),  # 5개 이상 연속 점
            re.compile(r'\d{3,}$'),  # 숫자로만 끝남 (페이지 번호)
            re.compile(r'^.{0,10}$'),  # 10자 이하
            re.compile(r'^\d+\s*$'),  # 숫자만
        ]

        def is_valid_syntax(s: str) -> bool:
            if not s or len(s) < 10:
                return False
            for pattern in INVALID_PATTERNS:
                if pattern.search(s):
                    return False
            # 의미있는 구문 요소 포함 확인
            has_syntax_element = any([
                '[' in s, '<' in s, '=' in s,
                '(' in s, '{' in s, '-' in s,
                s.count(' ') >= 1,  # 공백이 있어야 함
            ])
            return has_syntax_element

        # 1. $ 시작 명령어 우선 검색
        dollar_pattern = re.compile(r'^\s*\$\s*(' + re.escape(keyword) + r'[^\n]{5,80})$', re.MULTILINE | re.IGNORECASE)
        matches = dollar_pattern.findall(context)
        for match in matches:
            if is_valid_syntax(match):
                return match.strip()

        # 2. 구문/Syntax 레이블 다음 내용
        syntax_label = re.compile(
            r'(?:구문|Syntax|構文|语法|Usage)[:\s]*\n?\s*(' + re.escape(keyword) + r'[^\n]{5,100})',
            re.IGNORECASE
        )
        matches = syntax_label.findall(context)
        for match in matches:
            if is_valid_syntax(match):
                return match.strip()

        # 3. 키워드 + 옵션/파라미터 형식
        keyword_with_options = re.compile(
            r'^(' + re.escape(keyword) + r'\s+[\[<{(].+?[\]>})].*)$',
            re.MULTILINE | re.IGNORECASE
        )
        matches = keyword_with_options.findall(context)
        for match in matches:
            if is_valid_syntax(match):
                return match.strip()

        # 4. 키워드 SUBCOMMAND 형식 (tjesmgr BOOT 등)
        keyword_subcommand = re.compile(
            r'^(' + re.escape(keyword) + r'\s+[A-Z][A-Z0-9_]*(?:\s+.{5,60})?)$',
            re.MULTILINE | re.IGNORECASE
        )
        matches = keyword_subcommand.findall(context)
        for match in matches:
            if is_valid_syntax(match):
                return match.strip()

        # 5. 일반적인 키워드 시작 줄
        lines = context.split('\n')
        for line in lines:
            line = line.strip()
            if line.lower().startswith(keyword.lower()):
                if is_valid_syntax(line) and len(line) <= 150:
                    return line

        return None

    def _extract_parameters(self, syntax: str) -> List[str]:
        """파라미터 추출"""
        if not syntax:
            return []

        params = set()

        # <param> 형식
        for match in self.patterns.PARAM_ANGLE.findall(syntax):
            params.add(match)

        # [option] 형식
        for match in self.patterns.PARAM_BRACKET.findall(syntax):
            if not match.startswith('-'):
                params.add(f"[{match}]")

        # KEY= 형식
        for match in self.patterns.PARAM_KEYVALUE.findall(syntax):
            params.add(match)

        return list(params)[:10]

    def _extract_examples(self, context: str) -> List[str]:
        """예시 추출"""
        examples = []

        for pattern in self.patterns.EXAMPLE_PATTERNS:
            matches = pattern.findall(context)
            for match in matches:
                example = match.strip()
                if example and len(example) > 10:
                    examples.append(example[:200])

        return examples[:3]

    def _extract_product(self, filename: str) -> str:
        """파일명에서 제품명 추출"""
        for product, pattern in self.patterns.PRODUCT_PATTERNS.items():
            if pattern.search(filename):
                return product
        return "Unknown"

    def _detect_type(self, keyword: str, context: str) -> str:
        """항목 타입 감지"""
        for item_type, pattern in self.patterns.TYPE_PATTERNS.items():
            if pattern.search(keyword):
                return item_type
        return "concept"

    def _merge_occurrences(
        self,
        keyword: str,
        occurrences: List[SearchOccurrence],
    ) -> KeywordSearchResult:
        """여러 출처의 검색 결과 병합"""
        if not occurrences:
            return KeywordSearchResult(
                keyword=keyword,
                total_occurrences=0,
                item_type=self._detect_type(keyword, ""),
            )

        # 가장 긴 syntax 선택
        best_syntax = None
        max_len = 0
        for occ in occurrences:
            if occ.syntax and len(occ.syntax) > max_len:
                best_syntax = occ.syntax
                max_len = len(occ.syntax)

        # 파라미터 합집합
        all_params = set()
        for occ in occurrences:
            all_params.update(occ.parameters)

        # 주요 제품 결정
        product_counts = defaultdict(int)
        for occ in occurrences:
            if occ.product and occ.product != "Unknown":
                product_counts[occ.product] += 1

        primary_product = max(product_counts, key=product_counts.get) if product_counts else "Unknown"

        # 컨텍스트에서 타입 결정
        all_context = " ".join(occ.context for occ in occurrences)
        item_type = self._detect_type(keyword, all_context)

        return KeywordSearchResult(
            keyword=keyword,
            total_occurrences=len(occurrences),
            occurrences=occurrences[:10],  # 상위 10개만 저장
            best_syntax=best_syntax,
            all_parameters=list(all_params),
            primary_product=primary_product,
            item_type=item_type,
        )


# =============================================================================
# 학습 데이터 생성기
# =============================================================================

class LearningDataGenerator:
    """검색 결과를 학습 데이터로 변환"""

    def __init__(self):
        self.items: List[Dict[str, Any]] = []
        self.stats = {
            'total': 0,
            'with_syntax': 0,
            'with_params': 0,
            'by_type': defaultdict(int),
            'by_product': defaultdict(int),
        }

    def add_search_result(self, result: KeywordSearchResult) -> None:
        """검색 결과를 학습 항목으로 추가"""
        if result.total_occurrences == 0:
            return

        # 설명 구성
        description = self._build_description(result)

        item = {
            "name": result.keyword,
            "type": result.item_type,
            "description": description,
            "syntax": result.best_syntax,
            "parameters": result.all_parameters,
            "examples": [],
            "related": [],
            "source_file": result.occurrences[0].pdf_file if result.occurrences else "",
            "product": result.primary_product,
            "occurrence_count": result.total_occurrences,
        }

        # 예시 추가
        for occ in result.occurrences:
            if occ.examples:
                item["examples"].extend(occ.examples)
        item["examples"] = list(set(item["examples"]))[:3]

        self.items.append(item)

        # 통계
        self.stats['total'] += 1
        if result.best_syntax:
            self.stats['with_syntax'] += 1
        if result.all_parameters:
            self.stats['with_params'] += 1
        self.stats['by_type'][result.item_type] += 1
        self.stats['by_product'][result.primary_product] += 1

    def _build_description(self, result: KeywordSearchResult) -> str:
        """검색 결과에서 설명 구성"""
        if not result.occurrences:
            return f"{result.keyword}に関する情報です。"

        # 가장 긴 컨텍스트에서 설명 추출
        best_context = max(result.occurrences, key=lambda x: len(x.context)).context

        # 키워드 주변 문장 추출
        lines = best_context.split('\n')
        keyword_lower = result.keyword.lower()

        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                # 현재 줄과 다음 몇 줄을 설명으로 사용
                desc_lines = lines[i:i+3]
                description = ' '.join(l.strip() for l in desc_lines if l.strip())
                if len(description) > 50:
                    return description[:500]

        return best_context[:300]

    def save(self, output_path: Path) -> None:
        """학습 데이터 저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metadata": {
                "total_items": len(self.items),
                "generated_at": datetime.now().isoformat(),
                "type_stats": dict(self.stats['by_type']),
                "product_stats": dict(self.stats['by_product']),
                "quality_stats": {
                    "with_syntax": self.stats['with_syntax'],
                    "with_params": self.stats['with_params'],
                    "syntax_rate": round(self.stats['with_syntax'] / max(self.stats['total'], 1) * 100, 2),
                }
            },
            "items": self.items
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"학습 데이터 저장: {output_path}")
        logger.info(f"총 항목: {len(self.items)}")
        logger.info(f"syntax 포함: {self.stats['with_syntax']} ({data['metadata']['quality_stats']['syntax_rate']}%)")


# =============================================================================
# 메인 실행
# =============================================================================

def load_keywords(keywords_path: Path, priority_only: bool = False) -> List[str]:
    """키워드 로드"""
    keywords = []

    with open(keywords_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                keywords.append(line)

    logger.info(f"키워드 {len(keywords)}개 로드됨")

    if priority_only:
        # Manager 명령어 + 핵심 명령어만
        priority_patterns = [
            re.compile(r'mgr$', re.IGNORECASE),
            re.compile(r'^(idcams|iebgener|iebcopy|dfsort|dsmigin|textrun|tjclrun)$', re.IGNORECASE),
            re.compile(r'^(ofboot|ofdown|tmboot|tmdown|jesinit|jesdown)$', re.IGNORECASE),
            re.compile(r'\.conf$', re.IGNORECASE),
            re.compile(r'^ABEND', re.IGNORECASE),
        ]
        filtered = []
        for kw in keywords:
            for pattern in priority_patterns:
                if pattern.search(kw):
                    filtered.append(kw)
                    break
        keywords = filtered
        logger.info(f"우선순위 필터링 후: {len(keywords)}개")

    return keywords


def main():
    parser = argparse.ArgumentParser(description="키워드 기반 PDF 검색 및 학습 데이터 생성")
    parser.add_argument(
        "--keywords",
        type=Path,
        default=PROJECT_ROOT / "docs" / "keyword.txt",
        help="키워드 파일"
    )
    parser.add_argument(
        "--manuals",
        type=Path,
        default=PROJECT_ROOT / "uploads" / "manuals",
        help="매뉴얼 디렉토리"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "uploads" / "summaries" / "keyword_learning_dataset.json",
        help="출력 파일"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="배치 크기"
    )
    parser.add_argument(
        "--priority-only",
        action="store_true",
        help="우선순위 키워드만 처리"
    )
    parser.add_argument(
        "--preload",
        action="store_true",
        default=True,
        help="PDF 텍스트 프리로딩"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("키워드 기반 학습 데이터 생성 시작")
    logger.info(f"키워드: {args.keywords}")
    logger.info(f"매뉴얼: {args.manuals}")
    logger.info(f"출력: {args.output}")
    logger.info("=" * 60)

    # 키워드 로드
    keywords = load_keywords(args.keywords, args.priority_only)

    # 검색 엔진 초기화
    searcher = KeywordPDFSearcher(args.manuals)

    # PDF 프리로딩
    if args.preload:
        searcher.preload_pdf_texts()

    # 학습 데이터 생성기
    generator = LearningDataGenerator()

    # 배치 처리
    total = len(keywords)
    searcher.stats.total_keywords = total

    for i, keyword in enumerate(keywords, 1):
        if i % 100 == 0:
            found_rate = searcher.stats.keywords_found / i * 100
            logger.info(f"진행: {i}/{total} (발견률: {found_rate:.1f}%)")

        result = searcher.search_keyword(keyword)
        generator.add_search_result(result)

    # 저장
    generator.save(args.output)

    # 최종 통계
    logger.info("\n" + "=" * 60)
    logger.info("완료 통계:")
    logger.info(f"  총 키워드: {searcher.stats.total_keywords}")
    logger.info(f"  발견: {searcher.stats.keywords_found}")
    logger.info(f"  미발견: {searcher.stats.keywords_not_found}")
    logger.info(f"  syntax 추출: {searcher.stats.syntax_extracted}")
    logger.info(f"  총 출현: {searcher.stats.total_occurrences}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
