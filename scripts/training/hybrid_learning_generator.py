#!/usr/bin/env python3
"""
하이브리드 학습 데이터 생성기

두 가지 소스를 결합하여 완전한 학습 데이터를 생성합니다:
1. 요약본 (commands/*.md) - 정확한 syntax, parameters
2. 키워드 PDF 검색 - 추가 컨텍스트, 설명

이렇게 하면:
- 요약본에 있는 명령어는 정확한 syntax 사용
- 요약본에 없는 키워드는 PDF 검색으로 보완
- 모든 키워드에 대해 학습 데이터 생성

Usage:
    python hybrid_learning_generator.py
"""

import re
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

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
# 요약본 파서
# =============================================================================

class SummaryParser:
    """요약본 Markdown 파서 - 정확한 syntax 추출"""

    COMMAND_HEADER = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
    SYNTAX_BLOCK = re.compile(r'\*\*구문:\*\*\s*\n```\n?([\s\S]*?)\n?```', re.MULTILINE)
    SOURCE_LINE = re.compile(r'-\s*소스:\s*(.+?)(?:\n|$)')

    def __init__(self, summaries_dir: Path):
        self.summaries_dir = summaries_dir
        self.commands: Dict[str, Dict] = {}  # {name_lower: {name, syntax, description, ...}}

    def parse_all(self) -> Dict[str, Dict]:
        """모든 요약본 파싱"""
        commands_dir = self.summaries_dir / "commands"
        if not commands_dir.exists():
            logger.warning(f"commands 디렉토리 없음: {commands_dir}")
            return {}

        for md_file in commands_dir.glob("*.md"):
            if md_file.name == "index.md":
                continue
            self._parse_file(md_file)

        logger.info(f"요약본에서 {len(self.commands)}개 명령어 파싱됨")
        return self.commands

    def _parse_file(self, file_path: Path) -> None:
        """단일 파일 파싱"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {file_path}: {e}")
            return

        product = self._extract_product(file_path.stem)
        sections = re.split(r'\n---\n', content)

        for section in sections:
            header_match = self.COMMAND_HEADER.search(section)
            if not header_match:
                continue

            name = header_match.group(1).strip()
            header_end = header_match.end()
            remaining = section[header_end:].strip()

            # syntax 추출
            syntax_match = self.SYNTAX_BLOCK.search(remaining)
            syntax = syntax_match.group(1).strip() if syntax_match else None

            # source 추출
            source_match = self.SOURCE_LINE.search(remaining)
            source = source_match.group(1).strip() if source_match else ""

            # description 추출
            if syntax_match:
                desc_end = remaining.find('**구문:**')
            elif source_match:
                desc_end = remaining.find('- 소스:')
            else:
                desc_end = len(remaining)
            description = remaining[:desc_end].strip() if desc_end > 0 else ""

            if not name:
                continue

            # 파라미터 추출
            parameters = self._extract_parameters(syntax) if syntax else []

            # 저장 (소문자 키로)
            name_lower = name.lower()

            # 기존 항목보다 더 완전한 정보면 업데이트
            existing = self.commands.get(name_lower, {})
            if not existing or (syntax and not existing.get('syntax')):
                self.commands[name_lower] = {
                    'name': name,
                    'description': description,
                    'syntax': syntax,
                    'parameters': parameters,
                    'source_file': source if source else str(file_path.name),
                    'product': product,
                    'from_summary': True,
                }

    def _extract_product(self, filename: str) -> str:
        """파일명에서 제품 추출"""
        if filename.startswith("OpenFrame_"):
            parts = filename.replace("OpenFrame_", "").split("_")
            return f"OF_{parts[0]}" if parts else "OpenFrame"
        elif filename in ["Tibero", "Tmax", "JEUS", "WebtoB"]:
            return filename
        return "Unknown"

    def _extract_parameters(self, syntax: str) -> List[str]:
        """syntax에서 파라미터 추출"""
        if not syntax:
            return []

        params = []
        # <param>
        params.extend(re.findall(r'<([^>]+)>', syntax))
        # [option]
        for match in re.findall(r'\[([^\]]+)\]', syntax):
            if '=' in match or not match.startswith('-'):
                params.append(f"[{match}]")
        # KEY=value
        params.extend(re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=', syntax))

        return list(set(params))[:10]


# =============================================================================
# 키워드 PDF 검색 (간단 버전)
# =============================================================================

class SimplePDFSearcher:
    """간단한 PDF 검색 - 컨텍스트와 설명만 추출"""

    def __init__(self, manuals_dir: Path):
        self.manuals_dir = manuals_dir
        self._pdf_texts: Dict[str, List[tuple]] = {}

    def preload(self) -> None:
        """PDF 텍스트 프리로딩"""
        pdf_files = list(self.manuals_dir.rglob("*.pdf"))
        logger.info(f"PDF {len(pdf_files)}개 프리로딩...")

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 50 == 0:
                logger.info(f"  프리로딩: {i}/{len(pdf_files)}")
            try:
                doc = pymupdf.open(pdf_path)
                pages = []
                for page_num, page in enumerate(doc, 1):
                    text = page.get_text()
                    if text.strip():
                        pages.append((page_num, text, pdf_path.name))
                doc.close()
                self._pdf_texts[str(pdf_path)] = pages
            except:
                pass

        logger.info(f"프리로딩 완료: {len(self._pdf_texts)}개")

    def search_keyword(self, keyword: str) -> Optional[Dict]:
        """키워드 검색 - 설명과 컨텍스트 반환"""
        keyword_lower = keyword.lower()
        keyword_pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)

        best_context = ""
        best_description = ""
        occurrences = 0
        products = defaultdict(int)

        for pdf_path, pages in self._pdf_texts.items():
            for page_num, text, pdf_name in pages:
                if not keyword_pattern.search(text):
                    continue

                occurrences += 1
                product = self._extract_product(pdf_name)
                products[product] += 1

                # 컨텍스트 추출
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if keyword_lower in line.lower():
                        start = max(0, i - 3)
                        end = min(len(lines), i + 4)
                        context = '\n'.join(lines[start:end])

                        if len(context) > len(best_context):
                            best_context = context

                        # 설명 추출 (키워드 다음 문장)
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line and len(next_line) > len(best_description):
                                best_description = next_line

                if occurrences >= 20:
                    break
            if occurrences >= 20:
                break

        if occurrences == 0:
            return None

        primary_product = max(products, key=products.get) if products else "Unknown"

        return {
            'description': best_description[:500] if best_description else best_context[:300],
            'context': best_context[:500],
            'occurrences': occurrences,
            'product': primary_product,
        }

    def _extract_product(self, filename: str) -> str:
        """파일명에서 제품 추출"""
        patterns = [
            (r'TJES', 'OF_TJES'), (r'OSC', 'OF_OSC'), (r'OSI', 'OF_OSI'),
            (r'TACF', 'OF_TACF'), (r'Base', 'OF_Base'), (r'Batch', 'OF_Batch'),
            (r'Tibero', 'Tibero'), (r'Tmax', 'Tmax'), (r'JEUS', 'JEUS'),
            (r'WebtoB', 'WebtoB'), (r'COBOL', 'OFCOBOL'),
        ]
        for pattern, product in patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                return product
        return "Unknown"


# =============================================================================
# 하이브리드 생성기
# =============================================================================

class HybridLearningGenerator:
    """요약본 + PDF 검색 하이브리드"""

    def __init__(
        self,
        summaries_dir: Path,
        manuals_dir: Path,
        keywords_path: Path,
    ):
        self.summaries_dir = summaries_dir
        self.manuals_dir = manuals_dir
        self.keywords_path = keywords_path

        self.summary_parser = SummaryParser(summaries_dir)
        self.pdf_searcher = SimplePDFSearcher(manuals_dir)

        self.items: List[Dict] = []
        self.stats = {
            'total_keywords': 0,
            'from_summary': 0,
            'from_pdf': 0,
            'not_found': 0,
            'with_syntax': 0,
            'by_type': defaultdict(int),
            'by_product': defaultdict(int),
        }

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

    def detect_type(self, keyword: str) -> str:
        """항목 타입 감지"""
        keyword_lower = keyword.lower()

        if re.search(r'mgr$|run$|ctl$|cmd$|boot$|down$', keyword_lower):
            return 'command'
        if re.search(r'\.conf$|\.cfg$|\.properties$', keyword_lower):
            return 'config'
        if re.match(r'^[A-Z]+_[A-Z0-9_]+$', keyword):
            return 'api'
        if re.match(r'^ABEND|^-\d{4,}', keyword):
            return 'error'
        if keyword in ['JOB', 'EXEC', 'DD', 'PROC', 'PEND', 'IF', 'THEN', 'ELSE', 'ENDIF', 'SET']:
            return 'jcl'
        return 'concept'

    # 우선순위 키워드 패턴 (PDF 검색 대상)
    PRIORITY_KEYWORDS = {
        # Manager 명령어
        'tjesmgr', 'oscmgr', 'tacfmgr', 'hidbmgr', 'ndbmgr', 'volmgr', 'tconmgr',
        'smfmgr', 'cpmmgr', 'obmtsmgr', 'aimdtsmgr', 'hidbptrmgr', 'tbrmgr',
        # 주요 유틸리티
        'idcams', 'iebgener', 'iebcopy', 'dfsort', 'dsmigin', 'dsmigout',
        'textrun', 'tjclrun', 'ofboot', 'ofdown', 'tmboot', 'tmdown',
        # JCL
        'JOB', 'EXEC', 'DD', 'PROC', 'PEND', 'IF', 'THEN', 'ELSE', 'ENDIF', 'SET',
        # 설정
        'osc.conf', 'tjes.conf', 'tacf.conf', 'ds.conf', 'ofsys.conf',
    }

    def is_priority_keyword(self, keyword: str) -> bool:
        """우선순위 키워드인지 확인"""
        kw_lower = keyword.lower()
        # 정확히 일치하거나 mgr로 끝나는 경우
        if kw_lower in self.PRIORITY_KEYWORDS:
            return True
        if kw_lower.endswith('mgr'):
            return True
        if re.match(r'^ABEND', keyword):
            return True
        if re.match(r'^-\d{4,}', keyword):
            return True
        return False

    def generate(self, skip_pdf: bool = False, priority_only: bool = False) -> Dict:
        """학습 데이터 생성

        Args:
            skip_pdf: True면 PDF 검색 완전 생략 (요약본만 사용)
            priority_only: True면 우선순위 키워드만 PDF 검색
        """
        # 1. 요약본 파싱
        logger.info("요약본 파싱 중...")
        summary_commands = self.summary_parser.parse_all()

        # 2. PDF 프리로딩 (필요시에만)
        if not skip_pdf:
            logger.info("PDF 프리로딩 중...")
            self.pdf_searcher.preload()

        # 3. 키워드 로드
        keywords = self.load_keywords()
        self.stats['total_keywords'] = len(keywords)

        # 4. 각 키워드 처리
        logger.info(f"키워드 {len(keywords)}개 처리 중...")
        pdf_search_count = 0

        for i, keyword in enumerate(keywords, 1):
            if i % 5000 == 0:
                logger.info(f"  진행: {i}/{len(keywords)} (PDF 검색: {pdf_search_count}회)")

            keyword_lower = keyword.lower()
            item_type = self.detect_type(keyword)

            # 요약본에서 먼저 찾기
            if keyword_lower in summary_commands:
                cmd = summary_commands[keyword_lower]
                item = {
                    'name': keyword,
                    'type': item_type,
                    'description': cmd.get('description', ''),
                    'syntax': cmd.get('syntax'),
                    'parameters': cmd.get('parameters', []),
                    'examples': [],
                    'related': [],
                    'source_file': cmd.get('source_file', ''),
                    'product': cmd.get('product', 'Unknown'),
                    'from_summary': True,
                }
                self.items.append(item)
                self.stats['from_summary'] += 1
                if cmd.get('syntax'):
                    self.stats['with_syntax'] += 1

            elif skip_pdf:
                # PDF 검색 생략 - 키워드만으로 항목 생성
                item = {
                    'name': keyword,
                    'type': item_type,
                    'description': f"{keyword}はOpenFrameシステムの{item_type}です。",
                    'syntax': None,
                    'parameters': [],
                    'examples': [],
                    'related': [],
                    'source_file': 'keyword_only',
                    'product': 'Unknown',
                }
                self.items.append(item)
                self.stats['not_found'] += 1

            elif priority_only and not self.is_priority_keyword(keyword):
                # 우선순위 아님 - 스킵
                item = {
                    'name': keyword,
                    'type': item_type,
                    'description': f"{keyword}はOpenFrameシステムの{item_type}です。",
                    'syntax': None,
                    'parameters': [],
                    'examples': [],
                    'related': [],
                    'source_file': 'keyword_only',
                    'product': 'Unknown',
                }
                self.items.append(item)
                self.stats['not_found'] += 1

            else:
                # PDF 검색
                pdf_search_count += 1
                result = self.pdf_searcher.search_keyword(keyword)

                if result:
                    item = {
                        'name': keyword,
                        'type': item_type,
                        'description': result.get('description', ''),
                        'syntax': None,  # PDF에서는 syntax 추출 안함 (품질 문제)
                        'parameters': [],
                        'examples': [],
                        'related': [],
                        'source_file': 'pdf_search',
                        'product': result.get('product', 'Unknown'),
                        'from_pdf': True,
                        'occurrence_count': result.get('occurrences', 0),
                    }
                    self.items.append(item)
                    self.stats['from_pdf'] += 1
                else:
                    # 키워드만으로 항목 생성
                    item = {
                        'name': keyword,
                        'type': item_type,
                        'description': f"{keyword}はOpenFrameシステムの{item_type}です。",
                        'syntax': None,
                        'parameters': [],
                        'examples': [],
                        'related': [],
                        'source_file': 'keyword_only',
                        'product': 'Unknown',
                    }
                    self.items.append(item)
                    self.stats['not_found'] += 1

            self.stats['by_type'][item_type] += 1
            self.stats['by_product'][self.items[-1]['product']] += 1

        logger.info(f"총 PDF 검색 횟수: {pdf_search_count}")

        # 결과 구성
        return {
            'metadata': {
                'total_items': len(self.items),
                'generated_at': datetime.now().isoformat(),
                'stats': {
                    'total_keywords': self.stats['total_keywords'],
                    'from_summary': self.stats['from_summary'],
                    'from_pdf': self.stats['from_pdf'],
                    'not_found': self.stats['not_found'],
                    'with_syntax': self.stats['with_syntax'],
                    'syntax_rate': round(self.stats['with_syntax'] / max(len(self.items), 1) * 100, 2),
                },
                'type_stats': dict(self.stats['by_type']),
                'product_stats': dict(self.stats['by_product']),
            },
            'items': self.items
        }

    def save(self, output_path: Path, data: Dict) -> None:
        """저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"저장 완료: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="하이브리드 학습 데이터 생성")
    parser.add_argument("--summaries", type=Path,
                        default=PROJECT_ROOT / "uploads" / "summaries")
    parser.add_argument("--manuals", type=Path,
                        default=PROJECT_ROOT / "uploads" / "manuals")
    parser.add_argument("--keywords", type=Path,
                        default=PROJECT_ROOT / "docs" / "keyword.txt")
    parser.add_argument("--output", type=Path,
                        default=PROJECT_ROOT / "uploads" / "summaries" / "hybrid_learning_dataset.json")
    parser.add_argument("--priority-only", action="store_true",
                        help="우선순위 키워드만 PDF 검색 (빠른 모드)")
    parser.add_argument("--skip-pdf", action="store_true",
                        help="PDF 검색 생략 - 요약본만 사용")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("하이브리드 학습 데이터 생성 시작")
    logger.info(f"요약본: {args.summaries}")
    logger.info(f"매뉴얼: {args.manuals}")
    logger.info(f"키워드: {args.keywords}")
    logger.info(f"출력: {args.output}")
    logger.info(f"모드: {'요약본만' if args.skip_pdf else '우선순위만 PDF' if args.priority_only else '전체'}")
    logger.info("=" * 60)

    generator = HybridLearningGenerator(
        summaries_dir=args.summaries,
        manuals_dir=args.manuals,
        keywords_path=args.keywords,
    )

    data = generator.generate(skip_pdf=args.skip_pdf, priority_only=args.priority_only)
    generator.save(args.output, data)

    # 통계 출력
    stats = data['metadata']['stats']
    logger.info("\n" + "=" * 60)
    logger.info("완료 통계:")
    logger.info(f"  총 키워드: {stats['total_keywords']}")
    logger.info(f"  요약본에서: {stats['from_summary']}")
    logger.info(f"  PDF에서: {stats['from_pdf']}")
    logger.info(f"  미발견: {stats['not_found']}")
    logger.info(f"  syntax 포함: {stats['with_syntax']} ({stats['syntax_rate']}%)")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
