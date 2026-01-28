"""
Summary BM25 Search Service

BM25-based full-text search over all summary content.
Provides fast (<50ms) retrieval of error codes, commands, glossary terms, etc.

This is the core of the Summary-First RAG architecture:
1. User query arrives
2. BM25 searches all summaries for exact/fuzzy matches
3. Returns confidence-scored results for routing decisions
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Any
import hashlib
import json

from rank_bm25 import BM25Okapi
import numpy as np

from ..models.summary import (
    SummaryDocument,
    SummaryDocType,
    SummarySearchResult,
    ComprehensiveSearchResult,
    ConfidenceLevel,
    PageReference,
)

logger = logging.getLogger(__name__)


class SummaryBM25Service:
    """
    BM25-based search over all summary content.

    Features:
    - CJK-optimized tokenization (Korean, Japanese, Chinese)
    - Error code pattern detection and boosting
    - Command name extraction
    - Multi-category search across all summary types
    - Confidence-based routing (high/medium/low)
    """

    def __init__(
        self,
        summaries_dir: Optional[Path] = None,
        high_confidence_threshold: float = 0.7,
        medium_confidence_threshold: float = 0.4,
    ):
        """
        Initialize BM25 service.

        Args:
            summaries_dir: Path to summaries directory
            high_confidence_threshold: Score threshold for high confidence
            medium_confidence_threshold: Score threshold for medium confidence
        """
        self.summaries_dir = summaries_dir or Path("/opt/kms/uploads/summaries")
        self.high_threshold = high_confidence_threshold
        self.medium_threshold = medium_confidence_threshold

        # Index state
        self._documents: List[SummaryDocument] = []
        self._doc_contents: List[str] = []  # Tokenization source
        self._bm25: Optional[BM25Okapi] = None
        self._initialized: bool = False

        # Quick lookup indices
        self._error_code_index: Dict[str, SummaryDocument] = {}  # "-5212" -> doc
        self._command_index: Dict[str, List[SummaryDocument]] = {}  # "tjesmgr" -> [docs]
        self._term_index: Dict[str, SummaryDocument] = {}  # "TJES" -> doc

        # Cache for file hashes (detect changes)
        self._file_hashes: Dict[str, str] = {}

    def _tokenize(self, text: str) -> List[str]:
        """
        CJK-optimized tokenization with character bi-grams.

        For Korean/Japanese/Chinese text, generates character bi-grams
        for partial matching. English uses whitespace + alphanumeric split.

        Args:
            text: Input text to tokenize

        Returns:
            List of tokens including bi-grams for CJK characters
        """
        text = text.lower()

        # Split on whitespace and punctuation but keep alphanumeric
        tokens = re.findall(r'[a-z0-9_\-\.]+|[\u3131-\uD79D]+|[\u4E00-\u9FFF]+|[\u3040-\u309F\u30A0-\u30FF]+', text)

        ngrams = []
        for token in tokens:
            # Check if purely ASCII alphanumeric
            if re.match(r'^[a-z0-9_\-\.]+$', token):
                # English/numbers: use original token and split on - and _
                ngrams.append(token)
                # Also add parts split by - and _
                parts = re.split(r'[-_\.]', token)
                ngrams.extend([p for p in parts if p and len(p) > 1])
            else:
                # CJK characters: generate bi-grams + original
                for i in range(len(token) - 1):
                    ngrams.append(token[i:i+2])
                if len(token) > 2:
                    # Also add tri-grams for longer terms
                    for i in range(len(token) - 2):
                        ngrams.append(token[i:i+3])
                ngrams.append(token)

        return list(set(tokens + ngrams))

    async def initialize(self) -> bool:
        """
        Load and index all summary files at startup.

        Scans the summaries directory and builds BM25 index
        for fast full-text search.

        Returns:
            True if initialization successful
        """
        if not self.summaries_dir.exists():
            logger.warning(f"Summaries directory not found: {self.summaries_dir}")
            return False

        try:
            logger.info(f"Initializing BM25 index from {self.summaries_dir}")

            # Load all summary files
            self._documents = []
            self._doc_contents = []

            # Process each category directory
            categories = [
                ("error-codes", SummaryDocType.ERROR_CODES),
                ("error_codes", SummaryDocType.ERROR_CODES),  # Alternative naming
                ("commands", SummaryDocType.COMMANDS),
                ("glossary", SummaryDocType.GLOSSARY),
                ("configs", SummaryDocType.CONFIGS),
                ("apis", SummaryDocType.APIS),
                ("terms", SummaryDocType.TERMS),
                ("concepts", SummaryDocType.CONCEPTS),
                ("procedures", SummaryDocType.PROCEDURES),
            ]

            for dir_name, doc_type in categories:
                category_dir = self.summaries_dir / dir_name
                if category_dir.exists():
                    await self._load_category(category_dir, doc_type)

            if not self._documents:
                logger.warning("No summary documents found")
                return False

            # Build BM25 index
            tokenized_docs = [self._tokenize(content) for content in self._doc_contents]
            self._bm25 = BM25Okapi(tokenized_docs)

            self._initialized = True
            logger.info(
                f"BM25 index initialized: {len(self._documents)} documents, "
                f"{len(self._error_code_index)} error codes, "
                f"{len(self._command_index)} commands, "
                f"{len(self._term_index)} terms"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize BM25 index: {e}", exc_info=True)
            return False

    async def _load_category(self, category_dir: Path, doc_type: SummaryDocType):
        """Load all markdown files from a category directory"""
        for md_file in category_dir.glob("*.md"):
            if md_file.name in ("index.md", "README.md"):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                file_hash = hashlib.md5(content.encode()).hexdigest()
                self._file_hashes[str(md_file)] = file_hash

                # Parse based on document type
                if doc_type == SummaryDocType.ERROR_CODES:
                    await self._parse_error_codes(content, md_file.name, doc_type)
                elif doc_type == SummaryDocType.COMMANDS:
                    await self._parse_commands(content, md_file.name, doc_type)
                elif doc_type == SummaryDocType.GLOSSARY:
                    await self._parse_glossary(content, md_file.name, doc_type)
                elif doc_type == SummaryDocType.APIS:
                    await self._parse_apis(content, md_file.name, doc_type)
                else:
                    # Generic loading for other types
                    await self._parse_generic(content, md_file.name, doc_type)

            except Exception as e:
                logger.warning(f"Failed to load {md_file}: {e}")

    async def _parse_error_codes(self, content: str, source_file: str, doc_type: SummaryDocType):
        """Parse error code summary file

        Expected format:
        ### ERROR_NAME (-1234)
        - **설명**: Description
        - **대처방법**: Solution
        - **참고**: Reference
        """
        # Pattern: ### ERROR_NAME (-1234) or ### ERROR_NAME(-1234)
        pattern = r'^### ([A-Z][A-Z0-9_]*)\s*\((-?\d+)\)\n(.*?)(?=^### [A-Z]|\Z)'
        matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)

        # Get module name from header or filename
        module_match = re.search(r'^# (\w+)\s*에러', content, re.MULTILINE)
        module = module_match.group(1) if module_match else source_file.split('-')[0].upper()

        # Get source PDFs from YAML frontmatter
        source_pdfs = []
        yaml_match = re.search(r'^---\n.*?source_files:\s*(.*?)^---', content, re.DOTALL | re.MULTILINE)
        if yaml_match:
            source_pdfs = re.findall(r'-\s*([^\n]+\.pdf)', yaml_match.group(1))

        for name, code, details in matches:
            # Extract description
            desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|\Z)', details, re.DOTALL)
            description = None
            if desc_match:
                description = ' '.join(desc_match.group(1).strip().split())[:300]

            # Extract solution (대처방법)
            sol_match = re.search(r'\*\*대처방법\*\*:\s*(.+?)(?=\n-|\n\*\*|\Z)', details, re.DOTALL)
            solution = None
            if sol_match:
                solution = ' '.join(sol_match.group(1).strip().split())[:300]

            # Extract reference (참고)
            ref_match = re.search(r'\*\*참고\*\*:\s*(.+?)(?=\n-|\n\*\*|\Z)', details, re.DOTALL)

            # Extract page reference if present in any field
            page_match = re.search(r'[pP]\.?\s*(\d+)', details)
            pages = [int(page_match.group(1))] if page_match else []

            # Use first source PDF from frontmatter
            source_pdf = source_pdfs[0] if source_pdfs else None

            doc = SummaryDocument(
                id=f"error_{abs(int(code))}",
                content=details.strip()[:500],
                doc_type=doc_type,
                source_file=source_file,
                source_pdf=source_pdf,
                page_numbers=pages,
                name=name,
                description=description,
                solution=solution,
                product=module,
                metadata={
                    "code": code,
                    "module": module,
                    "reference": ref_match.group(1).strip() if ref_match else None
                }
            )

            self._documents.append(doc)
            # Create searchable content: name + code + description + solution
            search_content = f"{name} {code} {module} {description or ''} {solution or ''}"
            self._doc_contents.append(search_content)

            # Index by error code (both with and without minus)
            self._error_code_index[code] = doc
            self._error_code_index[code.lstrip('-')] = doc
            # Also index by absolute value string
            self._error_code_index[str(abs(int(code)))] = doc

    async def _parse_commands(self, content: str, source_file: str, doc_type: SummaryDocType):
        """Parse command summary file

        Expected format:
        ## command_name
        - **지원 제품**: Product1, Product2
        ### ProductName
        - **설명**: Description
        - **구문**: `syntax`
        - **참조**: file.pdf (p.123)
        """
        # Pattern: ## command_name followed by content until next ## or end
        pattern = r'^## ([a-zA-Z][a-zA-Z0-9_\-\.]*)\n(.*?)(?=^## [a-zA-Z]|\Z)'
        matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)

        for cmd_name, details in matches:
            # Extract products from "지원 제품" line
            products_match = re.search(r'\*\*지원 제품\*\*:\s*(.+?)(?:\n|$)', details)
            products = []
            if products_match:
                products = [p.strip() for p in products_match.group(1).split(",")]

            # Collect descriptions from all ### subsections
            descriptions = []
            syntaxes = []
            pages = []
            source_pdfs = []

            # Parse each product subsection (### ProductName)
            subsection_pattern = r'### ([^\n]+)\n(.*?)(?=### |\Z)'
            subsections = re.findall(subsection_pattern, details, re.DOTALL)

            for product_name, subsection in subsections:
                # Extract description
                desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|$)', subsection, re.DOTALL)
                if desc_match:
                    desc_text = desc_match.group(1).strip()
                    # Clean up and truncate
                    desc_clean = ' '.join(desc_text.split())[:200]
                    if desc_clean and desc_clean not in descriptions:
                        descriptions.append(desc_clean)

                # Extract syntax
                syntax_match = re.search(r'\*\*구문\*\*:\s*`([^`]+)`', subsection, re.DOTALL)
                if syntax_match:
                    syntax = syntax_match.group(1).strip().split('\n')[0]  # First line only
                    if syntax and syntax not in syntaxes:
                        syntaxes.append(syntax)

                # Extract page reference (소스: or 참조: file.pdf (p.XX))
                page_match = re.search(r'(?:소스|참조)\**:\s*.*?\(p\.?(\d+)\)', subsection)
                if page_match:
                    pages.append(int(page_match.group(1)))

                # Extract source PDF (handle both 소스: and 참조: formats)
                pdf_match = re.search(r'(?:소스|참조)\**:\s*([^\(\n]+\.pdf)', subsection, re.IGNORECASE)
                if pdf_match:
                    pdf_name = pdf_match.group(1).strip()
                    if pdf_name and pdf_name not in source_pdfs:
                        source_pdfs.append(pdf_name)

            # Also check for description/syntax directly under ## (without subsection)
            if not descriptions:
                desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|$)', details, re.DOTALL)
                if desc_match:
                    descriptions.append(' '.join(desc_match.group(1).strip().split())[:200])

            if not syntaxes:
                syntax_match = re.search(r'\*\*구문\*\*:\s*`([^`]+)`', details, re.DOTALL)
                if syntax_match:
                    syntaxes.append(syntax_match.group(1).strip().split('\n')[0])

            # Also check for source/page directly under ## (without subsection)
            # Handle both 소스: and 참조: formats
            if not source_pdfs:
                pdf_match = re.search(r'(?:소스|참조)\**:\s*([^\(\n]+\.pdf)', details, re.IGNORECASE)
                if pdf_match:
                    source_pdfs.append(pdf_match.group(1).strip())
            if not pages:
                page_match = re.search(r'(?:소스|참조)\**:.*?\(p\.?(\d+)\)', details)
                if page_match:
                    pages.append(int(page_match.group(1)))

            description = descriptions[0] if descriptions else None
            syntax = syntaxes[0] if syntaxes else None
            source_pdf = source_pdfs[0] if source_pdfs else None

            doc = SummaryDocument(
                id=f"cmd_{cmd_name.lower()}",
                content=details.strip()[:1000],  # Limit content size
                doc_type=doc_type,
                source_file=source_file,
                source_pdf=source_pdf,
                page_numbers=list(set(pages)),  # Deduplicate
                name=cmd_name,
                description=description,
                syntax=syntax,
                product=", ".join(products) if products else None,
                metadata={"products": products, "all_descriptions": descriptions}
            )

            self._documents.append(doc)
            # Create searchable content including all descriptions
            search_content = f"{cmd_name} {' '.join(descriptions)} {syntax or ''} {' '.join(products)}"
            self._doc_contents.append(search_content)

            # Index by command name
            cmd_lower = cmd_name.lower()
            if cmd_lower not in self._command_index:
                self._command_index[cmd_lower] = []
            self._command_index[cmd_lower].append(doc)

    async def _parse_glossary(self, content: str, source_file: str, doc_type: SummaryDocType):
        """Parse glossary summary file

        Expected format:
        ## TERM
        - **정식명칭**: Full Name
        - **설명**: Description
        - **주요기능**:
          - Feature 1
          - Feature 2
        """
        # Pattern: ## TERM followed by content until next ## or end
        pattern = r'^## ([A-Z][A-Z0-9_\-/]*)\n(.*?)(?=^## [A-Z]|\Z)'
        matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)

        for term_name, details in matches:
            # Extract full name (정식명칭)
            full_name_match = re.search(r'\*\*정식명칭\*\*:\s*(.+?)(?=\n|$)', details)
            full_name = full_name_match.group(1).strip() if full_name_match else None

            # Extract description (설명)
            desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-\s*\*\*|\Z)', details, re.DOTALL)
            description = None
            if desc_match:
                # Clean up and truncate description
                desc_text = desc_match.group(1).strip()
                # Remove line breaks in the middle of sentences
                description = ' '.join(desc_text.split())[:400]

            # Extract key features (주요기능)
            features = []
            features_match = re.search(r'\*\*주요기능\*\*:\s*\n((?:\s*-[^\n]+\n?)+)', details)
            if features_match:
                feature_lines = features_match.group(1).split('\n')
                for line in feature_lines[:5]:  # Limit to 5 features
                    line = line.strip()
                    if line.startswith('-'):
                        feature = line[1:].strip()[:100]
                        if feature:
                            features.append(feature)

            # Extract source PDFs from 참조매뉴얼
            source_pdf = None
            ref_match = re.search(r'\*\*참조매뉴얼\*\*:\s*([^\n]+)', details)
            if ref_match:
                # Get first PDF from the list
                pdf_list = ref_match.group(1).strip()
                pdf_match = re.search(r'([^\s,]+\.pdf)', pdf_list, re.IGNORECASE)
                if pdf_match:
                    source_pdf = pdf_match.group(1).strip()

            doc = SummaryDocument(
                id=f"term_{term_name.lower().replace('/', '_')}",
                content=details.strip()[:800],
                doc_type=doc_type,
                source_file=source_file,
                source_pdf=source_pdf,
                name=term_name.upper(),
                description=description,
                metadata={
                    "full_name": full_name,
                    "features": features
                }
            )

            self._documents.append(doc)
            # Create searchable content
            features_text = ' '.join(features) if features else ''
            search_content = f"{term_name} {full_name or ''} {description or ''} {features_text}"
            self._doc_contents.append(search_content)

            # Index by term (support both cases)
            self._term_index[term_name.upper()] = doc
            # Also index without special characters
            clean_term = re.sub(r'[^A-Z0-9]', '', term_name.upper())
            if clean_term != term_name.upper():
                self._term_index[clean_term] = doc

    async def _parse_apis(self, content: str, source_file: str, doc_type: SummaryDocType):
        """Parse API summary file"""
        # Pattern: ## api_name or ## api_name()
        pattern = r'## ([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(\))?\n(.*?)(?=\n## [a-zA-Z_]|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)

        for api_name, details in matches:
            # Extract product
            product_match = re.search(r'\*\*제품\*\*:\s*(.+?)(?:\n|$)', details)
            # Extract description
            desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|$)', details, re.DOTALL)
            # Extract syntax/prototype
            syntax_match = re.search(r'\*\*(?:구문|프로토타입)\*\*:\s*`(.+?)`', details, re.DOTALL)

            doc = SummaryDocument(
                id=f"api_{api_name.lower()}",
                content=details.strip(),
                doc_type=doc_type,
                source_file=source_file,
                name=api_name,
                description=' '.join(desc_match.group(1).strip().split())[:300] if desc_match else None,
                syntax=syntax_match.group(1).strip() if syntax_match else None,
                product=product_match.group(1).strip() if product_match else None,
            )

            self._documents.append(doc)
            search_content = f"{api_name} {doc.description or ''} {doc.syntax or ''}"
            self._doc_contents.append(search_content)

    async def _parse_generic(self, content: str, source_file: str, doc_type: SummaryDocType):
        """Generic parser for other summary types"""
        # Split by ## headers
        sections = re.split(r'\n## ', content)

        for i, section in enumerate(sections):
            if not section.strip():
                continue

            # First line is the title
            lines = section.strip().split('\n')
            title = lines[0].strip('#').strip()
            body = '\n'.join(lines[1:]).strip()

            if not title or not body:
                continue

            doc = SummaryDocument(
                id=f"{doc_type.value}_{source_file}_{i}",
                content=body,
                doc_type=doc_type,
                source_file=source_file,
                name=title,
                description=body[:300] if body else None,
            )

            self._documents.append(doc)
            self._doc_contents.append(f"{title} {body}")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        doc_types: Optional[List[SummaryDocType]] = None,
    ) -> List[SummarySearchResult]:
        """
        Full-text BM25 search across all summaries.

        Args:
            query: Search query (supports Korean, Japanese, English)
            top_k: Number of results to return
            doc_types: Optional filter for specific document types

        Returns:
            List of SummarySearchResult sorted by score descending
        """
        if not self._initialized or self._bm25 is None:
            logger.warning("BM25 index not initialized, attempting initialization...")
            await self.initialize()
            if not self._initialized:
                return []

        try:
            # Tokenize query
            tokenized_query = self._tokenize(query)

            # Get BM25 scores
            scores = self._bm25.get_scores(tokenized_query)

            # Normalize scores to 0-1 range
            max_score = scores.max() if scores.max() > 0 else 1.0
            normalized_scores = scores / (max_score + 1e-8)

            # Get top-k indices
            top_indices = np.argsort(scores)[::-1]

            results = []
            for rank, idx in enumerate(top_indices):
                if len(results) >= top_k:
                    break

                doc = self._documents[idx]

                # Filter by doc_type if specified
                if doc_types and doc.doc_type not in doc_types:
                    continue

                score = float(normalized_scores[idx])
                if score < 0.01:  # Skip very low scores
                    continue

                # Find matched terms
                doc_tokens = set(self._tokenize(self._doc_contents[idx]))
                matched_terms = list(set(tokenized_query) & doc_tokens)

                results.append(SummarySearchResult(
                    document=doc,
                    score=score,
                    matched_terms=matched_terms[:10],  # Limit matched terms
                    rank=rank + 1
                ))

            return results

        except Exception as e:
            logger.error(f"BM25 search error: {e}", exc_info=True)
            return []

    async def search_error_code(self, code: str) -> Optional[SummarySearchResult]:
        """
        Direct lookup for error codes.

        Faster than full BM25 search for known error code patterns.

        Args:
            code: Error code (e.g., "-5212", "5212")

        Returns:
            SummarySearchResult if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        # Normalize code
        code_clean = code.lstrip('-').strip()

        # Try direct lookup first
        doc = self._error_code_index.get(code_clean)
        if doc:
            return SummarySearchResult(
                document=doc,
                score=1.0,  # Exact match
                matched_terms=[code],
                rank=1
            )

        # Fall back to BM25 search
        results = await self.search(code, top_k=1, doc_types=[SummaryDocType.ERROR_CODES])
        return results[0] if results else None

    async def search_command(self, cmd: str) -> List[SummarySearchResult]:
        """
        Direct lookup for commands.

        Args:
            cmd: Command name (e.g., "tjesmgr", "oscboot")

        Returns:
            List of SummarySearchResult (may have multiple products)
        """
        if not self._initialized:
            await self.initialize()

        cmd_lower = cmd.lower()

        # Try direct lookup first
        docs = self._command_index.get(cmd_lower, [])
        if docs:
            return [
                SummarySearchResult(
                    document=doc,
                    score=1.0,
                    matched_terms=[cmd],
                    rank=i + 1
                )
                for i, doc in enumerate(docs)
            ]

        # Fall back to BM25 search
        return await self.search(cmd, top_k=5, doc_types=[SummaryDocType.COMMANDS])

    async def search_term(self, term: str) -> Optional[SummarySearchResult]:
        """
        Direct lookup for glossary terms.

        Args:
            term: Term (e.g., "TJES", "TACF")

        Returns:
            SummarySearchResult if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        term_upper = term.upper()

        # Try direct lookup first
        doc = self._term_index.get(term_upper)
        if doc:
            return SummarySearchResult(
                document=doc,
                score=1.0,
                matched_terms=[term],
                rank=1
            )

        # Fall back to BM25 search
        results = await self.search(term, top_k=1, doc_types=[SummaryDocType.GLOSSARY])
        return results[0] if results else None

    def get_confidence_level(self, results: List[SummarySearchResult]) -> ConfidenceLevel:
        """
        Determine overall confidence level from search results.

        Args:
            results: Search results

        Returns:
            ConfidenceLevel enum value
        """
        if not results:
            return ConfidenceLevel.LOW

        top_score = results[0].score

        if top_score >= self.high_threshold:
            return ConfidenceLevel.HIGH
        elif top_score >= self.medium_threshold:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    async def comprehensive_search(self, query: str, top_k: int = 10) -> ComprehensiveSearchResult:
        """
        Unified search across all summary types with query analysis.

        This is the main entry point for Summary-First RAG.

        Args:
            query: User query
            top_k: Maximum results to return

        Returns:
            ComprehensiveSearchResult with all matches and confidence
        """
        if not self._initialized:
            await self.initialize()

        result = ComprehensiveSearchResult(query=query)

        # Analyze query for patterns
        result.detected_error_codes = self._detect_error_codes(query)
        result.detected_commands = self._detect_commands(query)
        result.detected_terms = self._detect_terms(query)

        # Priority 1: Error code direct lookup
        for code in result.detected_error_codes:
            error_result = await self.search_error_code(code)
            if error_result:
                result.results.append(error_result)
                if SummaryDocType.ERROR_CODES not in result.matched_categories:
                    result.matched_categories.append(SummaryDocType.ERROR_CODES)

        # Priority 2: Command direct lookup
        for cmd in result.detected_commands:
            cmd_results = await self.search_command(cmd)
            for cr in cmd_results:
                if cr not in result.results:
                    result.results.append(cr)
            if cmd_results and SummaryDocType.COMMANDS not in result.matched_categories:
                result.matched_categories.append(SummaryDocType.COMMANDS)

        # Priority 3: Term direct lookup
        for term in result.detected_terms:
            term_result = await self.search_term(term)
            if term_result and term_result not in result.results:
                result.results.append(term_result)
                if SummaryDocType.GLOSSARY not in result.matched_categories:
                    result.matched_categories.append(SummaryDocType.GLOSSARY)

        # Priority 4: Full BM25 search for remaining slots
        remaining_slots = top_k - len(result.results)
        if remaining_slots > 0:
            bm25_results = await self.search(query, top_k=remaining_slots + 5)
            for br in bm25_results:
                if br.document.id not in [r.document.id for r in result.results]:
                    result.results.append(br)
                    if br.document.doc_type not in result.matched_categories:
                        result.matched_categories.append(br.document.doc_type)
                    if len(result.results) >= top_k:
                        break

        # Sort by score
        result.results.sort(key=lambda r: r.score, reverse=True)
        result.results = result.results[:top_k]

        # Determine confidence
        result.confidence = self.get_confidence_level(result.results)

        # Extract page references
        for sr in result.results:
            doc = sr.document
            if doc.source_pdf and doc.page_numbers:
                for page in doc.page_numbers:
                    ref = PageReference(
                        pdf_path=doc.source_pdf,
                        page_number=page,
                        source_file=doc.source_file
                    )
                    if ref not in result.page_references:
                        result.page_references.append(ref)

        return result

    def _detect_error_codes(self, query: str) -> List[str]:
        """Detect error code patterns in query"""
        # Pattern: -5212, 5212, ERROR-5212
        patterns = [
            r'-\d{4,5}',  # -5212
            r'(?<![a-zA-Z0-9])\d{4,5}(?![a-zA-Z0-9])',  # 5212 standalone
        ]
        codes = []
        for pattern in patterns:
            matches = re.findall(pattern, query)
            codes.extend(matches)
        return list(set(codes))

    def _detect_commands(self, query: str) -> List[str]:
        """Detect command patterns in query"""
        # OpenFrame command patterns
        patterns = [
            r'\b([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b',
            r'\b(tjes\w*|osc\w*|tac\w*|ofm\w*|osci\w*)\b',
            r'\b(tjesmgr|oscboot|tjadmin|tacfadm|dsload|dsunload)\b',
        ]
        commands = []
        for pattern in patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            commands.extend([m.lower() for m in matches])
        return list(set(commands))

    def _detect_terms(self, query: str) -> List[str]:
        """Detect technical term patterns in query"""
        # Uppercase acronyms (TJES, TACF, OSC, etc.)
        pattern = r'\b([A-Z]{2,}[A-Z0-9]*)\b'
        terms = re.findall(pattern, query)
        # Filter common words
        stopwords = {'THE', 'AND', 'FOR', 'NOT', 'WITH', 'THIS', 'FROM', 'ARE', 'WAS', 'PDF', 'API'}
        return [t for t in terms if t not in stopwords and len(t) >= 2]

    @property
    def is_initialized(self) -> bool:
        """Check if service is initialized"""
        return self._initialized

    @property
    def document_count(self) -> int:
        """Get total document count"""
        return len(self._documents)


# Singleton instance
_bm25_service: Optional[SummaryBM25Service] = None


def get_summary_bm25_service() -> SummaryBM25Service:
    """Get or create singleton SummaryBM25Service instance"""
    global _bm25_service
    if _bm25_service is None:
        _bm25_service = SummaryBM25Service()
    return _bm25_service


async def initialize_summary_bm25_service() -> bool:
    """Initialize the summary BM25 service at startup"""
    service = get_summary_bm25_service()
    return await service.initialize()
