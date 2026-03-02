#!/usr/bin/env python3
"""
LLM 기반 매뉴얼 추출 실행 스크립트

패턴 기반 대신 LLM을 사용하여 PDF 매뉴얼에서 정보를 추출하고
Two-Stage Retrieval용 요약 파일을 생성합니다.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import asdict

# LLM 파서 직접 임포트 (패키지 __init__ 우회)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "llm_parser",
    Path(__file__).parent / "parsers" / "llm_parser.py"
)
llm_parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(llm_parser_module)
LLMParser = llm_parser_module.LLMParser
ExtractedItem = llm_parser_module.ExtractedItem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class LLMSummaryGenerator:
    """LLM 추출 결과를 요약 파일로 생성"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, items: list[ExtractedItem]):
        """모든 요약 파일 생성"""
        # 유형별 분류
        by_type = defaultdict(list)
        for item in items:
            by_type[item.item_type].append(item)

        # 각 유형별 파일 생성
        self._generate_commands(by_type.get("command", []))
        self._generate_apis(by_type.get("api", []))
        self._generate_configs(by_type.get("config", []))
        self._generate_error_codes(by_type.get("error_code", []))
        self._generate_concepts(by_type.get("concept", []))

        # 통합 JSON 저장
        self._save_json(items)

        logger.info(f"Summary files generated in {self.output_dir}")

    def _generate_commands(self, items: list[ExtractedItem]):
        """명령어 요약 파일 생성"""
        if not items:
            return

        # 제품별로 그룹화
        by_product = defaultdict(list)
        for item in items:
            by_product[item.product].append(item)

        commands_dir = self.output_dir / "commands"
        commands_dir.mkdir(exist_ok=True)

        for product, product_items in by_product.items():
            safe_product = product.replace(" ", "_").replace("(", "").replace(")", "")
            filepath = commands_dir / f"{safe_product}.md"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {product} 명령어\n\n")
                f.write(f"> 자동 추출 일시: {datetime.now().isoformat()}\n\n")

                for item in sorted(product_items, key=lambda x: x.name.lower()):
                    f.write(f"## {item.name}\n\n")
                    f.write(f"{item.description}\n\n")
                    if item.syntax:
                        f.write(f"**구문:**\n```\n{item.syntax}\n```\n\n")
                    f.write(f"- 소스: {item.source_file} (p.{item.source_page})\n\n")
                    f.write("---\n\n")

        logger.info(f"  Commands: {len(items)} items → {len(by_product)} files")

    def _generate_apis(self, items: list[ExtractedItem]):
        """API 함수 요약 파일 생성"""
        if not items:
            return

        # 제품별로 그룹화
        by_product = defaultdict(list)
        for item in items:
            by_product[item.product].append(item)

        apis_dir = self.output_dir / "apis"
        apis_dir.mkdir(exist_ok=True)

        for product, product_items in by_product.items():
            safe_product = product.replace(" ", "_").replace("(", "").replace(")", "")
            filepath = apis_dir / f"{safe_product}.md"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {product} API 함수\n\n")
                f.write(f"> 자동 추출 일시: {datetime.now().isoformat()}\n\n")

                for item in sorted(product_items, key=lambda x: x.name.lower()):
                    f.write(f"## {item.name}\n\n")
                    f.write(f"{item.description}\n\n")
                    if item.syntax:
                        f.write(f"**프로토타입:**\n```c\n{item.syntax}\n```\n\n")
                    f.write(f"- 소스: {item.source_file} (p.{item.source_page})\n\n")
                    f.write("---\n\n")

        logger.info(f"  APIs: {len(items)} items → {len(by_product)} files")

    def _generate_configs(self, items: list[ExtractedItem]):
        """설정 파라미터 요약 파일 생성"""
        if not items:
            return

        by_product = defaultdict(list)
        for item in items:
            by_product[item.product].append(item)

        configs_dir = self.output_dir / "configs"
        configs_dir.mkdir(exist_ok=True)

        for product, product_items in by_product.items():
            safe_product = product.replace(" ", "_").replace("(", "").replace(")", "")
            filepath = configs_dir / f"{safe_product}.md"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {product} 설정 파라미터\n\n")
                f.write(f"> 자동 추출 일시: {datetime.now().isoformat()}\n\n")
                f.write("| 파라미터 | 설명 | 소스 |\n")
                f.write("|----------|------|------|\n")

                for item in sorted(product_items, key=lambda x: x.name.lower()):
                    desc = item.description.replace("|", "\\|").replace("\n", " ")[:100]
                    f.write(f"| `{item.name}` | {desc} | {item.source_file}:p{item.source_page} |\n")

        logger.info(f"  Configs: {len(items)} items → {len(by_product)} files")

    def _generate_error_codes(self, items: list[ExtractedItem]):
        """에러 코드 요약 파일 생성"""
        if not items:
            return

        by_product = defaultdict(list)
        for item in items:
            by_product[item.product].append(item)

        errors_dir = self.output_dir / "error_codes"
        errors_dir.mkdir(exist_ok=True)

        for product, product_items in by_product.items():
            safe_product = product.replace(" ", "_").replace("(", "").replace(")", "")
            filepath = errors_dir / f"{safe_product}.md"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {product} 에러 코드\n\n")
                f.write(f"> 자동 추출 일시: {datetime.now().isoformat()}\n\n")
                f.write("| 코드 | 설명 | 소스 |\n")
                f.write("|------|------|------|\n")

                for item in sorted(product_items, key=lambda x: x.name):
                    desc = item.description.replace("|", "\\|").replace("\n", " ")[:100]
                    f.write(f"| `{item.name}` | {desc} | {item.source_file}:p{item.source_page} |\n")

        logger.info(f"  Error codes: {len(items)} items → {len(by_product)} files")

    def _generate_concepts(self, items: list[ExtractedItem]):
        """개념/용어 요약 파일 생성"""
        if not items:
            return

        by_product = defaultdict(list)
        for item in items:
            by_product[item.product].append(item)

        concepts_dir = self.output_dir / "terms"
        concepts_dir.mkdir(exist_ok=True)

        for product, product_items in by_product.items():
            safe_product = product.replace(" ", "_").replace("(", "").replace(")", "")
            filepath = concepts_dir / f"{safe_product}.md"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {product} 용어집\n\n")
                f.write(f"> 자동 추출 일시: {datetime.now().isoformat()}\n\n")

                for item in sorted(product_items, key=lambda x: x.name.lower()):
                    f.write(f"## {item.name}\n\n")
                    f.write(f"{item.description}\n\n")
                    f.write(f"- 소스: {item.source_file} (p.{item.source_page})\n\n")

        logger.info(f"  Concepts: {len(items)} items → {len(by_product)} files")

    def _save_json(self, items: list[ExtractedItem]):
        """전체 데이터 JSON 저장"""
        data = {
            "extracted_at": datetime.now().isoformat(),
            "total_items": len(items),
            "items": [asdict(item) for item in items]
        }

        json_path = self.output_dir / "extracted_items.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"  JSON: {json_path}")


