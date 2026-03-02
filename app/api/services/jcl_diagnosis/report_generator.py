"""Report Generator Agent

수집된 모든 정보를 종합하여 LLM 기반 진단 리포트를 생성합니다.
SSE llm_token 이벤트로 스트리밍합니다.

LLM: vLLM (Qwen + QLoRA OpenFrame 어댑터)
"""
import logging
from typing import AsyncGenerator, Dict, Optional

from app.api.models.jcl_diagnosis import (
    JobAnalysis, DiagnosisResult, KnowledgeResult,
    DiagnosisEventType, StepStatus
)
from app.api.services.learning_llm_service import get_learning_llm_service

logger = logging.getLogger(__name__)


class ReportGenerator:
    """LLM 기반 진단 리포트 생성 (스트리밍)"""

    SYSTEM_PROMPT = """あなたはOpenFrame TJES バッチジョブ障害診断の専門エンジニアです。
JCL JOBの実行ログを分析し、障害原因と対処方法を提供します。

重要な規則:
- 提供された情報のみに基づいて回答してください
- 推測ではなく、ログから確認できる事実を報告してください
- エラーコードの説明は、提供されたエラーガイドを引用してください
- 対処方法は具体的なステップで提示してください
- 「UNKNOWN」というJOB名は解析失敗を意味します。UNKNOWNについて説明しないでください
- STEP数が0の場合、STEPが存在しないと断言せず、「JCL解析でSTEP情報が取得できませんでした」と報告してください"""

    async def stream_report(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        user_message: Optional[str] = None,
        language: str = "ja",
    ) -> AsyncGenerator[Dict, None]:
        """LLM 리포트를 토큰 단위로 스트리밍

        Yields:
            Dict: {"type": "llm_token", "token": "..."} 형태
        """
        prompt = self._build_prompt(
            job_analysis, diagnosis, knowledge, user_message, language
        )

        # UNKNOWN 가드: JOB 정보가 없으면 폴백 템플릿 사용
        # LLM에 빈 데이터를 전달하면 할루시네이션 발생
        if (job_analysis.job_name == "UNKNOWN"
                and job_analysis.total_steps == 0
                and not diagnosis.primary_error):
            logger.warning(
                "JOB is UNKNOWN with 0 steps and no errors - "
                "using fallback template to prevent hallucination"
            )
            fallback = self._generate_fallback_report(
                job_analysis, diagnosis, knowledge, language
            )
            yield {
                "type": DiagnosisEventType.LLM_TOKEN.value,
                "token": fallback,
            }
            return

        llm_service = get_learning_llm_service()

        try:
            if llm_service and llm_service.is_available:
                # LearningLLMService.generate_stream() 사용
                context = f"{self.SYSTEM_PROMPT}\n\n{prompt}"
                async for token in llm_service.generate_stream(
                    question=prompt,
                    context=self.SYSTEM_PROMPT,
                    max_tokens=2048,
                    temperature=0.3,
                    product="mvs_openframe_7.1",
                ):
                    yield {
                        "type": DiagnosisEventType.LLM_TOKEN.value,
                        "token": token,
                    }
            else:
                # LLM 미사용 시 폴백
                logger.warning("LLM service not available, using fallback report")
                fallback = self._generate_fallback_report(
                    job_analysis, diagnosis, knowledge, language
                )
                yield {
                    "type": DiagnosisEventType.LLM_TOKEN.value,
                    "token": fallback,
                }
        except Exception as e:
            logger.error(f"LLM report generation failed: {e}")
            fallback = self._generate_fallback_report(
                job_analysis, diagnosis, knowledge, language
            )
            yield {
                "type": DiagnosisEventType.LLM_TOKEN.value,
                "token": fallback,
            }

    def _build_prompt(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        user_message: Optional[str],
        language: str,
    ) -> str:
        """LLM 프롬프트 조합"""
        step_summary = self._format_step_flow(job_analysis)

        guides_text = "\n".join([
            f"- {g.code}: {g.description}\n  原因: {g.cause}\n  対処: {g.solution}"
            for g in knowledge.error_guides
        ]) or "エラーガイドなし"

        cases_text = "\n".join([
            f"- {c.title} (類似度: {c.similarity_score:.0%})\n  {c.description[:200]}"
            for c in knowledge.similar_cases[:3]
        ]) or "類似事例なし"

        lang_instruction = {
            "ja": "日本語で回答してください。",
            "ko": "한국어로 답변해 주세요.",
            "en": "Please respond in English.",
        }.get(language, "日本語で回答してください。")

        return f"""{lang_instruction}

## JOB情報
- JOB名: {job_analysis.job_name}
- JOBステータス: {job_analysis.job_status.value}
- STEP数: {job_analysis.total_steps}

## STEP実行フロー
{step_summary}

## エラー診断
- 障害STEP: {diagnosis.failed_step.step_name if diagnosis.failed_step else 'N/A'}
- プログラム: {diagnosis.failed_step.program if diagnosis.failed_step else 'N/A'}
- 主要エラー: {diagnosis.primary_error.code if diagnosis.primary_error else 'N/A'}
- 重大度: {diagnosis.severity.value}
- エラーメッセージ: {diagnosis.primary_error.message_line if diagnosis.primary_error else 'N/A'}

## エラーガイド（参照情報）
{guides_text}

## 類似障害事例
{cases_text}

{f"## ユーザー追加質問: {user_message}" if user_message else ""}

上記情報を基に、以下の構成で障害分析レポートを作成してください:
1. JOB実行サマリー（STEPフローの概要）
2. エラー原因分析（コード・メッセージ・発生箇所）
3. 対処方法（具体的なステップ）
4. 参考資料（エラーガイド・類似事例の引用）
5. 追加確認事項（再発防止・潜在リスク）"""

    def _format_step_flow(self, job: JobAnalysis) -> str:
        """STEP 흐름을 텍스트로 포맷"""
        lines = []
        for s in job.steps:
            icon = {
                StepStatus.NORMAL: "OK",
                StepStatus.WARNING: "WARN",
                StepStatus.ERROR: "ERR",
                StepStatus.ABEND_SYSTEM: "ABEND",
                StepStatus.ABEND_USER: "ABEND",
                StepStatus.SKIPPED: "SKIP",
                StepStatus.NOT_RUN: "---",
            }.get(s.status, "?")
            pgm = s.program or s.procedure or "?"
            rc = s.return_code or s.status.value
            lines.append(f"  STEP{s.step_number}({s.step_name}) PGM={pgm} → [{icon}] {rc}")
        return "\n".join(lines) or "  (STEP情報なし)"

    def _generate_fallback_report(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        language: str,
    ) -> str:
        """LLM 실패 시 템플릿 폴백 리포트"""
        step_flow = self._format_step_flow(job_analysis)
        primary = diagnosis.primary_error

        guides = "\n".join([
            f"- {g.code}: {g.description}"
            for g in knowledge.error_guides
        ]) or "- (参考情報なし)"

        return f"""## JOB実行サマリー
JOB名: {job_analysis.job_name}
STEP数: {job_analysis.total_steps}
{step_flow}

## エラー原因
コード: {primary.code if primary else 'N/A'}
メッセージ: {primary.message_line if primary else 'N/A'}
障害STEP: {diagnosis.failed_step.step_name if diagnosis.failed_step else 'N/A'}
重大度: {diagnosis.severity.value}

## 参考エラーガイド
{guides}

(注: LLM応答が利用できなかったため、テンプレートレポートを表示しています)
"""
