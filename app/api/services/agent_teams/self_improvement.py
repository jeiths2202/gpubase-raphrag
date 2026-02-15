"""
Pattern E: Self-Improvement Learning Team

검증 결과 + 사용자 피드백을 JSONL로 축적.
고품질 레코드를 QLoRA 재학습 데이터로 변환.
부정 피드백에서 anti-pattern 학습.
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_FEEDBACK_DIR = os.path.join("uploads", "feedback")


class SelfImprovementService:
    """
    인터랙션 피드백 수집, 학습 데이터 후보 생성, 품질 분석.
    """

    _instance: Optional["SelfImprovementService"] = None

    def __init__(self, output_dir: Optional[str] = None):
        self._output_dir = Path(output_dir or DEFAULT_FEEDBACK_DIR)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: List[Dict[str, Any]] = []
        self._buffer_limit = 50
        # 중복 감지 (세션 내 query fingerprint)
        self._seen_fingerprints: Set[str] = set()
        self._max_fingerprints = 10000

    # =========================================================================
    # Recording
    # =========================================================================

    def record_interaction(
        self,
        query: str,
        product: str,
        answer: str,
        verification_score: Optional[float] = None,
        user_feedback: Optional[str] = None,
        specialist_answers: Optional[List[Dict]] = None,
        retrieval_source: Optional[str] = None,
        pattern_used: Optional[str] = None,
        hypothesis_label: Optional[str] = None,
        search_score: Optional[float] = None,
        language: Optional[str] = None,
    ) -> bool:
        """
        인터랙션 기록. 중복이면 False 반환.

        Args:
            query: 사용자 질문
            product: 제품 ID
            answer: 생성된 답변
            verification_score: 검증 점수 (0.0~1.0)
            user_feedback: "positive" | "negative" | None
            specialist_answers: 전문가 팀 결과
            retrieval_source: "web_doc" | "pdf_rag" | "domain_specialist"
            pattern_used: 사용된 패턴 이름
            hypothesis_label: Pattern B에서 선택된 가설 라벨
            search_score: 검색 결과 최고 점수
            language: 응답 언어

        Returns:
            True if recorded, False if duplicate
        """
        # 중복 감지
        fingerprint = self._compute_fingerprint(query, product)
        if fingerprint in self._seen_fingerprints:
            return False
        self._seen_fingerprints.add(fingerprint)

        # 메모리 관리
        if len(self._seen_fingerprints) > self._max_fingerprints:
            # 오래된 절반 제거 (set이므로 임의 제거)
            to_remove = list(self._seen_fingerprints)[:self._max_fingerprints // 2]
            for fp in to_remove:
                self._seen_fingerprints.discard(fp)

        record = {
            "timestamp": time.time(),
            "fingerprint": fingerprint,
            "query": query,
            "product": product,
            "answer": answer,
            "answer_length": len(answer),
            "verification_score": verification_score,
            "user_feedback": user_feedback,
            "specialist_answers": specialist_answers,
            "retrieval_source": retrieval_source,
            "pattern_used": pattern_used,
            "hypothesis_label": hypothesis_label,
            "search_score": search_score,
            "language": language,
            # 자동 품질 마커
            "quality_markers": self._extract_quality_markers(answer),
        }
        self._buffer.append(record)

        if len(self._buffer) >= self._buffer_limit:
            self._flush()

        return True

    def record_user_feedback(
        self,
        query: str,
        product: str,
        feedback: str,
        answer: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> bool:
        """
        사용자 피드백 별도 기록.
        기존 interaction에 피드백을 추가하거나 새로 기록.

        Args:
            feedback: "positive" | "negative"
            comment: 사용자 코멘트 (선택)
        """
        record = {
            "timestamp": time.time(),
            "type": "user_feedback",
            "fingerprint": self._compute_fingerprint(query, product),
            "query": query,
            "product": product,
            "answer": answer or "",
            "user_feedback": feedback,
            "user_comment": comment,
        }
        self._buffer.append(record)

        if len(self._buffer) >= self._buffer_limit:
            self._flush()

        return True

    # =========================================================================
    # Training Data Generation
    # =========================================================================

    def generate_training_candidates(
        self,
        min_score: float = 0.7,
        include_negative: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        축적된 피드백에서 QLoRA 학습 후보 생성.

        Returns:
            {
                "positive": [QLoRA format records],
                "negative": [anti-pattern records],
                "stats": {총 레코드, 후보 수, 제품별 분포}
            }
        """
        self._flush()
        positive_candidates = []
        negative_candidates = []
        all_records = []

        feedback_files = sorted(self._output_dir.glob("feedback_*.jsonl"))
        for f in feedback_files:
            try:
                for line in f.read_text(encoding="utf-8").strip().split("\n"):
                    if not line:
                        continue
                    record = json.loads(line)
                    all_records.append(record)

                    if self._is_positive_candidate(record, min_score):
                        positive_candidates.append(
                            self._to_qlora_format(record)
                        )
                    elif include_negative and self._is_negative_candidate(record):
                        negative_candidates.append(
                            self._to_negative_format(record)
                        )
            except Exception as e:
                logger.warning(f"Error reading feedback file {f}: {e}")

        # 통계
        product_dist: Dict[str, int] = {}
        pattern_dist: Dict[str, int] = {}
        for r in all_records:
            pid = r.get("product", "unknown")
            product_dist[pid] = product_dist.get(pid, 0) + 1
            pat = r.get("pattern_used", "none")
            pattern_dist[pat] = pattern_dist.get(pat, 0) + 1

        return {
            "positive": positive_candidates,
            "negative": negative_candidates,
            "stats": {
                "total_records": len(all_records),
                "positive_candidates": len(positive_candidates),
                "negative_candidates": len(negative_candidates),
                "product_distribution": product_dist,
                "pattern_distribution": pattern_dist,
            },
        }

    def export_qlora_dataset(
        self,
        output_path: Optional[str] = None,
        min_score: float = 0.7,
    ) -> str:
        """
        QLoRA 학습용 JSONL 파일 생성.
        scripts/training/convert_to_qlora.py 호환 포맷.

        Returns:
            출력 파일 경로
        """
        candidates = self.generate_training_candidates(min_score=min_score)
        positive = candidates["positive"]

        if not output_path:
            output_path = str(
                self._output_dir / f"qlora_dataset_{int(time.time())}.jsonl"
            )

        with open(output_path, "w", encoding="utf-8") as f:
            for record in positive:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            f"Exported {len(positive)} QLoRA training records to {output_path}"
        )
        return output_path

    # =========================================================================
    # Quality Analysis
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """피드백 통계"""
        feedback_files = list(self._output_dir.glob("feedback_*.jsonl"))
        total_records = 0
        positive_count = 0
        negative_count = 0
        pattern_counts: Dict[str, int] = {}
        product_counts: Dict[str, int] = {}
        avg_verification = 0.0
        verification_count = 0

        for f in feedback_files:
            try:
                for line in f.read_text(encoding="utf-8").strip().split("\n"):
                    if not line:
                        continue
                    record = json.loads(line)
                    total_records += 1

                    fb = record.get("user_feedback")
                    if fb == "positive":
                        positive_count += 1
                    elif fb == "negative":
                        negative_count += 1

                    pat = record.get("pattern_used")
                    if pat:
                        pattern_counts[pat] = pattern_counts.get(pat, 0) + 1

                    pid = record.get("product")
                    if pid:
                        product_counts[pid] = product_counts.get(pid, 0) + 1

                    vs = record.get("verification_score")
                    if vs is not None:
                        avg_verification += vs
                        verification_count += 1
            except Exception:
                pass

        return {
            "total_files": len(feedback_files),
            "total_records": total_records,
            "buffer_size": len(self._buffer),
            "positive_feedback": positive_count,
            "negative_feedback": negative_count,
            "avg_verification_score": (
                round(avg_verification / verification_count, 3)
                if verification_count > 0 else None
            ),
            "pattern_distribution": pattern_counts,
            "product_distribution": product_counts,
        }

    def get_improvement_suggestions(self) -> List[Dict[str, Any]]:
        """
        피드백 분석에서 개선 제안 생성.
        부정 피드백이 많은 제품/패턴 식별.
        """
        suggestions = []
        stats = self.get_stats()

        # 부정 피드백 비율이 높은 제품
        if stats["negative_feedback"] > 5:
            neg_ratio = stats["negative_feedback"] / max(stats["total_records"], 1)
            if neg_ratio > 0.3:
                suggestions.append({
                    "type": "high_negative_ratio",
                    "ratio": round(neg_ratio, 2),
                    "message": (
                        f"부정 피드백 비율 {neg_ratio:.0%}. "
                        "프롬프트 또는 검색 품질 검토 권장."
                    ),
                })

        # 검증 점수가 낮은 경우
        avg = stats.get("avg_verification_score")
        if avg is not None and avg < 0.5:
            suggestions.append({
                "type": "low_verification",
                "avg_score": avg,
                "message": (
                    f"평균 검증 점수 {avg:.2f}. "
                    "검색 결과 품질 또는 LLM 프롬프트 개선 필요."
                ),
            })

        return suggestions

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _compute_fingerprint(self, query: str, product: str) -> str:
        """쿼리+제품 fingerprint (중복 감지용)"""
        content = f"{product}:{query.strip().lower()}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]

    def _extract_quality_markers(self, answer: str) -> Dict[str, Any]:
        """답변의 자동 품질 마커 추출"""
        import re
        return {
            "has_code_block": "```" in answer,
            "has_list": bool(re.search(r'^\s*[-*]\s', answer, re.MULTILINE)),
            "has_error_codes": bool(re.search(r'-\d{4,5}', answer)),
            "has_commands": bool(re.search(r'\b\w+mgr\b', answer)),
            "length": len(answer),
            "line_count": answer.count('\n') + 1,
        }

    def _is_positive_candidate(
        self, record: Dict, min_score: float = 0.7
    ) -> bool:
        """양질 학습 데이터 후보 판별"""
        # 피드백 기반
        if record.get("user_feedback") == "positive":
            return True
        # 검증 점수 기반
        if (record.get("verification_score") or 0) >= min_score:
            return True
        # 검색 점수 + 답변 길이 기반
        if (
            (record.get("search_score") or 0) >= 0.6
            and (record.get("answer_length") or 0) >= 100
            and record.get("user_feedback") != "negative"
        ):
            return True
        return False

    def _is_negative_candidate(self, record: Dict) -> bool:
        """부정 피드백 → anti-pattern 학습 데이터"""
        if record.get("user_feedback") == "negative":
            return True
        if (record.get("verification_score") or 0) < 0.3:
            return True
        return False

    def _to_qlora_format(self, record: Dict) -> Dict[str, Any]:
        """QLoRA SFT 포맷으로 변환 (Alpaca style)"""
        return {
            "instruction": record["query"],
            "input": "",
            "output": record["answer"],
            "product": record.get("product", "unknown"),
            "source": "agent_teams_feedback",
            "verification_score": record.get("verification_score"),
            "pattern_used": record.get("pattern_used"),
            "timestamp": record.get("timestamp"),
        }

    def _to_negative_format(self, record: Dict) -> Dict[str, Any]:
        """DPO 학습용 rejected 예시"""
        return {
            "instruction": record["query"],
            "rejected": record["answer"],
            "product": record.get("product", "unknown"),
            "reason": record.get("user_comment", "negative_feedback"),
            "verification_score": record.get("verification_score"),
        }

    def _flush(self) -> None:
        """버퍼를 디스크에 기록"""
        if not self._buffer:
            return
        filename = f"feedback_{int(time.time())}.jsonl"
        filepath = self._output_dir / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for record in self._buffer:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(
                f"Flushed {len(self._buffer)} feedback records to {filepath}"
            )
        except Exception as e:
            logger.error(f"Failed to flush feedback: {e}")
        self._buffer = []


def get_self_improvement_service() -> SelfImprovementService:
    """싱글톤 팩토리"""
    if SelfImprovementService._instance is None:
        SelfImprovementService._instance = SelfImprovementService()
    return SelfImprovementService._instance
