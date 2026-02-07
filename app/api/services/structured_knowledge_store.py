"""
Structured Knowledge Store

파일 시스템 기반 구조화 지식 검색 (LLM 없음).
요약본 파일에서 명령어, 에러코드, 설정, 용어를 검색합니다.
"""
import glob
import json as json_module
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 프로젝트 루트 기준 요약본 경로
SUMMARIES_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "uploads", "summaries",
)


@dataclass
class SearchResult:
    """구조화 검색 결과"""
    title: str
    content: str
    source_file: str
    source_page: str = ""
    relevance_score: float = 0.0
    domain: str = ""  # commands, error_codes, configs, glossary
    product: str = ""  # 검색 출처 Agent (cross-agent 검색 시 사용)


@dataclass
class ProductSearchContext:
    """제품별 검색 결과 컨테이너"""
    product: str = ""
    structured_results: List[SearchResult] = field(default_factory=list)
    vector_results: List[dict] = field(default_factory=list)
    graph_results: List[dict] = field(default_factory=list)

    @property
    def has_results(self) -> bool:
        return bool(self.structured_results or self.vector_results or self.graph_results)


class StructuredKnowledgeStore:
    """
    파일 시스템 기반 구조화 지식 저장소

    특징:
    - LLM 없이 키워드 기반 검색
    - Markdown 파일 파싱, 섹션 단위 검색
    - 메모리 캐시 (로딩 시 1회, 이후 <10ms)
    """

    def __init__(
        self,
        product_id: str,
        summary_paths: Dict[str, List[str]],
    ):
        self.product_id = product_id
        self.summary_paths = summary_paths
        self._cache: Dict[str, List[Dict]] = {}  # domain → parsed sections
        self._loaded = False

    def _ensure_loaded(self):
        """캐시가 로딩되지 않았으면 로딩"""
        if self._loaded:
            return
        for domain, path_patterns in self.summary_paths.items():
            sections = []
            for pattern in path_patterns:
                full_pattern = os.path.join(SUMMARIES_BASE, pattern) if not os.path.isabs(pattern) else pattern
                for filepath in glob.glob(full_pattern):
                    try:
                        if filepath.lower().endswith(".json"):
                            parsed = self._parse_learning_json(filepath, domain)
                        elif filepath.lower().endswith(".pdf"):
                            parsed = self._parse_pdf(filepath, domain)
                        else:
                            parsed = self._parse_markdown(filepath, domain)
                        sections.extend(parsed)
                    except Exception as e:
                        logger.warning(f"Failed to parse {filepath}: {e}")
            self._cache[domain] = sections
        self._loaded = True
        total = sum(len(v) for v in self._cache.values())
        logger.info(f"StructuredKnowledgeStore loaded for {self.product_id}: {total} sections")

    def _parse_markdown(self, filepath: str, domain: str) -> List[Dict]:
        """Markdown 파일을 섹션 단위로 파싱"""
        sections = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return sections

        filename = os.path.basename(filepath)
        current_title = ""
        current_content = []
        current_source = ""

        for line in content.split("\n"):
            # ## 레벨 헤더를 섹션 구분자로 사용
            if line.startswith("## "):
                # 이전 섹션 저장
                if current_title and current_content:
                    sections.append({
                        "title": current_title,
                        "content": "\n".join(current_content).strip(),
                        "source_file": filename,
                        "source_page": current_source,
                        "domain": domain,
                    })
                current_title = line[3:].strip()
                current_content = []
                current_source = ""
            elif line.startswith("### "):
                # ### 레벨도 별도 섹션으로 추가 (에러코드 등)
                if current_title and current_content:
                    sections.append({
                        "title": current_title,
                        "content": "\n".join(current_content).strip(),
                        "source_file": filename,
                        "source_page": current_source,
                        "domain": domain,
                    })
                current_title = line[4:].strip()
                current_content = []
                current_source = ""
            else:
                current_content.append(line)
                # 소스 페이지 추출
                source_match = re.search(r"소스:\s*(.+?)(?:\s*\(p\.(\d+)\))?$", line.strip())
                if source_match:
                    current_source = source_match.group(0)

        # 마지막 섹션 저장
        if current_title and current_content:
            sections.append({
                "title": current_title,
                "content": "\n".join(current_content).strip(),
                "source_file": filename,
                "source_page": current_source,
                "domain": domain,
            })

        return sections

    # PDF 섹션 구분용 heading 패턴
    _HEADING_PATTERN = re.compile(r'^(\d+\.)+\s+\S')
    _MAX_SECTION_CHARS = 8000  # 메모리 관리: 섹션당 최대 문자 수

    def _parse_pdf(self, filepath: str, domain: str) -> List[Dict]:
        """PDF 파일을 섹션 단위로 파싱 (PyMuPDF 사용)"""
        sections = []
        try:
            import pymupdf
        except ImportError:
            logger.warning("PyMuPDF not installed, skipping PDF parsing")
            return sections

        try:
            doc = pymupdf.open(filepath)
        except Exception as e:
            logger.warning(f"Failed to open PDF {filepath}: {e}")
            return sections

        filename = os.path.basename(filepath)

        # TOC 기반 섹션 분할 시도
        toc = doc.get_toc()
        if toc and len(toc) >= 3:
            sections = self._parse_pdf_by_toc(doc, toc, filename, domain)
        else:
            # TOC 없으면 heading 패턴 기반 fallback
            sections = self._parse_pdf_by_headings(doc, filename, domain)

        doc.close()
        return sections

    def _parse_pdf_by_toc(
        self, doc, toc: list, filename: str, domain: str,
    ) -> List[Dict]:
        """TOC 기반 PDF 섹션 분할"""
        sections = []
        total_pages = len(doc)

        for i, (level, title, page_num) in enumerate(toc):
            if level > 2:
                continue  # 3단계 이하 무시
            # 다음 TOC 항목의 페이지 번호
            next_page = total_pages
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    next_page = toc[j][2]
                    break

            # 해당 범위 텍스트 추출
            content_parts = []
            for p in range(max(0, page_num - 1), min(next_page, total_pages)):
                try:
                    page_text = doc[p].get_text("text")
                    if page_text:
                        content_parts.append(page_text.strip())
                except Exception:
                    continue

            content = "\n".join(content_parts)
            # 텍스트 정리
            content = self._clean_pdf_text(content)

            if content and len(content) > 30:
                sections.append({
                    "title": title.strip(),
                    "content": content[:self._MAX_SECTION_CHARS],
                    "source_file": filename,
                    "source_page": f"p.{page_num}",
                    "domain": domain,
                })

        return sections

    def _parse_pdf_by_headings(
        self, doc, filename: str, domain: str,
    ) -> List[Dict]:
        """Heading 패턴 기반 PDF 섹션 분할 (TOC 없을 때)"""
        sections = []
        current_title = filename.replace('.pdf', '')
        current_content: List[str] = []
        current_page = 1

        for page_num in range(len(doc)):
            try:
                page_text = doc[page_num].get_text("text")
            except Exception:
                continue
            if not page_text:
                continue

            for line in page_text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                # heading 패턴 감지
                if self._HEADING_PATTERN.match(stripped) and len(stripped) < 200:
                    # 이전 섹션 저장
                    if current_content:
                        content = self._clean_pdf_text("\n".join(current_content))
                        if content and len(content) > 30:
                            sections.append({
                                "title": current_title,
                                "content": content[:self._MAX_SECTION_CHARS],
                                "source_file": filename,
                                "source_page": f"p.{current_page}",
                                "domain": domain,
                            })
                    current_title = stripped
                    current_content = []
                    current_page = page_num + 1
                else:
                    current_content.append(stripped)

        # 마지막 섹션
        if current_content:
            content = self._clean_pdf_text("\n".join(current_content))
            if content and len(content) > 30:
                sections.append({
                    "title": current_title,
                    "content": content[:self._MAX_SECTION_CHARS],
                    "source_file": filename,
                    "source_page": f"p.{current_page}",
                    "domain": domain,
                })

        return sections

    @staticmethod
    def _clean_pdf_text(text: str) -> str:
        """PDF 텍스트 정리"""
        if not text:
            return ""
        # 연속 공백/탭 정리
        text = re.sub(r'[ \t]+', ' ', text)
        # 페이지 번호 패턴 제거
        text = re.sub(r'\n\s*-?\s*\d+\s*-?\s*\n', '\n', text)
        # 3줄 이상 연속 빈 줄 → 2줄로
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 반복되는 헤더/푸터 제거 (같은 줄이 3회 이상 등장)
        lines = text.split('\n')
        line_counts: Dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 5:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1
        repeated = {line for line, count in line_counts.items() if count >= 3}
        if repeated:
            lines = [line for line in lines if line.strip() not in repeated]
            text = '\n'.join(lines)
        return text.strip()

    # ChatML 파싱용 정규식
    _CHATML_USER = re.compile(r"<\|im_start\|>user\n(.*?)<\|im_end\|>", re.DOTALL)
    _CHATML_ASSISTANT = re.compile(r"<\|im_start\|>assistant\n(.*?)<\|im_end\|>", re.DOTALL)

    def _parse_learning_json(self, filepath: str, domain: str) -> List[Dict]:
        """QLoRA 학습 JSON (ChatML 형식)을 섹션으로 파싱

        각 Q&A 쌍을 하나의 섹션으로 변환:
        - title: 사용자 질문
        - content: 어시스턴트 답변
        """
        sections = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json_module.load(f)
        except Exception:
            return sections

        if not isinstance(data, list):
            return sections

        filename = os.path.basename(filepath)

        for entry in data:
            text = entry.get("text", "")
            user_match = self._CHATML_USER.search(text)
            assistant_match = self._CHATML_ASSISTANT.search(text)

            if user_match and assistant_match:
                question = user_match.group(1).strip()
                answer = assistant_match.group(1).strip()
                if question and answer and len(answer) > 20:
                    sections.append({
                        "title": question,
                        "content": answer,
                        "source_file": filename,
                        "source_page": "",
                        "domain": domain,
                    })

        return sections

    # 불용어 (일본어 조사 + 영어 관사/전치사)
    _STOPWORDS = frozenset([
        # 일본어 조사·접속사
        "の", "は", "が", "を", "に", "で", "と", "も", "や", "か",
        "へ", "から", "まで", "より", "ね", "よ", "わ", "な", "け",
        "って", "ので", "のに", "けど", "だけ", "しか", "ばかり",
        # 영어 불용어
        "the", "a", "an", "of", "in", "on", "at", "to", "for",
        "is", "are", "was", "were", "be", "and", "or", "not",
        "it", "this", "that", "with", "from", "by", "as",
        "about", "what", "how", "do", "does",
    ])

    def _tokenize_query(self, query: str) -> List[str]:
        """
        쿼리를 의미 있는 토큰으로 분리.

        - 영문/숫자: 2자 이상
        - 카타카나: 2자 이상
        - 한자: 1자 이상
        - 한국어: 2자 이상
        - 불용어 제거
        """
        query_lower = query.lower()
        # 영문+숫자+하이픈/언더스코어, 카타카나, 한자, 한국어, 히라가나
        raw_tokens = re.findall(
            r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'  # 영문숫자 (1자 이상)
            r'|[\u30a0-\u30ff]{2,}'   # 카타카나 (2자 이상)
            r'|[\u4e00-\u9fff]+'      # 한자 (1자 이상)
            r'|[\uac00-\ud7af]{2,}'   # 한국어 (2자 이상)
            r'|[\u3040-\u309f]{2,}',  # 히라가나 (2자 이상)
            query_lower,
        )
        # 불용어 제거 + 1자 영문 제거
        tokens = []
        for t in raw_tokens:
            if t in self._STOPWORDS:
                continue
            # 영문 1자는 의미 없으므로 제거
            if len(t) == 1 and t.isascii():
                continue
            tokens.append(t)
        return tokens

    def _calc_document_frequencies(
        self, tokens: List[str], search_domains: List[str]
    ) -> Dict[str, float]:
        """
        각 토큰의 IDF 가중치 계산.

        IDF = log((N + 1) / (DF + 1)) + 1.0
        - N: 전체 섹션 수
        - DF: 해당 토큰이 출현하는 섹션 수
        """
        total_sections = 0
        df_counts: Dict[str, int] = {t: 0 for t in tokens}

        for domain in search_domains:
            if domain not in self._cache:
                continue
            for section in self._cache[domain]:
                total_sections += 1
                title_lower = section["title"].lower()
                content_lower = section["content"].lower()
                combined = title_lower + " " + content_lower
                for token in tokens:
                    if token in combined:
                        df_counts[token] += 1

        idf_weights: Dict[str, float] = {}
        for token in tokens:
            df = df_counts[token]
            idf_weights[token] = math.log((total_sections + 1) / (df + 1)) + 1.0

        return idf_weights

    async def search(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """
        Progressive Token + IDF 기반 구조화 검색 (LLM 없음)

        Args:
            query: 검색 쿼리
            domains: 검색할 도메인 (None이면 전체)
            top_k: 반환할 최대 결과 수

        Returns:
            검색 결과 리스트 (relevance_score 내림차순)
        """
        self._ensure_loaded()

        search_domains = domains or list(self._cache.keys())

        # 토큰 추출 + IDF 계산
        tokens = self._tokenize_query(query)
        if not tokens:
            return []

        idf_weights = self._calc_document_frequencies(tokens, search_domains)

        # 에러코드 패턴 추출
        error_codes = re.findall(r'-?\d{4,5}', query)

        # 전체 후보 섹션 수집 + 점진적 스코어링
        # {(domain, idx): {"score": float, "matched_tokens": set}}
        candidates: Dict[tuple, dict] = {}

        for domain in search_domains:
            if domain not in self._cache:
                continue
            for idx, section in enumerate(self._cache[domain]):
                candidates[(domain, idx)] = {
                    "score": 0.0,
                    "matched_tokens": set(),
                    "section": section,
                }

        # 순차 토큰 처리: IDF 가중치 적용
        prune_threshold = top_k * 20  # 점진적 축소 임계값

        for i, token in enumerate(tokens):
            idf = idf_weights[token]
            for key, cand in candidates.items():
                section = cand["section"]
                title_lower = section["title"].lower()
                content_lower = section["content"].lower()

                if token in title_lower:
                    cand["score"] += 3.0 * idf
                    cand["matched_tokens"].add(token)
                elif token in content_lower:
                    cand["score"] += 1.0 * idf
                    cand["matched_tokens"].add(token)

            # 중간 프루닝: 2번째 토큰 이후, 후보가 임계값 초과 시 축소
            if i > 0 and len(candidates) > prune_threshold:
                sorted_keys = sorted(
                    candidates.keys(),
                    key=lambda k: candidates[k]["score"],
                    reverse=True,
                )
                candidates = {k: candidates[k] for k in sorted_keys[:prune_threshold]}

        # 에러코드 정확 매칭 보너스
        if error_codes:
            for key, cand in candidates.items():
                section = cand["section"]
                domain = key[0]
                if domain in ("error_codes",):
                    title_lower = section["title"].lower()
                    content_lower = section["content"].lower()
                    for code in error_codes:
                        if code in title_lower or code in content_lower:
                            cand["score"] += 10.0

        # 커버리지 보정: 매칭된 토큰 비율로 점수 조정
        total_tokens = len(tokens)
        for cand in candidates.values():
            if cand["score"] > 0 and total_tokens > 1:
                coverage = len(cand["matched_tokens"]) / total_tokens
                # coverage 0.0~1.0 → 보정계수 0.5~1.0
                coverage_factor = 0.5 + 0.5 * coverage
                cand["score"] *= coverage_factor

        # 최종 결과 수집 + content 중복 제거
        results: List[SearchResult] = []
        seen_content: set = set()

        # 점수 내림차순으로 정렬하여 최고 점수 우선 채택
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda c: c["score"],
            reverse=True,
        )

        for cand in sorted_candidates:
            if cand["score"] <= 0:
                continue
            section = cand["section"]
            # content 앞 120자를 정규화 fingerprint로 사용 (동일 답변 중복 제거)
            # 구두점/슬래시/공백 차이 무시 → 알파벳+숫자+CJK만 추출
            raw_fp = section["content"][:120].strip().lower()
            content_fp = re.sub(r"[^a-z0-9\u3040-\u9fff\uac00-\ud7af]", "", raw_fp)
            if content_fp in seen_content:
                continue
            seen_content.add(content_fp)

            results.append(SearchResult(
                title=section["title"],
                content=section["content"],
                source_file=section["source_file"],
                source_page=section.get("source_page", ""),
                relevance_score=cand["score"],
                domain=section["domain"],
            ))

            if len(results) >= top_k:
                break

        return results

    def get_stats(self) -> Dict[str, int]:
        """도메인별 섹션 수 반환"""
        self._ensure_loaded()
        return {domain: len(sections) for domain, sections in self._cache.items()}
