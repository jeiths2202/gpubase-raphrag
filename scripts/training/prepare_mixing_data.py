#!/usr/bin/env python3
"""
CPT Data Mixing Script - Catastrophic Forgetting 방지를 위한 데이터 믹싱

도메인 corpus에 일반 일본어/코드/수학 데이터를 혼합하여
Continued Pre-Training 시 기존 능력 유지 + 도메인 지식 흡수를 동시에 달성합니다.

Usage:
    # 기본 믹싱 (40% 도메인, 30% 일본어, 20% 코드, 10% 수학)
    python scripts/training/prepare_mixing_data.py \
        --domain uploads/training_text/MVS_Openframe_7.1/corpus.txt

    # 비율 조정
    python scripts/training/prepare_mixing_data.py \
        --domain uploads/training_text/MVS_Openframe_7.1/corpus.txt \
        --domain-ratio 0.5 --japanese-ratio 0.25 --code-ratio 0.15 --math-ratio 0.10

    # 오프라인 모드 (캐시된 데이터만 사용)
    python scripts/training/prepare_mixing_data.py \
        --domain uploads/training_text/MVS_Openframe_7.1/corpus.txt --offline

Requirements:
    pip install datasets tiktoken
"""

import os
import sys
import json
import random
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class MixingConfig:
    """데이터 믹싱 설정"""

    # 비율 (합계 = 1.0)
    domain_ratio: float = 0.40
    japanese_ratio: float = 0.30
    code_ratio: float = 0.20
    math_ratio: float = 0.10

    # 도메인 corpus 경로 (복수 가능)
    domain_paths: List[str] = field(default_factory=lambda: [
        "uploads/training_text/MVS_Openframe_7.1/corpus.txt",
    ])

    # HuggingFace dataset IDs
    japanese_dataset: str = "izumi-lab/wikinews-ja-all"
    code_dataset: str = "bigcode/starcoderdata"
    math_dataset: str = "openai/gsm8k"

    # 경로
    cache_dir: str = "uploads/training_text/mixing_cache"
    output_path: str = "uploads/training_text/mixed_corpus.txt"

    # 제한
    max_domain_chars: int = 0  # 0 = 전체 사용
    seed: int = 42
    offline: bool = False


def _estimate_tokens(text: str) -> int:
    """대략적 토큰 수 추정 (일본어: ~0.5 char/token, 영어: ~4 char/token)"""
    ja_chars = sum(1 for c in text if ord(c) > 0x3000)
    en_chars = len(text) - ja_chars
    return int(ja_chars * 2 + en_chars / 4)


