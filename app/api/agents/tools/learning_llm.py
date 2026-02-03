"""Learning LLM Module

Contains Learning LLM integration for fine-tuned knowledge-based answers.
"""
import logging
from typing import Dict, Any, Optional, List

from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


async def try_learning_llm(
    query: str,
    context: Optional[AgentContext] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fine-tuned Learning LLM으로 답변 시도

    Learning LLM은 Summaries 데이터로 학습되어 에러코드, 명령어,
    용어 관련 질문에 직접 답변할 수 있습니다.

    Returns:
        Dict with 'answer', 'confidence', 'mentioned_codes', 'mentioned_terms'
        or None if LLM is not available
    """
    try:
        from app.api.services.learning_llm_service import get_learning_llm_service

        service = get_learning_llm_service()
        if not service or not service.enabled:
            logger.debug("[LearningLLM] Service not available or disabled")
            return None

        # Check if service is initialized
        if not service._is_initialized or not service._adapter:
            logger.debug("[LearningLLM] Service not initialized")
            return None

        # Build context string from conversation history
        context_str = None
        if context and context.metadata:
            history = context.metadata.get("conversation_history", [])
            if history:
                recent = history[-3:] if len(history) > 3 else history
                context_str = "\n".join([
                    f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                    for msg in recent
                ])

        # Call Learning LLM with confidence scoring
        logger.info(f"[LearningLLM] Generating answer for: {query[:50]}...")
        result = await service._adapter.generate_with_confidence(
            question=query,
            context=context_str,
            max_new_tokens=1024,
            temperature=0.3,
        )

        if not result or not result.answer:
            logger.debug("[LearningLLM] No result or empty answer")
            return None

        logger.info(f"[LearningLLM] Generated: answer_len={len(result.answer)}, confidence={result.confidence:.2f}")

        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "mentioned_codes": result.mentioned_codes,
            "mentioned_terms": result.mentioned_terms,
            "mentioned_commands": result.mentioned_commands,
            "raw_response": result.raw_response,
        }

    except ImportError as e:
        logger.warning(f"[LearningLLM] Import error: {e}")
        return None
    except Exception as e:
        logger.warning(f"[LearningLLM] Exception: {e}")
        return None


async def verify_with_summaries(
    learning_llm_result: Dict[str, Any],
    context: Optional[AgentContext] = None,
) -> Optional[Dict[str, Any]]:
    """
    Summary 데이터로 Learning LLM 답변 검증

    Learning LLM이 생성한 답변에서 언급된 에러코드, 명령어, 용어가
    실제 Summary 데이터에 존재하는지 확인합니다.

    Returns:
        Dict with 'is_valid', 'verification_score', 'source_references'
        or None if verification service is not available
    """
    try:
        from app.api.services.answer_verification_service import (
            get_answer_verification_service
        )

        service = get_answer_verification_service()

        answer = learning_llm_result.get("answer", "")
        mentioned_codes = learning_llm_result.get("mentioned_codes", [])
        mentioned_terms = learning_llm_result.get("mentioned_terms", [])
        mentioned_commands = learning_llm_result.get("mentioned_commands", [])

        result = await service.verify_answer(
            answer=answer,
            mentioned_codes=mentioned_codes,
            mentioned_terms=mentioned_terms,
            mentioned_commands=mentioned_commands,
        )

        return result.to_dict()

    except ImportError as e:
        logger.debug(f"[LearningLLM] Verification service import error: {e}")
        return None
    except Exception as e:
        logger.warning(f"[LearningLLM] Verification error: {e}")
        return None


def build_learning_llm_response(
    learning_llm_result: Dict[str, Any],
    verification_result: Dict[str, Any],
    query: str,
    context: Optional[AgentContext],
    multi_product_results: Optional[List[Dict[str, Any]]],
    create_success_result_fn,
) -> ToolResult:
    """
    검증된 Learning LLM 응답을 ToolResult로 변환

    PDF 페이지 인용과 함께 검증된 답변을 반환합니다.
    """
    answer = learning_llm_result.get("answer", "")
    confidence = learning_llm_result.get("confidence", 0.0)
    verification_score = verification_result.get("verification_score", 0.0)
    source_references = verification_result.get("source_references", [])
    additional_context = verification_result.get("additional_context", "")

    # Build output text
    output_parts = []
    output_parts.append(f"📚 Knowledge Base Answer (Confidence: {confidence:.0%}, Verified: {verification_score:.0%})")
    output_parts.append("")
    output_parts.append(answer)

    # Add verification context
    if additional_context:
        output_parts.append("")
        output_parts.append("📋 Verified Context:")
        output_parts.append(additional_context)

    # Add source references
    if source_references:
        output_parts.append("")
        output_parts.append("📖 Sources:")
        for ref in source_references[:5]:
            ref_type = ref.get("type", "document")
            if ref_type == "error_code":
                output_parts.append(
                    f"  • Error {ref.get('code')}: {ref.get('source_pdf')} "
                    f"(p.{ref.get('page_numbers', ['?'])[0] if ref.get('page_numbers') else '?'})"
                )
            elif ref_type == "command":
                output_parts.append(
                    f"  • Command {ref.get('name')}: {ref.get('source_pdf')} "
                    f"(p.{ref.get('page_numbers', ['?'])[0] if ref.get('page_numbers') else '?'})"
                )
            elif ref_type == "term":
                output_parts.append(
                    f"  • Term {ref.get('name')}: {ref.get('source_pdf')}"
                )

    # Build metadata
    result_metadata = {
        "source": "learning_llm",
        "query": query,
        "confidence": confidence,
        "verification_score": verification_score,
        "verified_codes": verification_result.get("verified_codes", []),
        "verified_terms": verification_result.get("verified_terms", []),
        "verified_commands": verification_result.get("verified_commands", []),
        "unverified_codes": verification_result.get("unverified_codes", []),
        "hallucination_patterns": verification_result.get("hallucination_patterns", []),
        "sources": [
            {
                "source": ref.get("source_pdf", "Learning LLM"),
                "page_number": ref.get("page_numbers", [1])[0] if ref.get("page_numbers") else 1,
                "content": f"{ref.get('type')}: {ref.get('code') or ref.get('name')}",
                "source_type": "verified_knowledge",
            }
            for ref in source_references
        ],
    }

    # Add multi-product results
    if multi_product_results:
        result_metadata["multi_product"] = True
        result_metadata["multi_product_results"] = multi_product_results
        result_metadata["has_platform_differences"] = any(
            mpr.get("has_differences", False) for mpr in multi_product_results
        )
        logger.info(f"[LearningLLM] Added {len(multi_product_results)} multi-product results")

    # Store sources in context
    if context and context.metadata is not None:
        if 'sources' not in context.metadata:
            context.metadata['sources'] = []
        context.metadata['sources'].extend(result_metadata["sources"])

    return create_success_result_fn(
        "\n".join(output_parts),
        metadata=result_metadata
    )
