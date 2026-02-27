#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Extractor v2 검증 프로그램
==============================
표와 이미지 추출 기능이 개선된 v2 extractor 검증
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from openframe_qlora_full_extractor_v2 import (
    OpenFrameManualParserV2,
    QLoRADataGeneratorV2,
)


class PDFExtractorValidatorV2:
    """PDF Extractor v2 검증 클래스"""

    def __init__(self, manual_dir: str, output_dir: str = "validation_output_v2"):
        self.manual_dir = Path(manual_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[Dict[str, Any]] = []

    def get_pdf_files(self) -> List[Path]:
        """PDF 파일 목록 반환"""
        pdf_files = list(self.manual_dir.glob("*.pdf"))
        pdf_files = [f for f in pdf_files if "コピー" not in f.name]
        return sorted(pdf_files)

    def validate_single_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """단일 PDF 파일 검증"""
        result = {
            "filename": pdf_path.name,
            "filepath": str(pdf_path),
            "status": "pending",
            "sections_count": 0,
            "tables_count": 0,
            "images_count": 0,
            "training_examples_count": 0,
            "table_examples_count": 0,
            "image_examples_count": 0,
            "total_examples": 0,
            "content_types": {},
            "error_message": None,
            "processing_time": 0,
            "output_file": None
        }

        start_time = time.time()

        try:
            print(f"\n{'='*60}")
            print(f"검증 중: {pdf_path.name}")
            print(f"{'='*60}")

            # 1. PDF 파싱 (표/이미지 포함)
            print("  [1/4] PDF 파싱 중 (v2)...")
            parser = OpenFrameManualParserV2(extract_images=False)
            sections = parser.parse_pdf(str(pdf_path))

            parser_stats = parser.get_statistics()
            result["sections_count"] = parser_stats["total_sections"]
            result["tables_count"] = parser_stats["total_tables"]
            result["images_count"] = parser_stats["total_images"]

            print(f"       → 섹션: {result['sections_count']}개")
            print(f"       → 표: {result['tables_count']}개")
            print(f"       → 이미지: {result['images_count']}개")

            # 2. 학습 데이터 생성
            print("  [2/4] 학습 데이터 생성 중...")
            generator = QLoRADataGeneratorV2(parser)
            training_data = generator.generate_training_data(
                language="ja",
                include_tables=True,
                include_images=True
            )
            result["training_examples_count"] = len(training_data)
            print(f"       → 기본 학습 데이터: {len(training_data)}개")

            # 3. Q&A 쌍 추가
            print("  [3/4] Q&A 쌍 생성 중...")
            qa_pairs = generator.generate_qa_pairs(language="ja")
            generator.training_data.extend(qa_pairs)
            result["total_examples"] = len(generator.training_data)
            print(f"       → Q&A 쌍: {len(qa_pairs)}개")
            print(f"       → 총 학습 데이터: {len(generator.training_data)}개")

            # 4. 통계 수집
            stats = generator.get_statistics()
            result["content_types"] = stats.get("by_content_type", {})
            result["table_examples_count"] = stats.get("table_examples", 0)
            result["image_examples_count"] = stats.get("image_examples", 0)

            # 5. JSONL 출력
            print("  [4/4] JSONL 파일 저장 중...")
            output_filename = pdf_path.stem + "_v2_training_data.jsonl"
            output_path = self.output_dir / output_filename
            generator.export_jsonl(str(output_path), format_type="alpaca")
            result["output_file"] = str(output_path)

            result["status"] = "success"
            print(f"       → 저장 완료: {output_filename}")

        except Exception as e:
            result["status"] = "failed"
            result["error_message"] = str(e)
            print(f"  [ERROR] 실패: {e}")
            import traceback
            traceback.print_exc()

        result["processing_time"] = round(time.time() - start_time, 2)
        print(f"  처리 시간: {result['processing_time']}초")

        return result

    def validate_all(self) -> List[Dict[str, Any]]:
        """모든 PDF 파일 검증"""
        pdf_files = self.get_pdf_files()
        total_files = len(pdf_files)

        print(f"\n{'#'*60}")
        print(f"# OpenFrame MVS 7.1 PDF Extractor v2 검증")
        print(f"# (표 및 이미지 추출 지원)")
        print(f"# 총 PDF 파일: {total_files}개")
        print(f"# 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")

        for idx, pdf_path in enumerate(pdf_files, 1):
            print(f"\n[{idx}/{total_files}] ", end="")
            result = self.validate_single_pdf(pdf_path)
            self.results.append(result)

        return self.results

    def print_summary(self):
        """검증 결과 요약 출력"""
        print(f"\n\n{'='*60}")
        print("검증 결과 요약 (v2)")
        print(f"{'='*60}")

        success_count = sum(1 for r in self.results if r["status"] == "success")
        failed_count = sum(1 for r in self.results if r["status"] == "failed")
        total_examples = sum(r["total_examples"] for r in self.results)
        total_sections = sum(r["sections_count"] for r in self.results)
        total_tables = sum(r["tables_count"] for r in self.results)
        total_images = sum(r["images_count"] for r in self.results)
        total_table_examples = sum(r["table_examples_count"] for r in self.results)
        total_image_examples = sum(r["image_examples_count"] for r in self.results)
        total_time = sum(r["processing_time"] for r in self.results)

        print(f"\n[전체 통계]")
        print(f"  • 총 PDF 파일: {len(self.results)}개")
        print(f"  • 성공: {success_count}개")
        print(f"  • 실패: {failed_count}개")
        print(f"  • 총 섹션 수: {total_sections}개")
        print(f"  • 총 표 수: {total_tables}개")
        print(f"  • 총 이미지 수: {total_images}개")
        print(f"  • 총 학습 데이터: {total_examples}개")
        print(f"    - 표 기반 예제: {total_table_examples}개")
        print(f"    - 이미지 기반 예제: {total_image_examples}개")
        print(f"  • 총 처리 시간: {total_time:.2f}초")

        # 성공한 파일 목록
        print(f"\n[성공한 파일 ({success_count}개)]")
        for r in self.results:
            if r["status"] == "success":
                print(f"  ✓ {r['filename']}")
                print(f"    섹션:{r['sections_count']} 표:{r['tables_count']} "
                      f"이미지:{r['images_count']} 학습데이터:{r['total_examples']}")

        # 실패한 파일 목록
        if failed_count > 0:
            print(f"\n[실패한 파일 ({failed_count}개)]")
            for r in self.results:
                if r["status"] == "failed":
                    print(f"  ✗ {r['filename']}")
                    print(f"    에러: {r['error_message']}")

        # 콘텐츠 유형별 통계
        print(f"\n[콘텐츠 유형별 총계]")
        all_content_types: Dict[str, int] = {}
        for r in self.results:
            for ct, count in r.get("content_types", {}).items():
                all_content_types[ct] = all_content_types.get(ct, 0) + count

        for ct, count in sorted(all_content_types.items()):
            print(f"  • {ct}: {count}개")

        # 결과 JSON 저장
        report_path = self.output_dir / "validation_report_v2.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "version": "v2.0",
                "summary": {
                    "total_files": len(self.results),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "total_sections": total_sections,
                    "total_tables": total_tables,
                    "total_images": total_images,
                    "total_examples": total_examples,
                    "table_examples": total_table_examples,
                    "image_examples": total_image_examples,
                    "total_time": total_time
                },
                "content_types": all_content_types,
                "results": self.results
            }, f, ensure_ascii=False, indent=2)

        print(f"\n[보고서 저장]")
        print(f"  → {report_path}")
        print(f"\n{'='*60}")


def main():
    """메인 실행"""
    manual_dir = "/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130/manual_mvs_7.1"

    if not Path(manual_dir).exists():
        print(f"Error: 디렉토리를 찾을 수 없습니다: {manual_dir}")
        sys.exit(1)

    validator = PDFExtractorValidatorV2(manual_dir)
    validator.validate_all()
    validator.print_summary()


if __name__ == "__main__":
    main()
