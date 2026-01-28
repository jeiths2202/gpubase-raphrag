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
import os
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, Tuple
import hashlib
import json
import aiohttp

from rank_bm25 import BM25Okapi
import numpy as np

from collections import defaultdict
from ..models.summary import (
    SummaryDocument,
    SummaryDocType,
    SummarySearchResult,
    ComprehensiveSearchResult,
    ConfidenceLevel,
    PageReference,
    ProductVariant,
    MultiProductResult,
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
        self._parent_tool_index: Dict[str, List[SummaryDocument]] = {}  # "tjesmgr" -> [BOOT, CANCEL, ...]

        # Cache for file hashes (detect changes)
        self._file_hashes: Dict[str, str] = {}

        # LLM-based keyword extraction config
        self._llm_url = os.getenv("LLM_API_URL", "http://localhost:12800/v1/chat/completions")
        self._llm_model = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self._llm_keyword_cache: Dict[str, List[str]] = {}  # query -> extracted keywords
        self._llm_timeout = 10.0  # Timeout for keyword extraction (increased for reliability)

    def _extract_version_from_source(self, source_pdf: str) -> tuple:
        """
        Extract version information from PDF filename.

        Parses filenames like:
        OF_Common_MSP_7.3_Tool-Reference-Guide_v3.3.1_ja.pdf
        -> platform=MSP, product_version=7.3, doc_version=v3.3.1

        Args:
            source_pdf: PDF filename

        Returns:
            tuple (platform, product_version, doc_version) or (None, None, None)
        """
        if not source_pdf:
            return None, None, None

        # Pattern for OpenFrame PDFs: OF_<type>_<platform>_<version>_..._<doc_version>_<lang>.pdf
        pattern = r'OF_\w+_(\w+)_(\d+\.\d+)_.*?_(v[\d.]+)_\w+\.pdf'
        match = re.search(pattern, source_pdf, re.IGNORECASE)
        if match:
            return match.group(1).upper(), match.group(2), match.group(3)

        # Alternative pattern: OpenFrame_<category>_<platform>.md or similar
        alt_pattern = r'OpenFrame_\w+_(\w+)(?:_(\d+\.\d+))?'
        alt_match = re.search(alt_pattern, source_pdf, re.IGNORECASE)
        if alt_match:
            platform = alt_match.group(1).upper()
            version = alt_match.group(2) if alt_match.lastindex >= 2 else None
            return platform, version, None

        return None, None, None

    def _extract_platform_from_source_file(self, source_file: str) -> Optional[str]:
        """
        Extract platform from summary source file name.

        Args:
            source_file: Summary markdown file name (e.g., OpenFrame_TJES_MVS.md)

        Returns:
            Platform identifier (MVS, MSP, XSP, VOS3) or None
        """
        if not source_file:
            return None

        # Pattern: OpenFrame_<category>_<platform>.md
        pattern = r'OpenFrame_\w+_(\w+)\.md'
        match = re.search(pattern, source_file, re.IGNORECASE)
        if match:
            platform = match.group(1).upper()
            # Validate known platforms
            if platform in ('MVS', 'MSP', 'XSP', 'VOS3'):
                return platform

        return None

    def _extract_parent_tool_from_syntax(self, syntax: Optional[str], content: Optional[str] = None) -> Optional[str]:
        """
        Extract parent tool name from command syntax.

        For example:
        - "tjesmgr BOOT" -> "tjesmgr"
        - "hidbmgr START" -> "hidbmgr"
        - "$ tjesmgr -h" -> "tjesmgr"

        Args:
            syntax: Command syntax string
            content: Optional content to search if syntax is None

        Returns:
            Parent tool name or None
        """
        # Known OpenFrame tool prefixes (command tools)
        KNOWN_TOOLS = {
            'tjesmgr', 'hidbmgr', 'tjesedit', 'tacfmgr', 'ofminer',
            'oscmgr', 'tmadmin', 'fdlc', 'cobrun', 'ofcob',
            'ofasm', 'ofutil', 'ofdebug', 'osmgr', 'oprmgr',
            'tsam', 'vsam', 'jcl', 'sort', 'iebgener',
            'cics', 'dbmgr', 'ofrunner', 'ofstudio'
        }

        text_to_check = syntax or content or ""
        text_lower = text_to_check.lower()

        # Pattern 1: Look for known tool at start of syntax
        # e.g., "tjesmgr BOOT", "$ tjesmgr -h"
        for tool in KNOWN_TOOLS:
            if tool in text_lower:
                # Verify it's the tool, not a substring
                pattern = rf'(?:^|\$\s*|^\s*){tool}\b'
                if re.search(pattern, text_lower):
                    return tool

        # Pattern 2: Extract first word from syntax if it looks like a tool name
        if syntax:
            # Remove leading $ and whitespace
            clean_syntax = re.sub(r'^[\$\s]+', '', syntax)
            first_word_match = re.match(r'^([a-z][a-z0-9_]+)', clean_syntax.lower())
            if first_word_match:
                first_word = first_word_match.group(1)
                # Check if it ends with 'mgr' or 'run' pattern (common in OpenFrame tools)
                if re.match(r'.*(?:mgr|run|edit|admin|miner)$', first_word):
                    return first_word

        return None

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

        For multi-product search, we create separate documents per platform/subsection
        to enable platform-specific grouping in search results.
        """
        # Extract platform from source file name (e.g., OpenFrame_TJES_MVS.md)
        file_platform = self._extract_platform_from_source_file(source_file)

        # Pattern: ## command_name followed by content until next ## or end
        pattern = r'^## ([a-zA-Z][a-zA-Z0-9_\-\.]*)\n(.*?)(?=^## [a-zA-Z]|\Z)'
        matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)

        for cmd_name, details in matches:
            # Extract products from "지원 제품" line
            products_match = re.search(r'\*\*지원 제품\*\*:\s*(.+?)(?:\n|$)', details)
            products = []
            if products_match:
                products = [p.strip() for p in products_match.group(1).split(",")]

            # Parse each product subsection (### ProductName)
            subsection_pattern = r'### ([^\n]+)\n(.*?)(?=### |\Z)'
            subsections = re.findall(subsection_pattern, details, re.DOTALL)

            # Track if we created platform-specific documents
            created_platform_docs = False

            for product_name, subsection in subsections:
                # Try to identify platform from subsection header
                subsection_platform = None
                for known_platform in ('MVS', 'MSP', 'XSP', 'VOS3'):
                    if known_platform in product_name.upper():
                        subsection_platform = known_platform
                        break

                # Extract description - try **설명**: first, then first paragraph
                desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|$)', subsection, re.DOTALL)
                if not desc_match:
                    # Description is first paragraph before **구문** or **지원
                    desc_match = re.search(r'^(.+?)(?=\n\n\*\*|\n\*\*)', subsection.strip(), re.DOTALL)
                description = None
                if desc_match:
                    description = ' '.join(desc_match.group(1).strip().split())[:200]

                # Extract syntax (handle both single backticks and code blocks)
                # Try code block first: ```\n...\n```
                syntax_match = re.search(r'\*\*구문[:\*]*\s*\n```\n?([^`]+?)```', subsection, re.DOTALL)
                if not syntax_match:
                    # Try single backticks: `...`
                    syntax_match = re.search(r'\*\*구문\*\*:\s*`([^`]+)`', subsection, re.DOTALL)
                syntax = None
                if syntax_match:
                    syntax = syntax_match.group(1).strip().split('\n')[0]

                # Extract page reference
                page_match = re.search(r'(?:소스|참조)\**:\s*.*?\(p\.?(\d+)\)', subsection)
                page_numbers = [int(page_match.group(1))] if page_match else []

                # Extract source PDF
                pdf_match = re.search(r'(?:소스|참조)\**:\s*([^\(\n]+\.pdf)', subsection, re.IGNORECASE)
                source_pdf = pdf_match.group(1).strip() if pdf_match else None

                # Extract version from source PDF
                platform, product_version, doc_version = self._extract_version_from_source(source_pdf)

                # Determine final platform (subsection > pdf > file > product_name)
                final_platform = subsection_platform or platform or file_platform or product_name.strip()

                if final_platform and (description or syntax):
                    created_platform_docs = True

                    # Extract parent tool from syntax (e.g., "tjesmgr BOOT" -> "tjesmgr")
                    parent_tool = self._extract_parent_tool_from_syntax(syntax, subsection)

                    doc_id = f"cmd_{cmd_name.lower()}_{final_platform.lower()}"
                    doc = SummaryDocument(
                        id=doc_id,
                        content=subsection.strip()[:1000],
                        doc_type=doc_type,
                        source_file=source_file,
                        source_pdf=source_pdf,
                        page_numbers=page_numbers,
                        name=cmd_name,
                        description=description,
                        syntax=syntax,
                        product=product_name.strip(),
                        platform=final_platform,
                        product_version=product_version,
                        document_version=doc_version,
                        parent_tool=parent_tool,
                        metadata={
                            "products": products,
                            "subsection_header": product_name.strip()
                        }
                    )

                    self._documents.append(doc)
                    # Include parent_tool in searchable content
                    search_content = f"{cmd_name} {final_platform} {description or ''} {syntax or ''} {parent_tool or ''}"
                    self._doc_contents.append(search_content)

                    # Index by command name
                    cmd_lower = cmd_name.lower()
                    if cmd_lower not in self._command_index:
                        self._command_index[cmd_lower] = []
                    self._command_index[cmd_lower].append(doc)

                    # Index by parent tool (for grouping subcommands)
                    if parent_tool:
                        parent_lower = parent_tool.lower()
                        if parent_lower not in self._parent_tool_index:
                            self._parent_tool_index[parent_lower] = []
                        self._parent_tool_index[parent_lower].append(doc)

            # If no subsections found, create a single document with file-level platform
            if not created_platform_docs:
                # Check for description - try **설명**: first, then first paragraph
                desc_match = re.search(r'\*\*설명\*\*:\s*(.+?)(?=\n-|\n\*\*|$)', details, re.DOTALL)
                if not desc_match:
                    # Description is first paragraph before **구문** or **지원
                    # Match everything from start until we hit \n\n** or \n**
                    desc_match = re.search(r'^(.+?)(?=\n\n\*\*|\n\*\*)', details.strip(), re.DOTALL)
                description = ' '.join(desc_match.group(1).strip().split())[:200] if desc_match else None

                # Extract syntax (handle both single backticks and code blocks)
                # Try code block first: ```\n...\n```
                syntax_match = re.search(r'\*\*구문[:\*]*\s*\n```\n?([^`]+?)```', details, re.DOTALL)
                if not syntax_match:
                    # Try single backticks: `...`
                    syntax_match = re.search(r'\*\*구문\*\*:\s*`([^`]+)`', details, re.DOTALL)
                syntax = syntax_match.group(1).strip().split('\n')[0] if syntax_match else None

                pdf_match = re.search(r'(?:소스|참조)\**:\s*([^\(\n]+\.pdf)', details, re.IGNORECASE)
                source_pdf = pdf_match.group(1).strip() if pdf_match else None

                page_match = re.search(r'(?:소스|참조)\**:.*?\(p\.?(\d+)\)', details)
                pages = [int(page_match.group(1))] if page_match else []

                # Extract version from source PDF
                platform, product_version, doc_version = self._extract_version_from_source(source_pdf)
                final_platform = platform or file_platform

                # Extract parent tool from syntax
                parent_tool = self._extract_parent_tool_from_syntax(syntax, details)

                doc_id = f"cmd_{cmd_name.lower()}"
                if final_platform:
                    doc_id = f"cmd_{cmd_name.lower()}_{final_platform.lower()}"

                doc = SummaryDocument(
                    id=doc_id,
                    content=details.strip()[:1000],
                    doc_type=doc_type,
                    source_file=source_file,
                    source_pdf=source_pdf,
                    page_numbers=list(set(pages)),
                    name=cmd_name,
                    description=description,
                    syntax=syntax,
                    product=", ".join(products) if products else None,
                    platform=final_platform,
                    product_version=product_version,
                    document_version=doc_version,
                    parent_tool=parent_tool,
                    metadata={"products": products}
                )

                self._documents.append(doc)
                search_content = f"{cmd_name} {final_platform or ''} {description or ''} {syntax or ''} {' '.join(products)} {parent_tool or ''}"
                self._doc_contents.append(search_content)

                # Index by command name
                cmd_lower = cmd_name.lower()
                if cmd_lower not in self._command_index:
                    self._command_index[cmd_lower] = []
                self._command_index[cmd_lower].append(doc)

                # Index by parent tool (for grouping subcommands)
                if parent_tool:
                    parent_lower = parent_tool.lower()
                    if parent_lower not in self._parent_tool_index:
                        self._parent_tool_index[parent_lower] = []
                    self._parent_tool_index[parent_lower].append(doc)

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

        # Check if query contains CJK characters (Japanese/Korean/Chinese)
        has_cjk = bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]', query))

        # ================================================================
        # LLM-FIRST KEYWORD EXTRACTION
        # For CJK queries, rule-based regex fails due to lack of word boundaries
        # Use LLM as PRIMARY method for accurate keyword extraction
        # ================================================================
        if has_cjk:
            logger.info(f"[LLM-First] CJK query detected, using LLM for keyword extraction: '{query}'")
            llm_commands, llm_errors, llm_terms = await self._extract_keywords_llm(query)

            result.detected_commands = llm_commands
            result.detected_error_codes = llm_errors
            result.detected_terms = llm_terms

            logger.info(f"[LLM-First] Extracted: commands={result.detected_commands}, errors={result.detected_error_codes}, terms={result.detected_terms}")

            # Fallback to rule-based ONLY if LLM returned nothing
            if not (llm_commands or llm_errors or llm_terms):
                logger.debug("[LLM-First] LLM returned nothing, falling back to rule-based")
                result.detected_error_codes = self._detect_error_codes(query)
                result.detected_commands = self._detect_commands(query)
                result.detected_terms = self._detect_terms(query)
        else:
            # Non-CJK queries: use rule-based detection (fast, reliable for English)
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
        # Note: Use (?:^|[^a-zA-Z0-9]) instead of \b for CJK language support
        # Japanese/Korean/Chinese don't have word boundaries like English
        patterns = [
            # Commands ending with common suffixes (init, boot, mgr, etc.)
            r'(?:^|[^a-zA-Z0-9])([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))(?:[^a-zA-Z0-9]|$)',
            # TJES/OSC/TACF family commands - use [a-zA-Z0-9]* instead of \w* to avoid CJK matching
            r'(?:^|[^a-zA-Z0-9])(tjes[a-zA-Z0-9]*|osc[a-zA-Z0-9]*|tac[a-zA-Z0-9]*|ofm[a-zA-Z0-9]*|osci[a-zA-Z0-9]*|obm[a-zA-Z0-9]*)(?:[^a-zA-Z0-9]|$)',
            # Specific known commands
            r'(?:^|[^a-zA-Z0-9])(tjesmgr|oscboot|tjadmin|tacfadm|dsload|dsunload|obmjinit|hidbmgr|ndbmgr|osctdlrm|osctdlinit|osctdlupdate)(?:[^a-zA-Z0-9]|$)',
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

    async def _extract_keywords_llm(self, query: str) -> Tuple[List[str], List[str], List[str]]:
        """
        Extract keywords from query using LLM.

        For CJK queries (Japanese/Korean/Chinese), rule-based regex often fails
        because word boundaries don't exist. LLM can understand the semantic
        structure and extract the actual technical terms.

        Args:
            query: User query in any language

        Returns:
            Tuple of (commands, error_codes, terms)
        """
        # Check cache first
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self._llm_keyword_cache:
            cached = self._llm_keyword_cache[cache_key]
            return cached.get('commands', []), cached.get('error_codes', []), cached.get('terms', [])

        # Prepare prompt for keyword extraction
        prompt = f"""Extract technical keywords from the following query.

Query: {query}

Instructions:
- Extract ONLY the technical terms (commands, error codes, product names)
- Commands are lowercase (e.g., tjesmgr, osctdlrm, hidbmgr, obmjinit)
- Error codes are negative numbers (e.g., -5212, -21001)
- Terms are uppercase acronyms (e.g., TJES, TACF, OSC, VSAM)
- Return ONLY the extracted keywords, not the full query
- If no keywords found, return empty arrays

Output ONLY valid JSON:
{{"commands": ["cmd1", "cmd2"], "error_codes": ["-5212"], "terms": ["TERM1"]}}"""

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self._llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.1,
                }
                logger.debug(f"[LLM Keyword] Calling {self._llm_url} with model={self._llm_model}")

                async with session.post(
                    self._llm_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self._llm_timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                        # Parse JSON from response
                        # Handle cases where LLM wraps JSON in markdown
                        json_match = re.search(r'\{[^{}]*\}', content)
                        if json_match:
                            result = json.loads(json_match.group())
                            commands = [c.lower() for c in result.get("commands", []) if c]
                            error_codes = result.get("error_codes", [])
                            terms = [t.upper() for t in result.get("terms", []) if t]

                            # Cache result
                            self._llm_keyword_cache[cache_key] = {
                                'commands': commands,
                                'error_codes': error_codes,
                                'terms': terms
                            }

                            logger.debug(f"[LLM Keyword Extraction] Query: '{query}' -> commands={commands}, errors={error_codes}, terms={terms}")
                            return commands, error_codes, terms

        except asyncio.TimeoutError:
            logger.warning(f"[LLM Keyword] Timeout ({self._llm_timeout}s) for query: {query}")
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"[LLM Keyword] Connection error to {self._llm_url}: {e}")
        except Exception as e:
            logger.warning(f"[LLM Keyword] Error: {type(e).__name__}: {e}")

        # Return empty on failure (fall back to rule-based)
        return [], [], []

    @property
    def is_initialized(self) -> bool:
        """Check if service is initialized"""
        return self._initialized

    @property
    def document_count(self) -> int:
        """Get total document count"""
        return len(self._documents)

    async def search_multi_product(
        self,
        query: str,
        top_k: int = 10
    ) -> List[MultiProductResult]:
        """
        Search and aggregate results by command/error name across all platforms.

        This method groups search results by entity name (command, error code, term)
        and returns one MultiProductResult per unique entity, with platform-specific
        variants.

        Special handling for parent tools (e.g., "tjesmgr"):
        - If query matches a parent tool, aggregates all subcommands by platform
        - Creates a combined description with key subcommand info

        Args:
            query: Search query
            top_k: Maximum number of aggregated results to return

        Returns:
            List of MultiProductResult, each containing platform variants
        """
        if not self._initialized:
            await self.initialize()

        multi_results: List[MultiProductResult] = []

        # Check if query is a parent tool name (e.g., "tjesmgr", "hidbmgr")
        query_lower = query.lower().strip()
        query_tokens = query_lower.split()

        # Look for parent tool matches
        parent_tool_match = None

        # First, try token-based matching (works for space-separated queries)
        for token in query_tokens:
            if token in self._parent_tool_index:
                parent_tool_match = token
                break

        # If no match found, try substring matching for CJK queries
        # (Japanese/Korean/Chinese don't use spaces between words)
        if not parent_tool_match:
            for tool_name in self._parent_tool_index.keys():
                if tool_name in query_lower:
                    parent_tool_match = tool_name
                    logger.info(f"[MultiProduct] Substring match: '{tool_name}' in query '{query_lower[:50]}'")
                    break

        if parent_tool_match and len(self._parent_tool_index.get(parent_tool_match, [])) > 0:
            # Aggregate subcommands by platform for this parent tool
            subcommands = self._parent_tool_index[parent_tool_match]
            logger.info(f"[MultiProduct] Found {len(subcommands)} subcommands for tool: {parent_tool_match}")

            # Group subcommands by platform
            by_platform: Dict[str, List[SummaryDocument]] = defaultdict(list)
            for doc in subcommands:
                platform = doc.platform or self._extract_platform_from_source_file(doc.source_file)
                if not platform:
                    platform, _, _ = self._extract_version_from_source(doc.source_pdf or "")
                if not platform:
                    platform = "Common"
                by_platform[platform].append(doc)

            # Create variants for each platform
            variants: List[ProductVariant] = []
            for platform, docs in by_platform.items():
                # Sort docs by name for consistent ordering
                docs.sort(key=lambda d: d.name or "")

                # Build combined description from top subcommands
                subcommand_info = []
                for doc in docs[:5]:  # Top 5 subcommands
                    if doc.description:
                        subcommand_info.append(f"• {doc.name}: {doc.description[:80]}")
                    elif doc.syntax:
                        subcommand_info.append(f"• {doc.name}: {doc.syntax[:50]}")

                combined_desc = f"{parent_tool_match.upper()} 관리 유틸리티 ({platform})"
                if subcommand_info:
                    combined_desc += "\n주요 명령어:\n" + "\n".join(subcommand_info)

                # Get version from first doc
                first_doc = docs[0]
                variant = ProductVariant(
                    platform=platform,
                    product_version=first_doc.product_version,
                    description=combined_desc,
                    syntax=f"{parent_tool_match} <command> [options]",
                    source_pdf=first_doc.source_pdf,
                    page_numbers=first_doc.page_numbers,
                    document_version=first_doc.document_version
                )
                variants.append(variant)

            if variants:
                # Sort variants by platform priority
                platform_order = {"MVS": 0, "MSP": 1, "XSP": 2, "VOS3": 3, "Common": 4}
                variants.sort(key=lambda v: platform_order.get(v.platform, 99))

                multi_result = MultiProductResult(
                    name=parent_tool_match,
                    doc_type=SummaryDocType.COMMANDS,
                    variants=variants,
                    score=1.0  # High score for direct tool match
                )
                multi_results.append(multi_result)

        # Also do regular comprehensive search
        search_result = await self.comprehensive_search(query, top_k=top_k * 4)

        if search_result.results:
            # ================================================================
            # ANTI-HALLUCINATION: Filter results by score and relevance
            # Only include results that are actually related to the query
            # ================================================================
            MIN_MULTI_PRODUCT_SCORE = 0.3  # Minimum BM25 score threshold

            # Extract query keywords for relevance check
            query_keywords = set(query_lower.split())
            # Add query as a whole for substring matching
            query_normalized = re.sub(r'[^\w]', '', query_lower)

            # Group results by entity name (case-insensitive)
            by_name: Dict[str, List[SummarySearchResult]] = defaultdict(list)
            for sr in search_result.results:
                # Filter 1: Minimum score threshold
                if sr.score < MIN_MULTI_PRODUCT_SCORE:
                    logger.debug(f"[MultiProduct] Skipping '{sr.document.name}' - score {sr.score:.2f} < {MIN_MULTI_PRODUCT_SCORE}")
                    continue

                name_key = (sr.document.name or "").lower()

                # Skip if name matches the parent tool we already processed
                if parent_tool_match and name_key == parent_tool_match:
                    continue

                # Filter 2: Relevance check - name should be related to query
                if name_key:
                    name_normalized = re.sub(r'[^\w]', '', name_key)

                    # Check if query keyword appears in name OR name appears in query
                    is_relevant = (
                        query_normalized in name_normalized or
                        name_normalized in query_normalized or
                        any(kw in name_key for kw in query_keywords if len(kw) >= 3) or
                        any(part in query_lower for part in name_key.split() if len(part) >= 3)
                    )

                    if not is_relevant:
                        logger.debug(f"[MultiProduct] Skipping '{sr.document.name}' - not relevant to query '{query}'")
                        continue

                    by_name[name_key].append(sr)

            # Build MultiProductResult for each unique entity
            for name_key, docs in by_name.items():
                if not docs:
                    continue

                # Get the canonical name and doc_type from first result
                first_doc = docs[0].document
                canonical_name = first_doc.name or name_key

                # Build variants from all matching documents
                variants: List[ProductVariant] = []
                seen_platforms: Set[str] = set()

                for sr in docs:
                    doc = sr.document

                    # Determine platform
                    platform = doc.platform or self._extract_platform_from_source_file(doc.source_file)
                    if not platform:
                        # Try to extract from source PDF
                        platform, _, _ = self._extract_version_from_source(doc.source_pdf or "")
                    if not platform:
                        platform = "Common"  # Default for documents without platform info

                    # Skip duplicate platforms (keep highest scoring one)
                    if platform in seen_platforms:
                        continue
                    seen_platforms.add(platform)

                    variant = ProductVariant(
                        platform=platform,
                        product_version=doc.product_version,
                        description=doc.description,
                        syntax=doc.syntax,
                        source_pdf=doc.source_pdf,
                        page_numbers=doc.page_numbers,
                        solution=doc.solution,
                        document_version=doc.document_version
                    )
                    variants.append(variant)

                if variants:
                    # Sort variants by platform priority
                    platform_order = {"MVS": 0, "MSP": 1, "XSP": 2, "VOS3": 3, "Common": 4}
                    variants.sort(key=lambda v: platform_order.get(v.platform, 99))

                    multi_result = MultiProductResult(
                        name=canonical_name,
                        doc_type=first_doc.doc_type,
                        variants=variants,
                        score=max(sr.score for sr in docs)
                    )
                    multi_results.append(multi_result)

        # Sort by score and limit
        multi_results.sort(key=lambda r: r.score, reverse=True)
        return multi_results[:top_k]


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
