"""
Pattern F: Parallel Analysis Team

3개 관점(리스크, 실현가능성, 컴포넌트)에서 동시 분석 후 결과 병합.
VLLMAdapter 직접 사용 (AgentExecutor/Ollama 우회).
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, AsyncGenerator

from ...models.enhancement import (
    AIAnalysisResult,
    EnhancementType,
    EnhancementPriority,
    ComplexityLevel,
)
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)

# 관점별 시스템 프롬프트
RISK_PROMPT = """You are a Risk & Security Analyst. Analyze the enhancement request focusing on:
1. Security risks and vulnerabilities
2. Potential system instability
3. Data integrity concerns
4. Performance bottlenecks
5. Backward compatibility issues

Respond with ONLY a JSON object:
{
    "potential_risks": ["risk1", "risk2"],
    "security_considerations": ["consideration1"],
    "priority_recommendation": "critical|high|medium|low",
    "estimated_complexity": "low|medium|high|very_high"
}"""

FEASIBILITY_PROMPT = """You are a Feasibility Analyst. Analyze the enhancement request focusing on:
1. Technical feasibility
2. Resource requirements
3. Dependencies on external systems
4. Implementation timeline estimation
5. Alternative approaches

Respond with ONLY a JSON object:
{
    "feasibility_score": 0.0-1.0,
    "recommended_approach": "description",
    "dependencies": ["dep1", "dep2"],
    "estimated_complexity": "low|medium|high|very_high",
    "questions_for_submitter": ["question1"]
}"""

COMPONENT_PROMPT = """You are a System Component Analyst. Analyze the enhancement request focusing on:
1. Which system components are affected
2. Required API changes
3. Database schema impacts
4. Frontend/Backend separation of concerns
5. Integration points