class DatasetDownloader:
    """HuggingFace 데이터셋 다운로드 및 캐싱"""

    def __init__(self, config: MixingConfig):
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_japanese_texts(self, target_chars: int) -> str:
        """일반 일본어 텍스트 확보"""
        cache_file = self.cache_dir / "japanese.txt"

        if cache_file.exists():
            logger.info(f"일본어 캐시 로드: {cache_file}")
            text = cache_file.read_text(encoding="utf-8")
            if len(text) >= target_chars:
                return text[:target_chars]

        if self.config.offline:
            if cache_file.exists():
                return cache_file.read_text(encoding="utf-8")[:target_chars]
            logger.warning("오프라인 모드: 일본어 캐시 없음, 도메인 데이터 반복 사용")
            return ""

        logger.info(f"일본어 데이터 다운로드: {self.config.japanese_dataset}")
        try:
            from datasets import load_dataset

            ds = load_dataset(
                self.config.japanese_dataset,
                split="train",
                trust_remote_code=True,
            )

            texts = []
            total_chars = 0
            text_field = "text" if "text" in ds.column_names else ds.column_names[0]

            for item in ds:
                t = item[text_field]
                if t and len(t) > 50:
                    texts.append(t)
                    total_chars += len(t)
                    if total_chars >= target_chars * 1.2:
                        break

            result = "\n\n".join(texts)
            cache_file.write_text(result, encoding="utf-8")
            logger.info(f"일본어 데이터 캐시 저장: {len(result):,} chars")
            return result[:target_chars]
        except Exception as e:
            logger.error(f"일본어 데이터 다운로드 실패: {e}")
            return ""

    def get_code_texts(self, target_chars: int) -> str:
        """코드 텍스트 확보"""
        cache_file = self.cache_dir / "code.txt"

        if cache_file.exists():
            logger.info(f"코드 캐시 로드: {cache_file}")
            text = cache_file.read_text(encoding="utf-8")
            if len(text) >= target_chars:
                return text[:target_chars]

        if self.config.offline:
            if cache_file.exists():
                return cache_file.read_text(encoding="utf-8")[:target_chars]
            # JCL 샘플을 로컬에서 생성
            return self._generate_jcl_samples(target_chars)

        logger.info(f"코드 데이터 다운로드: {self.config.code_dataset}")
        try:
            from datasets import load_dataset

            ds = load_dataset(
                self.config.code_dataset,
                data_dir="python",
                split="train",
                streaming=True,
                trust_remote_code=True,
            )

            texts = []
            total_chars = 0
            for item in ds:
                t = item.get("content", "")
                if t and 100 < len(t) < 10000:
                    texts.append(t)
                    total_chars += len(t)
                    if total_chars >= target_chars * 1.2:
                        break

            result = "\n\n".join(texts)
            cache_file.write_text(result, encoding="utf-8")
            logger.info(f"코드 데이터 캐시 저장: {len(result):,} chars")
            return result[:target_chars]
        except Exception as e:
            logger.error(f"코드 데이터 다운로드 실패: {e}")
            return self._generate_jcl_samples(target_chars)

    def get_math_texts(self, target_chars: int) -> str:
        """수학/추론 텍스트 확보"""
        cache_file = self.cache_dir / "math.txt"

        if cache_file.exists():
            logger.info(f"수학 캐시 로드: {cache_file}")
            text = cache_file.read_text(encoding="utf-8")
            if len(text) >= target_chars:
                return text[:target_chars]

        if self.config.offline:
            if cache_file.exists():
                return cache_file.read_text(encoding="utf-8")[:target_chars]
            logger.warning("오프라인 모드: 수학 캐시 없음")
            return ""

        logger.info(f"수학 데이터 다운로드: {self.config.math_dataset}")
        try:
            from datasets import load_dataset

            ds = load_dataset(self.config.math_dataset, "main", split="train")

            texts = []
            total_chars = 0
            for item in ds:
                q = item.get("question", "")
                a = item.get("answer", "")
                if q and a:
                    entry = f"Question: {q}\nAnswer: {a}"
                    texts.append(entry)
                    total_chars += len(entry)
                    if total_chars >= target_chars * 1.2:
                        break

            result = "\n\n".join(texts)
            cache_file.write_text(result, encoding="utf-8")
            logger.info(f"수학 데이터 캐시 저장: {len(result):,} chars")
            return result[:target_chars]
        except Exception as e:
            logger.error(f"수학 데이터 다운로드 실패: {e}")
            return ""

    def _generate_jcl_samples(self, target_chars: int) -> str:
        """오프라인용 JCL/Shell 코드 샘플 생성"""
        samples = [
            "//MYJOB   JOB (ACCT),'SAMPLE JOB',CLASS=A,MSGCLASS=X\n"
            "//STEP1   EXEC PGM=IEBGENER\n"
            "//SYSUT1  DD DSN=INPUT.DATA,DISP=SHR\n"
            "//SYSUT2  DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG),\n"
            "//        SPACE=(CYL,(10,5)),DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)\n"
            "//SYSIN   DD DUMMY\n"
            "//SYSPRINT DD SYSOUT=*",

            "//SORTJOB JOB (ACCT),'SORT EXAMPLE'\n"
            "//SORT    EXEC PGM=SORT\n"
            "//SORTIN  DD DSN=UNSORTED.DATA,DISP=SHR\n"
            "//SORTOUT DD DSN=SORTED.DATA,DISP=(NEW,CATLG),\n"
            "//        SPACE=(TRK,(100,50))\n"
            "//SYSIN   DD *\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "  INCLUDE COND=(11,5,CH,EQ,C'ACTIV')\n"
            "/*",

            "#!/bin/bash\n"
            "# OpenFrame boot sequence\n"
            "tmboot -y\n"
            "ofboot\n"
            "jesinit\n"
            "echo 'OpenFrame started successfully'",

            "# TSAM dataset allocation\n"
            "idcams DEFINE CLUSTER -\n"
            "  (NAME(MY.KSDS.DATA) -\n"
            "   KEYS(10 0) -\n"
            "   RECORDSIZE(100 200) -\n"
            "   CYLINDERS(10 5))",

            "//COPYLIB JOB (ACCT),'COPY PDS MEMBERS'\n"
            "//COPY    EXEC PGM=IEBCOPY\n"
            "//SYSUT1  DD DSN=SOURCE.PDS,DISP=SHR\n"
            "//SYSUT2  DD DSN=TARGET.PDS,DISP=SHR\n"
            "//SYSIN   DD *\n"
            "  COPY OUTDD=SYSUT2,INDD=SYSUT1\n"
            "  SELECT MEMBER=(MEM1,MEM2,MEM3)\n"
            "/*",
        ]

        result = []
        total = 0
        while total < target_chars:
            for s in samples:
                result.append(s)
                total += len(s)
                if total >= target_chars:
                    break
        return "\n\n".join(result)[:target_chars]


