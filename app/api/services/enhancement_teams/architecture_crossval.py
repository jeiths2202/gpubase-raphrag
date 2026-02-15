"""
Pattern G: Architecture Cross-validation

Architect가 설계 → Validator가 분석 결과 대비 교차 검증 → 이슈 시 수정.
VLLMAdapter 직접 사용 (AgentExecutor/Ollama 우회).
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, AsyncGenerator

from ...models.enhancement import (
    AIAnalysisResult,
    ArchitectureProposal,
    DesignDecision,
    FileChange,
    NewFile,
    APIChange,
)
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)

ARCHITECT_PROMPT = """You are a Software Architect. Design an architecture proposal for the enhancement request.

Based on the analysis results provided, create a comprehensive architecture proposal.

Respond with ONLY a JSON object:
{
    "approach": "high-level approach description",
    "design_decisions": [
        {"title": "decision title", "description": "details", "rationale": "why", "alternatives_considered": ["alt1"], "trade_offs": "trade-off description"}
    ],
    "file_changes": [
        {"file_path": "path/to/file.py", "change_type": "modify", "description": "what to change", "estimated_lines": 50}
    ],
    "new_files": [
        {"file_path": "path/to/new_file.py", "purpose": "purpose of the file"}
    ],
    "api_changes": [
        {"endpoint": "/api/endpoint", "method": "POST", "change_type": "add", "description": "description"}
    ],
    "database_changes": ["change description"],
    "security_considerations": ["consideration"],
    "backward_compatible": true,
    "migration_required": false
}"""

VALIDATOR_PROMPT = """You are an Architecture Validator. Review the proposed architecture against the analysis results.

Check for:
1. All affected components from analysis are addressed
2. All identified risks have mitigations in the design
3. Backward compatibility is maintained (or migration plan exists)
4. Security considerations are addressed
5. Design decisions have clear rationale

If there are issues, list them. If the proposal is sound, confirm it.

Respond with ONLY a JSON object:
{
    "is_valid": true|false,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1"],
    "missing_components": ["component that should be addressed"],
    "risk_coverage": "all|partial|none"
}"""

REVISION_PROMPT = """You are a Software Architect. Revise your architecture proposal based on the validator's feedback.

Address all issues identified by the validator. Keep the original structure but fix the problems.

