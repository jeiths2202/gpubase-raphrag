#!/usr/bin/env python3
"""
영문 키워드 추출 스크립트

uploads/manuals 디렉토리의 모든 PDF에서 영문 키워드를 추출합니다.

추출 대상:
- 명령어 (tjesmgr, oscmgr, idcams 등)
- 설정 파라미터 (SPOOL, JOBCLASS 등)
- 함수/API 이름 (DSALC_*, tpcall 등)
- 에러 코드 (ABEND S0C7 등)
- 기술 용어 (VSAM, KSDS, JCL 등)
- 파일/경로명
- 환경변수
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Set, List, Tuple
import logging

# pymupdf 임포트
try:
    import pymupdf
except ImportError:
    print("pymupdf가 필요합니다: pip install pymupdf")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 프로젝트 루트 찾기
def get_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()

PROJECT_ROOT = get_project_root()
MANUALS_DIR = PROJECT_ROOT / "uploads" / "manuals"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "keyword.txt"


# =============================================================================
# 영문 키워드 추출 패턴
# =============================================================================

# 1. 대문자 키워드 (2글자 이상)
UPPERCASE_PATTERN = re.compile(r'\b[A-Z][A-Z0-9_]{1,}[A-Z0-9]\b')

# 2. 명령어 패턴 (소문자 + 숫자)
COMMAND_PATTERN = re.compile(r'\b[a-z][a-z0-9_]{2,}\b')

# 3. 혼합 케이스 (camelCase, PascalCase)
MIXED_CASE_PATTERN = re.compile(r'\b[A-Z][a-z]+[A-Z][a-zA-Z0-9]*\b|\b[a-z]+[A-Z][a-zA-Z0-9]*\b')

# 4. 함수/API 패턴 (접두사_이름)
FUNCTION_PATTERN = re.compile(r'\b[A-Za-z]+_[A-Za-z0-9_]+\b')

# 5. 파일 확장자 패턴
FILE_PATTERN = re.compile(r'\b[A-Za-z0-9_-]+\.(conf|cfg|xml|properties|sh|bat|txt|log|dat|jcl|cbl|asm|c|h|java|py)\b', re.IGNORECASE)

# 6. 환경변수 패턴
ENV_VAR_PATTERN = re.compile(r'\$\{?[A-Z][A-Z0-9_]+\}?|\$[A-Z][A-Z0-9_]+')

# 7. 경로 패턴
PATH_PATTERN = re.compile(r'(?:/[A-Za-z0-9_.-]+)+|(?:[A-Za-z]:\\[A-Za-z0-9_\\.-]+)+')

# 8. 에러코드 패턴 (ABEND, S0C7 등)
ERROR_CODE_PATTERN = re.compile(r'\bABEND\s+S[0-9A-F]{3,4}\b|\b[A-Z]{2,4}[-]?\d{3,5}\b')

# 9. 옵션/플래그 패턴
OPTION_PATTERN = re.compile(r'\s[-]{1,2}[a-zA-Z][a-zA-Z0-9_-]*\b')

# 10. JCL 키워드
JCL_KEYWORDS = re.compile(r'\b(JOB|EXEC|DD|PROC|PEND|IF|THEN|ELSE|ENDIF|SET|INCLUDE|JCLLIB|OUTPUT|CNTL|ENDCNTL)\b')

# 11. 영문 약어 (2-6글자 대문자)
ACRONYM_PATTERN = re.compile(r'\b[A-Z]{2,6}\b')

# 12. 버전 패턴
VERSION_PATTERN = re.compile(r'\b[vV]?\d+\.\d+(?:\.\d+)*\b')

# 13. 영문 단어 (3글자 이상, 소문자)
ENGLISH_WORD_PATTERN = re.compile(r'\b[a-z]{3,}\b')


# =============================================================================
# 제외할 패턴 (노이즈)
# =============================================================================

# 일반적인 영어 단어 (기술 용어가 아닌 것)
COMMON_WORDS = {
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her',
    'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may', 'new', 'now',
    'old', 'see', 'way', 'who', 'did', 'get', 'let', 'say', 'she', 'too', 'use',
    'this', 'that', 'with', 'have', 'will', 'your', 'from', 'they', 'been', 'call',
    'come', 'make', 'than', 'find', 'give', 'know', 'take', 'into', 'just', 'over',
    'such', 'also', 'back', 'only', 'some', 'them', 'then', 'when', 'most', 'much',
    'what', 'which', 'while', 'about', 'after', 'where', 'would', 'could', 'should',
    'there', 'these', 'those', 'other', 'their', 'being', 'because', 'before',
    'between', 'through', 'during', 'under', 'again', 'further', 'once', 'here',
    'page', 'chapter', 'section', 'table', 'figure', 'example', 'note', 'guide',
    'reference', 'manual', 'document', 'version', 'copyright', 'reserved', 'rights',
    'tmax', 'openframe', 'tibero', 'jeus', 'webtob',  # 제품명은 별도 처리
    'pdf', 'doc', 'html', 'http', 'https', 'www', 'com', 'org', 'net',
    'true', 'false', 'null', 'none', 'yes', 'no',
    'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
}

# 제외할 대문자 약어 (문서 메타데이터 등)
EXCLUDE_ACRONYMS = {
    'PDF', 'DOC', 'HTML', 'HTTP', 'HTTPS', 'WWW', 'URL', 'URI',
    'JP', 'EN', 'KO', 'KR',  # 언어 코드
    'AM', 'PM',  # 시간
}


# =============================================================================
# 기술 키워드 분류
# =============================================================================

class KeywordExtractor:
    """PDF에서 영문 키워드를 추출하는 클래스"""

    def __init__(self):
        self.all_keywords: Set[str] = set()
        self.keywords_by_category: defaultdict = defaultdict(set)
        self.keywords_by_file: defaultdict = defaultdict(set)
        self.processed_files = 0
        self.failed_files = []

    def extract_from_text(self, text: str, source_file: str = "") -> Set[str]:
        """텍스트에서 영문 키워드 추출"""
        keywords = set()

        # 1. 대문자 키워드 (가장 중요)
        for match in UPPERCASE_PATTERN.finditer(text):
            word = match.group()
            if word not in EXCLUDE_ACRONYMS and len(word) >= 2:
                keywords.add(word)
                self.keywords_by_category['uppercase'].add(word)

        # 2. 함수/API 패턴 (언더스코어 포함)
        for match in FUNCTION_PATTERN.finditer(text):
            word = match.group()
            keywords.add(word)
            self.keywords_by_category['function'].add(word)

        # 3. 명령어 패턴 (소문자)
        for match in COMMAND_PATTERN.finditer(text):
            word = match.group()
            if word.lower() not in COMMON_WORDS and len(word) >= 3:
                # 기술 용어로 보이는 것만
                if self._is_technical_term(word):
                    keywords.add(word)
                    self.keywords_by_category['command'].add(word)

        # 4. 혼합 케이스
        for match in MIXED_CASE_PATTERN.finditer(text):
            word = match.group()
            keywords.add(word)
            self.keywords_by_category['mixed_case'].add(word)

        # 5. 파일 패턴
        for match in FILE_PATTERN.finditer(text):
            word = match.group()
            keywords.add(word)
            self.keywords_by_category['file'].add(word)

        # 6. 환경변수
        for match in ENV_VAR_PATTERN.finditer(text):
            word = match.group().strip('${}')
            keywords.add(word)
            self.keywords_by_category['env_var'].add(word)

        # 7. 에러코드
        for match in ERROR_CODE_PATTERN.finditer(text):
            word = match.group()
            keywords.add(word)
            self.keywords_by_category['error_code'].add(word)

        # 8. 옵션/플래그
        for match in OPTION_PATTERN.finditer(text):
            word = match.group().strip()
            if len(word) >= 2:
                keywords.add(word)
                self.keywords_by_category['option'].add(word)

        # 9. JCL 키워드
        for match in JCL_KEYWORDS.finditer(text):
            word = match.group()
            keywords.add(word)
            self.keywords_by_category['jcl'].add(word)

        # 10. 영문 약어 (2-6글자)
        for match in ACRONYM_PATTERN.finditer(text):
            word = match.group()
            if word not in EXCLUDE_ACRONYMS and len(word) >= 2:
                keywords.add(word)
                self.keywords_by_category['acronym'].add(word)

        return keywords

    def _is_technical_term(self, word: str) -> bool:
        """기술 용어인지 판단"""
        # 숫자 포함
        if any(c.isdigit() for c in word):
            return True
        # 'mgr', 'cfg', 'lib' 등 기술 접미사
        tech_suffixes = ('mgr', 'cfg', 'lib', 'svr', 'srv', 'ctl', 'cmd', 'run', 'log', 'tmp', 'opt')
        if word.endswith(tech_suffixes):
            return True
        # 특정 접두사
        tech_prefixes = ('tjes', 'osc', 'osi', 'tacf', 'dsm', 'obs', 'obm', 'tp', 'tm', 'tb', 'of')
        if word.startswith(tech_prefixes):
            return True
        # 길이가 짧으면 약어일 가능성
        if len(word) <= 6:
            return True
        return False

    def process_pdf(self, pdf_path: Path) -> Set[str]:
        """단일 PDF 파일 처리"""
        keywords = set()
        try:
            doc = pymupdf.open(pdf_path)
            for page_num, page in enumerate(doc):
                try:
                    text = page.get_text()
                    page_keywords = self.extract_from_text(text, str(pdf_path))
                    keywords.update(page_keywords)
                except Exception as e:
                    logger.warning(f"Page {page_num} error in {pdf_path.name}: {e}")
            doc.close()

            self.all_keywords.update(keywords)
            self.keywords_by_file[pdf_path.name] = keywords
            self.processed_files += 1
            return keywords

        except Exception as e:
            logger.error(f"Failed to process {pdf_path}: {e}")
            self.failed_files.append(str(pdf_path))
            return set()

    def process_all_manuals(self, manuals_dir: Path) -> None:
        """모든 매뉴얼 처리"""
        pdf_files = list(manuals_dir.rglob("*.pdf"))
        total = len(pdf_files)
        logger.info(f"총 {total}개 PDF 파일 처리 시작...")

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 10 == 0:
                logger.info(f"진행: {i}/{total} ({len(self.all_keywords)} keywords)")
            self.process_pdf(pdf_path)

        logger.info(f"처리 완료: {self.processed_files}/{total} 파일, {len(self.all_keywords)} 키워드")
        if self.failed_files:
            logger.warning(f"실패: {len(self.failed_files)} 파일")

    def save_keywords(self, output_path: Path) -> None:
        """키워드를 파일로 저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 알파벳순 정렬
        sorted_keywords = sorted(self.all_keywords, key=lambda x: x.lower())

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# OpenFrame Manual Keywords\n")
            f.write(f"# 추출일: {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"# 총 키워드: {len(sorted_keywords)}개\n")
            f.write(f"# 처리 파일: {self.processed_files}개\n")
            f.write(f"#\n")
            f.write(f"# 카테고리별 통계:\n")
            for cat, kws in sorted(self.keywords_by_category.items()):
                f.write(f"#   {cat}: {len(kws)}개\n")
            f.write(f"#\n")
            f.write(f"# ============================================\n\n")

            for keyword in sorted_keywords:
                f.write(f"{keyword}\n")

        logger.info(f"키워드 저장 완료: {output_path}")
        logger.info(f"총 {len(sorted_keywords)}개 키워드")

    def save_categorized_keywords(self, output_dir: Path) -> None:
        """카테고리별로 키워드 저장"""
        output_dir.mkdir(parents=True, exist_ok=True)

        for category, keywords in self.keywords_by_category.items():
            cat_file = output_dir / f"keywords_{category}.txt"
            sorted_kws = sorted(keywords, key=lambda x: x.lower())
            with open(cat_file, 'w', encoding='utf-8') as f:
                f.write(f"# {category} keywords: {len(sorted_kws)}개\n\n")
                for kw in sorted_kws:
                    f.write(f"{kw}\n")
            logger.info(f"  {category}: {len(sorted_kws)}개 -> {cat_file.name}")


def main():
    """메인 함수"""
    logger.info("=" * 60)
    logger.info("영문 키워드 추출 시작")
    logger.info(f"매뉴얼 디렉토리: {MANUALS_DIR}")
    logger.info(f"출력 파일: {OUTPUT_FILE}")
    logger.info("=" * 60)

    if not MANUALS_DIR.exists():
        logger.error(f"매뉴얼 디렉토리가 없습니다: {MANUALS_DIR}")
        sys.exit(1)

    extractor = KeywordExtractor()
    extractor.process_all_manuals(MANUALS_DIR)
    extractor.save_keywords(OUTPUT_FILE)

    # 카테고리별 저장 (옵션)
    # extractor.save_categorized_keywords(OUTPUT_FILE.parent / "keywords_by_category")

    logger.info("완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