async def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM 기반 매뉴얼 추출")
    parser.add_argument(
        "--manuals-dir",
        type=Path,
        default=Path("/opt/kms/uploads/manuals"),
        help="매뉴얼 디렉토리"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/opt/kms/uploads/summaries"),
        help="출력 디렉토리"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="테스트 모드 (5개 PDF만 처리)"
    )
    parser.add_argument(
        "--single-file",
        type=str,
        help="단일 파일 처리 (파일명 패턴)"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("LLM 기반 매뉴얼 추출 시작")
    logger.info(f"  매뉴얼 디렉토리: {args.manuals_dir}")
    logger.info(f"  출력 디렉토리: {args.output_dir}")
    logger.info("=" * 60)

    # LLM 파서 초기화
    llm_parser = LLMParser(args.manuals_dir)

    # PDF 파일 목록
    if args.single_file:
        pdf_files = list(args.manuals_dir.rglob(f"*{args.single_file}*.pdf"))
        logger.info(f"Single file mode: {len(pdf_files)} files matching '{args.single_file}'")
    else:
        pdf_files = list(args.manuals_dir.rglob("*.pdf"))

    if args.test:
        pdf_files = pdf_files[:5]
        logger.info(f"Test mode: processing {len(pdf_files)} files")

    # 추출 실행
    all_items = []
    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"[{i}/{len(pdf_files)}] Processing {pdf_path.name}...")
        items = await llm_parser.parse_pdf(pdf_path)
        all_items.extend(items)
        logger.info(f"  → {len(items)} items extracted")

    # 중복 제거
    unique_items = llm_parser._deduplicate_items(all_items)
    logger.info(f"\nTotal: {len(all_items)} → {len(unique_items)} unique items")

    # 요약 파일 생성
    generator = LLMSummaryGenerator(args.output_dir)
    generator.generate_all(unique_items)

    # 통계 출력
    by_type = defaultdict(int)
    for item in unique_items:
        by_type[item.item_type] += 1

    logger.info("\n추출 통계:")
    for item_type, count in sorted(by_type.items()):
        logger.info(f"  {item_type}: {count}")

    logger.info("\n완료!")


if __name__ == "__main__":
    asyncio.run(main())
