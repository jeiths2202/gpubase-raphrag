#!/usr/bin/env python3
"""
Full Training Pipeline Orchestrator: CPT → SFT → DPO

3단계 학습 파이프라인을 순차적으로 실행하며,
상태 추적/재시작/개별 Phase 실행을 지원합니다.

Usage:
    # 전체 파이프라인 실행
    python scripts/training/run_full_pipeline.py --phase all --gpu 5

    # 개별 Phase 실행
    python scripts/training/run_full_pipeline.py --phase cpt --gpu 5
    python scripts/training/run_full_pipeline.py --phase sft --gpu 5
    python scripts/training/run_full_pipeline.py --phase dpo --gpu 5

    # 실패 지점부터 재시작
    python scripts/training/run_full_pipeline.py --phase all --gpu 5 --resume

    # Dry run (설정 확인만)
    python scripts/training/run_full_pipeline.py --phase all --dry-run

Requirements:
    pip install transformers peft datasets accelerate bitsandbytes trl
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent


# ============================================
# Configuration
# ============================================

@dataclass
class PipelineConfig:
    """전체 파이프라인 설정"""

    # Base
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"
    gpu: str = "5"

    # Work directory (모든 중간 결과 저장)
    work_dir: str = "models/pipeline_run"

    # Phase 1: CPT
    domain_corpus: str = "uploads/training_text/MVS_Openframe_7.1/corpus.txt"
    mixed_corpus: str = ""  # 자동 설정 (work_dir/mixed_corpus.txt)
    cpt_lora_rank: int = 128
    cpt_learning_rate: float = 2e-5
    cpt_embed_lr: float = 2e-6
    cpt_epochs: int = 3
    cpt_max_seq_length: int = 4096

    # Phase 2: SFT
    sft_data_dir: str = "uploads/summaries/multi_lora_v9_improved"
    sft_lora_rank: int = 64
    sft_learning_rate: float = 2e-4
    sft_epochs: int = 3

    # Phase 3: DPO
    e2e_test_file: str = "e2e/e2e_sentence_test.js"
    summaries_dir: str = "uploads/summaries"
    dpo_lora_rank: int = 32
    dpo_learning_rate: float = 5e-6
    dpo_beta: float = 0.1
    dpo_epochs: int = 2

    # Data mixing
    domain_ratio: float = 0.40
    japanese_ratio: float = 0.30
    code_ratio: float = 0.20
    math_ratio: float = 0.10
    offline_mixing: bool = False

    def __post_init__(self):
        if not self.mixed_corpus:
            self.mixed_corpus = str(Path(self.work_dir) / "mixed_corpus.txt")


# ============================================
# Pipeline Status Manager
# ============================================

class StatusManager:
    """파이프라인 상태 추적"""

    def __init__(self, work_dir: str):
        self.status_path = Path(work_dir) / "pipeline_status.json"
        self.status = self._load()

    def _load(self) -> Dict:
        if self.status_path.exists():
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        return {
            "started_at": datetime.now().isoformat(),
            "phases": {},
        }

    def save(self):
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(
            json.dumps(self.status, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_completed(self, phase: str) -> bool:
        return self.status.get("phases", {}).get(phase, {}).get("status") == "completed"

    def mark_running(self, phase: str):
        self.status.setdefault("phases", {})[phase] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        self.save()

    def mark_completed(self, phase: str, **extra):
        phase_data = self.status.setdefault("phases", {}).setdefault(phase, {})
        phase_data["status"] = "completed"
        phase_data["completed_at"] = datetime.now().isoformat()
        phase_data.update(extra)
        self.save()

    def mark_failed(self, phase: str, error: str):
        phase_data = self.status.setdefault("phases", {}).setdefault(phase, {})
        phase_data["status"] = "failed"
        phase_data["error"] = error
        phase_data["failed_at"] = datetime.now().isoformat()
        self.save()

    def get_output(self, phase: str, key: str) -> Optional[str]:
        return self.status.get("phases", {}).get(phase, {}).get(key)


# ============================================
# Phase Runners
# ============================================

def run_command(cmd: List[str], description: str) -> bool:
    """subprocess로 스크립트 실행"""
    logger.info(f"실행: {description}")
    logger.info(f"  명령: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"실패: {description} (exit code: {result.returncode})")
        return False

    logger.info(f"완료: {description}")
    return True


class PipelineOrchestrator:
    """3-Phase 파이프라인 오케스트레이터"""

    def __init__(self, config: PipelineConfig, resume: bool = False):
        self.config = config
        self.work = Path(config.work_dir)
        self.work.mkdir(parents=True, exist_ok=True)
        self.status = StatusManager(config.work_dir)
        self.resume = resume

    def run_phases(self, phases: List[str]):
        """지정된 Phase 실행"""
        for phase in phases:
            if self.resume and self.status.is_completed(phase):
                logger.info(f"Phase '{phase}' 이미 완료, 스킵")
                continue

            self.status.mark_running(phase)

            try:
                if phase == "cpt":
                    self._run_cpt()
                elif phase == "sft":
                    self._run_sft()
                elif phase == "dpo":
                    self._run_dpo()
                else:
                    raise ValueError(f"Unknown phase: {phase}")

                self.status.mark_completed(phase)
            except Exception as e:
                self.status.mark_failed(phase, str(e))
                logger.error(f"Phase '{phase}' 실패: {e}")
                raise

    # ----- Phase 1: CPT -----

    def _run_cpt(self):
        """Phase 1: 데이터 준비 → CPT 학습 → Adapter 병합 → 평가"""
        logger.info("=" * 60)
        logger.info("Phase 1: Continued Pre-Training (CPT)")
        logger.info("=" * 60)

        mixed_path = Path(self.config.mixed_corpus)
        cpt_adapter = self.work / "cpt_adapter"
        merged_cpt = self.work / "merged_cpt"
        eval_output = self.work / "eval_cpt.json"

        # Step 1-1: 데이터 믹싱
        if not mixed_path.exists():
            success = run_command(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "prepare_mixing_data.py"),
                    "--domain", self.config.domain_corpus,
                    "--output", str(mixed_path),
                    "--domain-ratio", str(self.config.domain_ratio),
                    "--japanese-ratio", str(self.config.japanese_ratio),
                    "--code-ratio", str(self.config.code_ratio),
                    "--math-ratio", str(self.config.math_ratio),
                ] + (["--offline"] if self.config.offline_mixing else []),
                "데이터 믹싱",
            )
            if not success:
                raise RuntimeError("데이터 믹싱 실패")
        else:
            logger.info(f"Mixed corpus 이미 존재: {mixed_path}")

        # Step 1-2: CPT 학습
        success = run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "run_cpt_training.py"),
                "--base-model", self.config.base_model,
                "--train-data", str(mixed_path),
                "--output-dir", str(cpt_adapter),
                "--lora-rank", str(self.config.cpt_lora_rank),
                "--learning-rate", str(self.config.cpt_learning_rate),
                "--embed-lr", str(self.config.cpt_embed_lr),
                "--epochs", str(self.config.cpt_epochs),
                "--max-seq-length", str(self.config.cpt_max_seq_length),
                "--gpu", self.config.gpu,
            ],
            "CPT 학습",
        )
        if not success:
            raise RuntimeError("CPT 학습 실패")

        # Step 1-3: Adapter 병합
        success = run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "merge_adapter.py"),
                "--base-model", self.config.base_model,
                "--adapter", str(cpt_adapter),
                "--output", str(merged_cpt),
            ],
            "CPT Adapter 병합",
        )
        if not success:
            raise RuntimeError("CPT Adapter 병합 실패")

        # Step 1-4: 평가
        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "evaluate_perplexity.py"),
                "--model", str(merged_cpt),
                "--test-data", self.config.domain_corpus,
                "--output", str(eval_output),
                "--cloze",
                "--gpu", self.config.gpu,
            ],
            "CPT 평가",
        )

        self.status.mark_completed("cpt", merged_model=str(merged_cpt))

    # ----- Phase 2: SFT -----

    def _run_sft(self):
        """Phase 2: 기존 SFT 파이프라인 실행 (CPT 병합 모델을 base로)"""
        logger.info("=" * 60)
        logger.info("Phase 2: Supervised Fine-Tuning (SFT)")
        logger.info("=" * 60)

        # CPT 병합 모델 또는 원본 base 사용
        base = self.status.get_output("cpt", "merged_model") or self.config.base_model
        sft_adapter = self.work / "sft_adapter"
        merged_sft = self.work / "merged_sft"

        # SFT 데이터 경로 확인
        sft_data = Path(self.config.sft_data_dir)
        if not sft_data.exists():
            raise FileNotFoundError(f"SFT 데이터 없음: {sft_data}")

        # 전체 제품 합본 train.json 찾기 또는 개별 제품 학습
        # train_multi_lora_v4.py 사용
        train_script = SCRIPT_DIR / "train_multi_lora_v4.py"
        if train_script.exists():
            success = run_command(
                [
                    sys.executable,
                    str(train_script),
                    "--all",
                    "--input", str(sft_data),
                    "--output", str(sft_adapter),
                    "--base-model", base,
                ],
                "Multi-LoRA SFT 학습",
            )
        else:
            # Fallback: qlora_trainer.py 직접 사용
            success = run_command(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "qlora_trainer.py"),
                    "--auto",
                ],
                "QLoRA SFT 학습",
            )

        if not success:
            raise RuntimeError("SFT 학습 실패")

        # SFT Adapter 병합 (DPO를 위해)
        # 개별 제품 adapter 중 대표 adapter 또는 combined adapter 병합
        adapter_path = sft_adapter
        if not (adapter_path / "adapter_config.json").exists():
            # 개별 제품 adapter 중 하나 선택
            for sub in adapter_path.iterdir():
                if sub.is_dir() and (sub / "adapter_config.json").exists():
                    adapter_path = sub
                    break

        if (adapter_path / "adapter_config.json").exists():
            run_command(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "merge_adapter.py"),
                    "--base-model", base,
                    "--adapter", str(adapter_path),
                    "--output", str(merged_sft),
                ],
                "SFT Adapter 병합",
            )
            self.status.mark_completed("sft", merged_model=str(merged_sft))
        else:
            # Adapter 병합 없이 base model 사용
            logger.warning("SFT adapter 병합 불가, base model 유지")
            self.status.mark_completed("sft", merged_model=base)

    # ----- Phase 3: DPO -----

    def _run_dpo(self):
        """Phase 3: DPO 데이터 생성 → DPO 학습"""
        logger.info("=" * 60)
        logger.info("Phase 3: Direct Preference Optimization (DPO)")
        logger.info("=" * 60)

        # SFT 또는 CPT 병합 모델 사용
        base = (
            self.status.get_output("sft", "merged_model")
            or self.status.get_output("cpt", "merged_model")
            or self.config.base_model
        )

        dpo_data = self.work / "dpo_pairs.json"
        dpo_adapter = self.work / "dpo_adapter"
        merged_final = self.work / "final_model"

        # Step 3-1: DPO 데이터 생성
        if not dpo_data.exists():
            success = run_command(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "generate_dpo_data.py"),
                    "--output", str(dpo_data),
                    "--e2e-test-file", self.config.e2e_test_file,
                    "--summaries-dir", self.config.summaries_dir,
                    "--sft-data-dir", self.config.sft_data_dir,
                    "--min-pairs", "300",
                ],
                "DPO 데이터 생성",
            )
            if not success:
                raise RuntimeError("DPO 데이터 생성 실패")
        else:
            logger.info(f"DPO 데이터 이미 존재: {dpo_data}")

        # Step 3-2: DPO 학습
        success = run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "run_dpo_training.py"),
                "--base-model", base,
                "--dpo-data", str(dpo_data),
                "--output-dir", str(dpo_adapter),
                "--lora-rank", str(self.config.dpo_lora_rank),
                "--learning-rate", str(self.config.dpo_learning_rate),
                "--beta", str(self.config.dpo_beta),
                "--epochs", str(self.config.dpo_epochs),
                "--gpu", self.config.gpu,
            ],
            "DPO 학습",
        )
        if not success:
            raise RuntimeError("DPO 학습 실패")

        # Step 3-3: Final model 병합
        success = run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "merge_adapter.py"),
                "--base-model", base,
                "--adapter", str(dpo_adapter),
                "--output", str(merged_final),
                "--verify",
            ],
            "최종 모델 병합",
        )
        if not success:
            raise RuntimeError("최종 모델 병합 실패")

        # Step 3-4: 최종 평가
        eval_output = self.work / "eval_final.json"
        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "evaluate_perplexity.py"),
                "--model", str(merged_final),
                "--test-data", self.config.domain_corpus,
                "--output", str(eval_output),
                "--cloze",
                "--gpu", self.config.gpu,
            ],
            "최종 모델 평가",
        )

        self.status.mark_completed("dpo", merged_model=str(merged_final))

    # ----- Summary -----

    def print_summary(self):
        """파이프라인 결과 요약"""
        print("\n" + "=" * 60)
        print("Pipeline Summary")
        print("=" * 60)

        for phase in ["cpt", "sft", "dpo"]:
            info = self.status.status.get("phases", {}).get(phase, {})
            status = info.get("status", "not started")
            icon = {"completed": "[OK]", "failed": "[FAIL]", "running": "[...]"}.get(
                status, "[ ]"
            )
            print(f"  {icon} {phase.upper()}: {status}")
            if info.get("merged_model"):
                print(f"       Model: {info['merged_model']}")
            if info.get("error"):
                print(f"       Error: {info['error']}")

        # 평가 결과 비교
        eval_files = list(self.work.glob("eval_*.json"))
        if eval_files:
            print(f"\n  Evaluation files: {len(eval_files)}")
            for f in sorted(eval_files):
                data = json.loads(f.read_text(encoding="utf-8"))
                ppl = data.get("perplexity", {}).get("perplexity", "N/A")
                cloze = data.get("cloze", {}).get("accuracy", "N/A")
                if isinstance(cloze, float):
                    cloze = f"{cloze:.1%}"
                print(f"    {f.name}: PPL={ppl}, Cloze={cloze}")

        print("=" * 60)


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="CPT+SFT+DPO 3-Phase Training Pipeline",
    )

    parser.add_argument(
        "--phase",
        default="all",
        choices=["all", "cpt", "sft", "dpo"],
        help="실행할 Phase (default: all)",
    )
    parser.add_argument("--gpu", default="5", help="GPU device index")
    parser.add_argument("--resume", action="store_true", help="완료된 Phase 스킵")
    parser.add_argument("--dry-run", action="store_true", help="설정 확인만")

    # Model
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--work-dir", default="models/pipeline_run")

    # CPT
    parser.add_argument(
        "--domain-corpus",
        default="uploads/training_text/MVS_Openframe_7.1/corpus.txt",
    )
    parser.add_argument("--cpt-rank", type=int, default=128)
    parser.add_argument("--cpt-lr", type=float, default=2e-5)
    parser.add_argument("--cpt-epochs", type=int, default=3)
    parser.add_argument("--offline", action="store_true", help="오프라인 데이터 믹싱")

    # SFT
    parser.add_argument(
        "--sft-data",
        default="uploads/summaries/multi_lora_v9_improved",
    )

    # DPO
    parser.add_argument("--dpo-rank", type=int, default=32)
    parser.add_argument("--dpo-lr", type=float, default=5e-6)
    parser.add_argument("--dpo-beta", type=float, default=0.1)

    args = parser.parse_args()

    config = PipelineConfig(
        base_model=args.base_model,
        gpu=args.gpu,
        work_dir=args.work_dir,
        domain_corpus=args.domain_corpus,
        cpt_lora_rank=args.cpt_rank,
        cpt_learning_rate=args.cpt_lr,
        cpt_epochs=args.cpt_epochs,
        sft_data_dir=args.sft_data,
        dpo_lora_rank=args.dpo_rank,
        dpo_learning_rate=args.dpo_lr,
        dpo_beta=args.dpo_beta,
        offline_mixing=args.offline,
    )

    if args.dry_run:
        phases = ["cpt", "sft", "dpo"] if args.phase == "all" else [args.phase]
        print("\n=== Pipeline Config (Dry Run) ===")
        print(f"Base Model: {config.base_model}")
        print(f"GPU: {config.gpu}")
        print(f"Work Dir: {config.work_dir}")
        print(f"Phases: {', '.join(phases)}")
        print(f"\nPhase 1 (CPT):")
        print(f"  Domain corpus: {config.domain_corpus}")
        print(f"  LoRA r={config.cpt_lora_rank}, LR={config.cpt_learning_rate}")
        print(f"  Embed LR: {config.cpt_embed_lr}")
        print(f"  Epochs: {config.cpt_epochs}")
        print(f"  Mixing: {config.domain_ratio}/{config.japanese_ratio}/{config.code_ratio}/{config.math_ratio}")
        print(f"\nPhase 2 (SFT):")
        print(f"  Data: {config.sft_data_dir}")
        print(f"  LoRA r={config.sft_lora_rank}, LR={config.sft_learning_rate}")
        print(f"\nPhase 3 (DPO):")
        print(f"  LoRA r={config.dpo_lora_rank}, LR={config.dpo_learning_rate}")
        print(f"  Beta: {config.dpo_beta}")
        print(f"  Epochs: {config.dpo_epochs}")

        # 데이터 존재 확인
        print(f"\n=== Data Check ===")
        for name, path in [
            ("Domain corpus", config.domain_corpus),
            ("SFT data", config.sft_data_dir),
            ("E2E tests", config.e2e_test_file),
            ("Summaries", config.summaries_dir),
        ]:
            exists = Path(path).exists()
            icon = "[OK]" if exists else "[MISSING]"
            print(f"  {icon} {name}: {path}")
        return

    # Phase 결정
    phases = ["cpt", "sft", "dpo"] if args.phase == "all" else [args.phase]

    # 실행
    orchestrator = PipelineOrchestrator(config, resume=args.resume)

    start = datetime.now()
    try:
        orchestrator.run_phases(phases)
    except Exception as e:
        logger.error(f"파이프라인 실패: {e}")
        orchestrator.print_summary()
        sys.exit(1)

    elapsed = datetime.now() - start
    logger.info(f"\n총 소요 시간: {elapsed}")
    orchestrator.print_summary()


if __name__ == "__main__":
    main()