Respond with ONLY a JSON object with the same structure as the original proposal."""


class ArchitectureCrossValidator:
    """
    아키텍처 교차 검증 서비스.

    1. Architect 역할로 초기 설계
    2. Validator 역할로 분석 결과 대비 검증
    3. 이슈 발견 시 1회 수정 (무한 루프 방지)
    """

    async def design_and_validate(
        self,
        title: str,
        description: str,
        analysis: AIAnalysisResult,
    ) -> ArchitectureProposal:
        """설계 + 검증 + (선택적) 수정"""
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if adapter is None:
            logger.warning("VLLMAdapter not available, returning default proposal")
            return self._create_default()

        analysis_context = self._format_analysis(analysis)
        request_context = f"## Title\n{title}\n\n## Description\n{description}"

        # Step 1: Initial architecture design
        architect_input = (
            f"{ARCHITECT_PROMPT}\n\n"
            f"## Enhancement Request\n{request_context}\n\n"
            f"## Analysis Results\n{analysis_context}"
        )
        initial_response = await adapter.generate(
            question=architect_input,
            max_new_tokens=2048,
            temperature=0.3,
        )
        initial_data = self._extract_json(initial_response)
        if not initial_data:
            logger.warning("Failed to parse initial architecture response")
            return self._create_default()

        initial_proposal = self._parse_proposal(initial_data)

        # Step 2: Validate against analysis
        validator_input = (
            f"{VALIDATOR_PROMPT}\n\n"
            f"## Analysis Results\n{analysis_context}\n\n"
            f"## Proposed Architecture\n{json.dumps(initial_data, ensure_ascii=False)}"
        )
        validation_response = await adapter.generate(
            question=validator_input,
            max_new_tokens=1024,
            temperature=0.2,
        )
        validation_data = self._extract_json(validation_response)

        if not validation_data:
            # 검증 파싱 실패 시 초기 설계 반환
            logger.warning("Failed to parse validation response, using initial proposal")
            return initial_proposal

        is_valid = validation_data.get("is_valid", True)
        issues = validation_data.get("issues", [])

        if is_valid or not issues:
            return initial_proposal

        # Step 3: Revise (최대 1회)
        logger.info(f"Architecture validation found {len(issues)} issues, revising")
        revision_input = (
            f"{REVISION_PROMPT}\n\n"
            f"## Original Proposal\n{json.dumps(initial_data, ensure_ascii=False)}\n\n"
            f"## Validator Issues\n{json.dumps(issues, ensure_ascii=False)}\n\n"
            f"## Validator Suggestions\n{json.dumps(validation_data.get('suggestions', []), ensure_ascii=False)}\n\n"
            f"## Analysis Results\n{analysis_context}"
        )
        revised_response = await adapter.generate(
            question=revision_input,
            max_new_tokens=2048,
            temperature=0.3,
        )
        revised_data = self._extract_json(revised_response)

        if revised_data:
            return self._parse_proposal(revised_data)

        # 수정 파싱 실패 시 초기 설계 반환
        return initial_proposal

    async def stream_design_and_validate(
        self,
        title: str,
        description: str,
        analysis: AIAnalysisResult,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE 이벤트를 yield하며 설계+검증 실행"""
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if adapter is None:
            yield {"event": "error", "data": {"message": "VLLMAdapter not available"}}
            return

        analysis_context = self._format_analysis(analysis)
        request_context = f"## Title\n{title}\n\n## Description\n{description}"

        # Step 1: Design
        yield {"event": "crossval_phase", "data": {"phase": "design", "status": "started"}}

        architect_input = (
            f"{ARCHITECT_PROMPT}\n\n"
            f"## Enhancement Request\n{request_context}\n\n"
            f"## Analysis Results\n{analysis_context}"
        )
        initial_response = await adapter.generate(
            question=architect_input,
            max_new_tokens=2048,
            temperature=0.3,
        )
        initial_data = self._extract_json(initial_response)

        if not initial_data:
            yield {"event": "error", "data": {"message": "Failed to parse architecture response"}}
            return

        yield {"event": "crossval_phase", "data": {"phase": "design", "status": "complete"}}

        # Step 2: Validate
        yield {"event": "crossval_phase", "data": {"phase": "validation", "status": "started"}}

        validator_input = (
            f"{VALIDATOR_PROMPT}\n\n"
            f"## Analysis Results\n{analysis_context}\n\n"
            f"## Proposed Architecture\n{json.dumps(initial_data, ensure_ascii=False)}"
        )
        validation_response = await adapter.generate(
            question=validator_input,
            max_new_tokens=1024,
            temperature=0.2,
        )
        validation_data = self._extract_json(validation_response) or {}
        is_valid = validation_data.get("is_valid", True)
        issues = validation_data.get("issues", [])

        yield {
            "event": "crossval_phase",
            "data": {
                "phase": "validation",
                "status": "complete",
                "is_valid": is_valid,
                "issues_count": len(issues),
            },
        }

        # Step 3: Revise if needed
        final_data = initial_data
        if not is_valid and issues:
            yield {"event": "crossval_phase", "data": {"phase": "revision", "status": "started"}}

            revision_input = (
                f"{REVISION_PROMPT}\n\n"
                f"## Original Proposal\n{json.dumps(initial_data, ensure_ascii=False)}\n\n"
                f"## Validator Issues\n{json.dumps(issues, ensure_ascii=False)}\n\n"
                f"## Analysis Results\n{analysis_context}"
            )
            revised_response = await adapter.generate(
                question=revision_input,
                max_new_tokens=2048,
                temperature=0.3,
            )
            revised_data = self._extract_json(revised_response)
            if revised_data:
                final_data = revised_data

            yield {"event": "crossval_phase", "data": {"phase": "revision", "status": "complete"}}

        proposal = self._parse_proposal(final_data)
        yield {
            "event": "crossval_complete",
            "data": proposal.model_dump(mode="json"),
        }

    def _format_analysis(self, analysis: AIAnalysisResult) -> str:
        """분석 결과를 텍스트로 포맷"""
        lines = [
            f"Summary: {analysis.summary}",
            f"Type: {analysis.type_classification.value}",
            f"Priority: {analysis.priority_recommendation.value}",
            f"Complexity: {analysis.estimated_complexity.value}",
            f"Feasibility: {analysis.feasibility_score}",
            f"Affected Components: {', '.join(analysis.affected_components)}",
            f"Risks: {', '.join(analysis.potential_risks)}",
            f"Dependencies: {', '.join(analysis.dependencies)}",
            f"Approach: {analysis.recommended_approach}",
        ]
        return "\n".join(lines)

    def _parse_proposal(self, data: Dict[str, Any]) -> ArchitectureProposal:
        """JSON dict → ArchitectureProposal"""
        design_decisions = []
        for dd in data.get("design_decisions", []):
            if isinstance(dd, dict):
                design_decisions.append(DesignDecision(
                    title=dd.get("title", ""),
                    description=dd.get("description", ""),
                    rationale=dd.get("rationale", ""),
                    alternatives_considered=dd.get("alternatives_considered", []),
                    trade_offs=dd.get("trade_offs", ""),
                ))

        file_changes = []
        for fc in data.get("file_changes", []):
            if isinstance(fc, dict):
                file_changes.append(FileChange(
                    file_path=fc.get("file_path", ""),
                    change_type=fc.get("change_type", "modify"),
                    description=fc.get("description", ""),
                    estimated_lines=fc.get("estimated_lines", 0),
                ))

        new_files = []
        for nf in data.get("new_files", []):
            if isinstance(nf, dict):
                new_files.append(NewFile(
                    file_path=nf.get("file_path", ""),
                    purpose=nf.get("purpose", ""),
                ))

        api_changes = []
        for ac in data.get("api_changes", []):
            if isinstance(ac, dict):
                api_changes.append(APIChange(
                    endpoint=ac.get("endpoint", ""),
                    method=ac.get("method", "GET"),
                    change_type=ac.get("change_type", "add"),
                    description=ac.get("description", ""),
                ))

        return ArchitectureProposal(
            approach=data.get("approach", ""),
            design_decisions=design_decisions,
            file_changes=file_changes,
            new_files=new_files,
            api_changes=api_changes,
            database_changes=data.get("database_changes", []),
            security_considerations=data.get("security_considerations", []),
            backward_compatible=data.get("backward_compatible", True),
            migration_required=data.get("migration_required", False),
            reviewed_at=datetime.now(timezone.utc),
            reviewer_agent_id="enhancement_teams.crossval",
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

    def _create_default(self) -> ArchitectureProposal:
        return ArchitectureProposal(
            approach="Architecture design pending - VLLMAdapter unavailable",
            reviewed_at=datetime.now(timezone.utc),
            reviewer_agent_id="enhancement_teams.crossval",
        )
