#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
다국어 학습 데이터 생성기
========================
모든 PDF에 대해 일본어/한국어/영어 학습 데이터를 생성합니다.
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from openframe_qlora_full_extractor_v2 import (
    OpenFrameManualParserV2,
    QLoRADataGeneratorV2,
)


LANGUAGES = ["ja", "ko", "en"]
LANGUAGE_NAMES = {"ja": "일본어", "ko": "한국어", "en": "영어"}


def process_single_pdf(args) -> Dict[str, Any]:
    """단일 PDF 처리 (멀티프로세싱용)"""
    pdf_path, output_dir, languages = args
    results = {
        "filename": pdf_path.name,
        "status": "pending",
        "languages": {},
        "total_examples": 0,
        "processing_time": 0,
        "error": None
    }

    start_time = time.time()

    try:
        # PDF 파싱 (한 번만)
        parser = OpenFrameManualParserV2(extract_images=False)
        sections = parser.parse_pdf(str(pdf_path))

        for lang in languages:
            lang_result = {
                "examples_count": 0,
                "output_file": None,
                "status": "pending"
            }

            try:
                # 학습 데이터 생성
                generator = QLoRADataGeneratorV2(parser)
                training_data = generator.generate_training_data(
                    language=lang,
                    include_tables=True,
                    include_images=True
                )

                # Q&A 쌍 추가
                qa_pairs = generator.generate_qa_pairs(language=lang)
                generator.training_data.extend(qa_pairs)

                # 출력 파일 저장
                output_filename = f"{pdf_path.stem}_{lang}.jsonl"
                output_path = output_dir / output_filename
                generator.export_jsonl(str(output_path), format_type="alpaca")

                lang_result["examples_count"] = len(generator.training_data)
                lang_result["output_file"] = str(output_path)
                lang_result["status"] = "success"
                results["total_examples"] += len(generator.training_data)

            except Exception as e:
                lang_result["status"] = "failed"
                lang_result["error"] = str(e)

            results["languages"][lang] = lang_result

        results["status"] = "success"

    except Exception as e:
        results["status"] = "failed"
        results["error"] = str(e)

    results["processing_time"] = round(time.time() - start_time, 2)
    return results


def main():
    """메인 실행"""
    manual_dir = Path("/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130/manual_mvs_7.1")
    output_dir = Path("/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130/training_data_multilang")
    output_dir.mkdir(exist_ok=True)

    # PDF 파일 목록
    pdf_files = sorted([f for f in manual_dir.glob("*.pdf") if "コピー" not in f.name])
    total_files = len(pdf_files)

    print("=" * 70)
    print("OpenFrame MVS 7.1 다국어 학습 데이터 생성기")
    print("=" * 70)
    print(f"총 PDF 파일: {total_files}개")
    print(f"언어: {', '.join([f'{k}({v})' for k, v in LANGUAGE_NAMES.items()])}")
    print(f"예상 출력 파일: {total_files * len(LANGUAGES)}개")
    print(f"출력 디렉토리: {output_dir}")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_results = []
    total_start = time.time()

    for idx, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{total_files}] {pdf_path.name}")
        print("-" * 50)

        result = process_single_pdf((pdf_path, output_dir, LANGUAGES))
        all_results.append(result)

        if result["status"] == "success":
            for lang in LANGUAGES:
                lang_result = result["languages"].get(lang, {})
                status = "✓" if lang_result.get("status") == "success" else "✗"
                count = lang_result.get("examples_count", 0)
                print(f"  {status} {LANGUAGE_NAMES[lang]}: {count}개")
            print(f"  처리 시간: {result['processing_time']}초")
        else:
            print(f"  ✗ 실패: {result.get('error', 'Unknown error')}")

    total_time = round(time.time() - total_start, 2)

    # 요약 출력
    print("\n" + "=" * 70)
    print("생성 완료 - 요약")
    print("=" * 70)

    success_count = sum(1 for r in all_results if r["status"] == "success")
    failed_count = sum(1 for r in all_results if r["status"] == "failed")

    # 언어별 통계
    lang_stats = {lang: {"files": 0, "examples": 0} for lang in LANGUAGES}
    for result in all_results:
        if result["status"] == "success":
            for lang in LANGUAGES:
                lang_result = result["languages"].get(lang, {})
                if lang_result.get("status") == "success":
                    lang_stats[lang]["files"] += 1
                    lang_stats[lang]["examples"] += lang_result.get("examples_count", 0)

    total_examples = sum(r["total_examples"] for r in all_results)

    print(f"\n[전체 통계]")
    print(f"  • 총 PDF 파일: {total_files}개")
    print(f"  • 성공: {success_count}개")
    print(f"  • 실패: {failed_count}개")
    print(f"  • 총 처리 시간: {total_time}초")

    print(f"\n[언어별 통계]")
    for lang in LANGUAGES:
        stats = lang_stats[lang]
        print(f"  • {LANGUAGE_NAMES[lang]} ({lang}): {stats['files']}개 파일, {stats['examples']:,}개 예제")

    print(f"\n[총 학습 데이터]")
    print(f"  • 총 예제 수: {total_examples:,}개")
    print(f"  • 출력 파일 수: {success_count * len(LANGUAGES)}개")

    # 결과 JSON 저장
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_files": total_files,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_examples": total_examples,
            "total_time": total_time,
            "languages": LANGUAGES
        },
        "language_stats": lang_stats,
        "results": all_results
    }

    report_path = output_dir / "generation_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[보고서 저장]")
    print(f"  → {report_path}")

    # 통합 파일 생성
    print(f"\n[통합 파일 생성 중...]")
    for lang in LANGUAGES:
        combined_path = output_dir / f"combined_{lang}.jsonl"
        with open(combined_path, 'w', encoding='utf-8') as outfile:
            for result in all_results:
                if result["status"] == "success":
                    lang_result = result["languages"].get(lang, {})
                    if lang_result.get("status") == "success" and lang_result.get("output_file"):
                        with open(lang_result["output_file"], 'r', encoding='utf-8') as infile:
                            outfile.write(infile.read())

        # 라인 수 계산
        with open(combined_path, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
        print(f"  → combined_{lang}.jsonl: {line_count:,}개 예제")

    print("\n" + "=" * 70)
    print("완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
