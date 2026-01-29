"""
Hallucination Detection for OpenCode Agent

Implements the hallucination auto-detection rules from the specification:
1. Statement without document + page reference
2. Use of words not present in verified sources
3. Generalization beyond document scope
4. Conflicting information between documents
5. Tool not used despite required content type
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

from .types import HallucinationCheckResult, OpenCodeContext, ToolType

logger = logging.getLogger(__name__)


class HallucinationDetector:
    """
    Detects hallucinations in generated answers.

    Detection strategies:
    1. Source Citation Check - Every claim should have [Source: doc, Page: X]
    2. Keyword Grounding - Query keywords should appear in answer or cited sources
    3. Entity Consistency - Entities mentioned should match retrieved documents
    4. Product Cross-contamination - TJES info shouldn't appear in TACF answer
    5. Tool Usage Validation - Vision tool should be used for visual content
    """

    # OpenFrame products for cross-contamination detection
    OPENFRAME_PRODUCTS = {
        "TJES", "TACF", "OSC", "OSI", "HiDB", "NDB",
        "Tibero", "Tmax", "WebT", "OFManager", "OFCOBOL",
    }

    # Citation pattern: [Source: doc_name, Page: X] or similar variations
    CITATION_PATTERNS = [
        r"\[Source:\s*([^,\]]+),?\s*Page:\s*(\d+)[^\]]*\]",  # [Source: doc, Page: X]
        r"\[출처:\s*([^,\]]+),?\s*페이지:\s*(\d+)[^\]]*\]",  # Korean
        r"\[参照:\s*([^,\]]+),?\s*ページ:\s*(\d+)[^\]]*\]",  # Japanese
        r"📎\s*([^(\n]+)\s*\(p\.(\d+)\)",                    # 📎 doc (p.X)
    ]

    def __init__(
        self,
        hallucination_threshold: float = 0.6,
        min_keyword_match_ratio: float = 0.3,
        require_citations: bool = True,
    ):
        self.hallucination_threshold = hallucination_threshold
        self.min_keyword_match_ratio = min_keyword_match_ratio
        self.require_citations = require_citations

    async def check(
        self,
        generated_answer: str,
        context: OpenCodeContext,
    ) -> HallucinationCheckResult:
        """
        Check if generated answer contains hallucinations.

        Args:
            generated_answer: The LLM-generated answer to validate
            context: OpenCode execution context with keywords and sources

        Returns:
            HallucinationCheckResult with detection details
        """
        if not generated_answer or not generated_answer.strip():
            return HallucinationCheckResult(
                is_hallucination=True,
                confidence=1.0,
                reasons=["Empty answer generated"],
                retry_recommended=True,
            )

        issues = []
        ungrounded_claims = []
        confidence_scores = []

        # Rule 1: Citation check
        citation_result = self._check_citations(generated_answer, context)
        if citation_result["has_issues"]:
            issues.extend(citation_result["issues"])
            ungrounded_claims.extend(citation_result["ungrounded"])
            confidence_scores.append(citation_result["confidence"])

        # Rule 2: Keyword grounding check
        keyword_result = self._check_keyword_grounding(generated_answer, context)
        if keyword_result["has_issues"]:
            issues.extend(keyword_result["issues"])
            confidence_scores.append(keyword_result["confidence"])

        # Rule 3: Product cross-contamination check
        contamination_result = self._check_product_contamination(generated_answer, context)
        if contamination_result["has_issues"]:
            issues.extend(contamination_result["issues"])
            confidence_scores.append(contamination_result["confidence"])

        # Rule 4: Tool usage validation
        tool_result = self._check_tool_usage(context)
        if tool_result["has_issues"]:
            issues.extend(tool_result["issues"])
            confidence_scores.append(tool_result["confidence"])

        # Rule 5: Content grounding (sentences trace to sources)
        grounding_result = self._check_content_grounding(generated_answer, context)
        if grounding_result["has_issues"]:
            issues.extend(grounding_result["issues"])
            ungrounded_claims.extend(grounding_result["ungrounded"])
            confidence_scores.append(grounding_result["confidence"])

        # Calculate overall confidence
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores else 0.0
        )

        is_hallucination = overall_confidence >= self.hallucination_threshold

        return HallucinationCheckResult(
            is_hallucination=is_hallucination,
            confidence=overall_confidence,
            reasons=issues,
            ungrounded_claims=ungrounded_claims[:5],  # Limit to top 5
            retry_recommended=is_hallucination and context.retry_count < context.config.max_retries,
        )

    def _check_citations(
        self,
        answer: str,
        context: OpenCodeContext
    ) -> Dict[str, Any]:
        """Check if answer has proper source citations"""
        if not self.require_citations:
            return {"has_issues": False, "issues": [], "ungrounded": [], "confidence": 0.0}

        # Find all citations in the answer
        citations = []
        for pattern in self.CITATION_PATTERNS:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            citations.extend(matches)

        # Get verified document names from context
        verified_docs = set()
        for pdf in context.pdf_verifications:
            verified_docs.add(pdf.document_name.lower())

        issues = []
        ungrounded = []

        # Check if answer has any citations
        if not citations:
            # Count substantive sentences (excluding headers, questions, etc.)
            sentences = [s.strip() for s in re.split(r'[.。!?]', answer) if len(s.strip()) > 20]
            if len(sentences) > 1:
                issues.append("No source citations found in answer")
                ungrounded.append("Answer lacks document references")
                return {
                    "has_issues": True,
                    "issues": issues,
                    "ungrounded": ungrounded,
                    "confidence": 0.8,
                }

        # Validate citations against verified documents
        invalid_citations = []
        for doc, page in citations:
            doc_lower = doc.lower().strip()
            if not any(verified in doc_lower or doc_lower in verified for verified in verified_docs):
                invalid_citations.append(f"{doc} (Page {page})")

        if invalid_citations:
            issues.append(f"Citations reference unverified documents: {', '.join(invalid_citations[:3])}")
            return {
                "has_issues": True,
                "issues": issues,
                "ungrounded": invalid_citations,
                "confidence": 0.7,
            }

        return {"has_issues": False, "issues": [], "ungrounded": [], "confidence": 0.0}

    def _check_keyword_grounding(
        self,
        answer: str,
        context: OpenCodeContext
    ) -> Dict[str, Any]:
        """Check if query keywords appear in answer or sources"""
        if not context.keywords:
            return {"has_issues": False, "issues": [], "confidence": 0.0}

        all_keywords = context.keywords.all_keywords()
        if not all_keywords:
            return {"has_issues": False, "issues": [], "confidence": 0.0}

        answer_lower = answer.lower()

        # Count keywords present in answer
        found_count = sum(1 for kw in all_keywords if kw.lower() in answer_lower)
        match_ratio = found_count / len(all_keywords)

        if match_ratio < self.min_keyword_match_ratio:
            missing = [kw for kw in all_keywords[:5] if kw.lower() not in answer_lower]
            return {
                "has_issues": True,
                "issues": [f"Answer missing query keywords: {', '.join(missing[:3])}"],
                "confidence": 0.5,
            }

        return {"has_issues": False, "issues": [], "confidence": 0.0}

    def _check_product_contamination(
        self,
        answer: str,
        context: OpenCodeContext
    ) -> Dict[str, Any]:
        """Check for cross-contamination between OpenFrame products"""
        if not context.keywords or not context.keywords.product_keywords:
            return {"has_issues": False, "issues": [], "confidence": 0.0}

        query_products = set(kw.upper() for kw in context.keywords.product_keywords)
        if not query_products:
            return {"has_issues": False, "issues": [], "confidence": 0.0}

        answer_upper = answer.upper()

        # Find products mentioned in answer
        mentioned_products = set()
        for product in self.OPENFRAME_PRODUCTS:
            # Use word boundary to avoid partial matches
            if re.search(rf"\b{product}\b", answer_upper):
                mentioned_products.add(product)

        # Check for products not in query
        unexpected_products = mentioned_products - query_products

        if unexpected_products:
            # Allow some related products (e.g., TJES and TACF are related)
            related_pairs = {
                ("TJES", "TACF"), ("OSC", "OSI"), ("TIBERO", "TMAX"),
            }
            truly_unexpected = set()
            for unexpected in unexpected_products:
                is_related = False
                for query_prod in query_products:
                    if (unexpected, query_prod) in related_pairs or (query_prod, unexpected) in related_pairs:
                        is_related = True
                        break
                if not is_related:
                    truly_unexpected.add(unexpected)

            if truly_unexpected:
                return {
                    "has_issues": True,
                    "issues": [
                        f"Answer mentions unrelated products: {', '.join(truly_unexpected)} "
                        f"(query was about {', '.join(query_products)})"
                    ],
                    "confidence": 0.7,
                }

        return {"has_issues": False, "issues": [], "confidence": 0.0}

    def _check_tool_usage(self, context: OpenCodeContext) -> Dict[str, Any]:
        """Check if correct tools were used based on content type"""
        if not context.tool_selection:
            return {"has_issues": False, "issues": [], "confidence": 0.0}

        # Check if Vision was needed but not used
        has_visual_content = any(
            pdf.has_visual_content for pdf in context.pdf_verifications
        )

        if has_visual_content and ToolType.VISION not in context.tool_selection.selected_tools:
            return {
                "has_issues": True,
                "issues": ["Visual content detected but Vision tool was not used"],
                "confidence": 0.6,
            }

        return {"has_issues": False, "issues": [], "confidence": 0.0}

    def _check_content_grounding(
        self,
        answer: str,
        context: OpenCodeContext
    ) -> Dict[str, Any]:
        """Check if answer content is grounded in retrieved sources"""
        # Get all source content
        source_contents = []
        for pdf in context.pdf_verifications:
            for chunk in pdf.verified_chunks:
                content = chunk.get("content", "")
                if content:
                    source_contents.append(content.lower())

        if not source_contents:
            # No sources to validate against
            if len(answer) > 100:
                return {
                    "has_issues": True,
                    "issues": ["Answer generated without verified source content"],
                    "ungrounded": ["Entire answer may be ungrounded"],
                    "confidence": 0.9,
                }
            return {"has_issues": False, "issues": [], "ungrounded": [], "confidence": 0.0}

        # Combine all source content for matching
        combined_sources = " ".join(source_contents)

        # Extract key phrases from answer (simple heuristic)
        # Skip common phrases, questions, and citations
        sentences = re.split(r'[.。!?]', answer)
        ungrounded = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30:
                continue
            if sentence.startswith(("?", "Source:", "출처:", "参照:")):
                continue

            # Extract potential fact claims (sentences with numbers, specific terms)
            if re.search(r'\d+', sentence) or any(p in sentence.upper() for p in self.OPENFRAME_PRODUCTS):
                # Check if key terms from this sentence appear in sources
                words = set(re.findall(r'\b\w{4,}\b', sentence.lower()))
                source_words = set(re.findall(r'\b\w{4,}\b', combined_sources))

                overlap = len(words & source_words)
                if overlap < len(words) * 0.3:  # Less than 30% overlap
                    ungrounded.append(sentence[:100])

        if len(ungrounded) > len(sentences) * 0.3:
            return {
                "has_issues": True,
                "issues": [f"Found {len(ungrounded)} potentially ungrounded claims"],
                "ungrounded": ungrounded[:3],
                "confidence": 0.6,
            }

        return {"has_issues": False, "issues": [], "ungrounded": [], "confidence": 0.0}


# Singleton instance
_hallucination_detector: Optional[HallucinationDetector] = None


def get_hallucination_detector(
    hallucination_threshold: float = 0.6,
    require_citations: bool = True,
) -> HallucinationDetector:
    """Get or create the hallucination detector singleton"""
    global _hallucination_detector
    if _hallucination_detector is None:
        _hallucination_detector = HallucinationDetector(
            hallucination_threshold=hallucination_threshold,
            require_citations=require_citations,
        )
    return _hallucination_detector
