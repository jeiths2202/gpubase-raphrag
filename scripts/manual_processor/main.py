#!/usr/bin/env python3
"""
OpenFrame 매뉴얼 프로세서 CLI

PDF 매뉴얼을 분석하여 AI Agent용 Markdown 요약본을 생성합니다.

Usage:
    python -m scripts.manual_processor.main process-all
    python -m scripts.manual_processor.main process /path/to/manual.pdf
    python -m scripts.manual_processor.main extract-errors
    python -m scripts.manual_processor.main extract-comprehensive
    python -m scripts.manual_processor.main rebuild-index
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from .config import config
from .parsers import PDFParser, ErrorCodeParser, ContentParser
from .generators import MarkdownGenerator, IndexGenerator
from .utils import find_manuals, find_error_guides, ensure_dir

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class ManualProcessor:
    """매뉴얼 프로세서

    PDF 매뉴얼을 분석하여 요약본을 생성하는 메인 클래스입니다.
    """

    def __init__(self):
        self.pdf_parser = PDFParser()
        self.error_parser = ErrorCodeParser()
        self.content_parser = ContentParser()
        self.md_generator = MarkdownGenerator()
        self.index_generator = IndexGenerator()

        # 누적 데이터
        self.all_error_modules = {}
        self.all_terms = {}
        self.processed_files = []

    def process_all(self) -> None:
        """모든 매뉴얼 처리"""
        logger.info("=== 전체 매뉴얼 처리 시작 ===")
        start_time = datetime.now()

        # 출력 디렉토리 준비
        ensure_dir(config.summaries_dir)

        # 1. 에러 참조 가이드 처리
        logger.info("\n[1/3] 에러 참조 가이드 처리")
        self._process_error_guides()

        # 2. 일반 가이드 처리 (용어 추출)
        logger.info("\n[2/3] 일반 가이드 처리 (용어 추출)")
        self._process_general_guides()

        # 3. 인덱스 생성
        logger.info("\n[3/3] 인덱스 생성")
        self.index_generator.generate_master_index()

        # 완료
        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 처리 완료 ===")
        logger.info(f"처리된 파일: {len(self.processed_files)}개")
        logger.info(f"에러 모듈: {len(self.all_error_modules)}개")
        logger.info(f"용어: {len(self.all_terms)}개")
        logger.info(f"소요 시간: {elapsed}")

    def _process_error_guides(self) -> None:
        """에러 참조 가이드 처리"""
        error_guides = list(find_error_guides())
        logger.info(f"에러 참조 가이드 {len(error_guides)}개 발견")

        for pdf_path in error_guides:
            try:
                logger.info(f"처리 중: {pdf_path.name}")

                # PDF 파싱
                content = self.pdf_parser.parse(pdf_path)
                if not content:
                    continue

                # 에러 코드 추출
                modules = self.error_parser.parse(content)

                # 누적
                for module_name, module in modules.items():
                    if module_name in self.all_error_modules:
                        # 기존 모듈에 에러 추가
                        existing = self.all_error_modules[module_name]
                        for error in module.errors:
                            if not existing.find_error(error.code):
                                existing.add_error(error)
                        existing.source_files.extend(module.source_files)
                    else:
                        self.all_error_modules[module_name] = module

                self.processed_files.append(pdf_path)

            except Exception as e:
                logger.error(f"에러 가이드 처리 실패: {pdf_path} - {e}")

        # 마크다운 생성
        if self.all_error_modules:
            self.md_generator.generate_error_codes(self.all_error_modules)

    def _process_general_guides(self) -> None:
        """일반 가이드 처리 (용어 추출)"""
        # 주요 가이드 타입만 처리
        priority_guides = [
            "TJES-Guide", "Batch-Guide", "Base-Guide",
            "Administrator-Guide", "User-Guide"
        ]

        processed_count = 0
        for pdf_path in find_manuals():
            # 이미 처리된 에러 가이드 건너뛰기
            if pdf_path in self.processed_files:
                continue

            # 우선순위 가이드인지 확인
            is_priority = any(g in pdf_path.name for g in priority_guides)

            # 너무 많은 파일 처리 방지 (우선순위 아닌 건 50개 제한)
            if not is_priority and processed_count >= 50:
                continue

            try:
                logger.info(f"처리 중: {pdf_path.name}")

                # PDF 파싱
                content = self.pdf_parser.parse(pdf_path)
                if not content:
                    continue

                # 용어 추출
                terms = self.content_parser.parse(content)

                # 누적
                for term_name, term in terms.items():
                    if term_name in self.all_terms:
                        # 기존 용어에 정보 병합
                        existing = self.all_terms[term_name]
                        if not existing.full_name and term.full_name:
                            existing.full_name = term.full_name
                        if not existing.description and term.description:
                            existing.description = term.description
                        existing.source_files.extend(term.source_files)
                        existing.features.extend(term.features)
                    else:
                        self.all_terms[term_name] = term

                self.processed_files.append(pdf_path)
                processed_count += 1

            except Exception as e:
                logger.error(f"가이드 처리 실패: {pdf_path} - {e}")

        # 마크다운 생성
        if self.all_terms:
            self.md_generator.generate_glossary(self.all_terms)

    def process_single(self, pdf_path: Path) -> None:
        """단일 PDF 처리"""
        logger.info(f"단일 파일 처리: {pdf_path}")

        if not pdf_path.exists():
            logger.error(f"파일을 찾을 수 없습니다: {pdf_path}")
            return

        content = self.pdf_parser.parse(pdf_path)
        if not content:
            return

        # 에러 가이드인 경우
        if content.metadata.is_error_guide:
            modules = self.error_parser.parse(content)
            if modules:
                self.md_generator.generate_error_codes(modules)
                logger.info(f"에러 코드 {sum(len(m.errors) for m in modules.values())}개 추출")
        else:
            # 일반 가이드
            terms = self.content_parser.parse(content)
            if terms:
                self.md_generator.generate_glossary(terms)
                logger.info(f"용어 {len(terms)}개 추출")

        self.index_generator.generate_master_index()

    def extract_errors_only(self) -> None:
        """에러 코드만 추출"""
        logger.info("=== 에러 코드 추출 ===")
        self._process_error_guides()
        self.index_generator.generate_master_index()

    def rebuild_index(self) -> None:
        """인덱스 재생성"""
        logger.info("=== 인덱스 재생성 ===")
        self.index_generator.rebuild_all()

    def extract_comprehensive(self) -> None:
        """포괄적 추출 - 모든 매뉴얼에서 모든 정보 추출"""
        logger.info("=== 포괄적 추출 시작 ===")
        start_time = datetime.now()

        from .parsers.comprehensive_parser import ComprehensiveParser
        from .generators.comprehensive_generator import ComprehensiveGenerator

        # 파서 및 생성기 초기화
        parser = ComprehensiveParser(config.manuals_dir)
        generator = ComprehensiveGenerator(config.summaries_dir)

        # 모든 매뉴얼에서 항목 추출
        logger.info("\n[1/2] 모든 매뉴얼에서 정보 추출 중...")
        items = parser.process_all_manuals()

        # 마크다운 생성
        logger.info("\n[2/2] 마크다운 파일 생성 중...")
        stats = generator.generate_all(items)

        # 완료
        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 포괄적 추출 완료 ===")
        logger.info(f"명령어/유틸리티: {stats['commands']}개")
        logger.info(f"설정 파라미터: {stats['configs']}개")
        logger.info(f"API/함수: {stats['apis']}개")
        logger.info(f"개념/정의: {stats['concepts']}개")
        logger.info(f"절차/가이드: {stats['procedures']}개")
        logger.info(f"총 항목: {sum(stats.values())}개")
        logger.info(f"소요 시간: {elapsed}")


def main():
    """CLI 엔트리포인트"""
    parser = argparse.ArgumentParser(
        description="OpenFrame 매뉴얼 프로세서",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python -m scripts.manual_processor.main process-all
  python -m scripts.manual_processor.main process /path/to/manual.pdf
  python -m scripts.manual_processor.main extract-errors
  python -m scripts.manual_processor.main rebuild-index
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # process-all 명령
    subparsers.add_parser("process-all", help="모든 매뉴얼 처리")

    # process 명령
    process_parser = subparsers.add_parser("process", help="단일 PDF 처리")
    process_parser.add_argument("pdf_path", type=Path, help="PDF 파일 경로")

    # extract-errors 명령
    subparsers.add_parser("extract-errors", help="에러 코드만 추출")

    # extract-comprehensive 명령
    subparsers.add_parser("extract-comprehensive", help="포괄적 추출 (모든 매뉴얼에서 모든 정보)")

    # rebuild-index 명령
    subparsers.add_parser("rebuild-index", help="인덱스 재생성")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    processor = ManualProcessor()

    if args.command == "process-all":
        processor.process_all()
    elif args.command == "process":
        processor.process_single(args.pdf_path)
    elif args.command == "extract-errors":
        processor.extract_errors_only()
    elif args.command == "extract-comprehensive":
        processor.extract_comprehensive()
    elif args.command == "rebuild-index":
        processor.rebuild_index()


if __name__ == "__main__":
    main()
