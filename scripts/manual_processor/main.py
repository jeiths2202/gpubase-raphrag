#!/usr/bin/env python3
"""
OpenFrame 매뉴얼 프로세서 CLI

PDF 매뉴얼을 분석하여 AI Agent용 Markdown 요약본을 생성합니다.

Usage:
    python -m scripts.manual_processor.main process-all
    python -m scripts.manual_processor.main process /path/to/manual.pdf
    python -m scripts.manual_processor.main extract-errors
    python -m scripts.manual_processor.main extract-comprehensive
    python -m scripts.manual_processor.main extract-structure --input /path/to/manual.pdf
    python -m scripts.manual_processor.main rebuild-index
    python -m scripts.manual_processor.main gen-training
    python -m scripts.manual_processor.main gen-training --formats sft cpt --languages ja ko
    python -m scripts.manual_processor.main gen-training --unified
    python -m scripts.manual_processor.main validate-training
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

    def quality_check(
        self,
        category: str = "all",
        output_path: Optional[Path] = None,
        verbose: bool = False
    ) -> None:
        """요약본 품질 검사

        Args:
            category: 검사할 카테고리 (all, commands, configs, apis, concepts)
            output_path: 리포트 출력 경로
            verbose: 상세 출력 여부
        """
        logger.info("=== 요약본 품질 검사 ===")
        start_time = datetime.now()

        from .quality_checker import QualityChecker

        checker = QualityChecker(config.summaries_dir)

        # 카테고리별 또는 전체 검사
        if category == "all":
            report = checker.check_all()
        else:
            report = checker.check_category(category)

        # 결과 출력
        summary = checker.generate_summary(report)
        print(summary)

        # 파일 저장
        if output_path is None:
            output_path = config.summaries_dir / "quality_report.json"

        report.save(str(output_path))
        logger.info(f"리포트 저장: {output_path}")

        # 상세 출력
        if verbose:
            print("\n--- 상세 JSON ---")
            print(report.to_json())

        elapsed = datetime.now() - start_time
        logger.info(f"소요 시간: {elapsed}")

    def quality_improve(
        self,
        dry_run: bool = False,
        skip_pdf_extraction: bool = False,
        output_path: Optional[Path] = None
    ) -> None:
        """요약본 품질 개선 (검사 + 자동 수정)

        Args:
            dry_run: 변경 없이 미리보기
            skip_pdf_extraction: PDF 재추출 건너뛰기
            output_path: 리포트 출력 경로
        """
        logger.info("=== 요약본 품질 개선 ===")
        start_time = datetime.now()

        from .quality_checker import QualityChecker
        from .quality_enhancer import QualityEnhancer

        # 1. 품질 검사
        logger.info("\n[1/3] 품질 검사 중...")
        checker = QualityChecker(config.summaries_dir)
        report = checker.check_all()

        summary = checker.generate_summary(report)
        print(summary)

        if report.total_issues == 0:
            logger.info("품질 이슈가 없습니다. 개선 작업 불필요.")
            return

        # 2. 품질 개선
        if dry_run:
            logger.info("\n[Dry-Run] 변경 없이 종료합니다.")
            logger.info(f"수정 대상: {report.total_issues}개 이슈")
            return

        logger.info(f"\n[2/3] 품질 개선 중... ({report.total_issues}개 이슈)")
        enhancer = QualityEnhancer(
            pdf_parser=self.pdf_parser,
            summaries_dir=config.summaries_dir,
            manuals_dir=config.manuals_dir
        )
        result = enhancer.enhance_all(
            report,
            skip_pdf_extraction=skip_pdf_extraction
        )

        logger.info(f"개선 완료:")
        logger.info(f"  - 불완전 설명 수정: {result.fixed_incomplete}개")
        logger.info(f"  - 중복 병합: {result.merged_duplicates}개")
        logger.info(f"  - 타입 재분류: {result.reclassified_items}개")

        if result.failed_items:
            logger.warning(f"실패한 항목: {len(result.failed_items)}개")
            for item in result.failed_items[:5]:
                logger.warning(f"  - {item}")

        # 3. 재검사
        logger.info("\n[3/3] 재검사 중...")
        final_report = checker.check_all()
        final_summary = checker.generate_summary(final_report)
        print("\n--- 개선 후 ---")
        print(final_summary)

        # 리포트 저장
        if output_path is None:
            output_path = config.summaries_dir / "quality_report.json"
        final_report.save(str(output_path))

        elapsed = datetime.now() - start_time
        logger.info(f"\n소요 시간: {elapsed}")
        logger.info(f"품질 점수 변화: {report.quality_score:.1f}% → {final_report.quality_score:.1f}%")

    def gen_training(
        self,
        formats: List[str] = None,
        languages: List[str] = None,
        dpo_count: int = 2000,
        unified: bool = False,
        unified_dpo_count: int = 500,
    ) -> None:
        """학습 데이터 생성 (SFT/CPT/DPO)

        Args:
            formats: 생성할 포맷 (sft, cpt, dpo 중 선택, 기본: 전부)
            languages: 대상 언어 (ja, ko, en 중 선택, 기본: 전부)
            dpo_count: DPO 쌍 목표 수 (기본: 2000)
            unified: 통합 LoRA 데이터셋도 생성 (기본: False)
            unified_dpo_count: 통합 DPO 쌍 목표 수 (기본: 500)
        """
        logger.info("=== 학습 데이터 생성 시작 ===")
        start_time = datetime.now()

        if formats is None:
            formats = ["sft", "cpt", "dpo"]
        if languages is None:
            languages = ["ja", "ko", "en"]

        output_dir = Path(config.training_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        all_stats = {}
        sft_records = []

        # 1. SFT 생성
        if "sft" in formats:
            logger.info("\n[1/3] SFT ChatML 학습 데이터 생성...")
            from .generators.sft_generator import SFTGenerator

            sft_gen = SFTGenerator(config.manuals_dir, output_dir)
            sft_stats = sft_gen.generate_all(languages=languages)
            sft_records = sft_gen.records  # DPO에서 재사용
            all_stats["sft"] = sft_stats.to_dict()

            logger.info(f"  SFT: {sft_stats.total_records} records")
            logger.info(f"    Train: {sft_stats.train_count}, Eval: {sft_stats.eval_count}")
        else:
            logger.info("\n[1/3] SFT 건너뜀")

        # 2. CPT 생성
        if "cpt" in formats:
            logger.info("\n[2/3] CPT Plain Text 코퍼스 생성...")
            from .generators.cpt_generator import CPTGenerator

            cpt_gen = CPTGenerator(config.manuals_dir, output_dir)
            cpt_stats = cpt_gen.generate_all(languages=languages)
            all_stats["cpt"] = cpt_stats.to_dict()

            logger.info(f"  CPT: {cpt_stats.total_records} chunks")
            for lang, count in cpt_stats.by_language.items():
                logger.info(f"    {lang}: {count} chunks")
        else:
            logger.info("\n[2/3] CPT 건너뜀")

        # 3. DPO 생성 (SFT 레코드 필요)
        if "dpo" in formats:
            if not sft_records and "sft" not in formats:
                # SFT를 먼저 생성하여 레코드 확보
                logger.info("\n  DPO 생성을 위해 SFT 레코드를 먼저 생성합니다...")
                from .generators.sft_generator import SFTGenerator
                sft_gen = SFTGenerator(config.manuals_dir, output_dir)
                sft_gen.generate_all(languages=languages)
                sft_records = sft_gen.records

            logger.info(f"\n[3/3] DPO Preference Pairs 생성 (목표: {dpo_count}쌍)...")
            from .generators.dpo_generator import DPOGenerator

            dpo_gen = DPOGenerator(output_dir)
            dpo_stats = dpo_gen.generate_all(
                sft_records=sft_records,
                target_count=dpo_count,
            )
            all_stats["dpo"] = dpo_stats.to_dict()

            logger.info(f"  DPO: {dpo_stats.total_records} pairs")
        else:
            logger.info("\n[3/3] DPO 건너뜀")

        # 4. 통합 LoRA 데이터셋 생성
        if unified:
            self._gen_unified_training(
                output_dir, languages, unified_dpo_count, all_stats
            )

        # 통계 저장
        import json
        stats_path = output_dir / "generation_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(all_stats, f, ensure_ascii=False, indent=2)

        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 학습 데이터 생성 완료 ===")
        logger.info(f"출력 디렉토리: {output_dir}")
        logger.info(f"소요 시간: {elapsed}")

    def _gen_unified_training(
        self,
        output_dir: Path,
        languages: List[str],
        unified_dpo_count: int,
        all_stats: dict,
    ) -> None:
        """통합 LoRA 학습 데이터 생성 (SFT + DPO + CPT)

        제품 간 관계(R-01~R-07)를 학습하기 위한 25번째 통합 어댑터용 데이터셋.
        """
        import json

        logger.info("\n=== 통합 LoRA 데이터셋 생성 ===")

        # 4-1. 통합 SFT
        logger.info("\n[Unified 1/3] 통합 SFT 생성...")
        from .generators.unified_sft_generator import UnifiedSFTGenerator

        unified_sft_gen = UnifiedSFTGenerator(config)
        unified_sft_records = unified_sft_gen.generate_all()
        self._save_unified_sft(unified_sft_records, output_dir)
        all_stats["unified_sft"] = {
            "total": len(unified_sft_records),
            "by_relation": {},
            "by_language": {},
            "by_source": {},
        }
        for r in unified_sft_records:
            rt = r.relation_type
            all_stats["unified_sft"]["by_relation"][rt] = (
                all_stats["unified_sft"]["by_relation"].get(rt, 0) + 1
            )
            lang = r.language.value
            all_stats["unified_sft"]["by_language"][lang] = (
                all_stats["unified_sft"]["by_language"].get(lang, 0) + 1
            )
            src = r.source
            all_stats["unified_sft"]["by_source"][src] = (
                all_stats["unified_sft"]["by_source"].get(src, 0) + 1
            )
        logger.info(f"  통합 SFT: {len(unified_sft_records)} records")

        # 4-2. 통합 DPO
        logger.info(
            f"\n[Unified 2/3] 통합 DPO 생성 (목표: {unified_dpo_count}쌍)..."
        )
        from .generators.unified_dpo_generator import UnifiedDPOGenerator

        unified_dpo_gen = UnifiedDPOGenerator(unified_sft_records)
        unified_dpo_records = unified_dpo_gen.generate_all(
            target_count=unified_dpo_count
        )
        self._save_unified_dpo(unified_dpo_records, output_dir)
        all_stats["unified_dpo"] = {
            "total": len(unified_dpo_records),
            "by_strategy": {},
        }
        for r in unified_dpo_records:
            s = r.strategy
            all_stats["unified_dpo"]["by_strategy"][s] = (
                all_stats["unified_dpo"]["by_strategy"].get(s, 0) + 1
            )
        logger.info(f"  통합 DPO: {len(unified_dpo_records)} pairs")

        # 4-3. 통합 CPT
        logger.info("\n[Unified 3/3] 통합 CPT 생성...")
        from .generators.unified_cpt_generator import UnifiedCPTGenerator

        unified_cpt_gen = UnifiedCPTGenerator(config.manuals_dir, output_dir)
        unified_cpt_chunks = unified_cpt_gen.generate_all(languages=languages)
        all_stats["unified_cpt"] = {
            "total": len(unified_cpt_chunks),
            "total_tokens": sum(c.token_count for c in unified_cpt_chunks),
        }
        logger.info(f"  통합 CPT: {len(unified_cpt_chunks)} chunks")

        logger.info(
            f"\n통합 LoRA 데이터셋 완료: "
            f"SFT {len(unified_sft_records)}, "
            f"DPO {len(unified_dpo_records)}, "
            f"CPT {len(unified_cpt_chunks)}"
        )

    def _save_unified_sft(
        self, records: list, output_dir: Path
    ) -> None:
        """통합 SFT 데이터 저장"""
        import json

        sft_dir = output_dir / "sft_unified"
        sft_dir.mkdir(parents=True, exist_ok=True)

        # Train/Eval 분할 (90/10)
        split_idx = int(len(records) * 0.9)
        train_records = records[:split_idx]
        eval_records = records[split_idx:]

        with open(sft_dir / "train_all.jsonl", "w", encoding="utf-8") as f:
            for r in train_records:
                f.write(json.dumps(r.to_jsonl(), ensure_ascii=False) + "\n")

        with open(sft_dir / "eval_all.jsonl", "w", encoding="utf-8") as f:
            for r in eval_records:
                f.write(json.dumps(r.to_jsonl(), ensure_ascii=False) + "\n")

        # 관계 유형별 분류
        by_relation_dir = sft_dir / "by_relation"
        by_relation_dir.mkdir(exist_ok=True)
        relation_names = {
            "R-01": "dependency", "R-02": "integration", "R-03": "comparison",
            "R-04": "boot_sequence", "R-05": "error_propagation",
            "R-06": "migration", "R-07": "shared_config",
        }
        for relation_type, relation_name in relation_names.items():
            type_records = [r for r in records if r.relation_type == relation_type]
            if type_records:
                with open(
                    by_relation_dir / f"{relation_type}_{relation_name}.jsonl",
                    "w",
                    encoding="utf-8",
                ) as f:
                    for r in type_records:
                        f.write(json.dumps(r.to_jsonl(), ensure_ascii=False) + "\n")

        logger.info(
            f"  통합 SFT 저장: train={len(train_records)}, "
            f"eval={len(eval_records)} → {sft_dir}"
        )

    def _save_unified_dpo(
        self, records: list, output_dir: Path
    ) -> None:
        """통합 DPO 데이터 저장"""
        import json

        dpo_dir = output_dir / "dpo_unified"
        dpo_dir.mkdir(parents=True, exist_ok=True)

        with open(dpo_dir / "dpo_all.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r.to_jsonl(), ensure_ascii=False) + "\n")

        logger.info(f"  통합 DPO 저장: {len(records)}쌍 → {dpo_dir}")

    def validate_training(
        self,
        data_dir: Optional[Path] = None,
        output_path: Optional[Path] = None,
    ) -> None:
        """학습 데이터 품질 검증

        Args:
            data_dir: 학습 데이터 디렉토리 (기본: config.training_output_dir)
            output_path: 리포트 출력 경로
        """
        logger.info("=== 학습 데이터 품질 검증 시작 ===")
        start_time = datetime.now()

        import json
        from .models.training import SFTRecord, DataLanguage
        from .validators.training_validator import TrainingValidator

        if data_dir is None:
            data_dir = Path(config.training_output_dir)

        validator = TrainingValidator()
        reports = {}

        # 1. SFT 검증
        sft_train = data_dir / "sft" / "train_all.jsonl"
        if sft_train.exists():
            logger.info("\n[1/3] SFT 데이터 검증...")
            records = self._load_sft_jsonl(sft_train)
            reports["sft"] = validator.validate_sft(records)
            logger.info(
                f"  SFT 품질: {reports['sft']['quality_score']}% "
                f"({reports['sft']['passed']}/{reports['sft']['total']})"
            )
            for rec in reports["sft"].get("recommendations", []):
                logger.info(f"    → {rec}")
        else:
            logger.info("\n[1/3] SFT 데이터 없음, 건너뜀")

        # 2. CPT 검증
        cpt_dir = data_dir / "cpt"
        if cpt_dir.exists():
            logger.info("\n[2/3] CPT 코퍼스 검증...")
            reports["cpt"] = {}
            for corpus_file in sorted(cpt_dir.glob("corpus_*.txt")):
                lang = corpus_file.stem.replace("corpus_", "")
                report = validator.validate_cpt(corpus_file)
                reports["cpt"][lang] = report
                logger.info(
                    f"  {lang}: {report['checks'].get('chunk_count', 0)} chunks, "
                    f"{report['checks'].get('file_size_mb', 0)} MB, "
                    f"품질: {report.get('quality_score', 0)}%"
                )
        else:
            logger.info("\n[2/3] CPT 데이터 없음, 건너뜀")

        # 3. DPO 검증
        dpo_all = data_dir / "dpo" / "dpo_all.jsonl"
        if dpo_all.exists():
            logger.info("\n[3/3] DPO 데이터 검증...")
            from .models.training import DPORecord
            dpo_records = self._load_dpo_jsonl(dpo_all)
            reports["dpo"] = validator.validate_dpo(dpo_records)
            logger.info(
                f"  DPO 품질: {reports['dpo']['quality_score']}% "
                f"({reports['dpo']['passed']}/{reports['dpo']['total']})"
            )
        else:
            logger.info("\n[3/3] DPO 데이터 없음, 건너뜀")

        # 리포트 저장
        if output_path is None:
            output_path = data_dir / "validation_report.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)

        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 검증 완료 ===")
        logger.info(f"리포트 저장: {output_path}")
        logger.info(f"소요 시간: {elapsed}")

    def _load_sft_jsonl(self, path: Path) -> List:
        """JSONL에서 SFT 레코드 로드"""
        import json
        from .models.training import SFTRecord, DataLanguage

        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                # ChatML text에서 instruction/response 추출
                text = data.get("text", "")
                parts = text.split("<|im_end|>")
                instruction = ""
                response = ""
                system_prompt = ""
                for part in parts:
                    if "<|im_start|>system" in part:
                        system_prompt = part.split("<|im_start|>system\n", 1)[-1].strip()
                    elif "<|im_start|>user" in part:
                        instruction = part.split("<|im_start|>user\n", 1)[-1].strip()
                    elif "<|im_start|>assistant" in part:
                        response = part.split("<|im_start|>assistant\n", 1)[-1].strip()

                lang_str = data.get("language", "ja")
                try:
                    lang = DataLanguage(lang_str)
                except ValueError:
                    lang = DataLanguage.JA

                records.append(SFTRecord(
                    instruction=instruction,
                    response=response,
                    system_prompt=system_prompt,
                    product=data.get("product", ""),
                    language=lang,
                    source_file=data.get("source", ""),
                    item_type=data.get("type", ""),
                ))
        return records

    def _load_dpo_jsonl(self, path: Path) -> List:
        """JSONL에서 DPO 레코드 로드"""
        import json
        from .models.training import DPORecord, DataLanguage

        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                lang_str = data.get("language", "ja")
                try:
                    lang = DataLanguage(lang_str)
                except ValueError:
                    lang = DataLanguage.JA

                records.append(DPORecord(
                    prompt=data.get("prompt", ""),
                    chosen=data.get("chosen", ""),
                    rejected=data.get("rejected", ""),
                    product=data.get("product", ""),
                    language=lang,
                    strategy=data.get("strategy", ""),
                ))
        return records

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

    def generate_learning_dataset(self, output_path: Optional[Path] = None) -> None:
        """전략 기반 학습 데이터셋 생성

        strategy_analysis.json을 활용하여 각 문서 유형에 최적화된
        추출 패턴으로 학습 데이터셋을 생성합니다.
        """
        logger.info("=== 전략 기반 학습 데이터셋 생성 ===")
        start_time = datetime.now()

        from .parsers.strategy_aware_parser import StrategyAwareParser, generate_learning_dataset

        # 출력 경로 설정
        if output_path is None:
            output_path = config.summaries_dir / "learning_dataset.json"

        # 전략 파일 경로
        strategy_file = config.summaries_dir / "strategy_analysis.json"

        if not strategy_file.exists():
            logger.error(f"전략 분석 파일이 없습니다: {strategy_file}")
            logger.info("먼저 analyze_all_manuals.py를 실행하세요.")
            return

        # 학습 데이터셋 생성
        stats = generate_learning_dataset(
            manuals_dir=config.manuals_dir,
            output_path=output_path,
            strategy_file=strategy_file
        )

        # 완료
        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 학습 데이터셋 생성 완료 ===")
        logger.info(f"총 항목: {stats['total_items']}개")
        logger.info(f"\n타입별 통계:")
        for item_type, count in sorted(stats['type_stats'].items(), key=lambda x: -x[1]):
            logger.info(f"  {item_type}: {count}개")
        logger.info(f"\n제품별 통계:")
        for product, count in sorted(stats['product_stats'].items(), key=lambda x: -x[1])[:10]:
            logger.info(f"  {product}: {count}개")
        logger.info(f"\n출력 파일: {output_path}")
        logger.info(f"소요 시간: {elapsed}")

    def extract_structure(
        self,
        input_path: Path,
        output_dir: Optional[Path] = None,
        language: str = "ja",
        validate: bool = True,
        skip_existing: bool = True
    ) -> None:
        """PDF 계층 구조 추출

        PDF 문서의 계층적 구조(Chapter/Section/Subsection)를 추출하여
        JSON 및 Markdown 파일로 저장합니다.

        Args:
            input_path: PDF 파일 또는 디렉토리 경로
            output_dir: 출력 디렉토리 (기본: summaries_dir)
            language: 문서 언어 (ja, en, ko)
            validate: TOC 검증 수행 여부
            skip_existing: 기존 파일 건너뛰기
        """
        logger.info("=== PDF 구조 추출 시작 ===")
        start_time = datetime.now()

        from .parsers.structure_parser import StructureParser
        from .generators.structure_generator import StructureGenerator, generate_batch_index

        # 출력 디렉토리 설정
        if output_dir is None:
            output_dir = config.summaries_dir

        # 파서 및 생성기 초기화
        parser = StructureParser(language=language)
        generator = StructureGenerator(output_dir)

        # 입력 경로 처리
        if input_path.is_file():
            pdf_files = [input_path]
        elif input_path.is_dir():
            # 재귀적으로 모든 PDF 파일 검색
            pdf_files = list(input_path.glob("**/*.pdf"))
        else:
            logger.error(f"유효하지 않은 경로: {input_path}")
            return

        logger.info(f"처리할 PDF 파일: {len(pdf_files)}개")

        # 결과 저장
        structures = []
        success_count = 0
        skip_count = 0
        fail_count = 0

        for pdf_path in pdf_files:
            try:
                # 기존 파일 확인
                base_name = pdf_path.stem
                existing_json = output_dir / "structures" / f"{base_name}_structure.json"

                if skip_existing and existing_json.exists():
                    logger.info(f"건너뛰기 (기존 파일): {pdf_path.name}")
                    skip_count += 1
                    continue

                logger.info(f"처리 중: {pdf_path.name}")

                # 구조 추출
                structure = parser.parse(pdf_path)
                if structure is None:
                    fail_count += 1
                    continue

                # 출력 파일 생성
                output_files = generator.generate_all(structure)

                structures.append(structure)
                success_count += 1

                # 검증 결과 로깅
                if validate and structure.validation:
                    coverage = structure.get_coverage_ratio() * 100
                    valid = structure.is_valid()
                    logger.info(f"  검증: {coverage:.1f}% 커버리지, {'통과' if valid else '실패'}")

            except Exception as e:
                logger.error(f"처리 실패: {pdf_path.name} - {e}")
                fail_count += 1

        # 배치 인덱스 생성 (여러 파일 처리 시)
        if len(structures) > 1:
            generate_batch_index(output_dir, structures)

        # 완료 통계
        elapsed = datetime.now() - start_time
        logger.info(f"\n=== 구조 추출 완료 ===")
        logger.info(f"성공: {success_count}개")
        logger.info(f"건너뜀: {skip_count}개")
        logger.info(f"실패: {fail_count}개")
        logger.info(f"총 노드: {sum(s.count_all_nodes() for s in structures)}개")
        logger.info(f"총 이미지 참조: {sum(len(s.images_index) for s in structures)}개")

        if validate and structures:
            valid_count = sum(1 for s in structures if s.is_valid())
            avg_coverage = sum(s.get_coverage_ratio() for s in structures) / len(structures)
            logger.info(f"검증 통과: {valid_count}/{len(structures)}개")
            logger.info(f"평균 커버리지: {avg_coverage * 100:.1f}%")

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
  python -m scripts.manual_processor.main extract-structure --input /path/to/manual.pdf
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

    # generate-learning-dataset 명령
    learning_parser = subparsers.add_parser(
        "generate-learning-dataset",
        help="전략 기반 학습 데이터셋 생성 (strategy_analysis.json 활용)"
    )
    learning_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="출력 파일 경로 (기본: summaries/learning_dataset.json)"
    )

    # extract-structure 명령
    structure_parser = subparsers.add_parser(
        "extract-structure",
        help="PDF 계층 구조 추출 (Two-Stage Retrieval용)"
    )
    structure_parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="PDF 파일 또는 디렉토리 경로"
    )
    structure_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="출력 디렉토리 (기본: summaries/structures)"
    )
    structure_parser.add_argument(
        "--language", "-l",
        type=str,
        default="ja",
        choices=["ja", "en", "ko"],
        help="문서 언어 (기본: ja)"
    )
    structure_parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="TOC 검증 수행 (기본: True)"
    )
    structure_parser.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="TOC 검증 건너뛰기"
    )
    structure_parser.add_argument(
        "--no-skip",
        action="store_true",
        help="기존 파일도 다시 처리"
    )

    # gen-training 명령
    gen_train_parser = subparsers.add_parser(
        "gen-training",
        help="학습 데이터 생성 (SFT/CPT/DPO)"
    )
    gen_train_parser.add_argument(
        "--formats", "-f",
        nargs="+",
        choices=["sft", "cpt", "dpo"],
        default=None,
        help="생성할 포맷 (기본: sft cpt dpo 전부)"
    )
    gen_train_parser.add_argument(
        "--languages", "-l",
        nargs="+",
        choices=["ja", "ko", "en"],
        default=None,
        help="대상 언어 (기본: ja ko en 전부)"
    )
    gen_train_parser.add_argument(
        "--dpo-count",
        type=int,
        default=2000,
        help="DPO 쌍 목표 수 (기본: 2000)"
    )
    gen_train_parser.add_argument(
        "--unified",
        action="store_true",
        help="통합 LoRA 데이터셋도 생성 (제품 간 관계 학습용)"
    )
    gen_train_parser.add_argument(
        "--unified-dpo-count",
        type=int,
        default=500,
        help="통합 DPO 쌍 목표 수 (기본: 500)"
    )

    # validate-training 명령
    val_train_parser = subparsers.add_parser(
        "validate-training",
        help="학습 데이터 품질 검증"
    )
    val_train_parser.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=None,
        help="학습 데이터 디렉토리 (기본: uploads/training/v10)"
    )
    val_train_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="리포트 출력 경로"
    )

    # rebuild-index 명령
    subparsers.add_parser("rebuild-index", help="인덱스 재생성")

    # quality-check 명령
    check_parser = subparsers.add_parser(
        "quality-check",
        help="요약본 품질 검사 (불완전 설명, 중복, 분류 오류 탐지)"
    )
    check_parser.add_argument(
        "--category", "-c",
        choices=["all", "commands", "configs", "apis", "concepts"],
        default="all",
        help="검사할 카테고리 (기본: all)"
    )
    check_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="리포트 출력 경로 (기본: summaries/quality_report.json)"
    )
    check_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 출력"
    )

    # quality-improve 명령
    improve_parser = subparsers.add_parser(
        "quality-improve",
        help="요약본 품질 개선 (검사 + 자동 수정)"
    )
    improve_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="변경 없이 미리보기"
    )
    improve_parser.add_argument(
        "--skip-pdf-extraction",
        action="store_true",
        help="PDF 재추출 건너뛰기 (빠른 실행)"
    )
    improve_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="리포트 출력 경로"
    )

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
    elif args.command == "generate-learning-dataset":
        processor.generate_learning_dataset(output_path=args.output)
    elif args.command == "extract-structure":
        processor.extract_structure(
            input_path=args.input,
            output_dir=args.output,
            language=args.language,
            validate=args.validate,
            skip_existing=not args.no_skip
        )
    elif args.command == "gen-training":
        processor.gen_training(
            formats=args.formats,
            languages=args.languages,
            dpo_count=args.dpo_count,
            unified=args.unified,
            unified_dpo_count=args.unified_dpo_count,
        )
    elif args.command == "validate-training":
        processor.validate_training(
            data_dir=args.data_dir,
            output_path=args.output,
        )
    elif args.command == "rebuild-index":
        processor.rebuild_index()
    elif args.command == "quality-check":
        processor.quality_check(
            category=args.category,
            output_path=args.output,
            verbose=args.verbose
        )
    elif args.command == "quality-improve":
        processor.quality_improve(
            dry_run=args.dry_run,
            skip_pdf_extraction=args.skip_pdf_extraction,
            output_path=args.output
        )


if __name__ == "__main__":
    main()
