"""
Query Visual Signal Detector

Detects visual-related signals in user queries to determine
if Vision LLM should be used for processing.

Supports:
- English queries
- Korean (한국어) queries
- Japanese (日本語) queries
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Literal, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported languages"""
    ENGLISH = "en"
    KOREAN = "ko"
    JAPANESE = "ja"
    AUTO = "auto"


@dataclass
class VisualQuerySignals:
    """Result of visual signal detection in a query"""
    is_visual_query: bool
    visual_aspects: List[str]  # ["chart", "diagram", "image", ...]
    confidence: float  # 0.0 - 1.0
    suggested_model: Literal["vision", "text", "code"]
    detected_patterns: List[str] = field(default_factory=list)
    language: str = "auto"


class QueryVisualSignalDetector:
    """
    Detects visual-related signals in queries.

    Detection categories:
    1. Direct visual references (chart, graph, image, diagram)
    2. Visual action verbs (show, display, visualize)
    3. Appearance questions (look, appear, see)
    4. Layout/structure queries (layout, format, design)
    5. Screenshot/capture references

    Usage:
        detector = QueryVisualSignalDetector()
        signals = detector.detect("이 차트의 데이터를 분석해주세요")

        if signals.is_visual_query:
            # Route to Vision LLM
            ...
    """

    # ==================== English Patterns ====================
    VISUAL_PATTERNS_EN = {
        # Direct visual element references
        "visual_elements": [
            r'\b(chart|charts)\b',
            r'\b(graph|graphs)\b',
            r'\b(diagram|diagrams)\b',
            r'\b(figure|figures|fig\.)\b',
            r'\b(image|images|picture|pictures|photo|photos)\b',
            r'\b(illustration|illustrations)\b',
            r'\b(screenshot|screenshots|screen\s*shot|screen\s*capture)\b',
            r'\b(infographic|infographics)\b',
            r'\b(plot|plots)\b',
            r'\b(visualization|visualizations)\b',
        ],
        # Visual action verbs
        "visual_actions": [
            r'\b(show|showing|shows)\s+(me\s+)?(the\s+)?(image|chart|graph|diagram|figure|picture)',
            r'\b(display|displaying|displays)\b',
            r'\b(visualize|visualizing|visualizes)\b',
            r'\b(illustrate|illustrating|illustrates)\b',
            r'\b(depict|depicting|depicts)\b',
            r'\b(draw|drawing|drawn)\b',
            r'\b(render|rendering|renders)\b',
        ],
        # Appearance questions
        "appearance": [
            r'\b(look|looks|looking)\s+like\b',
            r'\b(appear|appears|appearing)\b',
            r'\b(visible|visibility)\b',
            r'\bwhat\s+(does|do)\s+.+\s+look\s+like\b',
            r'\bhow\s+(does|do)\s+.+\s+(look|appear)\b',
            r'\bcan\s+you\s+see\b',
        ],
        # Layout and structure
        "layout": [
            r'\b(layout|layouts)\b',
            r'\b(design|designs)\b',
            r'\b(format|formatting)\b',
            r'\b(structure|structures)\b',
            r'\b(composition|compositions)\b',
            r'\b(arrangement|arrangements)\b',
        ],
        # Data visualization specific
        "data_viz": [
            r'\b(bar\s+chart|bar\s+graph)\b',
            r'\b(line\s+chart|line\s+graph)\b',
            r'\b(pie\s+chart)\b',
            r'\b(scatter\s+plot)\b',
            r'\b(histogram)\b',
            r'\b(heatmap|heat\s+map)\b',
            r'\b(treemap|tree\s+map)\b',
            r'\b(flowchart|flow\s+chart)\b',
            r'\b(org\s*chart|organization\s+chart)\b',
            r'\b(gantt\s+chart)\b',
        ],
        # Table data
        "table": [
            r'\b(table|tables)\s+(data|information|content|values)\b',
            r'\bdata\s+(in\s+)?(the\s+)?table\b',
            r'\b(extract|read|get)\s+.*(from\s+)?(the\s+)?table\b',
            r'\btable\s+(shows?|displays?|contains?)\b',
        ],
    }

    # ==================== Korean Patterns ====================
    VISUAL_PATTERNS_KO = {
        # 시각적 요소 직접 언급
        "visual_elements": [
            r'(차트|챠트)',
            r'(그래프)',
            r'(다이어그램|도식|도표)',
            r'(그림|이미지|사진|화상)',
            r'(도형|도안)',
            r'(스크린샷|화면\s*캡처|화면\s*촬영)',
            r'(인포그래픽)',
            r'(시각화|시각적)',
        ],
        # 시각적 동작
        "visual_actions": [
            r'(보여|보이|봐)',
            r'(표시|표현)',
            r'(시각화)',
            r'(그려|그리|그린)',
            r'(나타내|나타난)',
        ],
        # 외양/모습 질문
        "appearance": [
            r'(어떻게\s*생겼|어떻게\s*보이)',
            r'(모양|형태|외양)',
            r'(모습)',
            r'보이(는|나요|니|냐)',
            r'(뭐가\s*보|무엇이\s*보)',
        ],
        # 레이아웃/구조
        "layout": [
            r'(레이아웃|배치)',
            r'(디자인)',
            r'(포맷|형식)',
            r'(구조|구성)',
        ],
        # 데이터 시각화
        "data_viz": [
            r'(막대\s*그래프|막대\s*차트)',
            r'(선\s*그래프|꺾은선\s*그래프)',
            r'(원\s*그래프|파이\s*차트)',
            r'(산점도)',
            r'(히스토그램)',
            r'(히트맵)',
            r'(플로우\s*차트|순서도)',
            r'(조직도)',
            r'(간트\s*차트)',
        ],
        # 표 데이터
        "table": [
            r'(표|테이블).*(데이터|정보|내용|값)',
            r'표(에서|의|를)',
            r'(추출|읽|가져).*(표|테이블)',
            r'(표|테이블).*(보여|표시|나타)',
        ],
    }

    # ==================== Japanese Patterns ====================
    VISUAL_PATTERNS_JA = {
        "visual_elements": [
            r'(チャート|グラフ)',
            r'(図|図表|図形)',
            r'(画像|写真|イメージ)',
            r'(ダイアグラム)',
            r'(スクリーンショット|画面キャプチャ)',
            r'(可視化|ビジュアライゼーション)',
        ],
        "visual_actions": [
            r'(見せ|表示)',
            r'(描|描画)',
            r'(示し|示す)',
        ],
        "appearance": [
            r'(どう見える|どのように見える)',
            r'(見た目|外観)',
            r'(形状|形)',
        ],
    }

    # ==================== Code-related Patterns ====================
    CODE_PATTERNS = [
        r'\b(implement|write|create|build|develop)\s+(a\s+)?(function|class|method|code|script|program)\b',
        r'\b(code|coding|programming)\b',
        r'\b(python|javascript|typescript|java|c\+\+|rust|go)\s+(code|function|class)\b',
        r'\bdef\s+\w+\s*\(',
        r'\bfunction\s+\w+\s*\(',
        r'\bclass\s+\w+',
        r'(코드|코딩|프로그래밍|함수|클래스)',
        r'(작성|구현|개발).*(코드|함수|클래스)',
    ]

    # Confidence thresholds
    CONFIDENCE_THRESHOLD_HIGH = 0.8
    CONFIDENCE_THRESHOLD_MEDIUM = 0.5
    CONFIDENCE_THRESHOLD_LOW = 0.3

    def __init__(
        self,
        custom_patterns: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize detector.

        Args:
            custom_patterns: Optional custom patterns to add
        """
        self._patterns_en = self._compile_patterns(self.VISUAL_PATTERNS_EN)
        self._patterns_ko = self._compile_patterns(self.VISUAL_PATTERNS_KO)
        self._patterns_ja = self._compile_patterns(self.VISUAL_PATTERNS_JA)
        self._code_patterns = [re.compile(p, re.IGNORECASE) for p in self.CODE_PATTERNS]

        if custom_patterns:
            self._custom_patterns = self._compile_patterns(custom_patterns)
        else:
            self._custom_patterns = {}

    def detect(
        self,
        query: str,
        language: str = "auto",
    ) -> VisualQuerySignals:
        """
        Detect visual signals in a query.

        Args:
            query: User query text
            language: Language hint ("en", "ko", "ja", "auto")

        Returns:
            VisualQuerySignals with detection results
        """
        query_lower = query.lower()

        # Detect language if auto
        if language == "auto":
            language = self._detect_language(query)

        # Check for code-related patterns first
        if self._is_code_query(query_lower):
            return VisualQuerySignals(
                is_visual_query=False,
                visual_aspects=[],
                confidence=0.9,
                suggested_model="code",
                detected_patterns=["code_pattern"],
                language=language,
            )

        # Detect visual patterns
        visual_aspects = []
        detected_patterns = []
        total_confidence = 0.0

        # Select patterns based on language
        patterns = self._get_patterns_for_language(language)

        # Check each category
        for category, compiled_patterns in patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(query_lower):
                    visual_aspects.append(category)
                    detected_patterns.append(pattern.pattern)
                    total_confidence += self._get_category_weight(category)
                    break  # Only count once per category

        # Check custom patterns
        for category, compiled_patterns in self._custom_patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(query_lower):
                    visual_aspects.append(f"custom_{category}")
                    detected_patterns.append(pattern.pattern)
                    total_confidence += 0.15

        # Normalize confidence
        confidence = min(1.0, total_confidence)

        # Determine if it's a visual query
        is_visual = confidence >= self.CONFIDENCE_THRESHOLD_LOW

        # Determine suggested model
        if confidence >= self.CONFIDENCE_THRESHOLD_HIGH:
            suggested_model = "vision"
        elif confidence >= self.CONFIDENCE_THRESHOLD_MEDIUM:
            suggested_model = "vision"
        elif confidence >= self.CONFIDENCE_THRESHOLD_LOW:
            suggested_model = "vision"
        else:
            suggested_model = "text"

        return VisualQuerySignals(
            is_visual_query=is_visual,
            visual_aspects=list(set(visual_aspects)),
            confidence=confidence,
            suggested_model=suggested_model,
            detected_patterns=detected_patterns,
            language=language,
        )

    def _compile_patterns(
        self,
        pattern_dict: Dict[str, List[str]]
    ) -> Dict[str, List[re.Pattern]]:
        """Compile pattern strings to regex objects."""
        compiled = {}
        for category, patterns in pattern_dict.items():
            compiled[category] = [
                re.compile(p, re.IGNORECASE | re.UNICODE)
                for p in patterns
            ]
        return compiled

    def _detect_language(self, text: str) -> str:
        """Detect language from text."""
        # Simple heuristic based on character ranges

        # Korean characters (Hangul)
        korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))

        # Japanese characters (Hiragana, Katakana, Kanji)
        japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]', text))

        # ASCII/Latin characters
        ascii_chars = len(re.findall(r'[a-zA-Z]', text))

        total = korean_chars + japanese_chars + ascii_chars
        if total == 0:
            return "en"  # Default

        if korean_chars / total > 0.3:
            return "ko"
        elif japanese_chars / total > 0.3:
            return "ja"
        else:
            return "en"

    def _get_patterns_for_language(
        self,
        language: str
    ) -> Dict[str, List[re.Pattern]]:
        """Get compiled patterns for a language."""
        if language == "ko":
            # Korean + English (mixed usage common)
            combined = {}
            for cat, patterns in self._patterns_ko.items():
                combined[cat] = patterns.copy()
            for cat, patterns in self._patterns_en.items():
                if cat in combined:
                    combined[cat].extend(patterns)
                else:
                    combined[cat] = patterns.copy()
            return combined
        elif language == "ja":
            # Japanese + English
            combined = {}
            for cat, patterns in self._patterns_ja.items():
                combined[cat] = patterns.copy()
            for cat, patterns in self._patterns_en.items():
                if cat in combined:
                    combined[cat].extend(patterns)
                else:
                    combined[cat] = patterns.copy()
            return combined
        else:
            return self._patterns_en

    def _get_category_weight(self, category: str) -> float:
        """Get confidence weight for a pattern category."""
        weights = {
            "visual_elements": 0.35,
            "data_viz": 0.35,
            "visual_actions": 0.25,
            "table": 0.25,
            "appearance": 0.20,
            "layout": 0.15,
        }
        return weights.get(category, 0.15)

    def _is_code_query(self, query: str) -> bool:
        """Check if query is code-related."""
        for pattern in self._code_patterns:
            if pattern.search(query):
                return True
        return False

    def add_custom_pattern(
        self,
        category: str,
        pattern: str,
    ) -> None:
        """
        Add a custom detection pattern.

        Args:
            category: Pattern category name
            pattern: Regex pattern string
        """
        if category not in self._custom_patterns:
            self._custom_patterns[category] = []

        compiled = re.compile(pattern, re.IGNORECASE | re.UNICODE)
        self._custom_patterns[category].append(compiled)

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages."""
        return ["en", "ko", "ja", "auto"]

    def explain_detection(
        self,
        query: str,
        language: str = "auto"
    ) -> Dict:
        """
        Get detailed explanation of detection.

        Useful for debugging and understanding detection logic.
        """
        signals = self.detect(query, language)

        return {
            "query": query,
            "detected_language": signals.language,
            "is_visual_query": signals.is_visual_query,
            "confidence": signals.confidence,
            "suggested_model": signals.suggested_model,
            "visual_aspects": signals.visual_aspects,
            "matched_patterns": signals.detected_patterns,
            "confidence_breakdown": {
                aspect: self._get_category_weight(aspect)
                for aspect in signals.visual_aspects
            },
        }