class CorpusMixer:
    """도메인 + 일반 데이터 믹싱"""

    def __init__(self, config: MixingConfig):
        self.config = config
        self.downloader = DatasetDownloader(config)
        random.seed(config.seed)

    def load_domain_corpus(self) -> str:
        """도메인 corpus 로드"""
        texts = []
        for path_str in self.config.domain_paths:
            p = Path(path_str)
            if not p.exists():
                logger.warning(f"도메인 corpus 없음: {p}")
                continue
            text = p.read_text(encoding="utf-8")
            texts.append(text)
            logger.info(f"도메인 corpus 로드: {p} ({len(text):,} chars)")

        combined = "\n\n".join(texts)
        if self.config.max_domain_chars > 0:
            combined = combined[: self.config.max_domain_chars]
        return combined

    def mix(self) -> Dict[str, Any]:
        """데이터 믹싱 수행"""
        # 1. 도메인 데이터 로드
        domain_text = self.load_domain_corpus()
        if not domain_text:
            raise FileNotFoundError(
                "도메인 corpus가 없습니다. "
                "먼저 extract_plain_text.py를 실행하세요:\n"
                '  python scripts/training/extract_plain_text.py '
                '-i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --merge'
            )

        domain_chars = len(domain_text)
        logger.info(f"도메인 데이터: {domain_chars:,} chars")

        # 2. 비율 기반으로 각 소스의 목표 문자 수 계산
        # 도메인 데이터를 기준으로 전체 크기 역산
        total_target = int(domain_chars / self.config.domain_ratio)

        targets = {
            "japanese": int(total_target * self.config.japanese_ratio),
            "code": int(total_target * self.config.code_ratio),
            "math": int(total_target * self.config.math_ratio),
        }

        logger.info(f"목표 총량: {total_target:,} chars")
        for k, v in targets.items():
            logger.info(f"  {k}: {v:,} chars ({getattr(self.config, f'{k}_ratio', 0):.0%})")

        # 3. 각 소스 데이터 확보
        japanese_text = self.downloader.get_japanese_texts(targets["japanese"])
        code_text = self.downloader.get_code_texts(targets["code"])
        math_text = self.downloader.get_math_texts(targets["math"])

        # 4. 믹싱 (블록 단위로 인터리브)
        sources = {
            "domain": domain_text,
            "japanese": japanese_text,
            "code": code_text,
            "math": math_text,
        }

        # 각 소스를 청크 단위로 분할
        chunk_size = 5000  # ~5KB 청크
        chunks = []
        for name, text in sources.items():
            if not text:
                continue
            for i in range(0, len(text), chunk_size):
                chunk = text[i: i + chunk_size]
                if len(chunk) > 100:
                    chunks.append((name, chunk))

        # 셔플
        random.shuffle(chunks)

        # 5. 합본 생성
        mixed_parts = []
        for _, chunk in chunks:
            mixed_parts.append(chunk)

        mixed_text = "\n\n".join(mixed_parts)

        # 통계
        actual_stats = {}
        for name, text in sources.items():
            actual_stats[name] = {
                "chars": len(text),
                "ratio": len(text) / len(mixed_text) if mixed_text else 0,
                "estimated_tokens": _estimate_tokens(text),
            }

        stats = {
            "total_chars": len(mixed_text),
            "total_estimated_tokens": _estimate_tokens(mixed_text),
            "sources": actual_stats,
            "config": {
                "domain_ratio": self.config.domain_ratio,
                "japanese_ratio": self.config.japanese_ratio,
                "code_ratio": self.config.code_ratio,
                "math_ratio": self.config.math_ratio,
                "seed": self.config.seed,
            },
            "mixed_at": datetime.now().isoformat(),
        }

        return {"text": mixed_text, "stats": stats}

    def save(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """믹싱 결과 저장"""
        out = Path(output_path or self.config.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        result = self.mix()

        # 텍스트 저장
        out.write_text(result["text"], encoding="utf-8")
        logger.info(f"Mixed corpus 저장: {out} ({len(result['text']):,} chars)")

        # 통계 저장
        stats_path = out.with_suffix(".stats.json")
        stats_path.write_text(
            json.dumps(result["stats"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"통계 저장: {stats_path}")

        return result["stats"]


def main():
    parser = argparse.ArgumentParser(
        description="CPT 데이터 믹싱 - Catastrophic Forgetting 방지",
    )
    parser.add_argument(
        "--domain", "-d",
        nargs="+",
        default=["uploads/training_text/MVS_Openframe_7.1/corpus.txt"],
        help="도메인 corpus 파일 경로 (복수 가능)",
    )
    parser.add_argument(
        "--output", "-o",
        default="uploads/training_text/mixed_corpus.txt",
        help="출력 파일 경로",
    )
    parser.add_argument("--domain-ratio", type=float, default=0.40)
    parser.add_argument("--japanese-ratio", type=float, default=0.30)
    parser.add_argument("--code-ratio", type=float, default=0.20)
    parser.add_argument("--math-ratio", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="오프라인 모드 (캐시된 데이터만 사용)",
    )
    parser.add_argument(
        "--cache-dir",
        default="uploads/training_text/mixing_cache",
        help="데이터 캐시 디렉토리",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="드라이런 (데이터 확인만, 저장 안 함)",
    )

    args = parser.parse_args()

    # 비율 합계 검증
    total_ratio = args.domain_ratio + args.japanese_ratio + args.code_ratio + args.math_ratio
    if abs(total_ratio - 1.0) > 0.01:
        logger.error(f"비율 합계가 1.0이 아닙니다: {total_ratio:.2f}")
        sys.exit(1)

    config = MixingConfig(
        domain_ratio=args.domain_ratio,
        japanese_ratio=args.japanese_ratio,
        code_ratio=args.code_ratio,
        math_ratio=args.math_ratio,
        domain_paths=args.domain,
        output_path=args.output,
        cache_dir=args.cache_dir,
        seed=args.seed,
        offline=args.offline,
    )

    mixer = CorpusMixer(config)

    if args.dry_run:
        domain = mixer.load_domain_corpus()
        total_target = int(len(domain) / config.domain_ratio)
        print(f"\n=== Dry Run ===")
        print(f"도메인 corpus: {len(domain):,} chars")
        print(f"목표 총량: {total_target:,} chars")
        print(f"  일본어: {int(total_target * config.japanese_ratio):,} chars")
        print(f"  코드: {int(total_target * config.code_ratio):,} chars")
        print(f"  수학: {int(total_target * config.math_ratio):,} chars")
        print(f"추정 토큰: ~{_estimate_tokens(domain) / config.domain_ratio:,.0f}")
        return

    stats = mixer.save(args.output)

    print(f"\n=== Mixing Complete ===")
    print(f"Total: {stats['total_chars']:,} chars (~{stats['total_estimated_tokens']:,} tokens)")
    for name, info in stats["sources"].items():
        print(f"  {name}: {info['chars']:,} chars ({info['ratio']:.1%})")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