Respond with ONLY a JSON object:
{
    "affected_components": ["component1", "component2"],
    "type_classification": "feature|bug_fix|improvement|refactor|documentation|security|performance",
    "summary": "comprehensive summary of the enhancement",
    "api_impacts": ["impact1"],
    "database_impacts": ["impact1"]
}"""


class ParallelAnalysisTeam:
    """
    3개 관점 병렬 분석 팀.

    VLLMAdapter.generate()로 3개 프롬프트를 동시 실행하고 결과를 병합합니다.
    """

    def __init__(self, max_parallel: int = 3):
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def analyze(
        self,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
    ) -> AIAnalysisResult:
        """3개 관점 병렬 분석 실행"""
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if adapter is None:
            logger.warning("VLLMAdapter not available, returning default analysis")
            return self._create_default(title)

        # 공통 컨텍스트 구성
        context = f"## Title\n{title}\n\n## Description\n{description}"
        if attachments_text:
            context += f"\n\n## Attachments\n{attachments_text}"

        # 3개 관점 병렬 실행
        try:
            risk_task = self._run_perspective(
                adapter, "Risk Analysis", RISK_PROMPT, context
            )
            feasibility_task = self._run_perspective(
                adapter, "Feasibility Analysis", FEASIBILITY_PROMPT, context
            )
            component_task = self._run_perspective(
                adapter, "Component Analysis", COMPONENT_PROMPT, context
            )

            results = await asyncio.gather(
                risk_task, feasibility_task, component_task,
                return_exceptions=True,
            )

            risk_data = results[0] if not isinstance(results[0], Exception) else {}
            feasibility_data = results[1] if not isinstance(results[1], Exception) else {}
            component_data = results[2] if not isinstance(results[2], Exception) else {}

            # 결과 병합
            return self._merge_results(
                title, risk_data, feasibility_data, component_data
            )

        except Exception as e:
            logger.error(f"Parallel analysis failed: {e}")
            return self._create_default(title)

    async def stream_analyze(
        self,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE 이벤트를 yield하며 분석 실행"""
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if adapter is None:
            yield {"event": "error", "data": {"message": "VLLMAdapter not available"}}
            return

        context = f"## Title\n{title}\n\n## Description\n{description}"
        if attachments_text:
            context += f"\n\n## Attachments\n{attachments_text}"

        yield {
            "event": "team_analysis_started",
            "data": {"perspectives": ["risk", "feasibility", "component"]},
        }

        # 3개 관점 병렬 실행
        perspectives = {
            "risk": (RISK_PROMPT, None),
            "feasibility": (FEASIBILITY_PROMPT, None),
            "component": (COMPONENT_PROMPT, None),
        }

        async def run_and_track(name: str, prompt: str):
            result = await self._run_perspective(adapter, name, prompt, context)
            return name, result

        tasks = [
            run_and_track("risk", RISK_PROMPT),
            run_and_track("feasibility", FEASIBILITY_PROMPT),
            run_and_track("component", COMPONENT_PROMPT),
        ]

        completed_results = {}
        for coro in asyncio.as_completed(tasks):
            try:
                name, result = await coro
                completed_results[name] = result
                yield {
                    "event": "perspective_complete",
                    "data": {"perspective": name, "success": bool(result)},
                }
            except Exception as e:
                logger.error(f"Perspective failed: {e}")
                yield {
                    "event": "perspective_error",
                    "data": {"error": str(e)},
                }

        # 결과 병합
        analysis = self._merge_results(
            title,
            completed_results.get("risk", {}),
            completed_results.get("feasibility", {}),
            completed_results.get("component", {}),
        )

        yield {
            "event": "team_analysis_complete",
            "data": analysis.model_dump(mode="json"),
        }

    async def _run_perspective(
        self,
        adapter: Any,
        name: str,
        system_prompt: str,
        context: str,
    ) -> Dict[str, Any]:
        """세마포어로 보호된 단일 관점 실행"""
        async with self._semaphore:
            try:
                question = f"{system_prompt}\n\nAnalyze the following enhancement request:\n{context}"
                response = await adapter.generate(
                    question=question,
                    max_new_tokens=1024,
                    temperature=0.3,
                )
                return self._extract_json(response) or {}
            except Exception as e:
                logger.error(f"Perspective '{name}' failed: {e}")
                return {}

    def _merge_results(
        self,
        title: str,
        risk_data: Dict[str, Any],
        feasibility_data: Dict[str, Any],
        component_data: Dict[str, Any],
    ) -> AIAnalysisResult:
        """3개 관점 결과를 AIAnalysisResult로 병합"""
        # affected_components: component 관점 우선, risk에서 보충
        affected = list(set(
            component_data.get("affected_components", [])
            + risk_data.get("security_considerations", [])
        ))

        # potential_risks: risk 관점
        risks = risk_data.get("potential_risks", [])

        # dependencies: feasibility 관점
        deps = feasibility_data.get("dependencies", [])

        # feasibility_score: feasibility 관점
        feas_score = feasibility_data.get("feasibility_score", 0.7)
        if isinstance(feas_score, str):
            try:
                feas_score = float(feas_score)
            except (ValueError, TypeError):
                feas_score = 0.7
        feas_score = max(0.0, min(1.0, feas_score))

        # priority: risk 관점 우선 (리스크 기반 우선순위가 더 보수적)
        priority = self._parse_priority(
            risk_data.get("priority_recommendation")
        )

        # type: component 관점
        type_cls = self._parse_type(
            component_data.get("type_classification")
        )

        # complexity: max(risk, feasibility) — 보수적 추정
        complexity_risk = self._parse_complexity(
            risk_data.get("estimated_complexity")
        )
        complexity_feas = self._parse_complexity(
            feasibility_data.get("estimated_complexity")
        )
        complexity = max(
            complexity_risk, complexity_feas,
            key=lambda c: ["low", "medium", "high", "very_high"].index(c.value)
        )

        # summary: component 관점
        summary = component_data.get("summary", f"Analysis of: {title}")

        # recommended_approach: feasibility 관점
        approach = feasibility_data.get("recommended_approach", "")

        # questions: feasibility 관점
        questions = feasibility_data.get("questions_for_submitter", [])

        return AIAnalysisResult(
            summary=summary if summary else f"Analysis of: {title}",
            type_classification=type_cls,
            priority_recommendation=priority,
            affected_components=affected if affected else ["Analysis pending"],
            potential_risks=risks,
            dependencies=deps,
            estimated_complexity=complexity,
            feasibility_score=feas_score,
            recommended_approach=approach if approach else "See analysis details",
            questions_for_submitter=questions,
            analyzed_at=datetime.now(timezone.utc),
            agent_id="enhancement_teams.parallel_analysis",
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """텍스트에서 JSON 객체 추출"""
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _parse_type(self, val: Optional[str]) -> EnhancementType:
        if val:
            try:
                return EnhancementType(val.lower())
            except ValueError:
                pass
        return EnhancementType.IMPROVEMENT

    def _parse_priority(self, val: Optional[str]) -> EnhancementPriority:
        if val:
            try:
                return EnhancementPriority(val.lower())
            except ValueError:
                pass
        return EnhancementPriority.MEDIUM

    def _parse_complexity(self, val: Optional[str]) -> ComplexityLevel:
        if val:
            try:
                return ComplexityLevel(val.lower())
            except ValueError:
                pass
        return ComplexityLevel.MEDIUM

    def _create_default(self, title: str) -> AIAnalysisResult:
        return AIAnalysisResult(
            summary=f"Analysis of: {title}",
            type_classification=EnhancementType.IMPROVEMENT,
            priority_recommendation=EnhancementPriority.MEDIUM,
            affected_components=["Analysis pending - VLLMAdapter unavailable"],
            feasibility_score=0.5,
            recommended_approach="Retry when vLLM service is available",
            analyzed_at=datetime.now(timezone.utc),
            agent_id="enhancement_teams.parallel_analysis",
        )
